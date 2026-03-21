"""Edge case tests across actions/models, actions/scaling, core/models, and safety/models.

These tests target unusual inputs, boundary conditions, and graceful degradation
to improve coverage of defensive code paths.
"""

from __future__ import annotations

import pytest

from device_use.actions.models import (
    ClickAction,
    DragAction,
    HotkeyAction,
    ScreenshotAction,
    ScrollAction,
    TypeAction,
    WaitAction,
    parse_action,
)
from device_use.actions.scaling import CoordinateScaler
from device_use.core.models import (
    ActionRequest,
    ActionResult,
    ActionType,
)
from device_use.safety.models import SafetyVerdict

# ===========================================================================
# actions/models edge cases
# ===========================================================================


class TestParseActionEdgeCases:
    def test_empty_dict_raises(self):
        """Empty dict has no action_type or type key — ActionType('') fails."""
        with pytest.raises(ValueError):
            parse_action({})

    def test_missing_required_fields(self):
        """ClickAction needs x and y; missing them should raise ValidationError."""
        with pytest.raises(Exception):  # pydantic ValidationError
            parse_action({"action_type": "click"})

    def test_missing_required_fields_type_key(self):
        """Using 'type' key instead of 'action_type', but missing x/y."""
        with pytest.raises(Exception):
            parse_action({"type": "click"})

    def test_unknown_action_type_raises(self):
        """ActionType enum rejects invalid values before parse_action's own check."""
        with pytest.raises(ValueError, match="not a valid ActionType"):
            parse_action({"action_type": "nonexistent_action"})

    def test_coordinates_list_to_xy(self):
        """The 'coordinates': [x, y] normalization should work."""
        action = parse_action(
            {
                "action_type": "click",
                "coordinates": [100, 200],
            }
        )
        assert isinstance(action, ClickAction)
        assert action.x == 100
        assert action.y == 200

    def test_coordinates_list_floats_truncated(self):
        """Coordinates list with floats should be truncated to int."""
        action = parse_action(
            {
                "action_type": "click",
                "coordinates": [100.7, 200.9],
            }
        )
        assert action.x == 100
        assert action.y == 200

    def test_parameters_dict_flattened(self):
        """The 'parameters' dict should be flattened into top-level keys."""
        action = parse_action(
            {
                "action_type": "type",
                "parameters": {"text": "hello", "interval": 0.05},
            }
        )
        assert isinstance(action, TypeAction)
        assert action.text == "hello"
        assert action.interval == 0.05

    def test_type_key_normalized_to_action_type(self):
        """VLMs may use 'type' instead of 'action_type'."""
        action = parse_action(
            {
                "type": "wait",
            }
        )
        assert isinstance(action, WaitAction)

    def test_extra_fields_ignored(self):
        """Extra fields not in the model should be silently ignored."""
        action = parse_action(
            {
                "action_type": "screenshot",
                "extra_field": "should_be_ignored",
            }
        )
        assert isinstance(action, ScreenshotAction)


class TestClickActionEdgeCases:
    def test_negative_coordinates(self):
        """Negative coordinates should be accepted (the model doesn't forbid them)."""
        action = ClickAction(x=-10, y=-20)
        assert action.x == -10
        assert action.y == -20

    def test_zero_coordinates(self):
        action = ClickAction(x=0, y=0)
        assert action.x == 0
        assert action.y == 0

    def test_large_coordinates(self):
        action = ClickAction(x=999999, y=999999)
        assert action.x == 999999


class TestTypeActionEdgeCases:
    def test_unicode_text(self):
        action = TypeAction(text="\u4f60\u597d\u4e16\u754c")
        assert action.text == "\u4f60\u597d\u4e16\u754c"

    def test_empty_text(self):
        action = TypeAction(text="")
        assert action.text == ""

    def test_very_long_text(self):
        long_text = "a" * 10000
        action = TypeAction(text=long_text)
        assert len(action.text) == 10000

    def test_text_with_special_chars(self):
        action = TypeAction(text="hello\tworld\nnewline")
        assert "\t" in action.text
        assert "\n" in action.text

    def test_zero_interval(self):
        action = TypeAction(text="test", interval=0.0)
        assert action.interval == 0.0


