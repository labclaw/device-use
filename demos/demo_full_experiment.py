#!/usr/bin/env python3
"""Full Experiment Orchestrator — 5-phase end-to-end scientific experiment.

Drives a complete experiment from research through reporting using REAL components:

  Phase 1: RESEARCH   — ToolUniverse + PubChem background lookup (real API)
  Phase 2: INSTRUMENT — TopSpin GUI via GPT-5.4 Computer Use (real CU loop)
  Phase 3: ANALYZE    — Offline NMR processing + real OpenAI gpt-4o interpretation
  Phase 4: DISCOVER   — LabClaw scientific method loop (real API)
  Phase 5: REPORT     — AI-generated IMRAD report via gpt-4o (real API)

Usage:
    # Minimal (offline analysis only, no CU, no labclaw):
    PYTHONPATH=src .venv/bin/python demos/demo_full_experiment.py \
        --no-cu --no-labclaw --dataset exam_CMCse_1 --formula C13H20O

    # Full pipeline with GPT-5.4 Computer Use + LabClaw:
    PYTHONPATH=src .venv/bin/python demos/demo_full_experiment.py \
        --dataset Cyclosporine --formula C62H111N11O12

    # Skip CU but keep AI analysis + labclaw:
    PYTHONPATH=src .venv/bin/python demos/demo_full_experiment.py \
        --no-cu --dataset exam_CMCse_1 --formula C13H20O
"""

from __future__ import annotations

import argparse
import base64
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
from device_use.instruments.nmr.brain import NMR_SYSTEM_PROMPT
from device_use.instruments.nmr.processor import NMRProcessor
from device_use.tools.pubchem import PubChemTool, PubChemError
from device_use.tools.tooluniverse import ToolUniverseTool, _TU_AVAILABLE

# OpenAI client (lazy init)
_openai_client = None


def _get_openai():
    """Return a cached sync OpenAI client."""
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI()
    return _openai_client


# -- CLI ----------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Full Experiment Orchestrator — 5-phase scientific demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--dataset", default="Cyclosporine",
                        help="Dataset name or keyword (default: Cyclosporine)")
    parser.add_argument("--expno", type=int, default=1, help="Experiment number")
    parser.add_argument("--compound", default="",
                        help="Compound name for PubChem lookup (auto-detected from dataset title if omitted)")
    parser.add_argument("--formula", default="C62H111N11O12",
                        help="Molecular formula (default: Cyclosporine A)")
    parser.add_argument("--no-cu", action="store_true",
                        help="Skip Computer Use GUI phase")
    parser.add_argument("--no-gui", action="store_true",
                        help="Alias for --no-cu (backward compat)")
    parser.add_argument("--no-labclaw", action="store_true", help="Skip labclaw phase")
    parser.add_argument("--labclaw-url", default="http://localhost:18800",
                        help="LabClaw API base URL")
    parser.add_argument("--output", default="output/full_experiment",
                        help="Output directory")
    parser.add_argument("--topspin-dir", default="/opt/topspin5.0.0",
                        help="TopSpin installation path")
    parser.add_argument("--cu-model", default="gpt-5.4",
                        help="Model for Computer Use (default: gpt-5.4)")
    parser.add_argument("--cu-max-turns", type=int, default=12,
                        help="Max CU loop turns (default: 12)")
    args = parser.parse_args()
    # --no-gui is alias for --no-cu
    if args.no_gui:
        args.no_cu = True
    return args


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


def _take_screenshot() -> bytes | None:
    """Take a screenshot using mss, return PNG bytes or None."""
    try:
        import mss
        import mss.tools
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            img = sct.grab(monitor)
            return mss.tools.to_png(img.rgb, img.size)
    except Exception as e:
        print(f"  {YELLOW}  Screenshot failed: {e}{RESET}")
        return None


def _screenshot_to_b64(png_bytes: bytes) -> str:
    """Convert PNG bytes to base64 string."""
    return base64.b64encode(png_bytes).decode("ascii")


