#!/usr/bin/env python3
"""Streaming Demo — real-time event-driven data processing.

Shows the key differentiator of device-use as middleware:
events stream in real-time as instruments process data,
enabling live dashboards, audit trails, and reactive workflows.

This demo runs parallel pipelines and streams events with timing,
simulating what a production lab monitoring system would look like.

Usage:
    python demos/streaming_demo.py
"""

import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lib.terminal import RESET
from device_use.instruments import ControlMode
from device_use.instruments.nmr.adapter import TopSpinAdapter
from device_use.instruments.plate_reader import PlateReaderAdapter
from device_use.orchestrator import (
    Event,
    EventType,
    Orchestrator,
    Pipeline,
    PipelineStep,
)

# ── Event styling ────────────────────────────────────────────
ICONS = {
    EventType.INSTRUMENT_REGISTERED: "📡",
    EventType.INSTRUMENT_CONNECTED: "🔗",
    EventType.PIPELINE_START: "🚀",
    EventType.PIPELINE_END: "🏁",
    EventType.STEP_START: "⚙️ ",
    EventType.STEP_END: "✅",
    EventType.STEP_ERROR: "❌",
    EventType.TOOL_CALLED: "🔧",
}

COLORS = {
    EventType.PIPELINE_START: "\033[1;36m",  # bold cyan
    EventType.PIPELINE_END: "\033[1;32m",    # bold green
    EventType.STEP_START: "\033[0;33m",      # yellow
    EventType.STEP_END: "\033[0;32m",        # green
    EventType.STEP_ERROR: "\033[1;31m",      # bold red
    EventType.TOOL_CALLED: "\033[0;35m",     # magenta
    EventType.INSTRUMENT_REGISTERED: "\033[0;34m",  # blue
    EventType.INSTRUMENT_CONNECTED: "\033[0;34m",
}


def format_event(event: Event, t0: float) -> str:
    """Format an event as a colored log line."""
    elapsed = event.timestamp - t0
    icon = ICONS.get(event.event_type, "•")
    color = COLORS.get(event.event_type, "")

    # Build detail string from event data
    parts = []
    for key in ("pipeline", "step", "instrument", "tool"):
        if key in event.data:
            parts.append(event.data[key])

    if "duration_ms" in event.data:
        parts.append(f"{event.data['duration_ms']:.0f}ms")
    if "error" in event.data:
        parts.append(f"ERROR: {event.data['error']}")
    if "success" in event.data:
        parts.append("OK" if event.data["success"] else "FAILED")

    detail = " → ".join(parts)
    return f"  {color}[{elapsed:6.3f}s] {icon} {event.event_type.value:25s} {detail}{RESET}"


