"""Plate Reader adapter — multi-mode instrument control.

Supports the same three control modes as NMR:
  - OFFLINE: parse exported CSV/Excel data files
  - API: connect to instrument REST API (Gen5, Tecan)
  - GUI: Computer Use automation of plate reader software

Offline mode ships with demo data for immediate testing.
"""

from __future__ import annotations

import csv
import io
import logging
import random
from pathlib import Path
from typing import Any

from device_use.instruments.base import BaseInstrument, ControlMode, InstrumentInfo
from device_use.instruments.plate_reader.models import (
    PlateFormat,
    PlateReading,
    ReadingMode,
    Well,
    WellPlate,
)

logger = logging.getLogger(__name__)


# ── Demo data for offline mode ───────────────────────────────────────────

def _generate_demo_absorbance(wavelength: int = 450) -> PlateReading:
    """Generate realistic absorbance data for a 96-well ELISA plate.

    Simulates a standard curve in column 1-2 with serial dilutions,
    samples in columns 3-10, and blanks in columns 11-12.
    """
    random.seed(42)
    rows = "ABCDEFGH"
    wells: list[Well] = []

    for r in rows:
        for c in range(1, 13):
            if c <= 2:
                # Standard curve: decreasing concentration A→H
                base = 2.5 * (0.5 ** (ord(r) - ord("A")))
                value = base + random.gauss(0, 0.02)
            elif c <= 10:
                # Samples: random OD values typical of ELISA
                value = random.uniform(0.1, 1.8) + random.gauss(0, 0.01)
            else:
                # Blanks
                value = 0.04 + random.gauss(0, 0.005)

            wells.append(Well(row=r, col=c, value=round(max(0, value), 4)))

    # Blank correction
    blank_avg = sum(w.value for w in wells if w.col >= 11) / sum(
        1 for w in wells if w.col >= 11
    )
    for w in wells:
        w.blank_corrected = round(w.value - blank_avg, 4)

    plate = WellPlate(format=PlateFormat.PLATE_96, wells=wells)
    return PlateReading(
        plate=plate,
        mode=ReadingMode.ABSORBANCE,
        wavelength_nm=wavelength,
        protocol="ELISA Demo",
        metadata={
            "temperature_c": 25.0,
            "shake_before_read": True,
            "read_speed": "normal",
        },
    )


def _generate_demo_fluorescence() -> PlateReading:
    """Generate fluorescence data for a cell viability assay."""
    random.seed(123)
    rows = "ABCDEFGH"
    wells: list[Well] = []

    for r in rows:
        for c in range(1, 13):
            if c <= 2:
                # Positive control (healthy cells, high fluorescence)
                value = 45000 + random.gauss(0, 2000)
            elif c <= 4:
                # Drug treatment — dose-dependent reduction
                dose_factor = 1.0 - 0.2 * (ord(r) - ord("A"))
                value = 45000 * max(0.1, dose_factor) + random.gauss(0, 1500)
            elif c <= 10:
                # Various compounds under test
                value = random.uniform(5000, 40000) + random.gauss(0, 1000)
            else:
                # Negative control (dead cells)
                value = 2000 + random.gauss(0, 500)

            wells.append(Well(row=r, col=c, value=round(max(0, value), 1)))

    plate = WellPlate(format=PlateFormat.PLATE_96, wells=wells)
    return PlateReading(
        plate=plate,
        mode=ReadingMode.FLUORESCENCE,
        wavelength_nm=530,
        protocol="Cell Viability (Calcein AM)",
        metadata={
            "excitation_nm": 485,
            "emission_nm": 530,
            "gain": 50,
        },
    )


_DEMO_DATASETS = [
    {
        "name": "ELISA_IL6_plate1",
        "protocol": "ELISA Demo",
        "mode": "absorbance",
        "wavelength_nm": 450,
        "plate_format": 96,
        "date": "2025-01-15",
    },
    {
        "name": "CellViability_DrugScreen",
        "protocol": "Cell Viability (Calcein AM)",
        "mode": "fluorescence",
        "wavelength_nm": 530,
        "plate_format": 96,
        "date": "2025-01-16",
    },
]


# ── Adapter ──────────────────────────────────────────────────────────────

