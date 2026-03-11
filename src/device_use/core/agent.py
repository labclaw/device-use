"""DeviceAgent — OBSERVE → PLAN → ACT → VERIFY loop.

The core orchestrator that ties together observation, planning, safety,
and action execution into a coherent agent loop.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from pyautogui import FailSafeException as _FailSafeException

from device_use.actions.executor import ActionExecutor
from device_use.actions.models import parse_action
from device_use.actions.scaling import CoordinateScaler
from device_use.backends.base import VisionBackend
from device_use.core.history import AgentHistory, HistoryEntry
from device_use.core.models import ActionResult, DeviceProfile
from device_use.core.prompts import PromptBuilder
from device_use.core.result import AgentResult
from device_use.safety.guard import SafetyGuard

logger = logging.getLogger(__name__)

DEFAULT_MAX_STEPS = 30


class DeviceAgent:
    """GUI agent that operates instrument/scientific software.

    Implements the OBSERVE → PLAN → ACT → VERIFY loop:
    1. OBSERVE: Capture screenshot, get VLM understanding
    2. PLAN: VLM plans next action based on task + observation
    3. SAFETY: SafetyGuard checks the planned action
    4. ACT: Execute via pyautogui
    5. VERIFY: Capture new screenshot, check result
    6. UPDATE: Add to history, compact old images
    """

    def __init__(
        self,
        profile: DeviceProfile,
        backend: VisionBackend,
        observer: Any | None = None,
        max_steps: int = DEFAULT_MAX_STEPS,
        max_images: int = 5,
    ):
        self._profile = profile
        self._backend = backend
        self._observer = observer
        self._max_steps = max_steps
        self._prompts = PromptBuilder(profile)
        self._history = AgentHistory(max_images=max_images)
        self._safety = SafetyGuard(profile, auto_approve=False)

        # Pass system prompt to backend if it supports it
        if hasattr(backend, "system_prompt"):
            backend.system_prompt = self._prompts.system_prompt()

        # VLM sees screenshots scaled to 1280px max width (observer default)
        vlm_max_width = 1280
        aspect = profile.screen.height / profile.screen.width if profile.screen.width else 1.0
        vlm_height = int(vlm_max_width * aspect)
        self._scaler = CoordinateScaler(
            vlm_width=vlm_max_width,
            vlm_height=vlm_height,
            screen_width=profile.screen.width,
            screen_height=profile.screen.height,
        )
        self._executor = ActionExecutor(
            safety_guard=self._safety,
            scaler=self._scaler,
            settle_delay=2.0,
        )

    async def execute(self, task: str) -> AgentResult:
        """Execute a task on the instrument software.

        Args:
            task: Natural language description of what to do.

        Returns:
            AgentResult with success/failure, actions taken, timing.
        """
        logger.info("Starting task: %s (profile: %s)", task, self._profile.name)
        start_time = time.monotonic()
        all_actions: list[ActionResult] = []
        consecutive_parse_failures = 0
        max_parse_failures = 3

        try:
            for step in range(self._max_steps):
                logger.info("Step %d/%d", step + 1, self._max_steps)

                # OBSERVE
                screenshot = await self._capture_screenshot()
                observation = await self._observe(screenshot, task, step)

                # PLAN
                plan = await self._plan(screenshot, task, step)

                # Check if task is done
                if plan.get("done", False):
                    logger.info("Task completed at step %d", step + 1)
                    return AgentResult(
                        success=True,
                        task=task,
                        data=plan.get("data", {}),
                        actions=all_actions,
                        steps=step + 1,
                        duration_ms=(time.monotonic() - start_time) * 1000,
                        final_screenshot=screenshot,
                    )

                # Check for failure
                if plan.get("error"):
                    logger.error("Task failed: %s", plan["error"])
                    return AgentResult(
                        success=False,
                        task=task,
                        error=plan["error"],
                        actions=all_actions,
                        steps=step + 1,
                        duration_ms=(time.monotonic() - start_time) * 1000,
                    )

                # ACT (safety is enforced inside executor)
                action_data = plan.get("action", {})
                try:
                    action = parse_action(action_data)
                    consecutive_parse_failures = 0
                except (ValueError, KeyError, TypeError) as e:
                    consecutive_parse_failures += 1
                    logger.error(
                        "Failed to parse action (%d/%d): %s",
                        consecutive_parse_failures, max_parse_failures, e,
                    )
                    self._history.add(HistoryEntry(
                        step=step,
                        action=action_data,
                        observation=observation,
                        reasoning=plan.get("reasoning", ""),
                        screenshot=screenshot,
                        success=False,
                        call_id=plan.get("call_id"),
                    ))
                    self._history.compact()
                    if consecutive_parse_failures >= max_parse_failures:
                        return AgentResult(
                            success=False,
                            task=task,
                            error=f"Too many consecutive parse failures ({max_parse_failures})",
                            actions=all_actions,
                            steps=step + 1,
                            duration_ms=(time.monotonic() - start_time) * 1000,
                        )
                    continue

                result = self._executor.execute(action)
                all_actions.append(result)

                # VERIFY
                verify_screenshot = await self._capture_screenshot()

                # UPDATE history
                self._history.add(HistoryEntry(
                    step=step,
                    action=action_data,
                    observation=observation,
                    reasoning=plan.get("reasoning", ""),
                    screenshot=verify_screenshot,
                    success=result.success,
                    call_id=plan.get("call_id"),
                ))
                self._history.compact()

                if not result.success:
                    logger.warning(
                        "Action failed at step %d: %s", step + 1, result.error
                    )

            # Max steps reached
            logger.warning("Max steps (%d) reached", self._max_steps)
            return AgentResult(
                success=False,
                task=task,
                error=f"Max steps ({self._max_steps}) reached without completion",
                actions=all_actions,
                steps=self._max_steps,
                duration_ms=(time.monotonic() - start_time) * 1000,
            )

        except _FailSafeException:
            # Physical emergency stop — MUST propagate to caller
            raise

        except Exception as e:
            logger.exception("Agent execution error")
            return AgentResult(
                success=False,
                task=task,
                error=str(e),
                actions=all_actions,
                steps=len(all_actions),
                duration_ms=(time.monotonic() - start_time) * 1000,
            )

    async def _capture_screenshot(self) -> bytes:
        """Capture screenshot via observer or return placeholder."""
        if self._observer is not None:
            window_id = self._profile.metadata.get("window_id")
            if window_id is None:
                logger.warning("No window_id in profile metadata, capturing full screen")
                return self._observer.capture_full_screen()
            return self._observer.capture_and_scale(window_id=str(window_id))
        return b""

    async def _observe(self, screenshot: bytes, task: str, step: int) -> str:
        """Get VLM observation of current screen state."""
        if not screenshot:
            return "No screenshot available"
        context = self._prompts.observation_prompt(task, step)
        result = await self._backend.observe(screenshot, context)
        return result.get("description", "")

    async def _plan(self, screenshot: bytes, task: str, step: int) -> dict[str, Any]:
        """Get VLM plan for next action."""
        history_entries = [
            {
                "step": e.step,
                "action": e.action,
                "result": "success" if e.success else "failed",
                "observation": e.observation[:200],
                "call_id": e.call_id,
            }
            for e in self._history.entries
        ]

        if not screenshot:
            return {"done": False, "error": "No screenshot — cannot plan"}

        return await self._backend.plan(screenshot, task, history_entries)

    @property
    def history(self) -> AgentHistory:
        return self._history

    @property
    def profile(self) -> DeviceProfile:
        return self._profile
