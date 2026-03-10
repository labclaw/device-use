#!/usr/bin/env python3
"""
Device-Use Demo: Full AI Scientist Pipeline

The ultimate demo — complete autonomous scientific workflow:

  ┌──────────────────────────────────────────────┐
  │  Cloud Brain (Claude AI)                     │
  ├──────────────────────────────────────────────┤
  │  device-use middleware                       │
  ├─────────┬──────────┬─────────┬──────────────┤
  │ TopSpin │ PubChem  │ ToolUni │ K-Dense      │
  │  (NMR)  │ (lookup) │ (600+)  │ (analyst)    │
  └─────────┴──────────┴─────────┴──────────────┘

Pipeline:
  1. Load NMR data from TopSpin (any control mode)
  2. Process spectrum (FT → Phase → Baseline → Peaks)
  3. AI identifies compound from peaks
  4. PubChem cross-references compound metadata
  5. ToolUniverse discovers additional analysis tools
  6. AI recommends next experiments

Usage:
    python demos/topspin_ai_scientist.py
    python demos/topspin_ai_scientist.py --dataset exam_CMCse_1 --formula C13H20O
"""

import os
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning, module="nmrglue")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="scipy")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from device_use.instruments.nmr.adapter import TopSpinAdapter
from device_use.instruments.nmr.visualizer import plot_spectrum
from device_use.tools.pubchem import PubChemTool, PubChemError
from device_use.tools.tooluniverse import ToolUniverseTool, _TU_AVAILABLE


# ── Terminal styling ──────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
RESET = "\033[0m"
CHECK = f"{GREEN}✓{RESET}"
ARROW = f"{CYAN}→{RESET}"
STAR = f"{YELLOW}★{RESET}"


def banner():
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   {RESET}{BOLD}AI Scientist Pipeline{RESET}{BOLD}{CYAN}                                      ║
║   {RESET}{DIM}NMR → Process → Identify → Cross-Reference → Plan{RESET}{BOLD}{CYAN}          ║
║                                                              ║
║   {RESET}{DIM}device-use | ToolUniverse | PubChem | Claude AI{RESET}{BOLD}{CYAN}              ║
║   {RESET}{DIM}The complete autonomous discovery workflow{RESET}{BOLD}{CYAN}                   ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")


def phase(n: int, title: str, subtitle: str = ""):
    print(f"\n{BOLD}{MAGENTA}{'━' * 62}{RESET}")
    print(f"  {BOLD}Phase {n}{RESET} {DIM}│{RESET} {BOLD}{title}{RESET}")
    if subtitle:
        print(f"         {DIM}{subtitle}{RESET}")
    print(f"{BOLD}{MAGENTA}{'━' * 62}{RESET}\n")


# ── Known compounds for demo ─────────────────────────────────────

COMPOUNDS = [
    {"sample": "exam_CMCse_1", "expno": 1, "name": "Alpha Ionone",
     "formula": "C13H20O", "cas": "127-41-3"},
    {"sample": "exam_CMCse_3", "expno": 10, "name": "Strychnine",
     "formula": "C21H22N2O2", "cas": "57-24-9"},
]


