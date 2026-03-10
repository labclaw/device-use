#!/usr/bin/env python3
"""
Device-Use Demo: TopSpin AI Scientist — Multi-Mode NMR Analysis

Showcases the device-use middleware architecture:
  ┌──────────────────────────┐
  │  Cloud Brain (Claude AI)  │  ← Any AI agent
  ├──────────────────────────┤
  │  device-use (middleware)  │  ← ROS for lab instruments
  ├────────┬────────┬────────┤
  │  API   │  GUI   │Offline │  ← 3 control modes
  │ (gRPC) │ (CU)   │(local) │
  └────────┴────────┴────────┘

Usage:
    python demos/topspin_identify.py                                    # interactive
    python demos/topspin_identify.py --dataset exam_CMCse_1 --no-brain  # offline only
    python demos/topspin_identify.py --dataset Strychnine --expno 10 --formula C21H22N2O2
    python demos/topspin_identify.py --mode api                         # force API mode
"""

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from device_use.instruments import ControlMode
from device_use.instruments.nmr.adapter import TopSpinAdapter
from device_use.instruments.nmr.processor import NMRProcessor


# ── Terminal styling ──────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
WHITE = "\033[37m"
RESET = "\033[0m"
CHECK = f"{GREEN}✓{RESET}"
ARROW = f"{CYAN}→{RESET}"
WARN = f"{YELLOW}○{RESET}"


def banner():
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ██████╗ ███████╗██╗   ██╗██╗ ██████╗███████╗               ║
║   ██╔══██╗██╔════╝██║   ██║██║██╔════╝██╔════╝               ║
║   ██║  ██║█████╗  ██║   ██║██║██║     █████╗                 ║
║   ██║  ██║██╔══╝  ╚██╗ ██╔╝██║██║     ██╔══╝                ║
║   ██████╔╝███████╗ ╚████╔╝ ██║╚██████╗███████╗              ║
║   ╚═════╝ ╚══════╝  ╚═══╝  ╚═╝ ╚═════╝╚══════╝  {RESET}{DIM}USE{RESET}{BOLD}{CYAN}       ║
║                                                              ║
║   {RESET}{BOLD}TopSpin AI Scientist{RESET}{BOLD}{CYAN}                                       ║
║   {RESET}{DIM}ROS for Lab Instruments — AI meets Physical Science{RESET}{BOLD}{CYAN}         ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")


def step(n: int, text: str):
    print(f"\n{BOLD}{MAGENTA}{'━' * 62}{RESET}")
    print(f"  {BOLD}Step {n}{RESET} {DIM}│{RESET} {text}")
    print(f"{BOLD}{MAGENTA}{'━' * 62}{RESET}\n")


def ok(text: str):
    print(f"  {CHECK} {text}")


def warn(text: str):
    print(f"  {WARN} {text}")


def info(text: str):
    print(f"  {DIM}{text}{RESET}")


def err(text: str):
    print(f"  {RED}✗{RESET} {text}")


def progress(text: str):
    print(f"  {ARROW} {text}", end="", flush=True)


def done(dt: float):
    print(f" {GREEN}done{RESET} {DIM}({dt:.1f}s){RESET}")


