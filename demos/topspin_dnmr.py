#!/usr/bin/env python3
"""
Device-Use Demo: Dynamic NMR — Temperature-Dependent Conformational Analysis

Shows AI analyzing how molecular dynamics change with temperature:
  Multiple spectra at different temperatures → AI explains the chemistry

The exam_DNMR_Me2NCOMe dataset shows restricted rotation of the
N,N-dimethylformamide (DMF) amide bond. At low temperature, the two
N-methyl groups are distinct (slow rotation); at high temperature,
they merge (fast rotation). The coalescence temperature reveals the
rotation barrier energy.

Usage:
    python demos/topspin_dnmr.py                    # full analysis
    python demos/topspin_dnmr.py --no-brain         # processing only
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
RESET = "\033[0m"
CHECK = f"{GREEN}✓{RESET}"
ARROW = f"{CYAN}→{RESET}"


def banner():
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   {RESET}{BOLD}Dynamic NMR — Temperature Series Analysis{RESET}{BOLD}{CYAN}                 ║
║   {RESET}{DIM}AI watches molecular dynamics change in real time{RESET}{BOLD}{CYAN}            ║
║                                                              ║
║   {RESET}{DIM}device-use | ROS for Lab Instruments{RESET}{BOLD}{CYAN}                        ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")


def step(n: int, text: str):
    print(f"\n{BOLD}{MAGENTA}{'━' * 62}{RESET}")
    print(f"  {BOLD}Step {n}{RESET} {DIM}│{RESET} {text}")
    print(f"{BOLD}{MAGENTA}{'━' * 62}{RESET}\n")


def ok(text: str):
    print(f"  {CHECK} {text}")


def info(text: str):
    print(f"  {DIM}{text}{RESET}")


# ── Main ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Dynamic NMR Demo")
    parser.add_argument("--topspin-dir", type=str, default="/opt/topspin5.0.0")
    parser.add_argument("--no-brain", action="store_true", help="Skip AI analysis")
    parser.add_argument("--output", type=str, default="output")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)

    banner()

    # ── Connect ──

    adapter = TopSpinAdapter(topspin_dir=args.topspin_dir)
    adapter.connect()
    ok(f"Instrument: {BOLD}TopSpin 5.0.0{RESET} ({adapter.mode.value} mode)")

    # ── Find DNMR datasets ──

    step(1, "Load DNMR Temperature Series")

    all_datasets = adapter.list_datasets()
    dnmr_datasets = [
        ds for ds in all_datasets
        if "DNMR_Me2NCOMe" in ds["sample"]
    ]

    # Sort by experiment number (proxy for temperature)
    dnmr_datasets.sort(key=lambda d: d["expno"])

    info(f"Found {len(dnmr_datasets)} temperature points")
    print()
    for ds in dnmr_datasets:
        # Experiment numbers correspond roughly to temperature
        temp_k = ds["expno"] if ds["expno"] > 100 else None
        temp_str = f"{temp_k}K" if temp_k else f"exp {ds['expno']}"
        print(f"    {DIM}•{RESET} {temp_str}: {ds['title']}")

    # ── Process all spectra ──

    step(2, "Process Temperature Series  (batch)")

    spectra = []
    temps = []

    # Select a subset for the demo (low / mid / high temperatures)
    key_datasets = [d for d in dnmr_datasets if d["expno"] in [10, 320, 350, 370, 420]]
    if not key_datasets:
        key_datasets = dnmr_datasets[:5]

    for ds in key_datasets:
        temp_label = f"{ds['expno']}K" if ds["expno"] > 100 else f"T{ds['expno']}"
        print(f"  {ARROW} Processing {temp_label}... ", end="", flush=True)
        t0 = time.time()
        spectrum = adapter.process(ds["path"])
        dt = time.time() - t0
        spectra.append(spectrum)
        temps.append(ds["expno"])
        print(f"{GREEN}done{RESET} {DIM}({dt:.1f}s, {len(spectrum.peaks)} peaks){RESET}")

    ok(f"Processed {len(spectra)} spectra")

    # ── Generate overlay plot ──

    step(3, "Visualize Temperature Overlay")

    plot_path = output_dir / "dnmr_temperature_overlay.png"
    _plot_overlay(spectra, temps, plot_path)
    ok(f"Overlay plot saved: {BOLD}{plot_path}{RESET}")

    # ── Peak comparison table ──

    step(4, "Compare Peaks Across Temperatures")

    print(f"  {BOLD}N-Methyl Region (2.5–3.5 ppm) — Key Diagnostic Peaks{RESET}")
    print(f"  {'─' * 55}")
    print(f"  {'Temperature':>12}  {'Peaks in Region':>15}  {'Pattern'}")
    print(f"  {'─' * 55}")

    for spec, temp in zip(spectra, temps):
        temp_label = f"{temp}K" if temp > 100 else f"T={temp}"
        methyl_peaks = [p for p in spec.peaks if 2.5 <= p.ppm <= 3.5]
        if len(methyl_peaks) >= 2:
            pattern = "two peaks (slow rotation)"
        elif len(methyl_peaks) == 1:
            pattern = "coalesced (fast rotation)"
        else:
            pattern = "broad"
        print(f"  {temp_label:>12}  {len(methyl_peaks):>15}  {DIM}{pattern}{RESET}")

    print(f"  {'─' * 55}")

    if args.no_brain:
        print(f"\n  {YELLOW}○{RESET} Cloud Brain skipped")
        _print_finale(plot_path, brain_used=False)
        return

    # ── Cloud Brain analysis ──

    step(5, "Cloud Brain — Dynamics Analysis")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        from device_use.instruments.nmr.demo_cache import get_dnmr_analysis
        cached = get_dnmr_analysis()
        if cached:
            print(f"  {DIM}(using cached analysis){RESET}\n")
            print(f"  {CYAN}{'─' * 56}{RESET}")
            for chunk in _simulate_stream(cached):
                sys.stdout.write(chunk)
                sys.stdout.flush()
            print(f"\n  {CYAN}{'─' * 56}{RESET}")
        else:
            print(f"  {RED}✗{RESET} ANTHROPIC_API_KEY not set")
            info("  export ANTHROPIC_API_KEY=sk-ant-...")
        _print_finale(plot_path, brain_used=bool(cached))
        return

    from device_use.instruments.nmr.brain import NMRBrain

    brain = NMRBrain()

    # Build multi-spectrum prompt
    processor = NMRProcessor()
    summaries = []
    for spec, temp in zip(spectra, temps):
        label = f"{temp}K" if temp > 100 else f"T={temp}"
        summaries.append(f"--- {label} ---\n{processor.get_spectrum_summary(spec)}")

    print(f"  {ARROW} {BOLD}Claude is analyzing the temperature series...{RESET}\n")
    print(f"  {CYAN}{'─' * 56}{RESET}")

    # Custom prompt for DNMR analysis
    from anthropic import Anthropic
    client = Anthropic()
    t0 = time.time()
    with client.messages.stream(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system="You are an expert NMR spectroscopist analyzing dynamic NMR (DNMR) data. "
               "Analyze how the spectra change with temperature and explain the molecular dynamics.",
        messages=[{
            "role": "user",
            "content": (
                "Analyze this DNMR temperature series for N,N-dimethylacetamide (Me2NCOMe) in DMSO-d6.\n"
                "Focus on: coalescence behavior, rotation barrier estimation, and molecular dynamics.\n\n"
                + "\n\n".join(summaries)
            ),
        }],
    ) as stream:
        for text in stream.text_stream:
            sys.stdout.write(text)
            sys.stdout.flush()
    dt = time.time() - t0
    print(f"\n  {CYAN}{'─' * 56}{RESET}")
    info(f"  Analysis complete ({dt:.1f}s)")

    _print_finale(plot_path, brain_used=True)


def _plot_overlay(spectra, temps, output_path):
    """Generate a temperature overlay plot — key DNMR visualization."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.cm import coolwarm

    fig, ax = plt.subplots(1, 1, figsize=(14, 8))

    n = len(spectra)
    colors = [coolwarm(i / max(n - 1, 1)) for i in range(n)]

    for i, (spec, temp) in enumerate(zip(spectra, temps)):
        ppm = spec.ppm_scale
        data = spec.data
        mask = (ppm >= 1.0) & (ppm <= 9.0)
        ppm_plot = ppm[mask]
        data_plot = data[mask]
        data_max = np.max(np.abs(data_plot)) if len(data_plot) > 0 else 1.0
        data_norm = data_plot / data_max

        # Offset each spectrum vertically
        offset = i * 1.2
        label = f"{temp}K" if temp > 100 else f"T={temp}"
        ax.plot(ppm_plot, data_norm + offset, color=colors[i], linewidth=0.8, label=label)
        ax.text(ppm_plot[-1] + 0.3, offset + 0.5, label,
                fontsize=9, color=colors[i], fontweight="bold", va="center")

    ax.invert_xaxis()
    ax.set_xlabel("Chemical Shift (ppm)", fontsize=12, fontweight="bold")
    ax.set_ylabel("", fontsize=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.set_yticks([])

    ax.set_title("Dynamic NMR — Me₂NCOMe Temperature Series",
                 fontsize=14, fontweight="bold", pad=15)
    ax.text(0.5, 1.02, "N-methyl peak coalescence reveals amide rotation barrier",
            transform=ax.transAxes, ha="center", fontsize=10, color="#666666")
    ax.text(0.99, 0.01, "Device-Use | AI Scientist",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=8, color="#999999", style="italic")

    plt.tight_layout()
    fig.savefig(str(output_path), dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _simulate_stream(text, chunk_size=30, delay=0.02):
    """Simulate streaming output for cached responses."""
    import time as t
    for i in range(0, len(text), chunk_size):
        t.sleep(delay)
        yield text[i:i + chunk_size]


def _print_finale(plot_path, brain_used: bool):
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║  Dynamic NMR Analysis Complete                               ║
╚══════════════════════════════════════════════════════════════╝{RESET}

  {CHECK} Processed multi-temperature NMR series
  {CHECK} Generated temperature overlay visualization
  {CHECK} Saved to {BOLD}{plot_path}{RESET}""")

    if brain_used:
        print(f"  {CHECK} AI analyzed conformational dynamics")

    print(f"""
  {BOLD}Why this matters:{RESET}
  {DIM}Traditional DNMR analysis takes hours of manual peak fitting.{RESET}
  {DIM}Device-Use does it in seconds — from raw data to insight.{RESET}
""")


if __name__ == "__main__":
    main()