class TestScrollActionEdgeCases:
    def test_zero_clicks(self):
        action = ScrollAction(x=100, y=200, clicks=0)
        assert action.clicks == 0

    def test_negative_clicks_scroll_down(self):
        action = ScrollAction(x=100, y=200, clicks=-5)
        assert action.clicks == -5

    def test_large_positive_clicks(self):
        action = ScrollAction(x=0, y=0, clicks=1000)
        assert action.clicks == 1000


class TestDragActionEdgeCases:
    def test_single_point_path(self):
        """Start and end at the same point — degenerate drag."""
        action = DragAction(start_x=100, start_y=200, end_x=100, end_y=200)
        assert action.start_x == action.end_x
        assert action.start_y == action.end_y

    def test_zero_duration(self):
        action = DragAction(
            start_x=0,
            start_y=0,
            end_x=100,
            end_y=100,
            duration=0.0,
        )
        assert action.duration == 0.0

    def test_negative_duration(self):
        """Model doesn't validate non-negative duration."""
        action = DragAction(
            start_x=0,
            start_y=0,
            end_x=100,
            end_y=100,
            duration=-1.0,
        )
        assert action.duration == -1.0


class TestHotkeyActionEdgeCases:
    def test_single_key(self):
        action = HotkeyAction(keys=["escape"])
        assert action.keys == ["escape"]

    def test_many_modifiers(self):
        action = HotkeyAction(keys=["ctrl", "shift", "alt", "a"])
        assert len(action.keys) == 4

    def test_empty_keys_list(self):
        """Empty keys list is accepted — model does not enforce non-empty."""
        action = HotkeyAction(keys=[])
        assert action.keys == []


class TestWaitActionEdgeCases:
    def test_zero_wait(self):
        action = WaitAction(seconds=0.0)
        assert action.seconds == 0.0

    def test_very_long_wait(self):
        action = WaitAction(seconds=999999.0)
        assert action.seconds == 999999.0


# ===========================================================================
# actions/scaling edge cases
# ===========================================================================


