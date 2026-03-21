"""Tests for action models, coordinate scaling, and executor."""

from unittest.mock import MagicMock, patch

import pytest

from device_use.actions.executor import ActionExecutor
from device_use.actions.models import (
    ClickAction,
    DragAction,
    HotkeyAction,
    ScrollAction,
    TypeAction,
    WaitAction,
    parse_action,
)
from device_use.actions.scaling import CoordinateScaler
from device_use.core.models import ActionType

# --- Coordinate Scaling ---


class TestCoordinateScaler:
    def test_identity_scaling(self):
        """Same VLM and screen size → no scaling."""
        scaler = CoordinateScaler(
            vlm_width=1280,
            vlm_height=800,
            screen_width=1280,
            screen_height=800,
        )
        assert scaler.vlm_to_screen(100, 200) == (100, 200)
        assert scaler.screen_to_vlm(100, 200) == (100, 200)

    def test_2x_scaling(self):
        """VLM 1280x800, screen 2560x1600 → 2x scale."""
        scaler = CoordinateScaler(
            vlm_width=1280,
            vlm_height=800,
            screen_width=2560,
            screen_height=1600,
        )
        assert scaler.vlm_to_screen(100, 100) == (200, 200)
        assert scaler.screen_to_vlm(200, 200) == (100, 100)

    def test_window_offset(self):
        """Window at (100, 50) → adds offset to screen coords."""
        scaler = CoordinateScaler(
            vlm_width=1280,
            vlm_height=800,
            screen_width=1280,
            screen_height=800,
            window_x=100,
            window_y=50,
        )
        assert scaler.vlm_to_screen(0, 0) == (100, 50)
        assert scaler.vlm_to_screen(100, 100) == (200, 150)
        assert scaler.screen_to_vlm(100, 50) == (0, 0)

    def test_scaling_with_offset(self):
        """Combined 1.5x scale + window offset."""
        scaler = CoordinateScaler(
            vlm_width=1280,
            vlm_height=800,
            screen_width=1920,
            screen_height=1200,
            window_x=50,
            window_y=30,
        )
        sx, sy = scaler.vlm_to_screen(100, 100)
        # 100 * (1920/1280) + 50 = 150 + 50 = 200
        assert sx == 200
        # 100 * (1200/800) + 30 = 150 + 30 = 180
        assert sy == 180

    def test_roundtrip(self):
        """VLM→screen→VLM should approximately preserve coordinates."""
        scaler = CoordinateScaler(
            vlm_width=1280,
            vlm_height=800,
            screen_width=1920,
            screen_height=1080,
            window_x=100,
            window_y=50,
        )
        for vx, vy in [(0, 0), (640, 400), (1279, 799)]:
            sx, sy = scaler.vlm_to_screen(vx, vy)
            rx, ry = scaler.screen_to_vlm(sx, sy)
            assert abs(rx - vx) <= 1
            assert abs(ry - vy) <= 1

    def test_zero_vlm_dims_raises(self):
        with pytest.raises(ValueError, match="VLM dimensions"):
            CoordinateScaler(vlm_width=0, vlm_height=800, screen_width=1920, screen_height=1080)

    def test_zero_screen_dims_raises(self):
        with pytest.raises(ValueError, match="Screen dimensions"):
            CoordinateScaler(vlm_width=1280, vlm_height=800, screen_width=0, screen_height=1080)

    def test_clamp_screen(self):
        """Clamping keeps coordinates within window bounds."""
        scaler = CoordinateScaler(
            vlm_width=1280,
            vlm_height=800,
            screen_width=800,
            screen_height=600,
            window_x=100,
            window_y=50,
        )
        # Below window
        assert scaler.clamp_screen(0, 0) == (100, 50)
        # Above window
        assert scaler.clamp_screen(2000, 2000) == (899, 649)
        # Inside window
        assert scaler.clamp_screen(500, 300) == (500, 300)


# --- Action Models ---