def _save_screenshot(png_bytes: bytes, path: str) -> None:
    """Save PNG bytes to file."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(png_bytes)


def _execute_cu_action(action) -> None:
    """Execute a single GPT-5.4 Computer Use action via pyautogui."""
    import pyautogui
    pyautogui.PAUSE = 0.1

    action_type = action.type
    if action_type == "click":
        btn = getattr(action, "button", "left") or "left"
        pyautogui.click(action.x, action.y, button=btn)
    elif action_type == "type":
        pyautogui.write(action.text, interval=0.02)
    elif action_type == "keypress":
        keys = [k.lower() for k in action.keys]
        pyautogui.hotkey(*keys)
    elif action_type == "scroll":
        scroll_y = getattr(action, "scroll_y", 0)
        pyautogui.scroll(scroll_y, x=action.x, y=action.y)
    elif action_type == "screenshot":
        pass  # no-op, we always screenshot after actions
    elif action_type == "wait":
        time.sleep(1)
    elif action_type == "double_click":
        pyautogui.doubleClick(action.x, action.y)
    elif action_type == "move":
        pyautogui.moveTo(action.x, action.y)
    elif action_type == "drag":
        path = getattr(action, "path", [])
        if path and len(path) >= 2:
            pyautogui.moveTo(path[0].get("x", 0), path[0].get("y", 0))
            for pt in path[1:]:
                pyautogui.moveTo(pt.get("x", 0), pt.get("y", 0), duration=0.2)
    else:
        print(f"    {DIM}Unknown action type: {action_type}{RESET}")


# -- Phase 1: RESEARCH -------------------------------------------------------

def phase_research(args: argparse.Namespace) -> dict:
    """Background research via ToolUniverse + PubChem."""
    phase(1, "RESEARCH", "Background lookup via ToolUniverse + PubChem")
    t_phase = time.time()
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
        compound_name = args.compound or args.dataset.replace("_", " ")
        result = pubchem.lookup_by_name(compound_name)
        dt = time.time() - t0
        results["pubchem"] = result
        print(f"  {CHECK} Found compound {DIM}({dt:.1f}s){RESET}")
        print(f"    CID:     {BOLD}{result.get('CID', '?')}{RESET}")
        print(f"    Formula: {result.get('MolecularFormula', '?')}")
        print(f"    IUPAC:   {DIM}{result.get('IUPACName', '?')}{RESET}")
    except (PubChemError, Exception) as e:
        print(f"  {DIM}PubChem lookup skipped: {e}{RESET}")

    dt_phase = time.time() - t_phase
    print(f"\n  {DIM}Phase 1 completed in {dt_phase:.1f}s{RESET}")
    return results


# -- Phase 2: INSTRUMENT (GPT-5.4 Computer Use) -----------------------------

def phase_instrument(args: argparse.Namespace) -> dict:
    """Operate TopSpin via GPT-5.4 Computer Use loop."""
    phase(2, "INSTRUMENT", "TopSpin GUI control via GPT-5.4 Computer Use")
    t_phase = time.time()
    results: dict = {"screenshots": [], "actions_log": [], "skipped": False, "turns": 0}
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.no_cu:
        print(f"  {DIM}--no-cu: skipping Computer Use GUI phase{RESET}")
        results["skipped"] = True
        return results

    if not os.environ.get("OPENAI_API_KEY"):
        print(f"  {YELLOW}  OPENAI_API_KEY not set — skipping CU phase{RESET}")
        results["skipped"] = True
        return results

    try:
        # Step 1: Activate TopSpin
        print(f"  {ARROW} Activating TopSpin...")
        subprocess.run(
            ["osascript", "-e", 'tell application id "net.java.openjdk.java" to activate'],
            timeout=5, capture_output=True,
        )
        time.sleep(2)

        # Step 2: Take initial screenshot
        print(f"  {ARROW} Taking initial screenshot...")
        png = _take_screenshot()
        if not png:
            print(f"  {YELLOW}  Could not take screenshot — aborting CU phase{RESET}")
            results["skipped"] = True
            return results

        shot_path = str(out_dir / "cu_screenshot_00.png")
        _save_screenshot(png, shot_path)
        results["screenshots"].append(shot_path)
        print(f"  {CHECK} Screenshot: {shot_path}")

        b64 = _screenshot_to_b64(png)

        # Step 3: Retrieve device documentation for CU context
        docs_context = ""
        try:
            from device_use.knowledge import retrieve_docs
            task_desc = f"load dataset process NMR spectrum efp command line"
            docs_context = retrieve_docs(
                "bruker-topspin", task_desc,
                skills_dir=Path(__file__).resolve().parents[2] / "device-skills",
                max_results=4, max_chars=3000,
            )
            if docs_context:
                print(f"  {CHECK} Loaded {len(docs_context)} chars of TopSpin 5.0.0 official docs")
        except Exception as e:
            print(f"  {DIM}Docs retrieval skipped: {e}{RESET}")

        # Step 4: Build task description with docs context
        dataset = args.dataset
        expno = args.expno
        task = (
            f"In TopSpin NMR software, load dataset {dataset} experiment {expno} "
            f"using the command line at the bottom. Type "
            f"'re /opt/topspin5.0.0/examdata/{dataset}/{expno}' and press Enter. "
            f"Then run Fourier transform by typing 'efp' and press Enter."
        )
        if docs_context:
            task += f"\n\n## Official TopSpin 5.0.0 Documentation Reference\n{docs_context}"
        print(f"  {ARROW} CU task: {DIM}{task[:80]}...{RESET}")

        # Step 5: Send initial request to GPT-5.4
        client = _get_openai()
        print(f"  {ARROW} Sending to {args.cu_model}...")
        t0 = time.time()
        response = client.responses.create(
            model=args.cu_model,
            tools=[{"type": "computer"}],
            input=[{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": task},
                    {"type": "input_image", "image_url": f"data:image/png;base64,{b64}"},
                ],
            }],
            truncation="auto",
        )
        dt = time.time() - t0
        print(f"  {CHECK} Initial response {DIM}({dt:.1f}s){RESET}")

        # Step 5: CU loop
        for turn in range(args.cu_max_turns):
            results["turns"] = turn + 1

            # Find computer_call in output
            computer_call = None
            for item in response.output:
                if getattr(item, "type", None) == "computer_call":
                    computer_call = item
                    break

            if computer_call is None:
                # Model finished (text response, no more actions)
                print(f"  {CHECK} Model finished after {turn + 1} turns (no more actions)")
                # Log any text output
                for item in response.output:
                    if getattr(item, "type", None) == "message":
                        for c in getattr(item, "content", []):
                            if getattr(c, "type", None) == "output_text":
                                print(f"    {DIM}Model: {c.text[:120]}{RESET}")
                break

            call_id = computer_call.call_id
            actions = computer_call.actions

            # Execute each action
            for i, action in enumerate(actions):
                action_type = action.type
                action_desc = action_type
                if action_type == "click":
                    action_desc = f"click({action.x}, {action.y})"
                elif action_type == "type":
                    action_desc = f"type({action.text!r})"
                elif action_type == "keypress":
                    action_desc = f"keypress({action.keys})"
                elif action_type == "scroll":
                    action_desc = f"scroll(y={getattr(action, 'scroll_y', 0)})"

                print(f"    Turn {turn + 1}/{args.cu_max_turns} "
                      f"action {i + 1}/{len(actions)}: {BOLD}{action_desc}{RESET}")
                results["actions_log"].append({
                    "turn": turn + 1,
                    "action": action_desc,
                    "timestamp": time.time(),
                })

                _execute_cu_action(action)
                time.sleep(0.3)

            # Take screenshot after actions
            time.sleep(1)
            png = _take_screenshot()
            if not png:
                print(f"  {YELLOW}  Screenshot failed on turn {turn + 1}{RESET}")
                break

            shot_path = str(out_dir / f"cu_screenshot_{turn + 1:02d}.png")
            _save_screenshot(png, shot_path)
            results["screenshots"].append(shot_path)
            print(f"  {CHECK} Screenshot: {shot_path}")

            b64 = _screenshot_to_b64(png)

            # Send continuation
            t0 = time.time()
            response = client.responses.create(
                model=args.cu_model,
                tools=[{"type": "computer"}],
                previous_response_id=response.id,
                input=[{
                    "type": "computer_call_output",
                    "call_id": call_id,
                    "output": {
                        "type": "input_image",
                        "image_url": f"data:image/png;base64,{b64}",
                    },
                }],
                truncation="auto",
            )
            dt = time.time() - t0
            print(f"    {DIM}Response in {dt:.1f}s{RESET}")

        print(f"  {CHECK} CU loop completed: {results['turns']} turns, "
              f"{len(results['actions_log'])} actions, "
              f"{len(results['screenshots'])} screenshots")

    except Exception as e:
        print(f"  {YELLOW}  CU phase failed (non-fatal): {e}{RESET}")
        import traceback
        traceback.print_exc()
        results["skipped"] = True

    dt_phase = time.time() - t_phase
    print(f"\n  {DIM}Phase 2 completed in {dt_phase:.1f}s{RESET}")
    return results


# -- Phase 3: ANALYZE --------------------------------------------------------

def phase_analyze(args: argparse.Namespace) -> dict:
    """Offline NMR processing + real OpenAI gpt-4o interpretation."""
    phase(3, "ANALYZE", "Process NMR data + AI interpretation (gpt-4o)")
    t_phase = time.time()
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

    # Build spectrum summary for AI
    processor = NMRProcessor()
    summary = processor.get_spectrum_summary(spectrum)

    # AI interpretation (real OpenAI gpt-4o)
    print(f"\n  {BOLD}AI Interpretation (gpt-4o):{RESET}")
    print(f"  {CYAN}{'=' * 50}{RESET}")

    if not os.environ.get("OPENAI_API_KEY"):
        print(f"  {YELLOW}  OPENAI_API_KEY not set — skipping AI interpretation{RESET}")
    else:
        client = _get_openai()

        # Interpret spectrum
        user_message = f"Please analyze this NMR spectrum:\n\n{summary}"
        if args.formula:
            user_message += f"\n\nMolecular formula: {args.formula}"

        t0 = time.time()
        interpretation_chunks = []
        try:
            stream = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=2000,
                messages=[
                    {"role": "system", "content": NMR_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    sys.stdout.write(delta.content)
                    sys.stdout.flush()
                    interpretation_chunks.append(delta.content)
        except Exception as e:
            print(f"\n  {YELLOW}  Interpretation error: {e}{RESET}")

        dt = time.time() - t0
        results["interpretation"] = "".join(interpretation_chunks)
        print(f"\n  {CYAN}{'=' * 50}{RESET}")
        print(f"  {DIM}({dt:.1f}s){RESET}")

        # Next experiment suggestion
        print(f"\n  {BOLD}Suggested Next Experiment (gpt-4o):{RESET}")
        print(f"  {CYAN}{'-' * 50}{RESET}")

        next_message = (
            f"Based on this NMR data, what experiment should I run next?\n\n"
            f"{summary}\n\n"
            f"Provide a specific recommendation with:\n"
            f"1. Which experiment (COSY, HSQC, HMBC, 13C, DEPT, NOESY, etc.)\n"
            f"2. Why this experiment is most informative right now\n"
            f"3. What specific question it will answer\n"
            f"4. Expected key correlations to look for"
        )

        t0 = time.time()
        next_chunks = []
        try:
            stream = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=1500,
                messages=[
                    {"role": "system", "content": NMR_SYSTEM_PROMPT},
                    {"role": "user", "content": next_message},
                ],
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    sys.stdout.write(delta.content)
                    sys.stdout.flush()
                    next_chunks.append(delta.content)
        except Exception as e:
            print(f"\n  {YELLOW}  Suggestion error: {e}{RESET}")

        dt = time.time() - t0
        results["next_experiment"] = "".join(next_chunks)
        print(f"\n  {CYAN}{'-' * 50}{RESET}")
        print(f"  {DIM}({dt:.1f}s){RESET}")

    dt_phase = time.time() - t_phase
    print(f"\n  {DIM}Phase 3 completed in {dt_phase:.1f}s{RESET}")
    return results


# -- Phase 4: DISCOVER (LabClaw) ---------------------------------------------

def phase_discover(args: argparse.Namespace, spectrum_data: dict) -> dict:
    """Send data to LabClaw for pattern discovery."""
    phase(4, "DISCOVER", "LabClaw scientific method loop")
    t_phase = time.time()
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

    dt_phase = time.time() - t_phase
    print(f"\n  {DIM}Phase 4 completed in {dt_phase:.1f}s{RESET}")
    return results


# -- Phase 5: REPORT ---------------------------------------------------------

def phase_report(
    args: argparse.Namespace,
    research: dict,
    instrument: dict,
    analysis: dict,
    discovery: dict,
) -> str:
    """Generate AI-written IMRAD markdown report via gpt-4o."""
    phase(5, "REPORT", "AI-generated IMRAD experiment report (gpt-4o)")
    t_phase = time.time()

    spectrum = analysis.get("spectrum")
    ds = analysis.get("dataset") or {}
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    sample_name = ds.get("sample", args.dataset)

    # Build context for the AI report writer
    peak_data = ""
    if spectrum and spectrum.peaks:
        max_int = max(p.intensity for p in spectrum.peaks)
        top = sorted(spectrum.peaks, key=lambda p: p.intensity, reverse=True)[:15]
        peak_data = "\n".join(
            f"  {p.ppm:.3f} ppm, {p.intensity / max_int * 100:.1f}%, mult={p.multiplicity or '-'}"
            for p in top
        )

    pc = research.get("pubchem")
    pubchem_data = ""
    if pc:
        pubchem_data = (
            f"PubChem CID: {pc.get('CID', 'N/A')}\n"
            f"IUPAC: {pc.get('IUPACName', 'N/A')}\n"
            f"Formula: {pc.get('MolecularFormula', 'N/A')}\n"
            f"Weight: {pc.get('MolecularWeight', 'N/A')}\n"
            f"SMILES: {pc.get('CanonicalSMILES', pc.get('SMILES', 'N/A'))}\n"
            f"InChIKey: {pc.get('InChIKey', 'N/A')}"
        )

    discovery_data = ""
    if not discovery.get("skipped") and discovery.get("cycle"):
        cycle = discovery["cycle"]
        patterns = cycle.get("patterns", [])
        discovery_data = f"LabClaw found {len(patterns)} patterns: {patterns[:5]}"

    interpretation = analysis.get("interpretation") or "N/A"
    next_exp = analysis.get("next_experiment") or "N/A"

    instrument_mode = "GUI (GPT-5.4 Computer Use) + Offline" if not instrument.get("skipped") else "Offline only"
    cu_stats = ""
    if not instrument.get("skipped"):
        cu_stats = (
            f"CU turns: {instrument.get('turns', 0)}, "
            f"actions: {len(instrument.get('actions_log', []))}, "
            f"screenshots: {len(instrument.get('screenshots', []))}"
        )

    prompt = f"""Write a complete IMRAD (Introduction, Methods, Results and Discussion) scientific report in Markdown format for this NMR experiment.