class TestCoordinateScalerEdgeCases:
    def test_zero_vlm_dimensions_raises(self):
        with pytest.raises(ValueError, match="VLM dimensions"):
            CoordinateScaler(vlm_width=0, vlm_height=100, screen_width=100, screen_height=100)

    def test_negative_vlm_dimensions_raises(self):
        with pytest.raises(ValueError, match="VLM dimensions"):
            CoordinateScaler(vlm_width=-1, vlm_height=100, screen_width=100, screen_height=100)

    def test_zero_screen_dimensions_raises(self):
        with pytest.raises(ValueError, match="Screen dimensions"):
            CoordinateScaler(vlm_width=100, vlm_height=100, screen_width=0, screen_height=100)

    def test_negative_screen_dimensions_raises(self):
        with pytest.raises(ValueError, match="Screen dimensions"):
            CoordinateScaler(vlm_width=100, vlm_height=100, screen_width=100, screen_height=-1)

    def test_very_large_screen(self):
        scaler = CoordinateScaler(
            vlm_width=1280,
            vlm_height=800,
            screen_width=7680,
            screen_height=4320,
        )
        sx, sy = scaler.vlm_to_screen(640, 400)
        assert sx == 3840
        assert sy == 2160

    def test_very_small_screen(self):
        scaler = CoordinateScaler(
            vlm_width=1280,
            vlm_height=800,
            screen_width=320,
            screen_height=200,
        )
        sx, sy = scaler.vlm_to_screen(1280, 800)
        assert sx == 320
        assert sy == 200

    def test_screen_to_vlm_and_back_roundtrip(self):
        """vlm -> screen -> vlm should recover the original coords."""
        scaler = CoordinateScaler(
            vlm_width=1280,
            vlm_height=800,
            screen_width=1920,
            screen_height=1080,
            window_x=100,
            window_y=50,
        )
        original_x, original_y = 640, 400
        sx, sy = scaler.vlm_to_screen(original_x, original_y)
        rx, ry = scaler.screen_to_vlm(sx, sy)
        assert rx == original_x
        assert ry == original_y

    def test_vlm_to_screen_and_back_roundtrip(self):
        """screen -> vlm -> screen should recover the original coords."""
        scaler = CoordinateScaler(
            vlm_width=1280,
            vlm_height=800,
            screen_width=1920,
            screen_height=1080,
            window_x=100,
            window_y=50,
        )
        original_x, original_y = 500, 300
        vx, vy = scaler.screen_to_vlm(original_x, original_y)
        rx, ry = scaler.vlm_to_screen(vx, vy)
        assert rx == original_x
        assert ry == original_y

    def test_no_window_offset(self):
        """With window at (0,0), scaling is purely dimensional."""
        scaler = CoordinateScaler(
            vlm_width=1000,
            vlm_height=500,
            screen_width=2000,
            screen_height=1000,
            window_x=0,
            window_y=0,
        )
        sx, sy = scaler.vlm_to_screen(100, 50)
        assert sx == 200
        assert sy == 100

    def test_with_large_window_offset(self):
        scaler = CoordinateScaler(
            vlm_width=1000,
            vlm_height=500,
            screen_width=2000,
            screen_height=1000,
            window_x=5000,
            window_y=3000,
        )
        sx, sy = scaler.vlm_to_screen(0, 0)
        assert sx == 5000
        assert sy == 3000

    def test_clamp_screen_within_bounds(self):
        scaler = CoordinateScaler(
            vlm_width=1000,
            vlm_height=500,
            screen_width=2000,
            screen_height=1000,
            window_x=100,
            window_y=100,
        )
        cx, cy = scaler.clamp_screen(50, 50)
        assert cx == 100  # clamped to window_x
        assert cy == 100

    def test_clamp_screen_beyond_bounds(self):
        scaler = CoordinateScaler(
            vlm_width=1000,
            vlm_height=500,
            screen_width=2000,
            screen_height=1000,
            window_x=100,
            window_y=100,
        )
        cx, cy = scaler.clamp_screen(9999, 9999)
        assert cx == 100 + 2000 - 1  # window_x + screen_width - 1
        assert cy == 100 + 1000 - 1

    def test_screen_to_vlm_with_offset(self):
        scaler = CoordinateScaler(
            vlm_width=1000,
            vlm_height=500,
            screen_width=2000,
            screen_height=1000,
            window_x=500,
            window_y=250,
        )
        # Screen coords at the window origin should map to VLM (0, 0)
        vx, vy = scaler.screen_to_vlm(500, 250)
        assert vx == 0
        assert vy == 0

    def test_scale_properties(self):
        scaler = CoordinateScaler(
            vlm_width=800,
            vlm_height=600,
            screen_width=1600,
            screen_height=1200,
        )
        assert scaler.scale_x == 2.0
        assert scaler.scale_y == 2.0

    def test_non_uniform_scaling(self):
        scaler = CoordinateScaler(
            vlm_width=1280,
            vlm_height=720,
            screen_width=1920,
            screen_height=1080,
        )
        assert scaler.scale_x == 1920 / 1280
        assert scaler.scale_y == 1080 / 720

    def test_identity_scaling(self):
        """VLM and screen have the same dimensions."""
        scaler = CoordinateScaler(
            vlm_width=1920,
            vlm_height=1080,
            screen_width=1920,
            screen_height=1080,
        )
        assert scaler.scale_x == 1.0
        assert scaler.scale_y == 1.0
        sx, sy = scaler.vlm_to_screen(100, 200)
        assert sx == 100
        assert sy == 200


# ===========================================================================
# core/models edge cases
# ===========================================================================