class TestActionModels:
    def test_click_action(self):
        a = ClickAction(x=100, y=200)
        assert a.action_type == ActionType.CLICK
        assert a.button == "left"

    def test_type_action(self):
        a = TypeAction(text="hello world")
        assert a.text == "hello world"
        assert a.interval == 0.02

    def test_hotkey_action(self):
        a = HotkeyAction(keys=["ctrl", "s"])
        assert a.keys == ["ctrl", "s"]

    def test_drag_action(self):
        a = DragAction(start_x=0, start_y=0, end_x=100, end_y=100)
        assert a.duration == 0.5

    def test_wait_action(self):
        a = WaitAction(seconds=2.5)
        assert a.seconds == 2.5

    def test_parse_click(self):
        action = parse_action({"action_type": "click", "x": 10, "y": 20})
        assert isinstance(action, ClickAction)
        assert action.x == 10

    def test_parse_type(self):
        action = parse_action({"action_type": "type", "text": "hello"})
        assert isinstance(action, TypeAction)

    def test_parse_unknown_raises(self):
        with pytest.raises(ValueError):
            parse_action({"action_type": "fly"})

    def test_parse_nested_parameters(self):
        """VLM returns fields nested under 'parameters' dict."""
        action = parse_action(
            {
                "action_type": "type",
                "parameters": {"text": "hello"},
            }
        )
        assert isinstance(action, TypeAction)
        assert action.text == "hello"

    def test_parse_nested_parameters_with_coordinates(self):
        """VLM returns coordinates + parameters nested."""
        action = parse_action(
            {
                "action_type": "scroll",
                "coordinates": [100, 200],
                "parameters": {"clicks": -3},
            }
        )
        assert isinstance(action, ScrollAction)
        assert action.x == 100
        assert action.y == 200
        assert action.clicks == -3

    def test_click_button_literal(self):
        """ClickAction.button only accepts left, right, middle."""
        a = ClickAction(x=0, y=0, button="right")
        assert a.button == "right"
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            ClickAction(x=0, y=0, button="invalid")


# --- Executor (with mocked pyautogui) ---