def section(text: str):
    print(f"\n  {BOLD}{text}{RESET}")


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Device-Use Demo: TopSpin AI Scientist",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Examples:\n"
        "  %(prog)s --dataset exam_CMCse_1 --formula C13H20O\n"
        "  %(prog)s --dataset Strychnine --expno 10 --no-brain\n"
        "  %(prog)s --mode api  # force gRPC mode\n",
    )
    parser.add_argument("--dataset", type=str, help="Dataset name or title keyword")
    parser.add_argument("--expno", type=int, default=1, help="Experiment number")
    parser.add_argument("--formula", type=str, help="Molecular formula (e.g., C13H20O)")
    parser.add_argument("--topspin-dir", type=str, default="/opt/topspin5.0.0")
    parser.add_argument(
        "--mode", type=str, default="auto",
        choices=["auto", "api", "gui", "offline"],
        help="Control mode: auto tries API→GUI→Offline",
    )
    parser.add_argument("--no-brain", action="store_true", help="Skip Cloud Brain (no API call)")
    parser.add_argument("--output", type=str, default="output", help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)

    banner()

    # ── Step 0: Connect to Instrument ──

    step(0, "Connect to Instrument  (device-use middleware)")

    section("Instrument Discovery")
    adapter, active_mode = _connect_instrument(args)
    instrument_info = adapter.info()
    print()
    ok(f"Instrument: {BOLD}{instrument_info.name} {instrument_info.version}{RESET} ({instrument_info.vendor})")
    ok(f"Control mode: {BOLD}{active_mode.value.upper()}{RESET}")
    info(f"  Supported modes: {', '.join(m.value for m in instrument_info.supported_modes)}")

    # ── Step 1: Select Dataset ──

    step(1, "Load NMR Dataset")

    datasets = adapter.list_datasets()
    if not datasets:
        err(f"No datasets found at {args.topspin_dir}/examdata/")
        sys.exit(1)

    info(f"Found {len(datasets)} datasets in TopSpin examdata")

    dataset_path, selected_ds = _select_dataset(args, datasets)

    print()
    ok(f"Dataset: {BOLD}{selected_ds['sample']}/{selected_ds['expno']}{RESET}")
    ok(f"Title: {selected_ds['title']}")
    info(f"  Path: {dataset_path}")

    # ── Step 2: Process NMR Data ──

    step(2, f"Process NMR Data  ({active_mode.value.upper()} mode)")

    progress("Processing FID → Spectrum...")
    t0 = time.time()
    spectrum = adapter.process(dataset_path)
    done(time.time() - t0)

    print()
    section("Processing Pipeline")
    ok(f"Fourier Transform → {BOLD}{len(spectrum.data):,}{RESET} points")
    ok("Phase correction (ACME algorithm)")
    ok("Baseline correction (polynomial)")
    ok(f"Peak picking → {BOLD}{len(spectrum.peaks)} peaks{RESET}")

    section("Metadata")
    info(f"  {spectrum.frequency_mhz:.1f} MHz  |  {spectrum.nucleus}  |  {spectrum.solvent}")
    if spectrum.title:
        info(f"  {spectrum.title}")

    # ── Step 3: Visualize & Extract ──

    step(3, "Visualize & Extract Peak List")

    from device_use.instruments.nmr.visualizer import plot_spectrum

    plot_path = output_dir / f"{selected_ds['sample']}_spectrum.png"
    plot_spectrum(spectrum, output_path=plot_path)
    ok(f"Spectrum saved: {BOLD}{plot_path}{RESET}")

    print()
    _print_peak_table(spectrum)

    if args.no_brain:
        warn(f"{YELLOW}--no-brain{RESET} flag set, skipping Cloud Brain")
        _print_finale(plot_path, brain_used=False)
        return

    # ── Step 4: Cloud Brain ──

    step(4, "Cloud Brain Analysis  (Claude AI)")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        err("ANTHROPIC_API_KEY not set")
        info(f"  export ANTHROPIC_API_KEY=sk-ant-...")
        info(f"  Or run with --no-brain to skip AI analysis")
        _print_finale(plot_path, brain_used=False)
        return

    from device_use.instruments.nmr.brain import NMRBrain

    brain = NMRBrain()

    if args.formula:
        info(f"Constraint: molecular formula = {args.formula}")

    print(f"\n  {ARROW} {BOLD}Claude is analyzing the NMR spectrum...{RESET}\n")
    print(f"  {CYAN}{'─' * 56}{RESET}")
    t0 = time.time()
    for chunk in brain.interpret_spectrum(
        spectrum,
        molecular_formula=args.formula,
        context=f"Molecular formula: {args.formula}" if args.formula else "",
        stream=True,
    ):
        sys.stdout.write(chunk)
        sys.stdout.flush()
    dt = time.time() - t0
    print(f"\n  {CYAN}{'─' * 56}{RESET}")
    info(f"  Analysis complete ({dt:.1f}s)")

    # ── Step 5: Next Experiment ──

    step(5, "Recommend Next Experiment")

    print(f"  {ARROW} {BOLD}What should we run next?{RESET}\n")
    print(f"  {CYAN}{'─' * 56}{RESET}")
    t0 = time.time()
    for chunk in brain.suggest_next_experiment(spectrum, stream=True):
        sys.stdout.write(chunk)
        sys.stdout.flush()
    dt = time.time() - t0
    print(f"\n  {CYAN}{'─' * 56}{RESET}")
    info(f"  Recommendation complete ({dt:.1f}s)")

    _print_finale(plot_path, brain_used=True)