class TestActionRequestEdgeCases:
    def test_none_coordinates(self):
        req = ActionRequest(action_type=ActionType.CLICK, coordinates=None)
        assert req.coordinates is None

    def test_empty_parameters(self):
        req = ActionRequest(action_type=ActionType.CLICK, parameters={})
        assert req.parameters == {}

    def test_default_values(self):
        req = ActionRequest(action_type=ActionType.WAIT)
        assert req.target == ""
        assert req.parameters == {}
        assert req.coordinates is None
        assert req.description == ""

    def test_parameters_with_complex_values(self):
        req = ActionRequest(
            action_type=ActionType.CLICK,
            parameters={"nested": {"a": 1}, "list": [1, 2, 3]},
        )
        assert req.parameters["nested"]["a"] == 1
        assert req.parameters["list"] == [1, 2, 3]

    def test_coordinates_tuple(self):
        req = ActionRequest(action_type=ActionType.CLICK, coordinates=(100, 200))
        assert req.coordinates == (100, 200)


class TestActionResultEdgeCases:
    def test_zero_duration(self):
        req = ActionRequest(action_type=ActionType.CLICK)
        result = ActionResult(success=True, action=req, duration_ms=0)
        assert result.duration_ms == 0

    def test_negative_duration(self):
        """Model doesn't validate non-negative duration."""
        req = ActionRequest(action_type=ActionType.CLICK)
        result = ActionResult(success=False, action=req, duration_ms=-1.0)
        assert result.duration_ms == -1.0

    def test_success_true_no_error(self):
        req = ActionRequest(action_type=ActionType.WAIT)
        result = ActionResult(success=True, action=req)
        assert result.error == ""

    def test_failure_with_error(self):
        req = ActionRequest(action_type=ActionType.CLICK)
        result = ActionResult(success=False, action=req, error="Element not found")
        assert result.success is False
        assert result.error == "Element not found"

    def test_large_duration(self):
        req = ActionRequest(action_type=ActionType.WAIT)
        result = ActionResult(success=True, action=req, duration_ms=999999.999)
        assert result.duration_ms == 999999.999


class TestActionTypeEnum:
    def test_all_values(self):
        expected = {
            "click",
            "double_click",
            "right_click",
            "type",
            "hotkey",
            "scroll",
            "drag",
            "wait",
            "screenshot",
            "move",
        }
        actual = {v.value for v in ActionType}
        assert actual == expected

    def test_from_string(self):
        assert ActionType("click") == ActionType.CLICK
        assert ActionType("wait") == ActionType.WAIT
        assert ActionType("drag") == ActionType.DRAG

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError):
            ActionType("invalid_action")


# ===========================================================================
# safety/models edge cases
# ===========================================================================


class TestSafetyVerdictEdgeCases:
    def test_allowed_no_reason(self):
        verdict = SafetyVerdict(allowed=True)
        assert verdict.allowed is True
        assert verdict.reason == ""
        assert verdict.layer == ""
        assert verdict.requires_confirmation is False

    def test_denied_with_layer(self):
        verdict = SafetyVerdict(
            allowed=False,
            layer="L1_whitelist",
            reason="Action not in whitelist",
        )
        assert verdict.allowed is False
        assert verdict.layer == "L1_whitelist"
        assert verdict.reason == "Action not in whitelist"

    def test_empty_layer_string(self):
        verdict = SafetyVerdict(allowed=True, layer="")
        assert verdict.layer == ""

    def test_requires_confirmation_true(self):
        verdict = SafetyVerdict(allowed=True, requires_confirmation=True)
        assert verdict.requires_confirmation is True
        assert verdict.allowed is True

    def test_all_fields_populated(self):
        verdict = SafetyVerdict(
            allowed=True,
            layer="L2_safety",
            reason="Approved with caution",
            requires_confirmation=True,
        )
        assert verdict.allowed is True
        assert verdict.layer == "L2_safety"
        assert verdict.reason == "Approved with caution"
        assert verdict.requires_confirmation is True

    def test_allowed_false_no_layer(self):
        verdict = SafetyVerdict(allowed=False)
        assert verdict.allowed is False
        assert verdict.layer == ""
        assert verdict.reason == ""

    def test_reason_with_unicode(self):
        verdict = SafetyVerdict(allowed=False, reason="\u5371\u9669\u64cd\u4f5c")
        assert "\u5371\u9669" in verdict.reason
