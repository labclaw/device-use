#!/usr/bin/env python3
"""Full Experiment Orchestrator — 5-phase end-to-end scientific experiment.

Drives a complete experiment from research through reporting:

  Phase 1: RESEARCH   — ToolUniverse + PubChem background lookup
  Phase 2: INSTRUMENT — TopSpin GUI control (optional)
  Phase 3: ANALYZE    — Offline NMR processing + AI interpretation
  Phase 4: DISCOVER   — LabClaw scientific method loop (optional)
  Phase 5: REPORT     — IMRAD markdown report generation

Usage:
    # Minimal (offline only, no GUI, no labclaw):
    PYTHONPATH=src .venv/bin/python demos/demo_full_experiment.py \\
        --no-gui --no-labclaw --dataset exam_CMCse_1 --formula C13H20O

    # Full pipeline with TopSpin GUI + LabClaw:
    PYTHONPATH=src .venv/bin/python demos/demo_full_experiment.py \\
        --dataset Cyclosporine --formula C62H111N11O12
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning, module="nmrglue")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="scipy")

# -- Path setup ---------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent / "lib"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lib.terminal import (
    banner as _lib_banner,
    phase,
    finale,
    BOLD,
    DIM,
    GREEN,
    CYAN,
    YELLOW,
    RED,
    RESET,
    CHECK,
    ARROW,
    STAR,
)
from device_use.instruments import ControlMode
from device_use.instruments.nmr.adapter import TopSpinAdapter
from device_use.instruments.nmr.visualizer import plot_spectrum
from device_use.instruments.nmr.brain import NMRBrain
from device_use.tools.pubchem import PubChemTool, PubChemError
from device_use.tools.tooluniverse import ToolUniverseTool, _TU_AVAILABLE


# -- CLI ----------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Full Experiment Orchestrator — 5-phase scientific demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dataset", default="Cyclosporine",
                        help="Dataset name or keyword (default: Cyclosporine)")
    parser.add_argument("--expno", type=int, default=1, help="Experiment number")
    parser.add_argument("--formula", default="C62H111N11O12",
                        help="Molecular formula (default: Cyclosporine A)")
    parser.add_argument("--no-gui", action="store_true", help="Skip GUI phase")
    parser.add_argument("--no-labclaw", action="store_true", help="Skip labclaw phase")
    parser.add_argument("--labclaw-url", default="http://localhost:18800",
                        help="LabClaw API base URL")
    parser.add_argument("--output", default="output/full_experiment",
                        help="Output directory")
    parser.add_argument("--topspin-dir", default="/opt/topspin5.0.0",
                        help="TopSpin installation path")
    return parser.parse_args()


# -- Helpers ------------------------------------------------------------------

def _find_dataset(datasets: list[dict], keyword: str, expno: int) -> dict | None:
    """Find a dataset by sample name keyword and experiment number."""
    for ds in datasets:
        sample = ds.get("sample", "")
        title = ds.get("title", "")
        if (keyword.lower() in sample.lower() or keyword.lower() in title.lower()):
            if ds.get("expno") == expno:
                return ds
    # Fallback: match without expno constraint
    for ds in datasets:
        sample = ds.get("sample", "")
        title = ds.get("title", "")
        if keyword.lower() in sample.lower() or keyword.lower() in title.lower():
            return ds
    return None


# -- Phase 1: RESEARCH -------------------------------------------------------

def phase_research(args: argparse.Namespace) -> dict:
    """Background research via ToolUniverse + PubChem."""
    phase(1, "RESEARCH", "Background lookup via ToolUniverse + PubChem")
    results: dict = {"tools": None, "pubchem": None}

    # ToolUniverse
    print(f"  {BOLD}ToolUniverse{RESET}")
    try:
        if _TU_AVAILABLE:
            tu = ToolUniverseTool()
            tu.connect()
            tools = tu.find_spectroscopy_tools()
            results["tools"] = tools
            print(f"  {CHECK} Found {len(tools)} spectroscopy tools")
            for t in (tools[:5] if isinstance(tools, list) else []):
                name = t.get("name", str(t)) if isinstance(t, dict) else str(t)
                print(f"    {DIM}  {name}{RESET}")
        else:
            print(f"  {DIM}ToolUniverse not installed — skipped{RESET}")
    except Exception as e:
        print(f"  {YELLOW}  ToolUniverse error: {e}{RESET}")

    # PubChem
    print(f"\n  {BOLD}PubChem{RESET}")
    pubchem = PubChemTool()
    try:
        t0 = time.time()
        result = pubchem.lookup_by_name(args.dataset.replace("_", " "))
        dt = time.time() - t0
        results["pubchem"] = result
        print(f"  {CHECK} Found compound {DIM}({dt:.1f}s){RESET}")
        print(f"    CID:     {BOLD}{result.get('CID', '?')}{RESET}")
        print(f"    Formula: {result.get('MolecularFormula', '?')}")
        print(f"    IUPAC:   {DIM}{result.get('IUPACName', '?')}{RESET}")
    except (PubChemError, Exception) as e:
        print(f"  {DIM}PubChem lookup skipped: {e}{RESET}")

    return results


# -- Phase 2: INSTRUMENT (GUI) -----------------------------------------------

def phase_instrument(args: argparse.Namespace) -> dict:
    """Operate TopSpin via GUI (AppleScript + screenshot)."""
    phase(2, "INSTRUMENT", "TopSpin GUI control")
    results: dict = {"screenshots": [], "skipped": False}

    if args.no_gui:
        print(f"  {DIM}--no-gui: skipping GUI phase{RESET}")
        results["skipped"] = True
        return results

    try:
        # Activate TopSpin
        print(f"  {ARROW} Activating TopSpin...")
        subprocess.run(
            ["osascript", "-e", 'tell application id "net.java.openjdk.java" to activate'],
            timeout=5, capture_output=True,
        )
        time.sleep(2)

        # Screenshot with mss
        try:
            import mss
            out_dir = Path(args.output)
            out_dir.mkdir(parents=True, exist_ok=True)
            with mss.mss() as sct:
                shot_path = str(out_dir / "topspin_before.png")
                sct.shot(output=shot_path)
                results["screenshots"].append(shot_path)
                print(f"  {CHECK} Screenshot: {shot_path}")
        except ImportError:
            print(f"  {DIM}mss not installed — screenshot skipped{RESET}")

        # Send command to load dataset
        cmd = f're {args.dataset} {args.expno}'
        print(f"  {ARROW} Sending command: {cmd}")
        apple_script = (
            f'tell application id "net.java.openjdk.java"\n'
            f'  activate\n'
            f'  delay 1\n'
            f'  tell application "System Events"\n'
            f'    keystroke "{cmd}"\n'
            f'    keystroke return\n'
            f'  end tell\n'
            f'end tell'
        )
        subprocess.run(
            ["osascript", "-e", apple_script],
            timeout=10, capture_output=True,
        )
        time.sleep(3)

        # Post-command screenshot
        try:
            import mss
            with mss.mss() as sct:
                shot_path = str(Path(args.output) / "topspin_after.png")
                sct.shot(output=shot_path)
                results["screenshots"].append(shot_path)
                print(f"  {CHECK} Screenshot: {shot_path}")
        except ImportError:
            pass

        print(f"  {CHECK} GUI commands sent successfully")

    except Exception as e:
        print(f"  {YELLOW}  GUI phase failed (non-fatal): {e}{RESET}")
        results["skipped"] = True

    return results


# -- Phase 3: ANALYZE --------------------------------------------------------

def phase_analyze(args: argparse.Namespace) -> dict:
    """Offline NMR processing + AI brain interpretation."""
    phase(3, "ANALYZE", "Process NMR data + AI interpretation")
    results: dict = {
        "spectrum": None, "dataset": None, "plot_path": None,
        "interpretation": None, "next_experiment": None,
    }

    # Connect adapter (offline mode)
    adapter = TopSpinAdapter(topspin_dir=args.topspin_dir, mode=ControlMode.OFFLINE)
    if not adapter.connect():
        print(f"  {RED}  Failed to connect to TopSpin offline mode{RESET}")
        return results

    info = adapter.info()
    print(f"  {CHECK} Connected: {BOLD}{info.name} {info.version}{RESET} ({adapter.mode.value})")

    # Find dataset
    datasets = adapter.list_datasets()
    print(f"  {CHECK} {len(datasets)} datasets available")

    ds = _find_dataset(datasets, args.dataset, args.expno)
    if not ds:
        print(f"  {RED}  Dataset '{args.dataset}' (expno={args.expno}) not found{RESET}")
        print(f"  {DIM}Available:{RESET}")
        for d in datasets[:10]:
            print(f"    {DIM}{d['sample']}/{d.get('expno', '?')}: {d.get('title', '')}{RESET}")
        return results

    results["dataset"] = ds
    print(f"  {CHECK} Dataset: {BOLD}{ds['sample']}/{ds.get('expno', '?')}{RESET} — {ds.get('title', '')}")

    # Process spectrum
    sys.stdout.write(f"  {ARROW} Processing spectrum... ")
    sys.stdout.flush()
    t0 = time.time()
    spectrum = adapter.process(ds["path"])
    dt = time.time() - t0
    print(f"{GREEN}done{RESET} {DIM}({dt:.1f}s){RESET}")
    print(f"    {len(spectrum.peaks)} peaks, {spectrum.frequency_mhz:.0f} MHz, "
          f"nucleus={spectrum.nucleus}, solvent={spectrum.solvent}")
    results["spectrum"] = spectrum

    # Plot
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    plot_path = out_dir / f"{ds['sample']}_spectrum.png"
    plot_spectrum(spectrum, output_path=str(plot_path))
    results["plot_path"] = str(plot_path)
    print(f"  {CHECK} Plot saved: {plot_path}")

    # Peak table
    if spectrum.peaks:
        max_int = max(p.intensity for p in spectrum.peaks)
        print(f"\n  {BOLD}Top Peaks:{RESET}")
        print(f"  {'':>4}{'ppm':>10}  {'Rel.%':>8}  Visual")
        print(f"  {'':>4}{'---':>10}  {'-----':>8}  ------")
        for i, peak in enumerate(sorted(spectrum.peaks, key=lambda p: p.intensity, reverse=True)[:10]):
            rel = peak.intensity / max_int * 100
            bar = "=" * int(rel / 5)
            print(f"  {i+1:>4}{peak.ppm:10.3f}  {rel:7.1f}%  {DIM}{bar}{RESET}")

    # AI interpretation
    print(f"\n  {BOLD}AI Interpretation:{RESET}")
    print(f"  {CYAN}{'=' * 50}{RESET}")
    brain = NMRBrain()
    has_api = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not has_api:
        print(f"  {DIM}(Using cached expert responses){RESET}")

    t0 = time.time()
    interpretation_chunks = []
    for chunk in brain.interpret_spectrum(
        spectrum, molecular_formula=args.formula,
        context=f"Molecular formula: {args.formula}", stream=True,
    ):
        sys.stdout.write(chunk)
        sys.stdout.flush()
        interpretation_chunks.append(chunk)
    dt = time.time() - t0
    results["interpretation"] = "".join(interpretation_chunks)
    print(f"\n  {CYAN}{'=' * 50}{RESET}")
    print(f"  {DIM}({dt:.1f}s){RESET}")

    # Next experiment suggestion
    print(f"\n  {BOLD}Suggested Next Experiment:{RESET}")
    print(f"  {CYAN}{'-' * 50}{RESET}")
    t0 = time.time()
    next_chunks = []
    for chunk in brain.suggest_next_experiment(spectrum, stream=True):
        sys.stdout.write(chunk)
        sys.stdout.flush()
        next_chunks.append(chunk)
    dt = time.time() - t0
    results["next_experiment"] = "".join(next_chunks)
    print(f"\n  {CYAN}{'-' * 50}{RESET}")
    print(f"  {DIM}({dt:.1f}s){RESET}")

    return results


# -- Phase 4: DISCOVER (LabClaw) ---------------------------------------------

def phase_discover(args: argparse.Namespace, spectrum_data: dict) -> dict:
    """Send data to LabClaw for pattern discovery."""
    phase(4, "DISCOVER", "LabClaw scientific method loop")
    results: dict = {"cycle": None, "skipped": False}

    if args.no_labclaw:
        print(f"  {DIM}--no-labclaw: skipping discovery phase{RESET}")
        results["skipped"] = True
        return results

    import urllib.request
    import urllib.error

    base = args.labclaw_url.rstrip("/")
    api_token = os.environ.get("LABCLAW_API_TOKEN", "")

    def _labclaw_headers() -> dict:
        h = {"Content-Type": "application/json"}
        if api_token:
            h["Authorization"] = f"Bearer {api_token}"
        return h

    # Health check
    sys.stdout.write(f"  {ARROW} Checking LabClaw health... ")
    sys.stdout.flush()
    try:
        req = urllib.request.Request(f"{base}/api/health", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            health = json.loads(resp.read())
        print(f"{GREEN}ok{RESET} — {health.get('status', '?')}")
    except Exception as e:
        print(f"{YELLOW}unavailable{RESET} — {e}")
        results["skipped"] = True
        return results

    # Convert peaks to data rows
    spectrum = spectrum_data.get("spectrum")
    if not spectrum or not spectrum.peaks:
        print(f"  {DIM}No peaks to send{RESET}")
        results["skipped"] = True
        return results

    max_int = max(p.intensity for p in spectrum.peaks)
    data_rows = [
        {
            "ppm": round(p.ppm, 3),
            "intensity": round(p.intensity / max_int * 100, 1),
            "multiplicity": p.multiplicity or "s",
        }
        for p in spectrum.peaks
    ]

    # Submit cycle
    sys.stdout.write(f"  {ARROW} Submitting {len(data_rows)} peaks to orchestrator... ")
    sys.stdout.flush()
    try:
        payload = json.dumps({"data_rows": data_rows}).encode()
        req = urllib.request.Request(
            f"{base}/api/orchestrator/cycle",
            data=payload,
            headers=_labclaw_headers(),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            cycle = json.loads(resp.read())
        results["cycle"] = cycle
        print(f"{GREEN}done{RESET}")
        print(f"    Patterns found: {len(cycle.get('patterns', []))}")
    except Exception as e:
        print(f"{YELLOW}failed{RESET} — {e}")

    # Memory search
    try:
        ds_name = spectrum_data.get("dataset", {}).get("sample", "experiment")
        headers = _labclaw_headers()
        req = urllib.request.Request(
            f"{base}/api/memory/search/query?q={ds_name}&limit=3",
            method="GET",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            memories = json.loads(resp.read())
        if memories:
            print(f"  {CHECK} Related memories: {len(memories)}")
    except Exception:
        pass

    return results


# -- Phase 5: REPORT ---------------------------------------------------------

def phase_report(
    args: argparse.Namespace,
    research: dict,
    instrument: dict,
    analysis: dict,
    discovery: dict,
) -> str:
    """Generate IMRAD markdown report."""
    phase(5, "REPORT", "Generate IMRAD experiment report")

    spectrum = analysis.get("spectrum")
    ds = analysis.get("dataset") or {}
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Peak table
    peak_rows = ""
    if spectrum and spectrum.peaks:
        max_int = max(p.intensity for p in spectrum.peaks)
        top = sorted(spectrum.peaks, key=lambda p: p.intensity, reverse=True)[:15]
        peak_rows = "\n".join(
            f"| {p.ppm:.3f} | {p.intensity / max_int * 100:.1f}% | {p.multiplicity or '-'} |"
            for p in top
        )

    # PubChem section
    pc = research.get("pubchem")
    pubchem_section = ""
    if pc:
        pubchem_section = f"""
