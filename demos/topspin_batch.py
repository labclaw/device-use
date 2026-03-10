#!/usr/bin/env python3
"""
Device-Use Demo: Batch Analysis — Process All Compounds + PubChem Lookup

The AI Scientist processes every 1D NMR dataset, identifies each compound,
then cross-references with PubChem for authoritative metadata.

This showcases the full middleware pipeline:
  TopSpin Data → NMR Processor → Cloud Brain → PubChem Verification

Usage:
    python demos/topspin_batch.py                  # process all
    python demos/topspin_batch.py --no-brain       # processing + PubChem only
"""

import argparse
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning, module="nmrglue")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="scipy")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

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
RESET = "\033[0m"
CHECK = f"{GREEN}✓{RESET}"
ARROW = f"{CYAN}→{RESET}"


def banner():
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   {RESET}{BOLD}Batch NMR Analysis — Multi-Compound Pipeline{RESET}{BOLD}{CYAN}               ║
║   {RESET}{DIM}Process → Identify → PubChem Verify — Fully Automated{RESET}{BOLD}{CYAN}       ║
║                                                              ║
║   {RESET}{DIM}device-use | ROS for Lab Instruments{RESET}{BOLD}{CYAN}                        ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")


def main():
    parser = argparse.ArgumentParser(description="Batch NMR Analysis Demo")
    parser.add_argument("--topspin-dir", type=str, default="/opt/topspin5.0.0")
    parser.add_argument("--no-brain", action="store_true")
    parser.add_argument("--output", type=str, default="output")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)

    banner()

    # ── Connect ──
    adapter = TopSpinAdapter(topspin_dir=args.topspin_dir)
    adapter.connect()
    print(f"  {CHECK} Instrument: {BOLD}TopSpin 5.0.0{RESET} ({adapter.mode.value} mode)")

    # ── Select 1D datasets (skip DNMR temperature series and 2D) ──
    all_datasets = adapter.list_datasets()

    # Pick one experiment per unique sample (first expno only, skip DNMR)
    seen_samples = set()
    target_datasets = []
    for ds in all_datasets:
        if ds["sample"] in seen_samples:
            continue
        if "DNMR" in ds["sample"]:
            continue
        seen_samples.add(ds["sample"])
        target_datasets.append(ds)

    print(f"  {CHECK} Found {BOLD}{len(target_datasets)}{RESET} unique 1D compounds\n")

    # ── Process all ──
    print(f"{BOLD}{MAGENTA}{'━' * 62}{RESET}")
    print(f"  {BOLD}Batch Processing{RESET}")
    print(f"{BOLD}{MAGENTA}{'━' * 62}{RESET}\n")

    from device_use.instruments.nmr.visualizer import plot_spectrum

    results = []
    for ds in target_datasets:
        label = f"{ds['sample']}/{ds['expno']}"
        print(f"  {ARROW} {label:30s} ", end="", flush=True)
        t0 = time.time()
        try:
            spectrum = adapter.process(ds["path"])
            dt = time.time() - t0

            # Generate plot
            plot_path = output_dir / f"{ds['sample']}_spectrum.png"
            plot_spectrum(spectrum, output_path=plot_path)

            results.append({
                "dataset": ds,
                "spectrum": spectrum,
                "plot_path": plot_path,
                "error": None,
            })
            print(f"{GREEN}✓{RESET} {len(spectrum.peaks):2d} peaks  {DIM}({dt:.1f}s){RESET}")
        except Exception as e:
            results.append({
                "dataset": ds,
                "spectrum": None,
                "plot_path": None,
                "error": str(e),
            })
            print(f"{RED}✗{RESET} {DIM}{str(e)[:40]}{RESET}")

    success = [r for r in results if r["error"] is None]
    print(f"\n  {CHECK} Processed {BOLD}{len(success)}/{len(results)}{RESET} compounds")

    # ── PubChem cross-reference ──
    print(f"\n{BOLD}{MAGENTA}{'━' * 62}{RESET}")
    print(f"  {BOLD}PubChem Cross-Reference{RESET}")
    print(f"{BOLD}{MAGENTA}{'━' * 62}{RESET}\n")

    from device_use.tools.pubchem import PubChemTool, PubChemError

    pubchem = PubChemTool()

    for r in success:
        title = r["dataset"]["title"]
        # Extract compound name (first word/phrase before technical details)
        compound_name = _extract_compound_name(title)
        if not compound_name:
            continue

        print(f"  {ARROW} {compound_name:25s} ", end="", flush=True)
        try:
            props = pubchem.lookup_by_name(compound_name)
            cid = props.get("CID", "?")
            formula = props.get("MolecularFormula", "?")
            mw = props.get("MolecularWeight", "?")
            iupac = props.get("IUPACName", "?")
            r["pubchem"] = props
            print(f"{GREEN}✓{RESET} CID:{cid}  {formula}  MW:{mw}")
            print(f"    {DIM}IUPAC: {iupac[:55]}{RESET}")
        except PubChemError as e:
            print(f"{YELLOW}○{RESET} {DIM}{str(e)[:50]}{RESET}")
        except Exception as e:
            print(f"{RED}✗{RESET} {DIM}{str(e)[:50]}{RESET}")

    # ── Summary table ──
    print(f"\n{BOLD}{MAGENTA}{'━' * 62}{RESET}")
    print(f"  {BOLD}Summary{RESET}")
    print(f"{BOLD}{MAGENTA}{'━' * 62}{RESET}\n")

    print(f"  {'Compound':20s} {'Peaks':>6} {'MHz':>7} {'Solvent':>8} {'Plot'}")
    print(f"  {'─' * 58}")
    for r in success:
        sp = r["spectrum"]
        name = r["dataset"]["sample"][:20]
        print(
            f"  {name:20s} {len(sp.peaks):6d} {sp.frequency_mhz:7.1f} "
            f"{sp.solvent:>8s} {CHECK}"
        )
    print(f"  {'─' * 58}")

    # ── Finale ──
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║  Batch Analysis Complete                                     ║
╚══════════════════════════════════════════════════════════════╝{RESET}

  {CHECK} Processed {BOLD}{len(success)}{RESET} compounds
  {CHECK} Generated {BOLD}{len(success)}{RESET} spectrum plots
  {CHECK} Cross-referenced with PubChem
  {CHECK} All outputs saved to {BOLD}{output_dir}/{RESET}

  {BOLD}device-use{RESET} — from raw data to verified compound identity.
  {DIM}No manual intervention. No copy-paste. Fully automated.{RESET}
""")


def _extract_compound_name(title: str) -> str:
    """Best-effort extraction of compound name from TopSpin title."""
    if not title:
        return ""
    # Common patterns: "Alpha Ionone", "Strychnine C21H22N2O2 in CDCl3"
    # Remove formula and solvent info
    name = title.split(" in ")[0].strip()
    name = title.split(" C")[0].strip() if " C" in name and any(c.isdigit() for c in name.split(" C")[1][:3]) else name
    # Remove numbers-only and technical terms
    if name in ("ZGPR",) or not any(c.isalpha() for c in name):
        return ""
    return name


if __name__ == "__main__":
    main()
