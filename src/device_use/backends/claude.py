"""Claude VisionBackend — Anthropic vision API with base64 screenshots."""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

import backoff
from anthropic import AsyncAnthropic, RateLimitError

logger = logging.getLogger(__name__)


class ClaudeBackend:
    """VLM backend using Anthropic's Claude with vision capabilities.

    Claude Computer Use supports grounding (outputting pixel coordinates),
    making it suitable as a primary backend for device-use.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
        max_tokens: int = 4096,
    ):
        self._model = model
        self._client = AsyncAnthropic(api_key=api_key)
        self._max_tokens = max_tokens
        self.system_prompt: str = ""

    @property
    def supports_grounding(self) -> bool:
        return True

    @backoff.on_exception(backoff.expo, RateLimitError, max_tries=5)
    async def _call(
        self,
        messages: list[dict[str, Any]],
        system: str = "",
        temperature: float = 0.0,
    ) -> str:
        """Call Claude API with retry on rate limits."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": messages,
            "temperature": temperature,
        }
        if system:
            kwargs["system"] = system

        response = await self._client.messages.create(**kwargs)
        return response.content[0].text

    @staticmethod
    def _encode_image(screenshot: bytes) -> str:
        """Base64 encode a screenshot for the API."""
        return base64.standard_b64encode(screenshot).decode("utf-8")

    def _make_image_content(self, screenshot: bytes) -> dict[str, Any]:
        """Build image content block for Claude API."""
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": self._encode_image(screenshot),
            },
        }

    async def observe(self, screenshot: bytes, context: str = "") -> dict[str, Any]:
        """Describe what's visible on screen."""
        prompt = (
            "Describe what you see on this screen. Identify all visible UI elements, "
            "dialogs, menus, and the current state of the application. "
            "Respond with JSON: "
            '{"description": "...", "elements": '
            '[{"name": "...", "type": "...", "location": "..."}]}'
        )
        if context:
            prompt = f"Context: {context}\n\n{prompt}"

        messages = [
            {
                "role": "user",
                "content": [
                    self._make_image_content(screenshot),
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        response = await self._call(messages, system=self.system_prompt)
        try:
            return json.loads(_strip_markdown_fences(response))
        except json.JSONDecodeError:
            return {"description": response, "elements": []}

    async def plan(
        self,
        screenshot: bytes,
        task: str,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Plan the next action given current screen state."""
        history_text = ""
        if history:
            recent = history[-5:]
            history_text = "Recent actions:\n"
            for h in recent:
                step = h.get("step", "?")
                action = h.get("action", "?")
                result = h.get("result", "?")
                history_text += f"- Step {step}: {action} → {result}\n"
            history_text += "\n"

        prompt = (
            f"Task: {task}\n\n"
            f"{history_text}"
            "Look at the current screen and plan the next action.\n"
            "Respond with JSON:\n"
            "{\n"
            '  "reasoning": "why this action",\n'
            '  "action": {\n'
            '    "action_type": "click|type|hotkey|scroll|drag|wait",\n'
            '    "coordinates": [x, y],\n'
            '    "text": "...",\n'
            '    "keys": ["ctrl", "s"],\n'
            '    "description": "what this does"\n'
            "  },\n"
            '  "done": false,\n'
            '  "confidence": 0.9\n'
            "}"
        )

        messages = [
            {
                "role": "user",
                "content": [
                    self._make_image_content(screenshot),
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        response = await self._call(messages, system=self.system_prompt)
        try:
            return json.loads(_strip_markdown_fences(response))
        except json.JSONDecodeError:
            logger.warning("Failed to parse plan response as JSON: %s", response[:200])
            return {
                "reasoning": response,
                "action": {"action_type": "wait", "seconds": 1},
                "done": False,
                "confidence": 0.0,
            }

    async def locate(self, screenshot: bytes, element_description: str) -> tuple[int, int] | None:
        """Find coordinates of a UI element. Claude supports grounding."""
        prompt = (
            f"Find the UI element: {element_description}\n\n"
            'Respond with ONLY the pixel coordinates as JSON: {"x": 123, "y": 456}\n'
            'If the element is not visible, respond with: {"x": null, "y": null}'
        )

        messages = [
            {
                "role": "user",
                "content": [
                    self._make_image_content(screenshot),
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        response = await self._call(messages)
        try:
            data = json.loads(_strip_markdown_fences(response))
            x, y = data.get("x"), data.get("y")
            if x is not None and y is not None:
                return (int(x), int(y))
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
        return None


def _strip_markdown_fences(text: str) -> str:
    """Strip ```json ... ``` markdown fences from VLM responses."""
    stripped = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    stripped = re.sub(r"\n?```\s*$", "", stripped)
    return stripped.strip()
