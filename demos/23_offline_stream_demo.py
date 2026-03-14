#!/usr/bin/env python3
"""Real scientific research demo with live streaming to labwork-web.

Simulates a complete scientific method cycle using REAL tools:
  1. OBSERVE  — Load unknown NMR data, process spectrum (FFT, phase, peaks)
  2. MATCH    — Fingerprint match against spectral library (30 reference compounds)
  3. ANALYZE  — AI interprets spectrum (Sonnet 4.6, real VLM call)
  4. VERIFY   — Cross-reference with PubChem (real API call)
  5. CONCLUDE — AI synthesizes findings into research conclusion

All data is real (TopSpin examdata), all API calls are live, nothing is cached/faked.

Usage:
    # 1. Start web:  cd wt-labwork-web-vm && python app.py
    # 2. Run demo:   python demos/23_offline_stream_demo.py
    # 3. Watch:      open http://localhost:8430 → Live VM tab
"""
from __future__ import annotations

import asyncio
import base64
import io
import os
import sys
import time

import httpx
from PIL import Image, ImageDraw
from openai import OpenAI

# Add src to path for device-use imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# ── Config ──────────────────────────────────────
DATASET = os.environ.get("DATASET", "exam_CMCse_1")
EXPNO = os.environ.get("EXPNO", "1")
BRAIN_MODEL = "anthropic/claude-opus-4.6"   # Brain = Opus 4.6 (reasoning, analysis)
CU_MODEL = "anthropic/claude-sonnet-4.6"   # Hands = Sonnet 4.6 (CUA screenshot→action)
LABWORK_URL = os.environ.get("LABWORK_URL", "http://localhost:8430")
EXAMDATA = "/opt/topspin5.0.0/examdata"

B = "\033[1m"
G = "\033[32m"
C = "\033[36m"
Y = "\033[33m"
D = "\033[2m"
R = "\033[31m"
RST = "\033[0m"


# ── Stream helpers ─────────────────────────────

async def push_frame(jpeg_bytes: bytes):
    """Push a JPEG frame to labwork-web MJPEG stream."""
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{LABWORK_URL}/vm/frame",
                content=jpeg_bytes,
                headers={"Content-Type": "image/jpeg"},
                timeout=2,
            )
        except Exception:
            pass


async def push_log(text: str, status: str | None = None):
    """Push a log line to labwork-web."""
    data: dict = {"text": text}
    if status:
        data["status"] = status
    async with httpx.AsyncClient() as client:
        try:
            await client.post(f"{LABWORK_URL}/vm/log", json=data, timeout=2)
        except Exception:
            pass
    print(f"  {D}{text}{RST}")


async def push_image(img: Image.Image, label: str = ""):
    """Convert PIL image to JPEG and push as frame."""
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, "#1a1a2e")
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    if label:
        img_copy = img.copy()
        draw = ImageDraw.Draw(img_copy)
        draw.rectangle([(0, 0), (img.width, 30)], fill="#1a1a2e")
        draw.text((10, 8), label, fill="#00ff88")
        img = img_copy

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    await push_frame(buf.getvalue())


def ask_vlm(client: OpenAI, image_b64: str, question: str) -> str:
    """Send image + question to Opus 4.6 (brain), get text answer."""
    response = client.chat.completions.create(
        model=BRAIN_MODEL,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                    },
                    {"type": "text", "text": question},
                ],
            }
        ],
    )
    return response.choices[0].message.content.strip()


