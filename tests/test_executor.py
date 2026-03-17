"""Tests for the action executor — all dispatch paths and safety integration."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import device_use.actions.executor as executor_mod
from device_use.actions.executor import ActionExecutor
from device_use.actions.models import (
    ClickAction,
    DoubleClickAction,
    DragAction,
    HotkeyAction,
    MoveAction,
    RightClickAction,
    ScreenshotAction,
    ScrollAction,
    TypeAction,
    WaitAction,
)
from device_use.safety.guard import SafetyGuard
from device_use.safety.models import SafetyVerdict


@pytest.fixture(autouse=True)
def _ensure_mock_gui():
    """Ensure executor has mock pyautogui/pyperclip for all tests in this module."""
    orig_pag = executor_mod._pyautogui
    orig_clip = executor_mod._pyperclip
    orig_fail = executor_mod._FailSafeException

    mock_pag = MagicMock()
    mock_clip = MagicMock()

    class _FakeFailSafeError(Exception):
        pass

    mock_pag.FailSafeException = _FakeFailSafeError

    executor_mod._pyautogui = mock_pag
    executor_mod._pyperclip = mock_clip
    executor_mod._FailSafeException = _FakeFailSafeError

    yield mock_pag, mock_clip, _FakeFailSafeError

    executor_mod._pyautogui = orig_pag
    executor_mod._pyperclip = orig_clip
    executor_mod._FailSafeException = orig_fail


class TestActionExecutorDispatch:
    """Test every action type dispatch path."""

    def _make_executor(self):
        return ActionExecutor(settle_delay=0)

    def test_click(self, _ensure_mock_gui):
        mock_pag, _, _ = _ensure_mock_gui
        ex = self._make_executor()
        action = ClickAction(x=100, y=200, description="btn")
        result = ex.execute(action)
        assert result.success is True
        mock_pag.click.assert_called_once_with(100, 200, button="left")

    def test_double_click(self, _ensure_mock_gui):
        mock_pag, _, _ = _ensure_mock_gui
        ex = self._make_executor()
        action = DoubleClickAction(x=50, y=60, description="icon")
        result = ex.execute(action)
        assert result.success is True
        mock_pag.doubleClick.assert_called_once_with(50, 60)

    def test_right_click(self, _ensure_mock_gui):
        mock_pag, _, _ = _ensure_mock_gui
        ex = self._make_executor()
        action = RightClickAction(x=10, y=20, description="context")
        result = ex.execute(action)
        assert result.success is True
        mock_pag.rightClick.assert_called_once_with(10, 20)

    def test_type_ascii(self, _ensure_mock_gui):
        mock_pag, _, _ = _ensure_mock_gui
        ex = self._make_executor()
        action = TypeAction(text="hello", description="input")
        result = ex.execute(action)
        assert result.success is True
        mock_pag.write.assert_called_once()

    def test_type_unicode(self, _ensure_mock_gui):
        mock_pag, mock_clip, _ = _ensure_mock_gui
        ex = self._make_executor()
        action = TypeAction(text="25\u00b0C", description="temp")
        result = ex.execute(action)
        assert result.success is True
        mock_clip.copy.assert_called_once_with("25\u00b0C")
        mock_pag.hotkey.assert_called_once_with("ctrl", "v")

    def test_hotkey(self, _ensure_mock_gui):
        mock_pag, _, _ = _ensure_mock_gui
        ex = self._make_executor()
        action = HotkeyAction(keys=["ctrl", "s"], description="save")
        result = ex.execute(action)
        assert result.success is True
        mock_pag.hotkey.assert_called_once_with("ctrl", "s")

    def test_scroll(self, _ensure_mock_gui):
        mock_pag, _, _ = _ensure_mock_gui
        ex = self._make_executor()
        action = ScrollAction(x=500, y=500, clicks=3, description="scroll")
        result = ex.execute(action)
        assert result.success is True
        mock_pag.scroll.assert_called_once_with(3, x=500, y=500)

    def test_drag(self, _ensure_mock_gui):
        mock_pag, _, _ = _ensure_mock_gui
        ex = self._make_executor()
        action = DragAction(start_x=10, start_y=20, end_x=100, end_y=200, description="drag")
        result = ex.execute(action)
        assert result.success is True
        mock_pag.moveTo.assert_called_once_with(10, 20)
        mock_pag.drag.assert_called_once()

    def test_wait(self, _ensure_mock_gui):
        ex = self._make_executor()
        action = WaitAction(seconds=0.001, description="wait")
        result = ex.execute(action)
        assert result.success is True

    def test_screenshot(self, _ensure_mock_gui):
        ex = self._make_executor()
        action = ScreenshotAction(description="capture")
        result = ex.execute(action)
        assert result.success is True

    def test_move(self, _ensure_mock_gui):
        mock_pag, _, _ = _ensure_mock_gui
        ex = self._make_executor()
        action = MoveAction(x=300, y=400, description="hover")
        result = ex.execute(action)
        assert result.success is True
        mock_pag.moveTo.assert_called_once_with(300, 400)

    def test_unknown_action_type(self, _ensure_mock_gui):
        ex = self._make_executor()
        # Create a mock action with an unknown type — fails at ActionRequest
        # validation (pydantic rejects the unknown action_type)
        action = MagicMock()
        action.action_type = "unknown"
        action.description = "bad"
        from pydantic import ValidationError

        with pytest.raises(ValidationError, match="action_type"):
            ex.execute(action)


class TestActionExecutorSafety:
    def test_action_blocked_by_safety(self, _ensure_mock_gui):
        guard = MagicMock(spec=SafetyGuard)
        guard.check.return_value = SafetyVerdict(
            allowed=False, layer="rate_limit", reason="Too fast"
        )
        ex = ActionExecutor(safety_guard=guard, settle_delay=0)
        action = ClickAction(x=10, y=20, description="btn")
        result = ex.execute(action)
        assert result.success is False
        assert "rate_limit" in result.error
        guard.record_action.assert_not_called()

    def test_action_allowed_by_safety(self, _ensure_mock_gui):
        guard = MagicMock(spec=SafetyGuard)
        guard.check.return_value = SafetyVerdict(allowed=True)
        ex = ActionExecutor(safety_guard=guard, settle_delay=0)
        action = WaitAction(seconds=0.001, description="wait")
        result = ex.execute(action)
        assert result.success is True
        guard.record_action.assert_called_once()


class TestActionExecutorScaling:
    def test_with_scaler(self, _ensure_mock_gui):
        mock_pag, _, _ = _ensure_mock_gui
        scaler = MagicMock()
        scaler.vlm_to_screen.return_value = (200, 400)
        ex = ActionExecutor(scaler=scaler, settle_delay=0)
        action = ClickAction(x=100, y=200, description="scaled")
        result = ex.execute(action)
        assert result.success is True
        mock_pag.click.assert_called_once_with(200, 400, button="left")


class TestActionExecutorFailSafe:
    def test_failsafe_propagates(self, _ensure_mock_gui):
        mock_pag, _, fake_failsafe = _ensure_mock_gui
        mock_pag.click.side_effect = fake_failsafe("Emergency stop")
        ex = ActionExecutor(settle_delay=0)
        action = ClickAction(x=0, y=0, description="corner")
        with pytest.raises(fake_failsafe):
            ex.execute(action)


class TestActionToRequest:
    def test_click_action_to_request(self, _ensure_mock_gui):
        ex = ActionExecutor(settle_delay=0)
        action = ClickAction(x=10, y=20, description="btn")
        req = ex._action_to_request(action)
        assert req.coordinates == (10, 20)

    def test_type_action_to_request(self, _ensure_mock_gui):
        ex = ActionExecutor(settle_delay=0)
        action = TypeAction(text="hello", description="input")
        req = ex._action_to_request(action)
        assert req.parameters["text"] == "hello"

    def test_hotkey_action_to_request(self, _ensure_mock_gui):
        ex = ActionExecutor(settle_delay=0)
        action = HotkeyAction(keys=["ctrl", "s"], description="save")
        req = ex._action_to_request(action)
        assert req.parameters["keys"] == ["ctrl", "s"]

    def test_scroll_action_to_request(self, _ensure_mock_gui):
        ex = ActionExecutor(settle_delay=0)
        action = ScrollAction(x=500, y=500, clicks=3, description="scroll")
        req = ex._action_to_request(action)
        assert req.coordinates == (500, 500)
        assert req.parameters["clicks"] == 3

    def test_drag_action_to_request(self, _ensure_mock_gui):
        ex = ActionExecutor(settle_delay=0)
        action = DragAction(start_x=10, start_y=20, end_x=100, end_y=200, description="drag")
        req = ex._action_to_request(action)
        assert req.coordinates == (10, 20)

    def test_wait_action_to_request(self, _ensure_mock_gui):
        ex = ActionExecutor(settle_delay=0)
        action = WaitAction(seconds=1.0, description="wait")
        req = ex._action_to_request(action)
        assert req.parameters["seconds"] == 1.0

    def test_move_action_to_request(self, _ensure_mock_gui):
        ex = ActionExecutor(settle_delay=0)
        action = MoveAction(x=300, y=400, description="hover")
        req = ex._action_to_request(action)
        assert req.coordinates == (300, 400)