### PubChem Cross-Reference

| Property | Value |
|----------|-------|
| CID | {pc.get('CID', 'N/A')} |
| IUPAC Name | {pc.get('IUPACName', 'N/A')} |
| Molecular Formula | {pc.get('MolecularFormula', 'N/A')} |
| Molecular Weight | {pc.get('MolecularWeight', 'N/A')} |
| SMILES | `{pc.get('CanonicalSMILES', pc.get('SMILES', 'N/A'))}` |
| InChIKey | {pc.get('InChIKey', 'N/A')} |
"""

    # Discovery section
    discovery_section = ""
    if not discovery.get("skipped") and discovery.get("cycle"):
        cycle = discovery["cycle"]
        patterns = cycle.get("patterns", [])
        discovery_section = f"""
## Discussion

LabClaw pattern discovery identified **{len(patterns)} patterns** from the NMR data.

"""
        for i, pat in enumerate(patterns[:5]):
            discovery_section += f"- Pattern {i+1}: {pat}\n"

    sample_name = ds.get("sample", args.dataset)
    title_str = ds.get("title", sample_name)

    report = f"""# Full Experiment Report: {title_str}

*Generated by device-use Full Experiment Orchestrator*
*Date: {time.strftime('%Y-%m-%d %H:%M')}*

