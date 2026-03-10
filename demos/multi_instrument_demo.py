#!/usr/bin/env python3
"""Multi-Instrument Demo — the "ROS for Lab Instruments" vision.

Shows device-use orchestrating TWO different instrument types through
the same BaseInstrument abstraction:

  1. NMR Spectrometer (TopSpin) — chemical structure analysis
  2. Plate Reader (Gen5)         — ELISA / cell viability assays

Both instruments register with the same Orchestrator, share the same
pipeline engine, and connect to the same Cloud Brain (Claude AI).

This is the core value proposition: one middleware controls everything.

Usage:
    python demos/multi_instrument_demo.py
"""

import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from device_use.instruments import ControlMode
from device_use.instruments.nmr.adapter import TopSpinAdapter
from device_use.instruments.plate_reader import PlateReaderAdapter
from device_use.orchestrator import (
    Orchestrator,
    Pipeline,
    PipelineStep,
)


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║        device-use: Multi-Instrument Orchestration           ║
║                                                             ║
║  One middleware → Two instrument types → Same interface     ║
╚══════════════════════════════════════════════════════════════╝
""")

    # ── Phase 1: Create orchestrator and register instruments ─────────
    print("═══ Phase 1: Instrument Registration ═══\n")

    orch = Orchestrator()

    # Log events
    event_icons = {
        "instrument_registered": "🔬",
        "pipeline_start": "🚀",
        "step_start": "⚙️ ",
        "step_end": "✅",
        "pipeline_end": "🏁",
    }
    orch.on_event(lambda e: print(
        f"  {event_icons.get(e.event_type.value, '•')} {e.event_type.value}: "
        f"{e.data.get('instrument', e.data.get('step', e.data.get('pipeline', '')))}"
    ))

    # Register NMR spectrometer
    nmr = TopSpinAdapter(mode=ControlMode.OFFLINE)
    orch.register(nmr)

    # Register plate reader
    reader = PlateReaderAdapter(mode=ControlMode.OFFLINE)
    orch.register(reader)

    # Show what's registered
    instruments = orch.registry.list_instruments()
    tools = orch.registry.list_tools()
    print(f"\n  Registered instruments: {len(instruments)}")
    for inst in instruments:
        print(f"    • {inst.name} ({inst.vendor}) — {inst.instrument_type}")
        print(f"      Modes: {', '.join(m.value for m in inst.supported_modes)}")
    print(f"  Available tools: {len(tools)}")
    for tool in tools:
        print(f"    • {tool.name}")

    # ── Phase 2: Connect all instruments ─────────────────────────────
    print("\n═══ Phase 2: Connect All Instruments ═══\n")

    results = orch.connect_all()
    for name, ok in results.items():
        status = "✓ connected" if ok else "✗ failed"
        print(f"  {name}: {status}")

    # ── Phase 3: NMR Pipeline ────────────────────────────────────────
    print("\n═══ Phase 3: NMR Analysis Pipeline ═══\n")

    nmr_pipeline = Pipeline("nmr_analysis")
    nmr_pipeline.add_step(PipelineStep(
        name="list_nmr",
        tool_name="topspin.list_datasets",
    ))
    nmr_pipeline.add_step(PipelineStep(
        name="process_nmr",
        handler=lambda ctx: _process_nmr_sample(nmr, ctx),
    ))

    nmr_result = orch.run(nmr_pipeline)
    if nmr_result.success:
        spectrum = nmr_result.last_output
        print(f"  NMR: {len(spectrum.peaks)} peaks detected")
        print(f"  Frequency: {spectrum.frequency_mhz:.1f} MHz")
        top = sorted(spectrum.peaks, key=lambda p: p.intensity, reverse=True)[:3]
        for p in top:
            print(f"    δ {p.ppm:.2f} ppm (intensity {p.intensity:.0f})")
    else:
        print(f"  NMR pipeline failed: {nmr_result.steps[-1][1].error}")

    # ── Phase 4: Plate Reader Pipeline ───────────────────────────────
    print("\n═══ Phase 4: Plate Reader Analysis Pipeline ═══\n")

    reader_pipeline = Pipeline("plate_reader_analysis")
    reader_pipeline.add_step(PipelineStep(
        name="list_plates",
        tool_name="platereader.list_datasets",
    ))
    reader_pipeline.add_step(PipelineStep(
        name="read_elisa",
        handler=lambda ctx: _process_plate(reader, "ELISA"),
    ))
    reader_pipeline.add_step(PipelineStep(
        name="read_viability",
        handler=lambda ctx: _process_plate(reader, "CellViability"),
    ))

    reader_result = orch.run(reader_pipeline)
    if reader_result.success:
        # Show ELISA results
        elisa = reader_result.outputs["read_elisa"]
        print(f"  ELISA ({elisa.protocol}):")
        print(f"    Wavelength: {elisa.wavelength_nm} nm")
        print(f"    Wells read: {len(elisa.plate.wells)}")
        std_a1 = elisa.plate.get_well("A1")
        blank = elisa.plate.get_well("A12")
        print(f"    Standard A1: OD={std_a1.value:.4f}")
        print(f"    Blank A12:   OD={blank.value:.4f}")
        print(f"    Signal/noise: {std_a1.value / max(blank.value, 0.001):.1f}x")

        # Show viability results
        viab = reader_result.outputs["read_viability"]
        print(f"\n  Cell Viability ({viab.protocol}):")
        print(f"    Ex/Em: {viab.metadata['excitation_nm']}/{viab.metadata['emission_nm']} nm")
        pos = viab.plate.get_well("A1")
        neg = viab.plate.get_well("A12")
        print(f"    Positive ctrl: {pos.value:.0f} RFU")
        print(f"    Negative ctrl: {neg.value:.0f} RFU")
        print(f"    Z-factor: {_z_factor(viab):.2f}")

        # Generate heatmap plots
        try:
            from device_use.instruments.plate_reader.visualizer import plot_plate_heatmap
            plot_plate_heatmap(elisa, output_path="output/elisa_heatmap.png")
            plot_plate_heatmap(viab, output_path="output/viability_heatmap.png")
            print(f"\n  Plots saved: output/elisa_heatmap.png, output/viability_heatmap.png")
        except Exception:
            pass  # matplotlib not required
    else:
        print(f"  Plate reader pipeline failed: {reader_result.steps[-1][1].error}")

    # ── Phase 5: Cross-Instrument Summary ────────────────────────────
    print("\n═══ Phase 5: Cross-Instrument Summary ═══\n")

    print("  ┌─────────────────────────────────────────────────┐")
    print("  │  INSTRUMENT      TYPE           STATUS          │")
    print("  ├─────────────────────────────────────────────────┤")
    for inst_info in instruments:
        inst_obj = orch.registry.get_instrument(inst_info.name)
        status = "connected" if inst_obj.connected else "offline"
        print(f"  │  {inst_info.name:<16} {inst_info.instrument_type:<14} {status:<16}│")
    print("  └─────────────────────────────────────────────────┘")

    print(f"\n  Pipelines executed: 2")
    print(f"  Total steps run: {len(nmr_result.steps) + len(reader_result.steps)}")
    print(f"  All succeeded: {nmr_result.success and reader_result.success}")

    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                             ║
║  Same BaseInstrument abstraction, same Orchestrator,        ║
║  same Pipeline engine — just different instrument types.    ║
║                                                             ║
║  This is what makes device-use "ROS for Lab Instruments."   ║
║                                                             ║
║  Next: Add YOUR instrument by implementing BaseInstrument.  ║
║                                                             ║
╚══════════════════════════════════════════════════════════════╝
""")


def _process_nmr_sample(nmr, ctx):
    """Process the first NMR dataset."""
    datasets = ctx["list_nmr"]
    if not datasets:
        raise RuntimeError("No NMR datasets found")
    first = datasets[0]
    data_path = first.get("path", f"{first.get('sample', 'unknown')}/{first.get('expno', 1)}")
    return nmr.process(data_path)


def _process_plate(reader, name_hint):
    """Process a plate reader dataset."""
    return reader.process(name_hint)


def _z_factor(reading):
    """Calculate Z-factor (assay quality metric) from positive/negative controls."""
    pos_wells = [w for w in reading.plate.wells if w.col <= 2]
    neg_wells = [w for w in reading.plate.wells if w.col >= 11]

    pos_vals = [w.value for w in pos_wells]
    neg_vals = [w.value for w in neg_wells]

    pos_mean = statistics.mean(pos_vals)
    neg_mean = statistics.mean(neg_vals)
    pos_std = statistics.stdev(pos_vals)
    neg_std = statistics.stdev(neg_vals)

    separation = abs(pos_mean - neg_mean)
    if separation == 0:
        return float("-inf")
    return 1 - 3 * (pos_std + neg_std) / separation


if __name__ == "__main__":
    main()
