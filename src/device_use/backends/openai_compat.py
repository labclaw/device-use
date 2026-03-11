"""OpenAI-compatible VLM backend — GPT-5.4 Computer Use + legacy chat fallback."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re
from typing import Any

from dataclasses import dataclass

import backoff
from openai import AsyncOpenAI, RateLimitError

logger = logging.getLogger(__name__)


@dataclass
class _CUStepResult:
    """Result of a single computer use step, avoiding mutation of SDK response."""

    response: Any
    has_safety_checks: bool


# Models that support native computer use via Responses API
_COMPUTER_USE_MODELS = frozenset({
    "gpt-5.4",
    "gpt-5.4-pro",
    "computer-use-preview",
    "computer-use-preview-2025-03-11",
})


def _supports_computer_use(model: str) -> bool:
    """Check if model supports native computer use tool."""
    return any(model.startswith(m) for m in _COMPUTER_USE_MODELS)


class OpenAICompatBackend:
    """VLM backend using OpenAI API.

    For GPT-5.4+: Uses Responses API with native computer use tool.
    For older models (GPT-4o etc.): Falls back to chat completions with prompts.
    """

    def __init__(
        self,
        model: str = "gpt-5.4",
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 4096,
    ):
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._max_tokens = max_tokens
        self._native_cu = _supports_computer_use(model)
        self.system_prompt: str = ""

        # State for Responses API continuation
        self._previous_response_id: str | None = None

    @property
    def supports_grounding(self) -> bool:
        """GPT-5.4+ supports native pixel coordinates via computer use."""
        return self._native_cu

    # ------------------------------------------------------------------
    # Responses API path (GPT-5.4 computer use)
    # ------------------------------------------------------------------

    @backoff.on_exception(backoff.expo, RateLimitError, max_tries=5)
    async def _responses_create(self, **kwargs: Any) -> Any:
        """Call Responses API with retry on rate limits."""
        return await self._client.responses.create(**kwargs)

    async def _computer_use_step(
        self,
        screenshot: bytes,
        task: str,
        call_id: str | None = None,
    ) -> _CUStepResult:
        """Execute one step of the GPT-5.4 computer use loop.

        First call: send task as input text + initial screenshot.
        Subsequent calls: send computer_call_output with new screenshot.

        Uses Responses API with tools=[{"type": "computer"}].
        See: https://developers.openai.com/api/docs/guides/tools-computer-use
        """
        b64 = base64.b64encode(screenshot).decode("utf-8")
        image_url = f"data:image/png;base64,{b64}"

        if call_id is not None and self._previous_response_id is not None:
            # Continuation: send computer_call_output per SDK spec
            # Type: ComputerCallOutput TypedDict
            input_items: list[dict[str, Any]] = [{
                "type": "computer_call_output",
                "call_id": call_id,
                "output": {
                    "type": "computer_screenshot",
                    "image_url": image_url,
                },
            }]
            response = await self._responses_create(
                model=self._model,
                tools=[{"type": "computer"}],
                previous_response_id=self._previous_response_id,
                input=input_items,
                reasoning={"effort": "low"},
                truncation="auto",
            )
        else:
            # Initial call: EasyInputMessageParam with text + image
            input_items = [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": task},
                        {
                            "type": "input_image",
                            "image_url": image_url,
                            "detail": "original",
                        },
                    ],
                }
            ]
            kwargs: dict[str, Any] = {
                "model": self._model,
                "tools": [{"type": "computer"}],
                "input": input_items,
                "reasoning": {"effort": "low"},
                "truncation": "auto",
            }
            if self.system_prompt:
                kwargs["instructions"] = self.system_prompt
            response = await self._responses_create(**kwargs)

        self._previous_response_id = response.id

        # Check for pending safety checks on computer_call items
        has_safety_checks = False
        for item in getattr(response, "output", []):
            if getattr(item, "type", None) == "computer_call":
                checks = getattr(item, "pending_safety_checks", [])
                if checks:
                    logger.warning("CU pending safety checks: %s", checks)
                    has_safety_checks = True
                    break

        return _CUStepResult(response=response, has_safety_checks=has_safety_checks)

    def _extract_computer_calls(
        self, response: Any
    ) -> list[dict[str, Any]]:
        """Extract all computer_call actions from response output.

        GPT-5.4 uses `actions` (list). Older models use `action` (single).
        SDK types (from openai.types.responses.computer_action):
          Click(type, x, y, button), DoubleClick(type, x, y),
          Drag(type, path), Keypress(type, keys), Move(type, x, y),
          Screenshot(type), Scroll(type, x, y, scroll_x, scroll_y),
          Type(type, text), Wait(type)
        """
        results: list[dict[str, Any]] = []
        for item in response.output:
            if item.type != "computer_call":
                continue

            call_id = item.call_id

            # Collect actions: prefer `actions` list, fall back to single `action`
            actions = item.actions or []
            if not actions and item.action is not None:
                actions = [item.action]
            actions = [a for a in actions if a is not None]
            if not actions:
                logger.warning("computer_call %s has no actions", call_id)
                continue

            for action in actions:
                results.append({
                    "call_id": call_id,
                    "action_type": action.type,
                    "x": getattr(action, "x", None),
                    "y": getattr(action, "y", None),
                    "button": getattr(action, "button", None),
                    "text": getattr(action, "text", None),
                    "keys": getattr(action, "keys", None),
                    "scroll_x": getattr(action, "scroll_x", None),
                    "scroll_y": getattr(action, "scroll_y", None),
                    "path": getattr(action, "path", None),
                })
        return results

    def _extract_text(self, response: Any) -> str:
        """Extract text output from response."""
        return getattr(response, "output_text", "") or ""

    def reset_session(self) -> None:
        """Reset the Responses API session (clear previous_response_id)."""
        self._previous_response_id = None

    async def run_cu_loop(
        self,
        task: str,
        take_screenshot: Any,
        execute_action: Any,
        *,
        max_turns: int = 24,
    ) -> list[dict[str, Any]]:
        """Run a full computer use loop with safety and turn limits.

        Args:
            task: The task description for the CU agent.
            take_screenshot: Async callable returning screenshot bytes.
            execute_action: Async callable taking a mapped action dict.
            max_turns: Maximum loop iterations before breaking (default 24).

        Returns:
            List of all actions executed during the loop.
        """
        self.reset_session()
        all_actions: list[dict[str, Any]] = []
        call_id: str | None = None

        for turn in range(max_turns):
            screenshot = await take_screenshot()
            step_result = await self._computer_use_step(screenshot, task, call_id)

            # Handle pending safety checks — abort loop
            if step_result.has_safety_checks:
                logger.warning(
                    "CU loop aborting at turn %d due to pending_safety_checks", turn
                )
                break

            cu_actions = self._extract_computer_calls(step_result.response)
            if not cu_actions:
                # No more computer_call items — model considers task done
                logger.info("CU loop completed at turn %d (no actions)", turn)
                break

            # Execute each action with inter-action delay
            for i, cu in enumerate(cu_actions):
                mapped = self._map_cu_action(cu)
                await execute_action(mapped)
                all_actions.append(mapped)

                # 120ms delay between actions (skip for wait/screenshot)
                action_type = cu.get("action_type", "")
                if action_type not in ("wait", "screenshot") and i < len(cu_actions) - 1:
                    await asyncio.sleep(0.12)

            # Use last call_id for continuation
            call_id = cu_actions[-1].get("call_id")
        else:
            logger.warning("CU loop hit max_turns cap (%d)", max_turns)

        return all_actions

    # ------------------------------------------------------------------
    # VisionBackend protocol methods
    # ------------------------------------------------------------------

    async def observe(
        self, screenshot: bytes, context: str = ""
    ) -> dict[str, Any]:
        """Describe what's visible on screen using vision model."""
        if self._native_cu:
            # For GPT-5.4: use a one-shot responses call (no computer tool)
            b64 = base64.b64encode(screenshot).decode("utf-8")
            prompt = (
                "Describe the current screen state. "
                "Return JSON: {\"description\": \"...\", \"elements\": "
                "[{\"name\": \"...\", \"type\": \"...\", \"description\": \"...\"}]}"
            )
            if context:
                prompt = f"Context: {context}\n\n{prompt}"

            response = await self._responses_create(
                model=self._model,
                input=[{
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{b64}",
                            "detail": "original",
                        },
                    ],
                }],
            )
            raw = self._extract_text(response)
            try:
                return json.loads(_strip_markdown_fences(raw))
            except json.JSONDecodeError:
                return {"description": raw, "elements": []}

        # Legacy path: chat completions
        return await self._observe_legacy(screenshot, context)

    async def plan(
        self,
        screenshot: bytes,
        task: str,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Plan next action given current screen state and task.

        For GPT-5.4: Uses native computer use — model returns structured
        actions with pixel coordinates directly.

        For legacy models: Uses chat completions with prompt engineering.
        """
        if self._native_cu:
            return await self._plan_native(screenshot, task, history)
        return await self._plan_legacy(screenshot, task, history)

    async def locate(
        self, screenshot: bytes, element_description: str
    ) -> tuple[int, int] | None:
        """Find coordinates of a UI element.

        GPT-5.4 supports this natively via computer use.
        Legacy models return None (no grounding).
        """
        if self._native_cu:
            b64 = base64.b64encode(screenshot).decode("utf-8")
            prompt = (
                f"Find the UI element: {element_description}\n"
                "Return JSON: {\"x\": 123, \"y\": 456} or {\"x\": null, \"y\": null}"
            )
            response = await self._responses_create(
                model=self._model,
                input=[{
                    "type": "message",
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{b64}",
                            "detail": "original",
                        },
                    ],
                }],
            )
            raw = self._extract_text(response)
            try:
                data = json.loads(_strip_markdown_fences(raw))
                x, y = data.get("x"), data.get("y")
                if x is not None and y is not None:
                    return (int(x), int(y))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        return None

    # ------------------------------------------------------------------
    # GPT-5.4 native computer use plan
    # ------------------------------------------------------------------

    async def _plan_native(
        self,
        screenshot: bytes,
        task: str,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Use GPT-5.4 Responses API with computer use tool."""
        # Build task context with history
        full_task = task
        if history:
            recent = history[-5:]
            steps_text = "\n".join(
                f"- Step {h.get('step', '?')}: {h.get('action', '?')} → {h.get('result', '?')}"
                for h in recent
            )
            full_task = f"{task}\n\nPrevious steps:\n{steps_text}"

        # Determine if this is a continuation or initial call
        call_id = None
        if history and self._previous_response_id:
            # We're continuing — need last call_id from history
            last = history[-1] if history else {}
            call_id = last.get("call_id")

        step_result = await self._computer_use_step(screenshot, full_task, call_id)

        # Extract computer_call actions
        cu_actions = self._extract_computer_calls(step_result.response)
        if cu_actions:
            # Return the first action (agent loop handles one at a time)
            mapped = self._map_cu_action(cu_actions[0])
            # Attach remaining actions for callers that want batch execution
            if len(cu_actions) > 1:
                mapped["_remaining_actions"] = [
                    self._map_cu_action(a) for a in cu_actions[1:]
                ]
            return mapped

        # No computer_call — model is done or gave text response
        text = self._extract_text(step_result.response)
        return {
            "reasoning": text or "Task completed",
            "action": {"action_type": "wait", "seconds": 0},
            "done": True,
            "confidence": 1.0,
            "data": {"response": text},
        }

    @staticmethod
    def _map_cu_action(cu: dict[str, Any]) -> dict[str, Any]:
        """Map GPT-5.4 computer_call action to VisionBackend plan format."""
        action_type = cu["action_type"]
        action: dict[str, Any] = {"action_type": action_type}

        if action_type in ("click", "double_click", "right_click"):
            action["coordinates"] = [cu["x"], cu["y"]]
            button = cu.get("button", "left")
            if action_type == "right_click" or button == "right":
                action["action_type"] = "click"
                action["button"] = "right"
            elif action_type == "double_click":
                action["action_type"] = "double_click"
            elif button and button != "left":
                action["button"] = button
        elif action_type == "type":
            action["text"] = cu.get("text", "")
        elif action_type == "keypress":
            action["action_type"] = "hotkey"
            action["keys"] = cu.get("keys", [])
        elif action_type == "scroll":
            action["coordinates"] = [cu.get("x", 0), cu.get("y", 0)]
            scroll_y = cu.get("scroll_y", 0)
            # Map scroll_y to clicks: negative scroll_y = scroll down = negative clicks,
            # positive scroll_y = scroll up = positive clicks.
            # GPT-5.4 uses pixel deltas; convert to discrete clicks (120px per click).
            action["clicks"] = scroll_y // 120 if abs(scroll_y) >= 120 else (
                -1 if scroll_y < 0 else (1 if scroll_y > 0 else 0)
            )
        elif action_type == "drag":
            path = cu.get("path") or []
            if len(path) >= 2:
                start = path[0]
                end = path[-1]
                action["start_x"] = start.get("x", 0) if isinstance(start, dict) else getattr(start, "x", 0)
                action["start_y"] = start.get("y", 0) if isinstance(start, dict) else getattr(start, "y", 0)
                action["end_x"] = end.get("x", 0) if isinstance(end, dict) else getattr(end, "x", 0)
                action["end_y"] = end.get("y", 0) if isinstance(end, dict) else getattr(end, "y", 0)
            else:
                # Fallback: no valid path, use zero coordinates
                action["start_x"] = 0
                action["start_y"] = 0
                action["end_x"] = 0
                action["end_y"] = 0
        elif action_type == "move":
            action["coordinates"] = [cu.get("x", 0), cu.get("y", 0)]
        elif action_type == "screenshot":
            action["action_type"] = "screenshot"
        elif action_type == "wait":
            action["seconds"] = 1

        return {
            "reasoning": f"computer_use: {action_type}",
            "action": action,
            "done": False,
            "confidence": 0.9,
            "call_id": cu.get("call_id"),
        }

    # ------------------------------------------------------------------
    # Legacy chat completions path (GPT-4o, etc.)
    # ------------------------------------------------------------------

    @backoff.on_exception(backoff.expo, RateLimitError, max_tries=5)
    async def _chat_call(
        self, messages: list[dict], temperature: float = 0.0
    ) -> str:
        """Call Chat Completions API with retry on rate limits."""
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            max_tokens=self._max_tokens,
            temperature=temperature,
        )
        return response.choices[0].message.content or ""

    def _encode_image(self, screenshot: bytes) -> str:
        return base64.b64encode(screenshot).decode("utf-8")

    def _make_image_content(
        self, screenshot: bytes, text: str
    ) -> list[dict[str, Any]]:
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

    async def _observe_legacy(
        self, screenshot: bytes, context: str = ""
    ) -> dict[str, Any]:
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
        raw = await self._chat_call(messages)

        try:
            result = json.loads(_strip_markdown_fences(raw))
        except json.JSONDecodeError:
            logger.warning("Failed to parse observe response: %s", raw[:200])
            result = {"description": raw, "elements": []}
        return result

    async def _plan_legacy(
        self,
        screenshot: bytes,
        task: str,
        history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
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
        raw = await self._chat_call(messages)

        try:
            result = json.loads(_strip_markdown_fences(raw))
        except json.JSONDecodeError:
            logger.warning("Failed to parse plan response: %s", raw[:200])
            result = {
                "action": {"action_type": "wait", "seconds": 1},
                "reasoning": raw,
                "done": False,
                "confidence": 0.0,
            }
        return result


def _strip_markdown_fences(text: str) -> str:
    """Strip ```json ... ``` markdown fences from VLM responses."""
    stripped = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    stripped = re.sub(r"\n?```\s*$", "", stripped)
    return stripped.strip()