# ── Helpers ───────────────────────────────────────────────────────

def _connect_instrument(args) -> tuple[TopSpinAdapter, ControlMode]:
    """Connect to TopSpin using the requested mode, with auto-fallback."""

    if args.mode == "auto":
        # Try API → Offline (GUI requires more setup)
        for try_mode in [ControlMode.API, ControlMode.OFFLINE]:
            info(f"  Trying {try_mode.value.upper()} mode...")
            adapter = TopSpinAdapter(topspin_dir=args.topspin_dir, mode=try_mode)
            if adapter.connect():
                return adapter, try_mode
            info(f"    → not available")
        err("No control mode available")
        sys.exit(1)
    else:
        mode = ControlMode(args.mode)
        adapter = TopSpinAdapter(topspin_dir=args.topspin_dir, mode=mode)
        if not adapter.connect():
            err(f"{mode.value.upper()} mode not available")
            if mode == ControlMode.API:
                info("  Is TopSpin running? (gRPC port 3081)")
            elif mode == ControlMode.GUI:
                info("  Is TopSpin GUI visible on screen?")
            sys.exit(1)
        return adapter, mode


def _select_dataset(args, datasets) -> tuple[str, dict]:
    """Select a dataset by name, title, or interactive choice."""
    if args.dataset:
        for ds in datasets:
            name_match = args.dataset.lower() in ds["sample"].lower()
            title_match = args.dataset.lower() in ds["title"].lower()
            if (name_match or title_match) and ds["expno"] == args.expno:
                return ds["path"], ds
        err(f"Dataset '{args.dataset}' (expno={args.expno}) not found")
        info("  Available datasets:")
        for ds in datasets:
            info(f"    {ds['sample']}/{ds['expno']}: {ds['title']}")
        sys.exit(1)

    # Interactive selection
    print()
    for i, ds in enumerate(datasets):
        print(f"    {BOLD}[{i:2d}]{RESET} {ds['sample']}/{ds['expno']}: {DIM}{ds['title']}{RESET}")
    print()
    choice = input(f"  Select dataset number: ").strip()
    try:
        ds = datasets[int(choice)]
        return ds["path"], ds
    except (ValueError, IndexError):
        err("Invalid choice.")
        sys.exit(1)


def _print_peak_table(spectrum):
    """Print a formatted peak table with visual bars."""
    section("Peak List")
    print(f"  {'─' * 50}")
    print(f"  {'δ (ppm)':>10}  {'Rel. Intensity':>15}  {'Visual'}")
    print(f"  {'─' * 50}")

    max_int = max(p.intensity for p in spectrum.peaks) if spectrum.peaks else 1.0
    for peak in spectrum.peaks:
        rel = peak.intensity / max_int * 100
        bar = "█" * int(rel / 5)
        print(f"  {peak.ppm:10.3f}  {rel:14.1f}%  {DIM}{bar}{RESET}")

    print(f"  {'─' * 50}")


def _print_finale(plot_path, brain_used: bool):
    """Print the final summary."""
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║  Pipeline Complete                                           ║
╚══════════════════════════════════════════════════════════════╝{RESET}

  {CHECK} Raw FID loaded from TopSpin examdata
  {CHECK} Processed: FT → Phase → Baseline → Peak Pick
  {CHECK} Spectrum visualization → {BOLD}{plot_path}{RESET}""")

    if brain_used:
        print(f"  {CHECK} Cloud Brain identified compound structure")
        print(f"  {CHECK} Cloud Brain recommended next experiment")
    else:
        print(f"  {DIM}○ Cloud Brain skipped{RESET}")

    print(f"""
  {BOLD}device-use{RESET} — middleware for scientific instruments
  {DIM}Like ROS for robots, but for NMR, microscopes, and more.{RESET}
  {DIM}Any AI agent. Any control mode. Any instrument.{RESET}
""")


if __name__ == "__main__":
    main()