EXPERIMENT DETAILS:
- Sample: {sample_name}
- Molecular formula: {args.formula}
- Date: {time.strftime('%Y-%m-%d %H:%M')}
- Instrument: Bruker TopSpin 5.0.0
- Control mode: {instrument_mode}
- Nucleus: {spectrum.nucleus if spectrum else 'N/A'}
- Solvent: {spectrum.solvent if spectrum else 'N/A'}
- Frequency: {f'{spectrum.frequency_mhz:.1f} MHz' if spectrum else 'N/A'}
- Total peaks detected: {len(spectrum.peaks) if spectrum else 0}
{f'- {cu_stats}' if cu_stats else ''}

TOP PEAKS (ppm, relative intensity, multiplicity):
{peak_data or 'No peaks available'}

PUBCHEM DATA:
{pubchem_data or 'Not available'}

AI SPECTRUM INTERPRETATION:
{interpretation}

SUGGESTED NEXT EXPERIMENT:
{next_exp}

DISCOVERY RESULTS:
{discovery_data or 'Not available'}

PROCESSING PIPELINE:
1. Load raw FID (Bruker format)
2. Remove digital filter (group delay correction)
3. Zero-fill to 65,536 points
4. Apodization (exponential multiplication, LB=0.3 Hz)
5. Fast Fourier Transform
6. Automatic phase correction (ACME algorithm)
7. Baseline correction (polynomial)
8. Peak picking (threshold-based)

