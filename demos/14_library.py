#!/usr/bin/env python3
"""Spectral Library — build a reference database and match unknowns.

Processes all TopSpin examdata compounds into a spectral library,
then runs "blind" identification by matching peak fingerprints.
No AI needed — pure signal processing.

Usage:
    python demos/topspin_library.py
"""

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

sys.path.insert(0, str(Path(__file__).parent / "lib"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lib.terminal import banner
from device_use import create_orchestrator
from device_use.instruments.nmr.library import SpectralLibrary
from device_use.orchestrator import Pipeline, PipelineStep


def main():
    banner("NMR Spectral Library", "Fingerprint Matching — build and query reference database")

    # 1. Build library from all available data
    print("  Building spectral library from TopSpin examdata...")
    lib = SpectralLibrary.from_examdata(tolerance_ppm=0.05)
    print(f"  Loaded {len(lib)} reference compounds:\n")
    for i, name in enumerate(lib.list_entries(), 1):
        print(f"    {i:2d}. {name}")

    if len(lib) == 0:
        print("\n  No TopSpin examdata found. Install TopSpin 5.0.0 for full demo.")
        return

    # 2. Process a "query" compound through the orchestrator
    print("\n  Processing query compound...")
    orch = create_orchestrator()
    datasets = orch.call_tool("topspin.list_datasets")

    # Use the first dataset as our "unknown"
    query_ds = datasets[0]
    query_spectrum = orch.call_tool("topspin.process", data_path=query_ds["path"])

    print(f"    Query: {query_ds['sample']} (expno {query_ds.get('expno', '?')})")
    print(f"    Peaks: {len(query_spectrum.peaks)}")
    print(f"    Top peaks: {', '.join(f'{p.ppm:.2f}' for p in sorted(query_spectrum.peaks, key=lambda p: p.intensity, reverse=True)[:5])} ppm")

    # 3. Match against library
    print("\n  Matching against library...\n")
    matches = lib.match(query_spectrum, top_k=5)

    print(f"  {'Rank':<6} {'Compound':<35} {'Score':>7} {'Matched':>9}")
    print(f"  {'-'*60}")
    for i, m in enumerate(matches, 1):
        bar = "█" * int(m.score * 20)
        print(f"  {i:<6} {m.entry.name:<35} {m.score:>6.1%} {m.matched_peaks:>4}/{m.total_peaks:<4} {bar}")

    best = matches[0]
    if best.score > 0.5:
        print(f"\n  Best match: {best.entry.name} ({best.score:.0%} confidence)")
    else:
        print(f"\n  No strong match found (best: {best.entry.name} at {best.score:.0%})")

    # 4. Run as a pipeline with visualization
    print("\n  Running as composable pipeline...\n")

    load_pipeline = Pipeline("load")
    load_pipeline.add_step(PipelineStep(
        name="process",
        tool_name="topspin.process",
        params={"data_path": query_ds["path"]},
    ))

    match_pipeline = Pipeline("match")
    match_pipeline.add_step(PipelineStep(
        name="library_match",
        handler=lambda ctx: lib.match(ctx["process"], top_k=3),
    ))

    full = Pipeline.compose("identify_unknown", load_pipeline, match_pipeline)
    print(full.describe())

    result = orch.run(full)
    print(f"\n{result.summary()}")

    top_matches = result.outputs.get("library_match", [])
    if top_matches:
        print(f"\n  Library match: {top_matches[0].entry.name} ({top_matches[0].score:.0%})")


if __name__ == "__main__":
    main()