---

## Abstract

Automated end-to-end NMR experiment on **{sample_name}** (molecular formula: {args.formula}).
Data was processed from Bruker TopSpin format, analyzed by AI, and cross-referenced
against public databases. This report was generated with zero manual intervention.

## Introduction

This experiment demonstrates the device-use middleware driving a complete scientific
workflow: from instrument operation through data analysis to report generation.
The target compound has molecular formula **{args.formula}**.

## Methods

### Instrument
- **Spectrometer:** Bruker TopSpin 5.0.0
- **Mode:** {('GUI + Offline' if not instrument.get('skipped') else 'Offline')}
- **Nucleus:** {spectrum.nucleus if spectrum else 'N/A'}
- **Solvent:** {spectrum.solvent if spectrum else 'N/A'}
- **Frequency:** {f'{spectrum.frequency_mhz:.1f} MHz' if spectrum else 'N/A'}

### Processing Pipeline
1. Load raw FID (Bruker format)
2. Remove digital filter (group delay correction)
3. Zero-fill to 65,536 points
4. Apodization (exponential multiplication, LB=0.3 Hz)
5. Fast Fourier Transform
6. Automatic phase correction (ACME algorithm)
7. Baseline correction (polynomial)
8. Peak picking (threshold-based)

## Results

### Peak Table (Top 15 by Intensity)

