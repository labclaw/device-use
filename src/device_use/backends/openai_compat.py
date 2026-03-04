"""OpenAI-compatible VLM backend for GPT-4o, Gemini, GLM, etc."""

from __future__ import annotations

import base64
import json
import logging
import re
from typing import Any

import backoff
from openai import AsyncOpenAI, RateLimitError

logger = logging.getLogger(__name__)


class OpenAICompatBackend:
    """VLM backend using OpenAI-compatible API (GPT-4o, Gemini, GLM, etc.).

    Implements VisionBackend protocol.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 4096,
    ):
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._max_tokens = max_tokens
        self.system_prompt: str = ""

    @property
    def supports_grounding(self) -> bool:
        """GPT-4o and most OpenAI-compatible models cannot output coordinates."""
        return False

    @backoff.on_exception(backoff.expo, RateLimitError, max_tries=5)
    async def _call(self, messages: list[dict], temperature: float = 0.0) -> str:
        """Call OpenAI-compatible API with retry on rate limits."""
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=self._max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    def _encode_image(self, screenshot: bytes) -> str:
        """Base64 encode a screenshot for the API."""
        return base64.b64encode(screenshot).decode("utf-8")

    def _make_image_content(
        self, screenshot: bytes, text: str
    ) -> list[dict[str, Any]]:
        """Build multimodal content array with text and image."""
        b64 = self._encode_image(screenshot)
        return [
            {"type": "text", "text": text},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{b64}",
                    "detail": "high",
                },
            },
        ]

    async def observe(
        self, screenshot: bytes, context: str = ""
    ) -> dict[str, Any]:
        """Describe what's visible on screen using vision model.

        Returns:
            Dict with "description" (str) and "elements" (list[dict]).
        """
        prompt = (
            "You are a GUI analysis agent. Describe the current screen state.\n"
            "Return a JSON object with:\n"
            '  "description": a brief summary of what is visible,\n'
            '  "elements": a list of UI elements, each with "name", "type", '
            'and "description".\n'
            "Return ONLY valid JSON, no markdown fences."
        )
        if context:
            prompt += f"\n\nContext: {context}"

        content = self._make_image_content(screenshot, prompt)
        messages: list[dict] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": content})
        raw = await self._call(messages)

        try:
            result = json.loads(_strip_markdown_fences(raw))
        except json.JSONDecodeError:
            logger.warning("Failed to parse observe response as JSON: %s", raw[:200])
            result = {"description": raw, "elements": []}

        return result

    async def plan(
        self,
        screenshot: bytes,
        task: str,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Plan next action given current screen state and task.

        Since GPT-4o doesn't support grounding, it returns element descriptions
        rather than coordinates. The agent loop should use locate() or
        an external grounding model (OmniParser) to get coordinates.

        Returns:
            Dict with "action", "reasoning", "done", and "confidence".
        """
        prompt = (
            "You are a GUI automation agent. Given the screenshot and task, "
            "plan the next action.\n"
            "Return a JSON object with:\n"
            '  "action": {"action_type": one of click/double_click/right_click/'
            'type/hotkey/scroll/drag/wait/screenshot, "target": element description, '
            '"parameters": {}},\n'
            '  "reasoning": why this action,\n'
            '  "done": true if the task is complete,\n'
            '  "confidence": 0.0 to 1.0.\n'
            "Return ONLY valid JSON, no markdown fences.\n\n"
            f"Task: {task}"
        )
        if history:
            prompt += f"\n\nPrevious steps: {json.dumps(history[-5:])}"

        content = self._make_image_content(screenshot, prompt)
        messages: list[dict] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": content})
        raw = await self._call(messages)

        try:
            result = json.loads(_strip_markdown_fences(raw))
        except json.JSONDecodeError:
            logger.warning("Failed to parse plan response as JSON: %s", raw[:200])
            result = {
                "action": {"action_type": "wait", "seconds": 1},
                "reasoning": raw,
                "done": False,
                "confidence": 0.0,
            }

        return result

    async def locate(
        self, screenshot: bytes, element_description: str
    ) -> tuple[int, int] | None:
        """Attempt to locate element by description.

        Returns None since GPT-4o cannot output pixel coordinates.
        The agent loop should fall back to OmniParser or similar.
        """
        return None


def _strip_markdown_fences(text: str) -> str:
    """Strip ```json ... ``` markdown fences from VLM responses."""
    stripped = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    stripped = re.sub(r"\n?```\s*$", "", stripped)
    return stripped.strip()