class PlateReaderAdapter(BaseInstrument):
    """Multi-mode plate reader adapter.

    Demonstrates the BaseInstrument abstraction for a completely different
    instrument type than NMR — same interface, different domain.

    Example::

        reader = PlateReaderAdapter(mode=ControlMode.OFFLINE)
        reader.connect()
        datasets = reader.list_datasets()
        reading = reader.process(datasets[0]["name"])
        print(f"Well A1: OD={reading.plate.get_well('A1').value}")
    """

    def __init__(self, mode: ControlMode = ControlMode.OFFLINE) -> None:
        self._mode = mode
        self._connected = False

    # -- BaseInstrument interface ------------------------------------------

    def info(self) -> InstrumentInfo:
        return InstrumentInfo(
            name="PlateReader",
            vendor="BioTek",
            instrument_type="plate_reader",
            supported_modes=[ControlMode.OFFLINE, ControlMode.API, ControlMode.GUI],
            version="Gen5 3.x",
            description="96/384-well microplate reader — absorbance, fluorescence, luminescence",
        )

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def mode(self) -> ControlMode:
        return self._mode

    def connect(self) -> bool:
        if self._mode == ControlMode.OFFLINE:
            self._connected = True
            logger.info("PlateReader connected in OFFLINE mode (demo data)")
            return True

        if self._mode == ControlMode.API:
            logger.warning("PlateReader API mode not yet implemented")
            return False

        if self._mode == ControlMode.GUI:
            logger.warning("PlateReader GUI mode not yet implemented")
            return False

        return False

    def list_datasets(self) -> list[dict[str, Any]]:
        self._ensure_connected()
        if self._mode == ControlMode.OFFLINE:
            return _DEMO_DATASETS
        raise NotImplementedError(f"list_datasets not implemented for {self._mode}")

    def acquire(self, **kwargs: Any) -> Any:
        if self._mode == ControlMode.OFFLINE:
            raise RuntimeError("Cannot acquire in OFFLINE mode — no physical reader")
        raise NotImplementedError(f"acquire not implemented for {self._mode}")

    def process(self, data_path: str, **kwargs: Any) -> PlateReading:
        """Process plate reader data.

        Args:
            data_path: Dataset name (in OFFLINE mode) or file path.
            **kwargs: Optional processing parameters.

        Returns:
            PlateReading with well data and metadata.
        """
        self._ensure_connected()

        if self._mode == ControlMode.OFFLINE:
            return self._process_offline(data_path, **kwargs)

        raise NotImplementedError(f"process not implemented for {self._mode}")

    # -- Offline processing ------------------------------------------------

    def _process_offline(self, dataset_name: str, **kwargs: Any) -> PlateReading:
        """Return demo plate reading data."""
        if "viability" in dataset_name.lower() or "cell" in dataset_name.lower():
            return _generate_demo_fluorescence()
        return _generate_demo_absorbance(
            wavelength=kwargs.get("wavelength_nm", 450)
        )

    # -- CSV export --------------------------------------------------------

    @staticmethod
    def reading_to_csv(reading: PlateReading) -> str:
        """Export a PlateReading to CSV format (like Gen5 export)."""
        output = io.StringIO()
        writer = csv.writer(output)

        # Header
        writer.writerow([
            f"Protocol: {reading.protocol}",
            f"Mode: {reading.mode.value}",
            f"Wavelength: {reading.wavelength_nm}nm",
        ])
        writer.writerow([])

        # Find dimensions
        rows_set = sorted(set(w.row for w in reading.plate.wells))
        cols_set = sorted(set(w.col for w in reading.plate.wells))

        # Column headers
        writer.writerow([""] + [str(c) for c in cols_set])

        # Data rows
        for r in rows_set:
            row_data = [r]
            for c in cols_set:
                well = reading.plate.get_well(f"{r}{c}")
                row_data.append(f"{well.value:.4f}" if well else "")
            writer.writerow(row_data)

        return output.getvalue()

    # -- Internal ----------------------------------------------------------

    def _ensure_connected(self) -> None:
        if not self._connected:
            if not self.connect():
                raise RuntimeError(
                    f"Failed to connect PlateReader in {self._mode.value} mode"
                )