def ask_text(client: OpenAI, prompt: str) -> str:
    """Text-only query to Opus 4.6 (brain)."""
    response = client.chat.completions.create(
        model=BRAIN_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()


# ── Main pipeline ──────────────────────────────

async def main() -> int:
    print(
        f"\n{B}{'═' * 55}{RST}\n"
        f"{B}  Scientific Research Demo — Real NMR Analysis{RST}\n"
        f"{D}  Watch at {LABWORK_URL} → Live VM tab{RST}\n"
        f"{B}{'═' * 55}{RST}\n"
    )

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print(f"  {R}✗ OPENROUTER_API_KEY not set{RST}")
        return 1

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")
    t_total = time.monotonic()

    # ═══════════════════════════════════════════════════
    # PHASE 1: OBSERVE — Load and process NMR data
    # ═══════════════════════════════════════════════════
    await push_log("═══ PHASE 1: OBSERVE ═══", status="operating")
    await push_log("Loading raw NMR data from spectrometer...")

    from device_use.instruments.nmr.adapter import TopSpinAdapter
    from device_use.instruments.base import ControlMode
    from device_use.instruments.nmr.processor import NMRProcessor

    adapter = TopSpinAdapter(mode=ControlMode.OFFLINE)
    adapter.connect()
    await push_log("✓ Instrument connected (offline mode)")

    # Scan available datasets
    datasets = adapter.list_datasets()
    await push_log(f"  Spectrometer has {len(datasets)} datasets available")

    # Load target dataset
    dataset_path = f"{EXAMDATA}/{DATASET}/{EXPNO}"
    # Find title from dataset list
    title = ""
    for ds in datasets:
        if ds["sample"] == DATASET and ds["expno"] == int(EXPNO):
            title = ds.get("title", "")
            break
    await push_log(f"  Loading: {DATASET}/{EXPNO}" + (f" ({title})" if title else ""))

    # Process: FFT → Phase Correction → Peak Picking
    await push_log("  Processing: FFT → Phase Correction → Peak Picking")
    processor = NMRProcessor()
    dic, fid = processor.read_bruker(dataset_path)
    spectrum = processor.process_1d(dic, fid, dataset_path)
    n_peaks = len(spectrum.peaks)
    await push_log(f"  ✓ Processed: {n_peaks} peaks detected")

    # Visualize and push spectrum to stream
    from device_use.instruments.nmr.visualizer import plot_spectrum

    png_bytes = plot_spectrum(spectrum, output_path=None, title=f"{DATASET} exp {EXPNO}")
    img = Image.open(io.BytesIO(png_bytes))
    await push_image(img, f"1H NMR Spectrum: {DATASET}/{EXPNO}")
    await push_log("  ✓ Spectrum visualization streamed")

    spectrum_b64 = base64.b64encode(png_bytes).decode()

    # Show peaks
    await push_log(f"  Peak positions (δ ppm):")
    sorted_peaks = sorted(spectrum.peaks, key=lambda p: p.ppm)
    peak_str = ", ".join(f"{p.ppm:.2f}" for p in sorted_peaks)
    await push_log(f"    {peak_str}")

    # ═══════════════════════════════════════════════════
    # PHASE 2: MATCH — Spectral library fingerprinting
    # ═══════════════════════════════════════════════════
    await push_log("")
    await push_log("═══ PHASE 2: MATCH ═══")
    await push_log("Building spectral library from reference data...")

    import warnings
    warnings.filterwarnings("ignore")

    from device_use.instruments.nmr.library import SpectralLibrary

    lib = SpectralLibrary.from_examdata()
    await push_log(f"  ✓ Library built: {len(lib)} reference compounds")
    await push_log(f"  Matching unknown spectrum against library...")

    matches = lib.match(spectrum, top_k=3)
    for i, m in enumerate(matches, 1):
        score_pct = m.score * 100
        bar = "█" * int(score_pct / 5) + "░" * (20 - int(score_pct / 5))
        await push_log(
            f"    {i}. {m.entry.name}: {score_pct:.0f}% "
            f"({m.matched_peaks}/{m.total_peaks} peaks) {bar}"
        )

    top_match = matches[0] if matches else None
    if top_match and top_match.score > 0.5:
        await push_log(f"  ✓ Best match: {top_match.entry.name} ({top_match.score:.0%} confidence)")
        hypothesis = top_match.entry.name
    else:
        await push_log("  ⚠ No strong match — compound may be novel")
        hypothesis = title or "unknown compound"

    # ═══════════════════════════════════════════════════
    # PHASE 3: ANALYZE — AI interprets the spectrum
    # ═══════════════════════════════════════════════════
    await push_log("")
    await push_log("═══ PHASE 3: ANALYZE ═══")
    await push_log("Sending spectrum to AI for expert interpretation...")
    t_ai = time.monotonic()

    analysis = ask_vlm(
        client,
        spectrum_b64,
        (
            "You are an expert NMR spectroscopist at a research university.\n"
            "Analyze this 1H NMR spectrum rigorously:\n"
            "1. Identify each peak region and assign likely functional groups\n"
            "2. Note multiplicity patterns if visible\n"
            "3. Estimate integration ratios from relative intensities\n"
            "4. Propose a structural hypothesis\n"
            "5. Rate your confidence (low/medium/high)\n\n"
            "Be scientifically precise. 5-8 sentences."
        ),
    )
    dt_ai = time.monotonic() - t_ai
    await push_log(f"  ✓ AI analysis complete ({dt_ai:.1f}s)")
    for line in analysis.split("\n"):
        if line.strip():
            await push_log(f"    {line.strip()}")

    # ═══════════════════════════════════════════════════
    # PHASE 4: VERIFY — Cross-reference with PubChem
    # ═══════════════════════════════════════════════════
    await push_log("")
    await push_log("═══ PHASE 4: VERIFY ═══")

    # Extract compound name for PubChem lookup
    # Use the library match name or dataset title, cleaned of formulas/solvents
    lookup_name = hypothesis if hypothesis != "unknown compound" else title
    # Clean up: remove solvent info, molecular formulas, concentrations
    import re
    for suffix in [" in CDCl3", " in DMSO", " in d6-DMSO", " + TMS", " in toluene-d8"]:
        lookup_name = lookup_name.split(suffix)[0]
    # Remove molecular formula patterns like "C21H22N2O2"
    lookup_name = re.sub(r"\s+C\d+H\d+\w*", "", lookup_name).strip()
    # Remove concentration patterns like "180mM"
    lookup_name = re.sub(r"^\d+m?M\s+", "", lookup_name).strip()
    await push_log(f"  Querying PubChem for '{lookup_name}'...")

    from device_use.tools.pubchem import PubChemTool

    pubchem = PubChemTool()
    try:
        compound_data = pubchem.lookup_by_name(lookup_name)
        if compound_data:
            await push_log(f"  ✓ PubChem match found:")
            await push_log(f"    CID: {compound_data.get('CID', 'N/A')}")
            await push_log(f"    Formula: {compound_data.get('MolecularFormula', 'N/A')}")
            await push_log(f"    MW: {compound_data.get('MolecularWeight', 'N/A')} g/mol")
            iupac = compound_data.get("IUPACName", "N/A")
            await push_log(f"    IUPAC: {iupac}")
            smiles = compound_data.get("SMILES", "N/A")
            await push_log(f"    SMILES: {smiles}")
        else:
            await push_log(f"  ⚠ No PubChem match for '{lookup_name}'")
            compound_data = {}
    except Exception as e:
        await push_log(f"  ⚠ PubChem error: {e}")
        compound_data = {}

    # ═══════════════════════════════════════════════════
    # PHASE 5: CONCLUDE — Synthesize findings
    # ═══════════════════════════════════════════════════
    await push_log("")
    await push_log("═══ PHASE 5: CONCLUDE ═══")
    await push_log("Synthesizing all evidence into research conclusion...")

    # Build evidence summary for AI
    evidence = (
        f"NMR Analysis Report\n"
        f"==================\n"
        f"Sample: {DATASET}/{EXPNO}\n"
        f"Peaks detected: {n_peaks}\n"
        f"Peak positions (ppm): {peak_str}\n\n"
        f"Spectral Library Match: {top_match.entry.name} "
        f"(score={top_match.score:.2f})\n\n" if top_match else ""
        f"AI Spectrum Interpretation:\n{analysis}\n\n"
        f"PubChem Data:\n"
        f"  Name: {lookup_name}\n"
        f"  Formula: {compound_data.get('MolecularFormula', 'N/A')}\n"
        f"  MW: {compound_data.get('MolecularWeight', 'N/A')}\n"
        f"  IUPAC: {compound_data.get('IUPACName', 'N/A')}\n"
    )

    conclusion = ask_text(
        client,
        (
            "You are writing a brief research conclusion based on NMR analysis.\n"
            "Synthesize ALL the evidence below into a concise scientific conclusion.\n"
            "State: (1) compound identity, (2) confidence level and why, "
            "(3) any discrepancies between methods, (4) recommended next steps.\n\n"
            f"{evidence}\n\n"
            "Write 4-6 sentences. Be precise and scientific."
        ),
    )

    await push_log("  ✓ Conclusion:")
    for line in conclusion.split("\n"):
        if line.strip():
            await push_log(f"    {line.strip()}")

    # Final summary
    dt = time.monotonic() - t_total
    await push_log("")
    await push_log(f"{'─' * 50}")
    await push_log(f"  Total time: {dt:.1f}s")
    await push_log(f"  Data source: {dataset_path}")
    await push_log(f"  Library match: {top_match.entry.name if top_match else 'N/A'} "
                   f"({top_match.score:.0%})" if top_match else "")
    await push_log(f"  PubChem: {compound_data.get('MolecularFormula', 'N/A')}")
    await push_log(f"  Brain: Opus 4.6 | Hands: Sonnet 4.6")
    await push_log(f"{'─' * 50}", status="done")

    print(f"\n{B}{G}✓ Research complete in {dt:.1f}s{RST}\n")
    return 0


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Real NMR research demo with live streaming")
    parser.add_argument("--dataset", default=DATASET, help="Dataset name (default: exam_CMCse_1)")
    parser.add_argument("--expno", default=EXPNO, help="Experiment number (default: 1)")
    parser.add_argument("--url", default=LABWORK_URL, help="labwork-web URL")
    args = parser.parse_args()
    DATASET = args.dataset
    EXPNO = args.expno
    LABWORK_URL = args.url

    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print(f"\n  {R}Interrupted{RST}")
        sys.exit(130)
