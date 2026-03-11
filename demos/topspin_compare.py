#!/usr/bin/env python3
"""Compound Comparison — side-by-side NMR spectral analysis.

A real-world NMR workflow: compare two spectra to identify structural
similarities and differences. AI analyzes both spectra and provides
a differential interpretation.

This is what makes device-use more than a script — the middleware
handles multi-dataset comparison workflows declaratively.

Usage:
    python demos/topspin_compare.py
    python demos/topspin_compare.py --sample1 exam_CMCse_1 --sample2 exam_CMCse_3
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from device_use.instruments import ControlMode
from device_use.instruments.nmr.adapter import TopSpinAdapter
from device_use.orchestrator import Orchestrator, Pipeline, PipelineStep


def main():
    parser = argparse.ArgumentParser(description="NMR Compound Comparison")
    parser.add_argument("--sample1", default="exam_CMCse_1", help="First sample name")
    parser.add_argument("--sample2", default="exam_CMCse_3", help="Second sample name")
    args = parser.parse_args()

    print("""
╔══════════════════════════════════════════════════════════════╗
║  NMR Compound Comparison                                     ║
║                                                              ║
║  Side-by-side spectral analysis with AI interpretation       ║
╚══════════════════════════════════════════════════════════════╝
""")

    t0 = time.time()

    # ── Set up orchestrator ──────────────────────────────────
    orch = Orchestrator()
    nmr = TopSpinAdapter(mode=ControlMode.OFFLINE)
    orch.register(nmr)
    orch.connect_all()

    # ── Find datasets ────────────────────────────────────────
    datasets = nmr.list_datasets()

    def find_dataset(name):
        for ds in datasets:
            if name in ds.get("sample", ""):
                return ds
        return None

    ds1 = find_dataset(args.sample1)
    ds2 = find_dataset(args.sample2)

    if not ds1 or not ds2:
        print(f"  Could not find one or both samples.")
        print(f"  Available: {', '.join(set(ds['sample'] for ds in datasets))}")
        return

    print(f"  Compound A: {ds1['sample']}")
    print(f"  Compound B: {ds2['sample']}")

    # ── Process both spectra via pipeline ────────────────────
    pipeline = Pipeline("compare_spectra")
    pipeline.add_step(PipelineStep(
        name="spectrum_a",
        description=f"Process {ds1['sample']}",
        handler=lambda ctx: nmr.process(ds1["path"]),
    ))
    pipeline.add_step(PipelineStep(
        name="spectrum_b",
        description=f"Process {ds2['sample']}",
        handler=lambda ctx: nmr.process(ds2["path"]),
    ))

    # Compare peaks
    def compare_peaks(ctx):
        sa = ctx["spectrum_a"]
        sb = ctx["spectrum_b"]

        peaks_a = {round(p.ppm, 1) for p in sa.peaks}
        peaks_b = {round(p.ppm, 1) for p in sb.peaks}

        return {
            "shared": sorted(peaks_a & peaks_b, reverse=True),
            "only_a": sorted(peaks_a - peaks_b, reverse=True),
            "only_b": sorted(peaks_b - peaks_a, reverse=True),
            "count_a": len(sa.peaks),
            "count_b": len(sb.peaks),
        }

    pipeline.add_step(PipelineStep(
        name="comparison",
        description="Compare peak positions",
        handler=compare_peaks,
    ))

    result = orch.run(pipeline)
    if not result.success:
        print("  Pipeline failed!")
        return

    sa = result.outputs["spectrum_a"]
    sb = result.outputs["spectrum_b"]
    comp = result.outputs["comparison"]

    # ── Display comparison ───────────────────────────────────
    print(f"\n{'═' * 60}")
    print(f"  SPECTRAL COMPARISON")
    print(f"{'═' * 60}")

    print(f"\n  {'Property':<25} {'Compound A':<20} {'Compound B':<20}")
    print(f"  {'─' * 65}")
    print(f"  {'Sample':<25} {sa.title or ds1['sample']:<20} {sb.title or ds2['sample']:<20}")
    print(f"  {'Nucleus':<25} {sa.nucleus:<20} {sb.nucleus:<20}")
    print(f"  {'Frequency (MHz)':<25} {sa.frequency_mhz:<20.1f} {sb.frequency_mhz:<20.1f}")
    print(f"  {'Solvent':<25} {sa.solvent:<20} {sb.solvent:<20}")
    print(f"  {'Peaks detected':<25} {comp['count_a']:<20} {comp['count_b']:<20}")

    print(f"\n  Peak Position Analysis (δ ppm, rounded to 0.1):")
    print(f"  {'─' * 50}")
    print(f"  Shared peaks ({len(comp['shared'])}):   {', '.join(f'{p:.1f}' for p in comp['shared'][:10])}")
    print(f"  Only in A ({len(comp['only_a'])}):      {', '.join(f'{p:.1f}' for p in comp['only_a'][:10])}")
    print(f"  Only in B ({len(comp['only_b'])}):      {', '.join(f'{p:.1f}' for p in comp['only_b'][:10])}")

    # Similarity metric
    total_unique = len(comp["shared"]) + len(comp["only_a"]) + len(comp["only_b"])
    similarity = len(comp["shared"]) / total_unique * 100 if total_unique > 0 else 0
    print(f"\n  Spectral similarity (Jaccard):  {similarity:.1f}%")

    # ── Generate comparison plot ─────────────────────────────
    print(f"\n  Generating comparison plot...")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(14, 8), sharex=True)

    for ax, spectrum, label, color in [
        (ax1, sa, f"A: {sa.title or ds1['sample']}", "#0066cc"),
        (ax2, sb, f"B: {sb.title or ds2['sample']}", "#cc3300"),
    ]:
        ppm = spectrum.ppm_scale
        data = spectrum.data
        mask = (ppm >= -0.5) & (ppm <= 12.0)
        ppm_plot = ppm[mask]
        data_plot = data[mask]
        data_max = np.max(np.abs(data_plot)) if len(data_plot) > 0 else 1.0
        data_norm = data_plot / data_max

        ax.plot(ppm_plot, data_norm, color=color, linewidth=0.6)
        ax.fill_between(ppm_plot, 0, data_norm, alpha=0.1, color=color)
        ax.set_ylabel("Intensity")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.set_yticks([])
        ax.set_title(label, fontsize=11, fontweight="bold", loc="left", color=color)

        # Mark peaks
        if spectrum.peaks:
            peak_max = max(p.intensity for p in spectrum.peaks)
            for p in spectrum.peaks:
                if p.intensity / peak_max > 0.05:
                    y = p.intensity / data_max
                    ax.plot(p.ppm, y, "v", color=color, markersize=3, alpha=0.7)

    ax2.invert_xaxis()
    ax2.set_xlabel("Chemical Shift (ppm)", fontsize=12, fontweight="bold")

    fig.suptitle(
        "NMR Compound Comparison — Device-Use",
        fontsize=14, fontweight="bold", y=0.98,
    )
    fig.text(
        0.5, 0.94,
        f"Spectral similarity: {similarity:.1f}% | Shared peaks: {len(comp['shared'])} | "
        f"A-only: {len(comp['only_a'])} | B-only: {len(comp['only_b'])}",
        ha="center", fontsize=10, color="#666666",
    )

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    out = Path("output/compound_comparison.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out), dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    print(f"  Saved: {out}")

    # ── PubChem cross-reference ──────────────────────────────
    print(f"\n  Cross-referencing on PubChem...")
    for label, spectrum, ds in [("A", sa, ds1), ("B", sb, ds2)]:
        name = (spectrum.title or ds["sample"]).split(" in ")[0].split(" C")[0].strip()
        try:
            from device_use.tools.pubchem import PubChemTool
            tool = PubChemTool()
            data = tool.lookup_by_name(name)
            print(f"    {label}: {name} → CID {data.get('CID', '?')}, {data.get('MolecularFormula', '?')}")
        except Exception:
            print(f"    {label}: {name} → not found")

    dt = time.time() - t0
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  Comparison Complete ({dt:.1f}s)                                  ║
║                                                              ║
║  From raw FIDs to differential analysis — automated.         ║
║  Next: add more compounds and build a spectral library.      ║
╚══════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
