"""ToolUniverse integration — 600+ scientific tools via Harvard's SDK.

Bridges device-use with Harvard's ToolUniverse ecosystem, providing
access to scientific tools for compound analysis, database lookups,
ML model inference, and more.

Install: pip install tooluniverse
Docs: https://zitniklab.hms.harvard.edu/ToolUniverse/

Falls back gracefully if tooluniverse is not installed.
"""

from __future__ import annotations

import logging
from typing import Any

from device_use.tools.base import BaseTool

logger = logging.getLogger(__name__)

# Try importing tooluniverse — graceful fallback if not installed
_TU_AVAILABLE = False
try:
    from tooluniverse import ToolUniverse as _ToolUniverse

    _TU_AVAILABLE = True
except ImportError:
    _ToolUniverse = None


class ToolUniverseError(Exception):
    """Raised when a ToolUniverse operation fails."""


class ToolUniverseTool(BaseTool):
    """Gateway to Harvard's ToolUniverse — 600+ scientific tools.

    Provides tool discovery, execution, and chemistry-specific
    convenience methods for the device-use middleware.

    Example::

        tool = ToolUniverseTool()
        tool.connect()

        # Find tools for NMR analysis
        results = tool.find_tools("NMR spectroscopy analysis")

        # Call a specific tool
        result = tool.call_tool("PubChem_get_compound_by_name",
                                name="strychnine")
    """

    def __init__(self) -> None:
        self._tu: Any | None = None
        self._connected = False

    # -- BaseTool interface ------------------------------------------------

    @property
    def name(self) -> str:
        return "tooluniverse"

    @property
    def description(self) -> str:
        return (
            "Access 600+ scientific tools via Harvard's ToolUniverse — "
            "compound analysis, database lookups, ML models, and more."
        )

    def execute(self, **kwargs: Any) -> Any:
        action = kwargs.pop("action", "find")
        if action == "find":
            return self.find_tools(kwargs.get("query", ""), kwargs.get("limit", 5))
        if action == "call":
            tool_name = kwargs.pop("tool_name", None)
            if not tool_name:
                raise ValueError("tool_name required for action='call'")
            return self.call_tool(tool_name, **kwargs)
        if action == "spec":
            tool_name = kwargs.get("tool_name", "")
            return self.get_tool_spec(tool_name)
        raise ValueError(f"Unknown action: {action!r}. Use 'find', 'call', or 'spec'.")

    # -- Connection --------------------------------------------------------

    @property
    def available(self) -> bool:
        """Whether the tooluniverse package is installed."""
        return _TU_AVAILABLE

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        """Initialize the ToolUniverse SDK."""
        if not _TU_AVAILABLE:
            raise ToolUniverseError(
                "tooluniverse package not installed. Install with: pip install tooluniverse"
            )
        self._tu = _ToolUniverse()
        self._connected = True
        logger.info("ToolUniverse connected — 600+ scientific tools available")

    # -- Tool discovery ----------------------------------------------------

    def find_tools(self, query: str, limit: int = 5, method: str = "keyword") -> Any:
        """Find tools matching a query.

        Args:
            query: Natural language description of what you need.
            limit: Maximum number of results.
            method: Search method — "keyword" (fast) or "embedding" (semantic).

        Returns:
            List of tool descriptions with name, description, parameters.
        """
        self._ensure_connected()

        finder_name = {
            "keyword": "Tool_Finder_Keyword",
            "embedding": "Tool_Finder_Embedding",
            "llm": "Tool_Finder_LLM",
        }.get(method, "Tool_Finder_Keyword")

        result = self._tu.run(
            {
                "name": finder_name,
                "arguments": {"description": query, "limit": limit},
            }
        )
        return result

    def get_tool_spec(self, tool_name: str, format: str = "openai") -> dict[str, Any]:
        """Get the full specification for a tool.

        Args:
            tool_name: Exact tool name from ToolUniverse.
            format: Spec format — "openai" or "anthropic".

        Returns:
            Tool specification dict with parameters, description, etc.
        """
        self._ensure_connected()
        return self._tu.tool_specification(tool_name, format=format)

    # -- Tool execution ----------------------------------------------------

    def call_tool(self, tool_name: str, **arguments: Any) -> Any:
        """Execute a ToolUniverse tool.

        Args:
            tool_name: The tool to call (e.g. "UniProt_get_function_by_accession").
            **arguments: Tool-specific keyword arguments.

        Returns:
            Tool result (varies by tool).
        """
        self._ensure_connected()

        logger.info("ToolUniverse calling: %s(%s)", tool_name, arguments)
        result = self._tu.run(
            {
                "name": tool_name,
                "arguments": arguments,
            }
        )
        return result

    # -- Chemistry convenience methods -------------------------------------

    def find_chemistry_tools(self, task: str = "compound analysis") -> list[dict]:
        """Find chemistry-specific tools.

        Convenience wrapper that searches for tools related to chemical
        analysis, compound identification, and molecular properties.
        """
        return self.find_tools(f"chemistry {task}", limit=10)

    def find_spectroscopy_tools(self) -> list[dict]:
        """Find tools related to NMR, IR, MS, and other spectroscopy."""
        return self.find_tools("spectroscopy NMR IR mass spectrometry analysis", limit=10)

    def find_drug_discovery_tools(self) -> list[dict]:
        """Find tools for drug discovery and pharmacology."""
        return self.find_tools("drug discovery pharmacology ADMET toxicity", limit=10)

    # -- Internal ----------------------------------------------------------

    def _ensure_connected(self) -> None:
        if not self._connected:
            if not _TU_AVAILABLE:
                raise ToolUniverseError(
                    "tooluniverse not installed. Install: pip install tooluniverse"
                )
            self.connect()


# -- Registry helper -------------------------------------------------------


def get_available_tools() -> list[BaseTool]:
    """Return all available external tools for the Cloud Brain.

    This is the entry point for the Orchestrator to discover what
    tools are available for compound analysis and cross-referencing.
    """
    from device_use.tools.pubchem import PubChemTool

    tools: list[BaseTool] = [PubChemTool()]

    if _TU_AVAILABLE:
        tools.append(ToolUniverseTool())

    return tools
