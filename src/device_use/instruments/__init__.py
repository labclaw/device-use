"""Instrument adapters — device-use middleware for scientific instruments.

Like ROS for lab instruments: abstract interface between AI agents and physical devices.
"""

from device_use.instruments.base import BaseInstrument, ControlMode, InstrumentInfo

__all__ = ["BaseInstrument", "ControlMode", "InstrumentInfo"]