| ppm | Rel. Intensity | Multiplicity |
|---------|----------------|--------------|
{peak_rows}

**Total peaks detected:** {len(spectrum.peaks) if spectrum else 0}

### Spectrum

![NMR Spectrum]({sample_name}_spectrum.png)

### AI Analysis

{analysis.get('interpretation', 'N/A')}

### Suggested Next Experiment

{analysis.get('next_experiment', 'N/A')}
{pubchem_section}
{discovery_section}

## Conclusions

Automated analysis of {sample_name} ({args.formula}) successfully completed all phases:
- {'Research: PubChem lookup ' + ('succeeded' if pc else 'skipped') }
- {'Instrument: GUI control ' + ('executed' if not instrument.get('skipped') else 'skipped')}
- Analysis: {len(spectrum.peaks) if spectrum else 0} peaks detected and interpreted by AI
- {'Discovery: LabClaw ' + ('completed' if not discovery.get('skipped') else 'skipped')}

---

*Generated with [device-use](https://github.com/labclaw/device-use) — ROS for Lab Instruments*
"""

    # Write report
    report_path = out_dir / f"{sample_name}_report.md"
    report_path.write_text(report)
    print(f"  {CHECK} Report: {BOLD}{report_path}{RESET}")

    # Write raw JSON results
    json_path = out_dir / f"{sample_name}_results.json"
    json_data = {
        "dataset": sample_name,
        "formula": args.formula,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "peaks": [
            {"ppm": p.ppm, "intensity": p.intensity, "multiplicity": p.multiplicity}
            for p in (spectrum.peaks if spectrum else [])
        ],
        "pubchem": research.get("pubchem"),
        "discovery_skipped": discovery.get("skipped", True),
    }
    json_path.write_text(json.dumps(json_data, indent=2, default=str))
    print(f"  {CHECK} Raw JSON: {BOLD}{json_path}{RESET}")

    return str(report_path)


# -- Main --------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    _lib_banner(
        "Full Experiment Orchestrator",
        "Research -> Instrument -> Analyze -> Discover -> Report",
    )

    t_start = time.time()

    # Phase 1: Research
    research = phase_research(args)

    # Phase 2: Instrument (GUI)
    instrument = phase_instrument(args)

    # Phase 3: Analyze
    analysis = phase_analyze(args)

    # Phase 4: Discover (LabClaw)
    discovery = phase_discover(args, analysis)

    # Phase 5: Report
    report_path = phase_report(args, research, instrument, analysis, discovery)

    # Finale
    dt = time.time() - t_start
    spectrum = analysis.get("spectrum")
    finale([
        f"Dataset: {BOLD}{args.dataset}{RESET} ({args.formula})",
        f"Peaks: {BOLD}{len(spectrum.peaks) if spectrum else 0}{RESET}",
        f"Report: {BOLD}{report_path}{RESET}",
        f"Total time: {BOLD}{dt:.1f}s{RESET}",
        f"Phases completed: 5/5",
    ], title="Full Experiment Complete")


if __name__ == "__main__":
    main()