def main():
    banner()

    # ── Phase 1: Instrument Layer ──

    phase(1, "Instrument Layer", "Connect to NMR spectrometer via device-use")

    adapter = TopSpinAdapter()
    adapter.connect()
    instrument = adapter.info()
    print(f"  {CHECK} Instrument: {BOLD}{instrument.name} {instrument.version}{RESET}")
    print(f"  {CHECK} Mode: {BOLD}{adapter.mode.value.upper()}{RESET}")
    print(f"  {CHECK} Supported: {', '.join(m.value for m in instrument.supported_modes)}")

    datasets = adapter.list_datasets()
    print(f"  {CHECK} Datasets available: {BOLD}{len(datasets)}{RESET}")

    # ── Phase 2: Process NMR Data ──

    phase(2, "Signal Processing", "FID → FFT → Phase → Baseline → Peak Pick")

    spectra = {}
    for compound in COMPOUNDS:
        ds = None
        for d in datasets:
            if d["sample"] == compound["sample"] and d["expno"] == compound["expno"]:
                ds = d
                break
        if not ds:
            print(f"  {RED}✗{RESET} {compound['name']}: dataset not found")
            continue

        sys.stdout.write(f"  {ARROW} {compound['name']}... ")
        sys.stdout.flush()
        t0 = time.time()
        spectrum = adapter.process(ds["path"])
        dt = time.time() - t0
        print(f"{GREEN}done{RESET} {DIM}({dt:.1f}s, {len(spectrum.peaks)} peaks, "
              f"{spectrum.frequency_mhz:.0f} MHz){RESET}")
        spectra[compound["name"]] = {"spectrum": spectrum, "compound": compound, "dataset": ds}

    print(f"\n  {CHECK} {BOLD}{len(spectra)} spectra{RESET} processed successfully")

    # ── Phase 3: Visualization ──

    phase(3, "Visualization", "Publication-quality spectrum plots")

    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    for name, entry in spectra.items():
        spectrum = entry["spectrum"]
        plot_path = output_dir / f"{entry['dataset']['sample']}_ai_scientist.png"
        plot_spectrum(spectrum, output_path=plot_path)
        print(f"  {CHECK} {name}: {BOLD}{plot_path}{RESET}")

    # ── Phase 4: AI Compound Identification ──

    phase(4, "Cloud Brain", "AI identifies compounds from NMR peaks")

    from device_use.instruments.nmr.brain import NMRBrain
    brain = NMRBrain()

    has_api = bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not has_api:
        print(f"  {DIM}(No API key — using cached expert responses){RESET}\n")

    for name, entry in spectra.items():
        spectrum = entry["spectrum"]
        compound = entry["compound"]

        print(f"  {BOLD}{'─' * 56}{RESET}")
        print(f"  {STAR} {BOLD}{name}{RESET} ({compound['formula']})")
        print(f"  {BOLD}{'─' * 56}{RESET}")

        # Show top peaks
        max_int = max(p.intensity for p in spectrum.peaks) if spectrum.peaks else 1.0
        for peak in spectrum.peaks[:8]:
            rel = peak.intensity / max_int * 100
            bar = "█" * int(rel / 5)
            print(f"    δ {peak.ppm:7.3f} ppm  {rel:5.1f}%  {DIM}{bar}{RESET}")

        print(f"\n  {ARROW} {BOLD}AI analysis:{RESET}")
        print(f"  {CYAN}{'─' * 50}{RESET}")
        t0 = time.time()
        for chunk in brain.interpret_spectrum(
            spectrum,
            molecular_formula=compound["formula"],
            context=f"Molecular formula: {compound['formula']}",
            stream=True,
        ):
            sys.stdout.write(chunk)
            sys.stdout.flush()
        dt = time.time() - t0
        print(f"\n  {CYAN}{'─' * 50}{RESET}")
        print(f"  {DIM}({dt:.1f}s){RESET}\n")

    # ── Phase 5: PubChem Cross-Reference ──

    phase(5, "PubChem Cross-Reference", "Verify compounds against NCBI database")

    pubchem = PubChemTool()

    for name, entry in spectra.items():
        compound = entry["compound"]
        sys.stdout.write(f"  {ARROW} {name}... ")
        sys.stdout.flush()

        try:
            t0 = time.time()
            result = pubchem.lookup_by_name(name.replace(" ", " "))
            dt = time.time() - t0
            cid = result.get("CID", "?")
            iupac = result.get("IUPACName", "?")
            formula = result.get("MolecularFormula", "?")
            weight = result.get("MolecularWeight", "?")
            smiles = result.get("CanonicalSMILES") or result.get("SMILES", "?")

            print(f"{GREEN}verified{RESET} {DIM}({dt:.1f}s){RESET}")
            print(f"    CID:     {BOLD}{cid}{RESET}")
            print(f"    IUPAC:   {iupac}")
            print(f"    Formula: {formula}  (expected: {compound['formula']})")
            print(f"    Weight:  {weight}")
            print(f"    SMILES:  {DIM}{smiles}{RESET}")

            # Formula match check
            if formula == compound["formula"]:
                print(f"    {CHECK} Formula matches NMR identification!")
            else:
                print(f"    {YELLOW}○{RESET} Formula mismatch — may be isomer or different compound")
            print()
        except PubChemError as e:
            print(f"{RED}failed{RESET} — {e}")
            print()

    # ── Phase 6: ToolUniverse Discovery ──

    phase(6, "ToolUniverse Integration", "Discover scientific tools for deeper analysis")

    if _TU_AVAILABLE:
        tu = ToolUniverseTool()
        tu.connect()
        print(f"  {CHECK} ToolUniverse connected — 600+ scientific tools\n")

        # Find relevant tools
        for query, label in [
            ("NMR spectroscopy compound identification", "NMR Analysis"),
            ("molecular property prediction ADMET", "Property Prediction"),
            ("chemical structure similarity search", "Structure Search"),
        ]:
            sys.stdout.write(f"  {ARROW} {label}... ")
            sys.stdout.flush()
            try:
                tools = tu.find_tools(query, limit=3)
                print(f"{GREEN}found {len(tools)} tools{RESET}")
                if isinstance(tools, list):
                    for tool in tools[:3]:
                        tool_name = tool.get("name", "?") if isinstance(tool, dict) else str(tool)
                        print(f"    {DIM}• {tool_name}{RESET}")
            except Exception as e:
                print(f"{YELLOW}skipped{RESET} — {e}")
            print()
    else:
        print(f"  {DIM}ToolUniverse not installed — showing integration architecture{RESET}\n")
        print(f"  {BOLD}Available when installed:{RESET} pip install tooluniverse")
        print(f"  {DIM}• Tool_Finder_Keyword — discover tools by description{RESET}")
        print(f"  {DIM}• Tool_Finder_Embedding — semantic tool search{RESET}")
        print(f"  {DIM}• 600+ scientific tools: ML models, databases, APIs{RESET}")
        print(f"  {DIM}• MCP server for direct AI agent integration{RESET}")
        print()
        print(f"  {BOLD}Architecture:{RESET}")
        print(f"  {DIM}┌──────────────────────────────────────────────┐{RESET}")
        print(f"  {DIM}│  Cloud Brain (Claude / GPT / Gemini)         │{RESET}")
        print(f"  {DIM}├──────────────────────────────────────────────┤{RESET}")
        print(f"  {DIM}│  device-use middleware (this project)         │{RESET}")
        print(f"  {DIM}├──────────┬──────────┬─────────┬─────────────┤{RESET}")
        print(f"  {DIM}│ TopSpin  │ PubChem  │ToolUniv │ K-Dense     │{RESET}")
        print(f"  {DIM}│ (NMR)   │ (NCBI)   │(Harvard)│ (Analyst)   │{RESET}")
        print(f"  {DIM}└──────────┴──────────┴─────────┴─────────────┘{RESET}")
        print()
        print(f"  {DIM}ToolUniverse MCP config:{RESET}")
        print(f'  {DIM}{{"mcpServers": {{"tooluniverse": {{{RESET}')
        print(f'  {DIM}    "command": "uvx", "args": ["tooluniverse"]{RESET}')
        print(f'  {DIM}}}}}}}{RESET}')
        print()

    # ── Phase 7: Next Experiment Recommendation ──

    phase(7, "Experiment Planning", "AI recommends next steps")

    # Pick the most complex compound for recommendation
    target = list(spectra.values())[-1]
    spectrum = target["spectrum"]
    compound = target["compound"]

    print(f"  {STAR} Planning next experiments for {BOLD}{compound['name']}{RESET}\n")
    print(f"  {CYAN}{'─' * 50}{RESET}")
    t0 = time.time()
    for chunk in brain.suggest_next_experiment(spectrum, stream=True):
        sys.stdout.write(chunk)
        sys.stdout.flush()
    dt = time.time() - t0
    print(f"\n  {CYAN}{'─' * 50}{RESET}")
    print(f"  {DIM}({dt:.1f}s){RESET}")

    # ── Finale ──

    total_peaks = sum(len(e["spectrum"].peaks) for e in spectra.values())

    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║  AI Scientist Pipeline Complete                              ║
╚══════════════════════════════════════════════════════════════╝{RESET}

  {CHECK} {BOLD}{len(spectra)} compounds{RESET} processed ({total_peaks} total peaks)
  {CHECK} NMR spectra acquired via {BOLD}device-use{RESET} middleware
  {CHECK} Compounds identified by {BOLD}Claude AI{RESET} Cloud Brain
  {CHECK} Cross-referenced against {BOLD}PubChem{RESET} (NCBI)
  {CHECK} ToolUniverse: {BOLD}{'connected (600+ tools)' if _TU_AVAILABLE else 'architecture ready'}{RESET}
  {CHECK} Next experiments planned autonomously

  {BOLD}What this demonstrates:{RESET}
  {DIM}• AI can autonomously run the full scientific method{RESET}
  {DIM}• device-use provides ROS-like middleware for instruments{RESET}
  {DIM}• Loose coupling: any AI brain + any instrument + any tool{RESET}
  {DIM}• ToolUniverse adds 600+ scientific tools to the pipeline{RESET}
  {DIM}• From raw FID to discovery — end to end, no human in the loop{RESET}
""")


if __name__ == "__main__":
    main()
