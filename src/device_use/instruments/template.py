"""Template for adding a new instrument to device-use.

Copy this file and implement the abstract methods to add support for
any lab instrument — from microscopes to mass spectrometers.

Steps:
  1. Copy this template to instruments/your_instrument/adapter.py
  2. Implement the 5 methods + 2 properties below
  3. Register with the orchestrator: orch.register(YourAdapter())
  4. Done — your instrument gets pipelines, events, and AI for free

Example:
    from device_use.instruments.template import InstrumentTemplate

    class MyMicroscopeAdapter(InstrumentTemplate):
        def info(self):
            return InstrumentInfo(
                name="ZeissZEN",
                vendor="Zeiss",
                instrument_type="microscope",
                supported_modes=[ControlMode.OFFLINE, ControlMode.GUI],
            )
        ...
"""

from __future__ import annotations

from typing import Any

from device_use.instruments.base import BaseInstrument, ControlMode, InstrumentInfo


class InstrumentTemplate(BaseInstrument):
    """Template adapter — copy and implement for your instrument.

    Required methods/properties (7 total):
      info()          → InstrumentInfo   metadata about the instrument
      connected       → bool             are we connected?
      mode            → ControlMode      current control mode
      connect()       → bool             establish connection
      list_datasets() → list[dict]       what data is available?
      acquire()       → Any              run a measurement
      process()       → Any              process raw data into results
    """

    def __init__(self, mode: ControlMode = ControlMode.OFFLINE) -> None:
        self._mode = mode
        self._connected = False

    def info(self) -> InstrumentInfo:
        # TODO: Return your instrument's metadata
        return InstrumentInfo(
            name="MyInstrument",
            vendor="Vendor",
            instrument_type="spectrometer",  # nmr, plate_reader, microscope, etc.
            supported_modes=[ControlMode.OFFLINE],
            version="1.0",
            description="Description of your instrument",
        )

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def mode(self) -> ControlMode:
        return self._mode

    def connect(self) -> bool:
        # TODO: Implement connection logic for each mode
        if self._mode == ControlMode.OFFLINE:
            self._connected = True
            return True
        if self._mode == ControlMode.API:
            # Connect to instrument API (gRPC, REST, serial, etc.)
            raise NotImplementedError("API mode not yet implemented")
        if self._mode == ControlMode.GUI:
            # Detect instrument software window on screen
            raise NotImplementedError("GUI mode not yet implemented")
        return False

    def list_datasets(self) -> list[dict[str, Any]]:
        # TODO: Return available experiments/samples
        return [
            {"name": "sample_1", "date": "2025-01-15", "type": "measurement"},
        ]

    def acquire(self, **kwargs: Any) -> Any:
        # TODO: Start a measurement (not available in OFFLINE mode)
        if self._mode == ControlMode.OFFLINE:
            raise RuntimeError("Cannot acquire in OFFLINE mode")
        raise NotImplementedError("Acquisition not yet implemented")

    def process(self, data_path: str, **kwargs: Any) -> Any:
        # TODO: Process raw data into results
        # Return whatever makes sense for your instrument:
        #   NMR → NMRSpectrum with peaks
        #   Plate reader → PlateReading with wells
        #   Microscope → Image with annotations
        raise NotImplementedError("Processing not yet implemented")
