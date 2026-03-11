"""Shared demo runner — standard argparse, connection, dataset selection."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

# Ensure demos/lib and src/ are importable
_lib_dir = Path(__file__).parent
_demos_dir = _lib_dir.parent
_src_dir = _demos_dir.parent / "src"
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

from lib.terminal import BOLD, DIM, RESET, CHECK, ARROW, ok, err, info, section

from device_use.instruments import ControlMode
from device_use.instruments.nmr.adapter import TopSpinAdapter
from device_use.instruments.nmr.processor import NMRSpectrum


class DemoRunner:
    """Standard demo runner with shared CLI arguments."""

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.parser = argparse.ArgumentParser(
            description=description or f"Device-Use Demo: {name}",
            formatter_class=argparse.RawDescriptionHelpFormatter,
        )
        self._add_standard_args()

    def _add_standard_args(self) -> None:
        self.parser.add_argument(
            "--mode", type=str, default="auto",
            choices=["auto", "api", "gui", "offline"],
            help="Control mode: auto tries API→GUI→Offline",
        )
        self.parser.add_argument("--dataset", type=str, help="Dataset name or title keyword")
        self.parser.add_argument("--expno", type=int, default=1, help="Experiment number")
        self.parser.add_argument("--formula", type=str, help="Molecular formula")
        self.parser.add_argument("--topspin-dir", type=str, default="/opt/topspin5.0.0")
        self.parser.add_argument("--no-brain", action="store_true", help="Skip AI analysis")
        self.parser.add_argument("--output", type=str, default="output", help="Output directory")

    def connect(self, args: argparse.Namespace) -> tuple[TopSpinAdapter, ControlMode]:
        """Connect to TopSpin using the requested mode, with auto-fallback."""
        if args.mode == "auto":
            for try_mode in [ControlMode.API, ControlMode.GUI, ControlMode.OFFLINE]:
                info(f"  Trying {try_mode.value.upper()} mode...")
                adapter = TopSpinAdapter(topspin_dir=args.topspin_dir, mode=try_mode)
                if adapter.connect():
                    return adapter, try_mode
                info("    → not available")
            err("No control mode available")
            sys.exit(1)
        else:
            mode = ControlMode(args.mode)
            adapter = TopSpinAdapter(topspin_dir=args.topspin_dir, mode=mode)
            if not adapter.connect():
                err(f"{mode.value.upper()} mode not available")
                sys.exit(1)
            return adapter, mode

    def select_dataset(
        self, args: argparse.Namespace, datasets: list[dict[str, Any]]
    ) -> tuple[str, dict[str, Any]]:
        """Select a dataset by name, title, or interactive choice."""
        if args.dataset:
            for ds in datasets:
                name_match = args.dataset.lower() in ds["sample"].lower()
                title_match = args.dataset.lower() in ds["title"].lower()
                if (name_match or title_match) and ds["expno"] == args.expno:
                    return ds["path"], ds
            err(f"Dataset '{args.dataset}' (expno={args.expno}) not found")
            info("  Available datasets:")
            for ds in datasets:
                info(f"    {ds['sample']}/{ds['expno']}: {ds['title']}")
            sys.exit(1)

        # Interactive selection
        print()
        for i, ds in enumerate(datasets):
            print(f"    {BOLD}[{i:2d}]{RESET} {ds['sample']}/{ds['expno']}: {DIM}{ds['title']}{RESET}")
        print()
        choice = input("  Select dataset number: ").strip()
        try:
            ds = datasets[int(choice)]
            return ds["path"], ds
        except (ValueError, IndexError):
            err("Invalid choice.")
            sys.exit(1)

    def output_dir(self, args: argparse.Namespace) -> Path:
        out = Path(args.output)
        out.mkdir(exist_ok=True)
        return out


def print_peak_table(spectrum: NMRSpectrum) -> None:
    """Print a formatted peak table with visual bars."""
    section("Peak List")
    print(f"  {'─' * 50}")
    print(f"  {'δ (ppm)':>10}  {'Rel. Intensity':>15}  {'Visual'}")
    print(f"  {'─' * 50}")

    max_int = max(p.intensity for p in spectrum.peaks) if spectrum.peaks else 1.0
    for peak in spectrum.peaks:
        rel = peak.intensity / max_int * 100
        bar = "█" * int(rel / 5)
        print(f"  {peak.ppm:10.3f}  {rel:14.1f}%  {DIM}{bar}{RESET}")

    print(f"  {'─' * 50}")
