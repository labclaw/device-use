#!/usr/bin/env python3
"""Quickstart — the simplest possible device-use demo.

Run this first. No API key needed, no TopSpin needed, no setup.
Shows the core pattern: register instruments → connect → process → done.

Usage:
    python demos/quickstart.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from device_use.instruments import ControlMode
from device_use.instruments.nmr.adapter import TopSpinAdapter
from device_use.instruments.plate_reader import PlateReaderAdapter
from device_use.orchestrator import Orchestrator


def main():
    print("""
╔════════════════════════════════════════════╗
║  device-use — ROS for Lab Instruments      ║
║  Quickstart Demo                           ║
╚════════════════════════════════════════════╝
""")

    # ── 1. Create orchestrator (the middleware hub) ──────────
    orch = Orchestrator()
    print("  1. Created Orchestrator")

    # ── 2. Register instruments ──────────────────────────────
    nmr = TopSpinAdapter(mode=ControlMode.OFFLINE)
    reader = PlateReaderAdapter(mode=ControlMode.OFFLINE)
    orch.register(nmr)
    orch.register(reader)

    instruments = orch.registry.list_instruments()
    for inst in instruments:
        print(f"  2. Registered: {inst.name} ({inst.vendor}) — {inst.instrument_type}")

    # ── 3. Connect ───────────────────────────────────────────
    results = orch.connect_all()
    for name, ok in results.items():
        print(f"  3. {name}: {'connected' if ok else 'failed'}")

    # ── 4. List available data ───────────────────────────────
    nmr_datasets = orch.call_tool("topspin.list_datasets")
    plate_datasets = orch.call_tool("platereader.list_datasets")
    print(f"\n  Available data:")
    print(f"    NMR datasets:    {len(nmr_datasets)}")
    print(f"    Plate assays:    {len(plate_datasets)}")

    # ── 5. Process NMR spectrum ──────────────────────────────
    first_nmr = nmr_datasets[0]
    spectrum = orch.call_tool("topspin.process", data_path=first_nmr["path"])
    print(f"\n  NMR Spectrum: {spectrum.title}")
    print(f"    Nucleus:    {spectrum.nucleus}")
    print(f"    Frequency:  {spectrum.frequency_mhz:.1f} MHz")
    print(f"    Peaks:      {len(spectrum.peaks)}")

    top3 = sorted(spectrum.peaks, key=lambda p: p.intensity, reverse=True)[:3]
    for p in top3:
        print(f"      δ {p.ppm:.2f} ppm")

    # ── 6. Process plate reader data ─────────────────────────
    reading = orch.call_tool("platereader.process", data_path="ELISA_IL6_plate1")
    print(f"\n  Plate Reader: {reading.protocol}")
    print(f"    Format:     {reading.plate.format.value}-well")
    print(f"    Wavelength: {reading.wavelength_nm} nm")
    a1 = reading.plate.get_well("A1")
    print(f"    Well A1:    OD = {a1.value:.4f}")

    # ── 7. List all tools ────────────────────────────────────
    tools = orch.registry.list_tools()
    print(f"\n  Available tools ({len(tools)}):")
    for tool in tools:
        print(f"    • {tool.name}")

    print("""
╔════════════════════════════════════════════╗
║  That's it! One Orchestrator, any number   ║
║  of instruments, same interface.           ║
║                                            ║
║  Next: python demos/topspin_identify.py    ║
╚════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
