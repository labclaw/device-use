"""Action executor — pyautogui execution with safety checks.

Safety is wired here, not in the agent loop — actions physically cannot
bypass safety. Every action goes through: safety check → coordinate
scaling → pyautogui execution → result.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import pyautogui
from pyautogui import FailSafeException as _FailSafeException
import pyperclip

from device_use.actions.models import (
    Action,
    ClickAction,
    DoubleClickAction,
    DragAction,
    HotkeyAction,
    RightClickAction,
    ScreenshotAction,
    ScrollAction,
    TypeAction,
    WaitAction,
)
from device_use.actions.scaling import CoordinateScaler
from device_use.core.models import ActionRequest, ActionResult, ActionType

if TYPE_CHECKING:
    from device_use.safety.guard import SafetyGuard

logger = logging.getLogger(__name__)

# Anthropic computer-use pattern: wait for UI to settle after action
UI_SETTLE_DELAY = 2.0

# Disable pyautogui failsafe in production (we have our own safety)
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1


class ActionExecutor:
    """Execute GUI actions via pyautogui with safety checks.

    Every action passes through SafetyGuard before execution.
    Coordinates are scaled from VLM space to screen space.
    """

    def __init__(
        self,
        safety_guard: SafetyGuard | None = None,
        scaler: CoordinateScaler | None = None,
        settle_delay: float = UI_SETTLE_DELAY,
    ):
        self._safety = safety_guard
        self._scaler = scaler
        self._settle_delay = settle_delay

    def execute(self, action: Action) -> ActionResult:
        """Execute a GUI action with safety checks.

        Returns ActionResult with success/failure and timing.
        """
        # Build ActionRequest for safety check
        request = self._action_to_request(action)

        # Safety gate
        if self._safety is not None:
            verdict = self._safety.check(request)
            if not verdict.allowed:
                logger.warning(
                    "Action blocked by safety %s: %s", verdict.layer, verdict.reason
                )
                return ActionResult(
                    success=False,
                    action=request,
                    error=f"Blocked by {verdict.layer}: {verdict.reason}",
                )

        # Record attempt in safety history (counts all attempts, not just successes)
        if self._safety is not None:
            self._safety.record_action(request)

        # Execute
        start = time.monotonic()
        try:
            self._dispatch(action)
            duration_ms = (time.monotonic() - start) * 1000

            # Settle delay (UI needs time to respond)
            if not isinstance(action, WaitAction):
                time.sleep(self._settle_delay)

            return ActionResult(
                success=True, action=request, duration_ms=duration_ms
            )

        except _FailSafeException:
            # Physical emergency stop (mouse moved to corner) — MUST propagate
            raise

        except Exception as e:
            duration_ms = (time.monotonic() - start) * 1000
            logger.error("Action execution failed: %s", e)
            return ActionResult(
                success=False,
                action=request,
                error=str(e),
                duration_ms=duration_ms,
            )

    def _dispatch(self, action: Action) -> None:
        """Dispatch action to appropriate pyautogui call."""
        if isinstance(action, ClickAction):
            x, y = self._scale(action.x, action.y)
            pyautogui.click(x, y, button=action.button)

        elif isinstance(action, DoubleClickAction):
            x, y = self._scale(action.x, action.y)
            pyautogui.doubleClick(x, y)

        elif isinstance(action, RightClickAction):
            x, y = self._scale(action.x, action.y)
            pyautogui.rightClick(x, y)

        elif isinstance(action, TypeAction):
            if action.text.isascii():
                pyautogui.write(action.text, interval=action.interval)
            else:
                # Clipboard paste for Unicode (CJK, µm, °C, etc.)
                pyperclip.copy(action.text)
                pyautogui.hotkey("ctrl", "v")

        elif isinstance(action, HotkeyAction):
            pyautogui.hotkey(*action.keys)

        elif isinstance(action, ScrollAction):
            x, y = self._scale(action.x, action.y)
            pyautogui.scroll(action.clicks, x=x, y=y)

        elif isinstance(action, DragAction):
            sx, sy = self._scale(action.start_x, action.start_y)
            ex, ey = self._scale(action.end_x, action.end_y)
            pyautogui.moveTo(sx, sy)
            pyautogui.drag(
                ex - sx, ey - sy, duration=action.duration, button="left"
            )

        elif isinstance(action, WaitAction):
            time.sleep(action.seconds)

        elif isinstance(action, ScreenshotAction):
            pass  # No-op — screenshot is captured by the agent loop

        else:
            raise ValueError(f"Unknown action type: {type(action)}")

    def _scale(self, x: int, y: int) -> tuple[int, int]:
        """Scale VLM coordinates to screen coordinates."""
        if self._scaler is not None:
            return self._scaler.vlm_to_screen(x, y)
        return x, y

    def _action_to_request(self, action: Action) -> ActionRequest:
        """Convert typed Action to ActionRequest for safety checking.

        Coordinates are scaled to screen space so safety checks
        (e.g. forbidden regions) compare against screen-space coordinates.
        """
        coords = None
        params = {}

        if isinstance(action, (ClickAction, DoubleClickAction, RightClickAction)):
            coords = self._scale(action.x, action.y)
        elif isinstance(action, TypeAction):
            params = {"text": action.text}
        elif isinstance(action, HotkeyAction):
            params = {"keys": action.keys}
        elif isinstance(action, ScrollAction):
            coords = self._scale(action.x, action.y)
            params = {"clicks": action.clicks}
        elif isinstance(action, DragAction):
            coords = self._scale(action.start_x, action.start_y)
            ex, ey = self._scale(action.end_x, action.end_y)
            params = {"end_x": ex, "end_y": ey}
        elif isinstance(action, WaitAction):
            params = {"seconds": action.seconds}

        return ActionRequest(
            action_type=action.action_type,
            target=action.description,
            coordinates=coords,
            parameters=params,
            description=action.description,
        )
