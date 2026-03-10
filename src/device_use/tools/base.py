"""Base interface for external tools (PubChem, ChEMBL, etc.).

Inspired by Harvard's ToolUniverse project (2114 tools).  Each tool
wraps a single external API and exposes a uniform execute() entry point
so the Cloud Brain can invoke it after compound identification.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Abstract base class that all external tools implement.

    Subclasses must define:
      - name:        short machine-friendly identifier (e.g. "pubchem")
      - description: one-line human-readable purpose
      - execute():   run the tool with arbitrary keyword arguments
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Machine-friendly tool identifier."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """One-line description shown to the Cloud Brain."""
        ...

    @abstractmethod
    def execute(self, **kwargs: Any) -> Any:
        """Run the tool.

        Args:
            **kwargs: Tool-specific parameters (e.g. name, formula, cid).

        Returns:
            Tool-specific result (dict, str, list, etc.).
        """
        ...

    def __repr__(self) -> str:  # pragma: no cover
        return f"<{type(self).__name__} name={self.name!r}>"