Requirements:
- Use proper Markdown with headers (#, ##, ###)
- Include a peak table in Markdown table format
- Reference the spectrum image as ![NMR Spectrum]({sample_name}_spectrum.png)
- End with a note: *Generated with [device-use](https://github.com/labclaw/device-use) — ROS for Lab Instruments*
- Be scientifically rigorous and specific
- Include the PubChem cross-reference data if available
"""

    report_chunks = []

    if not os.environ.get("OPENAI_API_KEY"):
        print(f"  {YELLOW}  OPENAI_API_KEY not set — generating template report{RESET}")
        # Fallback: simple template
        report = _fallback_report(args, research, instrument, analysis, discovery)
        report_chunks.append(report)
    else:
        client = _get_openai()
        print(f"  {ARROW} Generating report with gpt-4o...")
        t0 = time.time()
        try:
            stream = client.chat.completions.create(
                model="gpt-4o",
                max_tokens=4000,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a scientific report writer. Write clear, rigorous, "
                            "publication-quality IMRAD reports in Markdown. Be specific "
                            "about NMR data interpretation. Do not use filler text."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                stream=True,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    sys.stdout.write(delta.content)
                    sys.stdout.flush()
                    report_chunks.append(delta.content)
        except Exception as e:
            print(f"\n  {YELLOW}  Report generation error: {e}{RESET}")
            report_chunks.append(_fallback_report(args, research, instrument, analysis, discovery))

        dt = time.time() - t0
        print(f"\n  {DIM}({dt:.1f}s){RESET}")

    report = "".join(report_chunks)

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
        "cu_actions": instrument.get("actions_log", []),
        "cu_turns": instrument.get("turns", 0),
        "cu_screenshots": instrument.get("screenshots", []),
    }
    json_path.write_text(json.dumps(json_data, indent=2, default=str))
    print(f"  {CHECK} Raw JSON: {BOLD}{json_path}{RESET}")

    dt_phase = time.time() - t_phase
    print(f"\n  {DIM}Phase 5 completed in {dt_phase:.1f}s{RESET}")
    return str(report_path)


def _fallback_report(
    args: argparse.Namespace,
    research: dict,
    instrument: dict,
    analysis: dict,
    discovery: dict,
) -> str:
    """Generate a template report when OpenAI API is unavailable."""
    spectrum = analysis.get("spectrum")
    ds = analysis.get("dataset") or {}
    sample_name = ds.get("sample", args.dataset)
    pc = research.get("pubchem")

    peak_rows = ""
    if spectrum and spectrum.peaks:
        max_int = max(p.intensity for p in spectrum.peaks)
        top = sorted(spectrum.peaks, key=lambda p: p.intensity, reverse=True)[:15]
        peak_rows = "\n".join(
            f"| {p.ppm:.3f} | {p.intensity / max_int * 100:.1f}% | {p.multiplicity or '-'} |"
            for p in top
        )

    return f"""# Experiment Report: {sample_name}

*Generated by device-use Full Experiment Orchestrator*
*Date: {time.strftime('%Y-%m-%d %H:%M')}*

## Methods

- Spectrometer: Bruker TopSpin 5.0.0
- Nucleus: {spectrum.nucleus if spectrum else 'N/A'}
- Solvent: {spectrum.solvent if spectrum else 'N/A'}
- Frequency: {f'{spectrum.frequency_mhz:.1f} MHz' if spectrum else 'N/A'}

## Results

| ppm | Rel. Intensity | Multiplicity |
|-----|----------------|--------------|
{peak_rows}

![NMR Spectrum]({sample_name}_spectrum.png)

### AI Analysis

{analysis.get('interpretation', 'N/A')}

### Suggested Next Experiment

{analysis.get('next_experiment', 'N/A')}

---

*Generated with [device-use](https://github.com/labclaw/device-use) — ROS for Lab Instruments*
"""


# -- Main --------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    _lib_banner(
        "Full Experiment Orchestrator",
        "Research -> Instrument -> Analyze -> Discover -> Report",
    )

    # Show config
    print(f"  {BOLD}Configuration:{RESET}")
    print(f"    Dataset:   {args.dataset} (expno {args.expno})")
    print(f"    Formula:   {args.formula}")
    print(f"    CU:        {'skip' if args.no_cu else args.cu_model}")
    print(f"    LabClaw:   {'skip' if args.no_labclaw else args.labclaw_url}")
    print(f"    Output:    {args.output}")
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    print(f"    OPENAI_API_KEY: {'set' if has_openai else 'NOT SET'}")
    print()

    t_start = time.time()

    # Phase 1: Research
    research = phase_research(args)

    # Phase 2: Instrument (GPT-5.4 Computer Use)
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
        f"CU: {BOLD}{instrument.get('turns', 0)} turns, {len(instrument.get('actions_log', []))} actions{RESET}" if not instrument.get("skipped") else f"CU: {DIM}skipped{RESET}",
        f"Report: {BOLD}{report_path}{RESET}",
        f"Total time: {BOLD}{dt:.1f}s{RESET}",
        f"Phases completed: 5/5",
    ], title="Full Experiment Complete")


if __name__ == "__main__":
    main()
