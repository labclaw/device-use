"""Base operator abstraction for instrument control."""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import IntEnum
from typing import Any


class ControlLayer(IntEnum):
    """Control layers ordered by preference (lower = faster/more reliable)."""
    API = 1       # Direct programmatic control
    SCRIPT = 2    # AppleScript/JXA/macro
    A11Y = 3      # Accessibility API
    CU = 4        # Computer Use (VLM)


class BaseOperator(ABC):
    """Base class for instrument operators.

    An operator knows how to control a specific application using one
    or more control layers. The instrument profile declares which layers
    are available; the orchestrator picks the best one for each action.
    """

    @abstractmethod
    def available_layers(self) -> list[ControlLayer]:
        """Return control layers this operator supports, in preference order."""

    @abstractmethod
    async def execute(
        self,
        command: str,
        *,
        layer: ControlLayer | None = None,
        timeout_s: float = 30.0,
    ) -> OperatorResult:
        """Execute a command using the best available layer."""

    @abstractmethod
    async def read_state(self) -> dict[str, Any]:
        """Read current application state (status, active dataset, etc.)."""

    @abstractmethod
    async def wait_ready(self, timeout_s: float = 10.0) -> bool:
        """Wait until the application is ready for the next command."""


class OperatorResult:
    """Result of an operator action."""

    __slots__ = ("success", "layer_used", "output", "error", "duration_s")

    def __init__(
        self,
        success: bool,
        layer_used: ControlLayer,
        output: str = "",
        error: str = "",
        duration_s: float = 0.0,
    ):
        self.success = success
        self.layer_used = layer_used
        self.output = output
        self.error = error
        self.duration_s = duration_s

    def __repr__(self) -> str:
        status = "OK" if self.success else "FAIL"
        return f"OperatorResult({status}, {self.layer_used.name}, {self.duration_s:.2f}s)"
