"""NMR instrument adapter — TopSpin + nmrglue processing."""

from device_use.instruments.nmr.adapter import TopSpinAdapter
from device_use.instruments.nmr.processor import NMRProcessor

__all__ = ["NMRProcessor", "TopSpinAdapter"]
