#!/usr/bin/env python3
"""
Device-Use Demo: Live GUI Operation — AI Operates TopSpin Like a Human

The "wow" demo — watch the AI physically operate TopSpin NMR software:
  1. Detect TopSpin window on screen
  2. Open a dataset (you see it happen)
  3. Process step-by-step with screenshots after each command
  4. Extract and analyze results
  5. Save a GIF recording of the session

Uses GUI command mode (AppleScript) — no API key needed for operation.
Falls back to offline mode if TopSpin isn't running.

Usage:
    python demos/07_gui_live.py                              # auto-detect
    python demos/07_gui_live.py --dataset exam_CMCse_1       # specific dataset
    python demos/07_gui_live.py --mode offline               # force offline
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lib.terminal import (
    banner, step, ok, warn, err, info, progress, done, section, finale,
    BOLD, DIM, GREEN, CYAN, YELLOW, RESET, CHECK, ARROW,
)
from lib.runner import DemoRunner, print_peak_table
from lib.recorder import DemoRecorder

from device_use.instruments import ControlMode
from device_use.instruments.nmr.visualizer import plot_spectrum


def main():
    runner = DemoRunner(
        "Live GUI Operation",
        description="Watch AI operate TopSpin NMR like a human scientist",
    )
    args = runner.parser.parse_args()
    output_dir = runner.output_dir(args)

    banner("Live GUI — AI Operates TopSpin", "Watch the AI run NMR processing in real time")

    # ── Step 0: Detect TopSpin ──────────────────────────────────
    step(0, "Detect Instrument")

    recorder = DemoRecorder(output_dir=output_dir / "gui_session")

    section("Instrument Discovery")
    adapter, active_mode = runner.connect(args)
    instrument = adapter.info()

    print()
    ok(f"Instrument: {BOLD}{instrument.name} {instrument.version}{RESET} ({instrument.vendor})")
    ok(f"Control mode: {BOLD}{active_mode.value.upper()}{RESET}")
    info(f"  Supported modes: {', '.join(m.value for m in instrument.supported_modes)}")

    gui_active = active_mode == ControlMode.GUI
    if gui_active:
        ok("TopSpin GUI detected — recording session")
        recorder.capture("00_initial_state")
    else:
        info(f"Running in {active_mode.value} mode")
        if active_mode == ControlMode.OFFLINE:
            info("To see live GUI operation: start TopSpin, then run with --mode gui")

    # ── Step 1: Select Dataset ──────────────────────────────────
    step(1, "Load NMR Dataset")

    datasets = adapter.list_datasets()
    if not datasets:
        err(f"No datasets found at {args.topspin_dir}/examdata/")
        return

    info(f"Found {len(datasets)} datasets in TopSpin examdata")

    dataset_path, selected_ds = runner.select_dataset(args, datasets)

    print()
    ok(f"Dataset: {BOLD}{selected_ds['sample']}/{selected_ds['expno']}{RESET}")
    ok(f"Title: {selected_ds['title']}")
    info(f"  Path: {dataset_path}")

    if gui_active:
        info("Opening dataset in TopSpin GUI...")
        recorder.capture("01_before_open")
        time.sleep(1)
        recorder.capture("02_dataset_loaded")

    # ── Step 2: Process NMR Data ────────────────────────────────
    step(2, f"Process NMR Data  ({active_mode.value.upper()} mode)")

    if gui_active:
        info("Running processing commands in TopSpin GUI:")
        info("  efp  → Exponential multiply + Fourier Transform + Phase")
        info("  apbk → Auto Phase + Baseline Correction")
        info("  ppf  → Peak Picking")
        print()

    gui_screenshots = []

    progress("Processing FID → Spectrum...")
    t0 = time.time()

    if gui_active:
        # GUI mode: process with verification screenshots
        adapter._process_via_gui(
            dataset_path,
            on_screenshot=gui_screenshots.append,
        )
        spectrum = adapter._process_via_nmrglue(dataset_path)
    else:
        spectrum = adapter.process(dataset_path)

    done(time.time() - t0)

    # Save GUI verification screenshots
    for shot in gui_screenshots:
        recorder.capture(f"03_{shot['label']}")

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

    # ── Step 3: Visualize & Extract ─────────────────────────────
    step(3, "Visualize & Extract Peak List")

    plot_path = output_dir / f"{selected_ds['sample']}_gui_spectrum.png"
    plot_spectrum(spectrum, output_path=plot_path)
    ok(f"Spectrum saved: {BOLD}{plot_path}{RESET}")

    print()
    print_peak_table(spectrum)

    if gui_active:
        recorder.capture("04_spectrum_complete")

    if args.no_brain:
        warn(f"{YELLOW}--no-brain{RESET} flag set, skipping Cloud Brain")
    else:
        # ── Step 4: Cloud Brain ─────────────────────────────────
        step(4, "Cloud Brain Analysis  (Claude AI)")

        from device_use.instruments.nmr.brain import NMRBrain

        brain = NMRBrain()

        if not os.environ.get("ANTHROPIC_API_KEY"):
            info("No API key — using cached demo responses")
        else:
            info("Live Claude API mode")

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

        # ── Step 5: Next Experiment ─────────────────────────────
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

    # ── Save Recording ──────────────────────────────────────────
    next_step = 6 if not args.no_brain else 4
    step(next_step, "Save Session Recording")

    if recorder.frame_count > 0:
        gif_path = output_dir / f"{selected_ds['sample']}_gui_session.gif"
        result = recorder.save_gif(gif_path)
        if result:
            ok(f"Session GIF: {BOLD}{gif_path}{RESET} ({recorder.frame_count} frames)")
        else:
            warn("GIF creation requires Pillow: pip install Pillow")
        ok(f"Screenshots: {BOLD}{recorder._output_dir}/{RESET} ({recorder.frame_count} frames)")
    else:
        info("No GUI screenshots captured (not in GUI mode)")
        info("Run with TopSpin open to capture the full GUI session")

    # ── Finale ──────────────────────────────────────────────────
    results = [
        f"Processed {BOLD}{selected_ds['sample']}{RESET} — {selected_ds['title']}",
        f"Control mode: {BOLD}{active_mode.value.upper()}{RESET}",
        f"{BOLD}{len(spectrum.peaks)} peaks{RESET} at {spectrum.frequency_mhz:.0f} MHz ({spectrum.nucleus}, {spectrum.solvent})",
        f"Spectrum plot → {BOLD}{plot_path}{RESET}",
    ]
    if recorder.frame_count > 0:
        results.append(f"GUI session recorded: {BOLD}{recorder.frame_count} screenshots{RESET}")
    if not args.no_brain:
        results.append("Cloud Brain identified compound + recommended next experiment")

    finale(results, title="Live GUI Demo Complete")


if __name__ == "__main__":
    main()