class TestActionExecutor:
    @patch("device_use.actions.executor._pyautogui")
    def test_click_execution(self, mock_pyautogui):
        executor = ActionExecutor(settle_delay=0)
        action = ClickAction(x=100, y=200)
        result = executor.execute(action)
        assert result.success is True
        mock_pyautogui.click.assert_called_once_with(100, 200, button="left")

    @patch("device_use.actions.executor._pyautogui")
    def test_type_execution_ascii(self, mock_pyautogui):
        executor = ActionExecutor(settle_delay=0)
        action = TypeAction(text="hello")
        result = executor.execute(action)
        assert result.success is True
        mock_pyautogui.write.assert_called_once_with("hello", interval=0.02)

    @patch("device_use.actions.executor._pyperclip")
    @patch("device_use.actions.executor._pyautogui")
    def test_type_execution_unicode(self, mock_pyautogui, mock_pyperclip):
        executor = ActionExecutor(settle_delay=0)
        action = TypeAction(text="温度 25°C")
        result = executor.execute(action)
        assert result.success is True
        mock_pyperclip.copy.assert_called_once_with("温度 25°C")
        mock_pyautogui.hotkey.assert_called_once_with("ctrl", "v")

    @patch("device_use.actions.executor._pyautogui")
    def test_hotkey_execution(self, mock_pyautogui):
        executor = ActionExecutor(settle_delay=0)
        action = HotkeyAction(keys=["ctrl", "c"])
        result = executor.execute(action)
        assert result.success is True
        mock_pyautogui.hotkey.assert_called_once_with("ctrl", "c")

    @patch("device_use.actions.executor._pyautogui")
    def test_scroll_execution(self, mock_pyautogui):
        executor = ActionExecutor(settle_delay=0)
        action = ScrollAction(x=100, y=200, clicks=-3)
        result = executor.execute(action)
        assert result.success is True
        mock_pyautogui.scroll.assert_called_once_with(-3, x=100, y=200)

    @patch("device_use.actions.executor._pyautogui")
    def test_wait_execution(self, mock_pyautogui):
        executor = ActionExecutor(settle_delay=0)
        action = WaitAction(seconds=0.01)
        result = executor.execute(action)
        assert result.success is True

    @patch("device_use.actions.executor._pyautogui")
    def test_execution_with_scaler(self, mock_pyautogui):
        scaler = CoordinateScaler(
            vlm_width=1280,
            vlm_height=800,
            screen_width=1920,
            screen_height=1200,
            window_x=50,
            window_y=30,
        )
        executor = ActionExecutor(scaler=scaler, settle_delay=0)
        action = ClickAction(x=100, y=100)
        result = executor.execute(action)
        assert result.success is True
        # 100 * (1920/1280) + 50 = 200
        # 100 * (1200/800) + 30 = 180
        mock_pyautogui.click.assert_called_once_with(200, 180, button="left")

    @patch("device_use.actions.executor._FailSafeException", type("MockFailSafe", (Exception,), {}))
    @patch("device_use.actions.executor._pyautogui")
    def test_execution_failure(self, mock_pyautogui):
        mock_pyautogui.click.side_effect = RuntimeError("Display not found")
        executor = ActionExecutor(settle_delay=0)
        action = ClickAction(x=100, y=200)
        result = executor.execute(action)
        assert result.success is False
        assert "Display not found" in result.error

    @patch("device_use.actions.executor._pyautogui")
    def test_safety_blocks_action(self, mock_pyautogui):
        from device_use.safety.models import SafetyVerdict

        mock_guard = MagicMock()
        mock_guard.check.return_value = SafetyVerdict(
            allowed=False, layer="L1_whitelist", reason="Action not in whitelist"
        )
        executor = ActionExecutor(safety_guard=mock_guard, settle_delay=0)
        action = ClickAction(x=100, y=200)
        result = executor.execute(action)
        assert result.success is False
        assert "L1_whitelist" in result.error
        mock_pyautogui.click.assert_not_called()

    @patch("device_use.actions.executor._pyautogui")
    def test_safety_allows_action(self, mock_pyautogui):
        from device_use.safety.models import SafetyVerdict

        mock_guard = MagicMock()
        mock_guard.check.return_value = SafetyVerdict(allowed=True)
        executor = ActionExecutor(safety_guard=mock_guard, settle_delay=0)
        action = ClickAction(x=100, y=200)
        result = executor.execute(action)
        assert result.success is True
        mock_guard.record_action.assert_called_once()

    @patch("device_use.actions.executor._pyautogui")
    def test_duration_tracking(self, mock_pyautogui):
        executor = ActionExecutor(settle_delay=0)
        action = ClickAction(x=100, y=200)
        result = executor.execute(action)
        assert result.duration_ms >= 0

    @patch("device_use.actions.executor._pyautogui")
    def test_failsafe_exception_propagates(self, mock_pyautogui):
        """pyautogui.FailSafeException must propagate (physical e-stop)."""
        import device_use.actions.executor as _executor_mod

        # Create a custom exception to stand in for FailSafeException
        class _MockFailSafeError(Exception):
            pass

        mock_pyautogui.click.side_effect = _MockFailSafeError("corner")
        # Patch the module-level sentinel so the except clause recognises it
        _executor_mod._FailSafeException = _MockFailSafeError
        executor = ActionExecutor(settle_delay=0)
        action = ClickAction(x=100, y=200)
        with pytest.raises(_MockFailSafeError):
            executor.execute(action)

    @patch("device_use.actions.executor._pyautogui")
    def test_scaled_coords_in_safety_request(self, mock_pyautogui):
        """Safety check receives screen-space coordinates, not VLM-space."""
        from device_use.safety.models import SafetyVerdict

        scaler = CoordinateScaler(
            vlm_width=1280,
            vlm_height=800,
            screen_width=2560,
            screen_height=1600,
        )
        mock_guard = MagicMock()
        mock_guard.check.return_value = SafetyVerdict(allowed=True)
        executor = ActionExecutor(safety_guard=mock_guard, scaler=scaler, settle_delay=0)
        action = ClickAction(x=100, y=100)
        executor.execute(action)
        # The ActionRequest passed to safety should have scaled coords
        request = mock_guard.check.call_args[0][0]
        assert request.coordinates == (200, 200)  # 100*2 = 200
