"""Base instrument interface — all instruments implement this.

Each instrument provides one or more control backends:
  - API: programmatic control (gRPC, REST, serial, etc.)
  - GUI: visual automation via Computer Use
  - Offline: local processing without the instrument software

The framework doesn't care HOW the instrument is controlled,
only WHAT data comes back.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ControlMode(Enum):
    """How device-use talks to the instrument."""

    API = "api"  # programmatic (gRPC, REST, serial, VISA, etc.)
    GUI = "gui"  # visual automation (Computer Use / screen interaction)
    OFFLINE = "offline"  # local processing, no instrument software needed


@dataclass
class InstrumentInfo:
    """Metadata about an instrument."""

    name: str
    vendor: str
    instrument_type: str  # "nmr", "microscope", "liquid_handler", etc.
    supported_modes: list[ControlMode] = field(default_factory=list)
    version: str = ""
    description: str = ""


class BaseInstrument(ABC):
    """Abstract base class for all instruments.

    Subclasses implement specific backends (API, GUI, Offline).
    The framework uses this interface to:
      1. Discover available instruments
      2. Connect to them
      3. Execute commands
      4. Collect data
    """

    @abstractmethod
    def info(self) -> InstrumentInfo:
        """Return instrument metadata."""
        ...

    @abstractmethod
    def connect(self) -> bool:
        """Attempt to connect. Returns True if successful."""
        ...

    @property
    @abstractmethod
    def connected(self) -> bool:
        """Whether the instrument is currently connected."""
        ...

    @property
    @abstractmethod
    def mode(self) -> ControlMode:
        """Current control mode."""
        ...

    @abstractmethod
    def list_datasets(self) -> list[dict[str, Any]]:
        """List available datasets/samples."""
        ...

    @abstractmethod
    def acquire(self, **kwargs) -> Any:
        """Acquire data (run experiment, take measurement, etc.)."""
        ...

    @abstractmethod
    def process(self, data_path: str, **kwargs) -> Any:
        """Process raw data into a usable result."""
        ...
