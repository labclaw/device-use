#!/usr/bin/env python3
"""Quickstart — the simplest possible device-use demo.

Run this first. No API key needed, no TopSpin needed, no setup.
Shows the core pattern: one line to create a fully-wired orchestrator.

Usage:
    python demos/quickstart.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from device_use import create_orchestrator


def main():
    print("""
╔════════════════════════════════════════════╗
║  device-use — ROS for Lab Instruments      ║
║  Quickstart Demo                           ║
╚════════════════════════════════════════════╝
""")

    # ── 1. One line: auto-discover and connect all instruments ─
    orch = create_orchestrator()
    instruments = orch.registry.list_instruments()
    tools = orch.registry.list_tools()
    print(f"  1. Created Orchestrator: {len(instruments)} instruments, {len(tools)} tools")
    for inst in instruments:
        print(f"     • {inst.name} ({inst.vendor}) — {inst.instrument_type}")

    # ── 2. List available data ───────────────────────────────
    nmr_datasets = orch.call_tool("topspin.list_datasets")
    plate_datasets = orch.call_tool("platereader.list_datasets")
    print(f"\n  2. Available data:")
    print(f"     NMR datasets:    {len(nmr_datasets)}")
    print(f"     Plate assays:    {len(plate_datasets)}")

    # ── 3. Process NMR spectrum ──────────────────────────────
    first_nmr = nmr_datasets[0]
    spectrum = orch.call_tool("topspin.process", data_path=first_nmr["path"])
    print(f"\n  3. NMR Spectrum: {spectrum.title}")
    print(f"     Nucleus:    {spectrum.nucleus}")
    print(f"     Frequency:  {spectrum.frequency_mhz:.1f} MHz")
    print(f"     Peaks:      {len(spectrum.peaks)}")

    top3 = sorted(spectrum.peaks, key=lambda p: p.intensity, reverse=True)[:3]
    for p in top3:
        print(f"       δ {p.ppm:.2f} ppm")

    # ── 4. Process plate reader data ─────────────────────────
    reading = orch.call_tool("platereader.process", data_path="ELISA_IL6_plate1")
    print(f"\n  4. Plate Reader: {reading.protocol}")
    print(f"     Format:     {reading.plate.format.value}-well")
    print(f"     Wavelength: {reading.wavelength_nm} nm")
    a1 = reading.plate.get_well("A1")
    print(f"     Well A1:    OD = {a1.value:.4f}")

    print("""
╔════════════════════════════════════════════╗
║  That's it! One function call sets up      ║
║  the entire middleware. Add your own        ║
║  instrument by implementing BaseInstrument.║
║                                            ║
║  Next: python demos/topspin_identify.py    ║
╚════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