def main():
    from lib.terminal import banner
    banner("Real-Time Event Stream",
           "Watch events flow as instruments process data in real-time")

    t0 = time.time()
    events: list[Event] = []

    # ── Create orchestrator with event stream ────────────────
    orch = Orchestrator()

    def on_event(e: Event):
        events.append(e)
        print(format_event(e, t0))

    orch.on_event(on_event)

    # ── Register instruments (events fire here) ──────────────
    nmr = TopSpinAdapter(mode=ControlMode.OFFLINE)
    reader = PlateReaderAdapter(mode=ControlMode.OFFLINE)
    orch.register(nmr)
    orch.register(reader)
    orch.connect_all()

    # ── Pipeline 1: NMR multi-sample processing ──────────────
    print(f"\n{'─' * 60}")
    print("  Pipeline 1: NMR Multi-Sample Processing")
    print(f"{'─' * 60}\n")

    nmr_pipeline = Pipeline("nmr_multi_sample")

    # Step 1: List all datasets
    nmr_pipeline.add_step(PipelineStep(
        name="discover",
        description="Discover available NMR datasets",
        tool_name="topspin.list_datasets",
    ))

    # Step 2: Process first 3 samples
    def process_batch(ctx):
        datasets = ctx["discover"][:3]
        results = []
        for ds in datasets:
            spectrum = nmr.process(ds["path"])
            top_peak = max(spectrum.peaks, key=lambda p: p.intensity).ppm if spectrum.peaks else None
            results.append({
                "sample": ds.get("sample", "unknown"),
                "peaks": len(spectrum.peaks),
                "frequency_mhz": spectrum.frequency_mhz,
                "top_peak_ppm": top_peak,
            })
        return results

    nmr_pipeline.add_step(PipelineStep(
        name="process_batch",
        description="Process first 3 NMR samples",
        handler=process_batch,
    ))

    # Step 3: Summary statistics
    def nmr_summary(ctx):
        batch = ctx["process_batch"]
        total_peaks = sum(r["peaks"] for r in batch)
        return {
            "samples_processed": len(batch),
            "total_peaks": total_peaks,
            "avg_peaks": total_peaks / len(batch),
            "samples": batch,
        }

    nmr_pipeline.add_step(PipelineStep(
        name="summarize",
        description="Compute batch statistics",
        handler=nmr_summary,
    ))

    nmr_result = orch.run(nmr_pipeline)

    # ── Pipeline 2: Plate Reader QC ──────────────────────────
    print(f"\n{'─' * 60}")
    print("  Pipeline 2: Plate Reader Quality Control")
    print(f"{'─' * 60}\n")

    qc_pipeline = Pipeline("plate_reader_qc")

    # Step 1: Process ELISA
    qc_pipeline.add_step(PipelineStep(
        name="elisa",
        description="Process ELISA plate",
        handler=lambda ctx: reader.process("ELISA_IL6_plate1"),
    ))

    # Step 2: Process viability
    qc_pipeline.add_step(PipelineStep(
        name="viability",
        description="Process cell viability plate",
        handler=lambda ctx: reader.process("CellViability_DrugScreen"),
    ))

    # Step 3: QC metrics
    def compute_qc(ctx):
        elisa = ctx["elisa"]
        viability = ctx["viability"]

        # ELISA signal/noise
        std_wells = [w for w in elisa.plate.wells if w.col <= 2]
        blank_wells = [w for w in elisa.plate.wells if w.col >= 11]
        snr = statistics.mean([w.value for w in std_wells]) / max(
            statistics.mean([w.value for w in blank_wells]), 0.001
        )

        # Viability Z-factor
        pos = [w.value for w in viability.plate.wells if w.col <= 2]
        neg = [w.value for w in viability.plate.wells if w.col >= 11]
        separation = abs(statistics.mean(pos) - statistics.mean(neg))
        z = 1 - 3 * (statistics.stdev(pos) + statistics.stdev(neg)) / separation if separation > 0 else float("-inf")

        return {
            "elisa_snr": round(snr, 1),
            "viability_z_factor": round(z, 3),
            "elisa_pass": snr > 3.0,
            "viability_pass": z > 0.5,
            "all_pass": snr > 3.0 and z > 0.5,
        }

    qc_pipeline.add_step(PipelineStep(
        name="qc_check",
        description="Compute quality control metrics",
        handler=compute_qc,
    ))

    qc_result = orch.run(qc_pipeline)

    # ── Event Summary ────────────────────────────────────────
    dt = time.time() - t0
    print(f"\n{'═' * 60}")
    print("  EVENT STREAM SUMMARY")
    print(f"{'═' * 60}")

    # Count by type
    from collections import Counter
    counts = Counter(e.event_type.value for e in events)
    for etype, count in sorted(counts.items()):
        print(f"    {etype:30s} {count:3d}")

    print(f"\n    Total events:    {len(events)}")
    print(f"    Total time:      {dt:.2f}s")
    print(f"    Pipelines:       2 ({'all passed' if nmr_result.success and qc_result.success else 'FAILURES'})")

    # Show pipeline results
    if nmr_result.success:
        summary = nmr_result.last_output
        print(f"\n    NMR: {summary['samples_processed']} samples, {summary['total_peaks']} peaks")

    if qc_result.success:
        qc = qc_result.last_output
        print(f"    ELISA S/N: {qc['elisa_snr']}x {'PASS' if qc['elisa_pass'] else 'FAIL'}")
        print(f"    Viability Z: {qc['viability_z_factor']} {'PASS' if qc['viability_pass'] else 'FAIL'}")

    from lib.terminal import finale
    finale([
        "Every event is capturable — feed to dashboards, audit logs, or AI agents",
        "This is what makes device-use middleware, not just a script",
    ])


if __name__ == "__main__":
    main()
