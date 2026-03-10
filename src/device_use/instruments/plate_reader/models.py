"""Data models for plate reader experiments."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PlateFormat(Enum):
    """Standard microplate formats."""
    PLATE_6 = 6
    PLATE_12 = 12
    PLATE_24 = 24
    PLATE_48 = 48
    PLATE_96 = 96
    PLATE_384 = 384


class ReadingMode(Enum):
    """Measurement modes available on plate readers."""
    ABSORBANCE = "absorbance"
    FLUORESCENCE = "fluorescence"
    LUMINESCENCE = "luminescence"


@dataclass
class Well:
    """A single well in a microplate."""
    row: str      # A-H for 96-well
    col: int      # 1-12 for 96-well
    value: float = 0.0
    blank_corrected: float | None = None

    @property
    def name(self) -> str:
        return f"{self.row}{self.col}"


@dataclass
class WellPlate:
    """A microplate with readings."""
    format: PlateFormat
    wells: list[Well] = field(default_factory=list)

    def get_well(self, name: str) -> Well | None:
        for w in self.wells:
            if w.name == name:
                return w
        return None

    def column(self, col: int) -> list[Well]:
        return [w for w in self.wells if w.col == col]

    def row(self, row: str) -> list[Well]:
        return [w for w in self.wells if w.row == row]


@dataclass
class PlateReading:
    """Result of a plate reader measurement."""
    plate: WellPlate
    mode: ReadingMode
    wavelength_nm: int
    protocol: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
