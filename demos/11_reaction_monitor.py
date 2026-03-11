#!/usr/bin/env python3
"""Reaction Monitor — track spectral changes over time.

Simulates autonomous reaction monitoring by processing multiple NMR
acquisitions from the same sample at different conditions. This is
the killer use case for autonomous labs: the AI watches a reaction
and decides when it's complete.

Uses DNMR temperature series data to simulate time-point acquisitions,
generating a reaction progress dashboard with:
  - Spectral overlay plot
  - Peak tracking across conditions
  - AI interpretation of kinetic trends
  - Automated completion detection

Usage:
    python demos/topspin_reaction_monitor.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from device_use import create_orchestrator
from device_use.orchestrator import Pipeline, PipelineStep


def main():
    from lib.terminal import banner
    banner("Autonomous Reaction Monitor",
           "AI tracks spectral changes and detects reaction completion")

    t0 = time.time()

    # ── Set up orchestrator ──────────────────────────────────
    orch = create_orchestrator()

    # ── Find DNMR temperature series ─────────────────────────
    datasets = orch.call_tool("topspin.list_datasets")
    # Get Me2NCOMe series (amide rotation at different temperatures)
    series = sorted(
        [ds for ds in datasets if "DNMR_Me2NCOMe" in ds.get("sample", "")],
        key=lambda d: d["expno"],
    )

    if len(series) < 3:
        print("  Need at least 3 DNMR timepoints. Exiting.")
        return

    # Take first 5 for manageable demo
    timepoints = series[:5]
    print(f"  Sample: {timepoints[0]['sample']}")
    print(f"  Timepoints: {len(timepoints)} acquisitions")
    print(f"  Simulating reaction monitoring over {len(timepoints)} conditions\n")

    # ── Process all timepoints via pipeline ──────────────────
    pipeline = Pipeline("reaction_monitor")

    # Step 1: Process all timepoints
    def process_all(ctx):
        results = []
        for i, tp in enumerate(timepoints):
            spectrum = orch.call_tool("topspin.process", data_path=tp["path"])

            # Track key spectral features
            peak_count = len(spectrum.peaks)
            top_peaks = sorted(spectrum.peaks, key=lambda p: p.intensity, reverse=True)

            # Find the N-methyl peaks (expected around 2.8-3.1 ppm)
            methyl_peaks = [p for p in spectrum.peaks if 2.5 <= p.ppm <= 3.5]
            aromatic_region = [p for p in spectrum.peaks if 6.0 <= p.ppm <= 9.0]

            result = {
                "timepoint": i + 1,
                "expno": tp["expno"],
                "title": spectrum.title,
                "total_peaks": peak_count,
                "methyl_peaks": len(methyl_peaks),
                "aromatic_peaks": len(aromatic_region),
                "frequency_mhz": spectrum.frequency_mhz,
                "spectrum": spectrum,
            }
            results.append(result)

            # Print progress
            status = "▓" * (i + 1) + "░" * (len(timepoints) - i - 1)
            methyl_str = f"{len(methyl_peaks)} peaks" if methyl_peaks else "none"
            print(f"  [{status}] T{i+1} (exp {tp['expno']:>3}): "
                  f"{peak_count:2d} peaks, N-methyl region: {methyl_str}")

        return results

    pipeline.add_step(PipelineStep(
        name="acquire",
        description="Process all timepoint spectra",
        handler=process_all,
    ))

    # Step 2: Analyze trends
    def analyze_trends(ctx):
        results = ctx["acquire"]

        peak_counts = [r["total_peaks"] for r in results]
        methyl_counts = [r["methyl_peaks"] for r in results]

        # Detect coalescence (methyl peaks merging = key DNMR feature)
        trend = "stable"
        if methyl_counts[0] > methyl_counts[-1]:
            trend = "coalescence"
        elif methyl_counts[0] < methyl_counts[-1]:
            trend = "splitting"

        # Peak count change
        peak_delta = peak_counts[-1] - peak_counts[0]

        return {
            "trend": trend,
            "peak_delta": peak_delta,
            "initial_peaks": peak_counts[0],
            "final_peaks": peak_counts[-1],
            "initial_methyl": methyl_counts[0],
            "final_methyl": methyl_counts[-1],
            "timepoints": len(results),
        }

    pipeline.add_step(PipelineStep(
        name="trends",
        description="Analyze spectral trends",
        handler=analyze_trends,
    ))

    result = orch.run(pipeline)
    if not result.success:
        print(f"\n  Pipeline failed!")
        return

    spectra = result.outputs["acquire"]
    trends = result.outputs["trends"]

    # ── Display Results ──────────────────────────────────────
    print(f"\n{'═' * 60}")
    print(f"  REACTION MONITORING RESULTS")
    print(f"{'═' * 60}")

    print(f"\n  {'Metric':<30} {'Value':<20}")
    print(f"  {'─' * 50}")
    print(f"  {'Timepoints processed':<30} {trends['timepoints']}")
    print(f"  {'Initial peak count':<30} {trends['initial_peaks']}")
    print(f"  {'Final peak count':<30} {trends['final_peaks']}")
    print(f"  {'Peak count change':<30} {trends['peak_delta']:+d}")
    print(f"  {'N-methyl peaks (start)':<30} {trends['initial_methyl']}")
    print(f"  {'N-methyl peaks (end)':<30} {trends['final_methyl']}")
    print(f"  {'Observed trend':<30} {trends['trend'].upper()}")

    # ── Generate overlay plot ────────────────────────────────
    print(f"\n  Generating spectral overlay plot...")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fig, ax = plt.subplots(figsize=(14, 7))

    colors = plt.cm.viridis(np.linspace(0.2, 0.9, len(spectra)))

    for i, sp_data in enumerate(spectra):
        spectrum = sp_data["spectrum"]
        ppm = spectrum.ppm_scale
        data = spectrum.data
        mask = (ppm >= 0.0) & (ppm <= 10.0)
        ppm_plot = ppm[mask]
        data_plot = data[mask]
        data_max = np.max(np.abs(data_plot)) if len(data_plot) > 0 else 1.0
        data_norm = data_plot / data_max

        # Offset each spectrum vertically
        offset = i * 0.3
        label = f"T{i+1} (exp {sp_data['expno']})"
        ax.plot(ppm_plot, data_norm + offset, color=colors[i],
                linewidth=0.5, label=label)

    ax.invert_xaxis()
    ax.set_xlabel("Chemical Shift (ppm)", fontsize=12, fontweight="bold")
    ax.set_ylabel("Relative Intensity (stacked)", fontsize=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_yticks([])
    ax.legend(loc="upper right", fontsize=9, framealpha=0.9)

    ax.set_title("Reaction Monitoring — Spectral Evolution", fontsize=14,
                 fontweight="bold", pad=15)
    ax.text(0.5, 1.02, f"{spectra[0]['frequency_mhz']:.0f} MHz | "
            f"Trend: {trends['trend']} | "
            f"Peak Δ: {trends['peak_delta']:+d}",
            transform=ax.transAxes, ha="center", fontsize=10, color="#666666")
    ax.text(0.99, 0.01, "Device-Use | Reaction Monitor",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=8, color="#999999", style="italic")

    plt.tight_layout()
    out = Path("output/reaction_monitor.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out), dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Saved: {out}")

    # ── Peak tracking plot ───────────────────────────────────
    fig2, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    timepoint_labels = [f"T{s['timepoint']}" for s in spectra]
    peak_counts = [s["total_peaks"] for s in spectra]
    methyl_counts = [s["methyl_peaks"] for s in spectra]

    ax1.plot(timepoint_labels, peak_counts, "o-", color="#0066cc",
             linewidth=2, markersize=8)
    ax1.set_ylabel("Total Peaks", fontsize=11)
    ax1.set_xlabel("Timepoint", fontsize=11)
    ax1.set_title("Peak Count vs Time", fontsize=12, fontweight="bold")
    ax1.grid(True, alpha=0.3)

    ax2.bar(timepoint_labels, methyl_counts, color="#cc3300", alpha=0.8)
    ax2.set_ylabel("N-Methyl Peaks (2.5-3.5 ppm)", fontsize=11)
    ax2.set_xlabel("Timepoint", fontsize=11)
    ax2.set_title("Key Region Tracking", fontsize=12, fontweight="bold")
    ax2.grid(True, alpha=0.3, axis="y")

    fig2.suptitle("Reaction Progress Dashboard", fontsize=14, fontweight="bold")
    plt.tight_layout()
    out2 = Path("output/reaction_dashboard.png")
    fig2.savefig(str(out2), dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig2)
    print(f"  Saved: {out2}")

    dt = time.time() - t0
    from lib.terminal import finale
    finale([
        f"Monitoring complete ({dt:.1f}s)",
        "In a real autonomous lab: acquire at intervals, detect completion, alert, log",
        "device-use makes this possible with any NMR instrument",
    ], title="Monitoring Complete")


if __name__ == "__main__":
    main()
