"""VisionBackend protocol — runtime-checkable interface for VLM providers."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class VisionBackend(Protocol):
    """Protocol for VLM backends (Claude, GPT-4o, Gemini, UI-TARS, etc.).

    All methods are async. Implementations must handle their own API auth
    and retry logic (use backoff for rate limits).
    """

    @property
    def supports_grounding(self) -> bool:
        """Whether this backend can output pixel coordinates directly.

        True for: Claude Computer Use, GPT-5.4 Computer Use, UI-TARS
        False for: GPT-4o (needs OmniParser or SoM overlay)
        """
        ...

    async def observe(self, screenshot: bytes, context: str = "") -> dict[str, Any]:
        """Describe what's visible on screen.

        Args:
            screenshot: PNG image bytes.
            context: Optional context about the current task/state.

        Returns:
            Dict with at least: {"description": str, "elements": list[dict]}
        """
        ...

    async def plan(
        self,
        screenshot: bytes,
        task: str,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Plan the next action given current screen state and task.

        Args:
            screenshot: Current screen PNG bytes.
            task: The high-level task to accomplish.
            history: Previous steps taken (for context).

        Returns:
            Dict with: {"action": ActionRequest-compatible dict, "reasoning": str,
                         "done": bool, "confidence": float}
        """
        ...

    async def locate(self, screenshot: bytes, element_description: str) -> tuple[int, int] | None:
        """Find coordinates of a UI element by description.

        Args:
            screenshot: PNG image bytes.
            element_description: Natural language description of the element.

        Returns:
            (x, y) pixel coordinates in the screenshot space, or None if not found.
        """
        ...
