"""Tests for OpenAI-compatible VLM backend."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from openai import RateLimitError

from device_use.backends.base import VisionBackend
from device_use.backends.openai_compat import OpenAICompatBackend

# A minimal 1x1 red PNG for testing
TINY_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
    b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
    b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


def _make_chat_response(content: str) -> SimpleNamespace:
    """Build a minimal object mimicking openai ChatCompletion response."""
    message = SimpleNamespace(content=content)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice])


@pytest.fixture
def backend():
    """Create an OpenAICompatBackend with a dummy key."""
    return OpenAICompatBackend(model="gpt-4o", api_key="sk-test-key")


class TestSupportsGrounding:
    def test_supports_grounding_is_false(self, backend: OpenAICompatBackend):
        assert backend.supports_grounding is False


class TestProtocolConformance:
    def test_implements_vision_backend(self, backend: OpenAICompatBackend):
        assert isinstance(backend, VisionBackend)


class TestBase64Encoding:
    def test_encode_image(self, backend: OpenAICompatBackend):
        encoded = backend._encode_image(TINY_PNG)
        assert isinstance(encoded, str)
        # Round-trip: decode back should give original bytes
        decoded = base64.b64decode(encoded)
        assert decoded == TINY_PNG

    def test_make_image_content_structure(self, backend: OpenAICompatBackend):
        content = backend._make_image_content(TINY_PNG, "Describe this.")
        assert len(content) == 2
        assert content[0]["type"] == "text"
        assert content[0]["text"] == "Describe this."
        assert content[1]["type"] == "image_url"
        assert content[1]["image_url"]["detail"] == "high"
        assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")


class TestLocate:
    async def test_locate_returns_none(self, backend: OpenAICompatBackend):
        result = await backend.locate(TINY_PNG, "some button")
        assert result is None


class TestObserve:
    async def test_observe_with_valid_json(self, backend: OpenAICompatBackend):
        mock_response = json.dumps(
            {
                "description": "A file manager window",
                "elements": [{"name": "Open", "type": "button", "description": "Open file button"}],
            }
        )
        with patch.object(
            backend._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=_make_chat_response(mock_response),
        ):
            result = await backend.observe(TINY_PNG, context="testing")

        assert result["description"] == "A file manager window"
        assert len(result["elements"]) == 1
        assert result["elements"][0]["name"] == "Open"

    async def test_observe_with_invalid_json_fallback(self, backend: OpenAICompatBackend):
        """When model returns non-JSON, observe should gracefully degrade."""
        raw_text = "I see a file manager with an open button."
        with patch.object(
            backend._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=_make_chat_response(raw_text),
        ):
            result = await backend.observe(TINY_PNG)

        assert result["description"] == raw_text
        assert result["elements"] == []


class TestPlan:
    async def test_plan_with_valid_json(self, backend: OpenAICompatBackend):
        mock_response = json.dumps(
            {
                "action": {
                    "action_type": "click",
                    "target": "Open button",
                    "parameters": {},
                },
                "reasoning": "Need to click Open to load the file.",
                "done": False,
                "confidence": 0.85,
            }
        )
        with patch.object(
            backend._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=_make_chat_response(mock_response),
        ):
            result = await backend.plan(TINY_PNG, task="Open image.tif")

        assert result["action"]["action_type"] == "click"
        assert result["action"]["target"] == "Open button"
        assert result["reasoning"] == "Need to click Open to load the file."
        assert result["done"] is False
        assert result["confidence"] == 0.85

    async def test_plan_with_history(self, backend: OpenAICompatBackend):
        mock_response = json.dumps(
            {
                "action": {
                    "action_type": "type",
                    "target": "filename field",
                    "parameters": {"text": "image.tif"},
                },
                "reasoning": "Type filename after opening dialog.",
                "done": False,
                "confidence": 0.9,
            }
        )
        history = [{"step": 0, "action": "click", "target": "Open button"}]
        with patch.object(
            backend._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=_make_chat_response(mock_response),
        ):
            result = await backend.plan(TINY_PNG, task="Open image.tif", history=history)

        assert result["action"]["action_type"] == "type"

    async def test_plan_with_invalid_json_fallback(self, backend: OpenAICompatBackend):
        raw_text = "Click the open button in the toolbar."
        with patch.object(
            backend._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=_make_chat_response(raw_text),
        ):
            result = await backend.plan(TINY_PNG, task="Open file")

        assert result["action"]["action_type"] == "wait"
        assert result["action"]["seconds"] == 1
        assert result["reasoning"] == raw_text
        assert result["done"] is False
        assert result["confidence"] == 0.0


class TestRetryBehavior:
    async def test_retry_on_rate_limit_then_success(self, backend: OpenAICompatBackend):
        """Simulate RateLimitError on first call, then success."""
        success_response = _make_chat_response(
            json.dumps({"description": "desktop", "elements": []})
        )
        mock_create = AsyncMock(
            side_effect=[
                RateLimitError(
                    message="Rate limit exceeded",
                    response=SimpleNamespace(
                        status_code=429,
                        headers={"retry-after": "1"},
                        request=SimpleNamespace(
                            method="POST", url="https://api.openai.com/v1/chat/completions"
                        ),
                    ),
                    body=None,
                ),
                success_response,
            ]
        )
        with patch.object(backend._client.chat.completions, "create", mock_create):
            result = await backend.observe(TINY_PNG)

        assert result["description"] == "desktop"
        assert mock_create.call_count == 2

    async def test_retry_exhausted_raises(self, backend: OpenAICompatBackend):
        """If all retries fail, the exception should propagate."""
        rate_limit_error = RateLimitError(
            message="Rate limit exceeded",
            response=SimpleNamespace(
                status_code=429,
                headers={"retry-after": "1"},
                request=SimpleNamespace(
                    method="POST", url="https://api.openai.com/v1/chat/completions"
                ),
            ),
            body=None,
        )
        mock_create = AsyncMock(side_effect=rate_limit_error)
        with (
            patch.object(backend._client.chat.completions, "create", mock_create),
            pytest.raises(RateLimitError),
        ):
            await backend.observe(TINY_PNG)

        # backoff max_tries=5 means up to 5 attempts
        assert mock_create.call_count == 5


class TestMarkdownFenceStripping:
    async def test_plan_with_markdown_fenced_json(self, backend: OpenAICompatBackend):
        """VLM wraps JSON in ```json fences — should still parse."""
        fenced_json = (
            '```json\n{"action": {"action_type": "click", "target": "button"},'
            ' "reasoning": "test", "done": false, "confidence": 0.8}\n```'
        )
        with patch.object(
            backend._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=_make_chat_response(fenced_json),
        ):
            result = await backend.plan(TINY_PNG, task="Click")

        assert result["action"]["action_type"] == "click"
        assert result["confidence"] == 0.8

    async def test_observe_with_markdown_fenced_json(self, backend: OpenAICompatBackend):
        fenced_json = '```json\n{"description": "Desktop window", "elements": []}\n```'
        with patch.object(
            backend._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=_make_chat_response(fenced_json),
        ):
            result = await backend.observe(TINY_PNG)

        assert result["description"] == "Desktop window"


class TestExtractComputerCalls:
    def test_extract_computer_calls_handles_none_actions(self):
        """Regression: None actions in computer_call should not crash."""
        from unittest.mock import MagicMock

        backend = OpenAICompatBackend.__new__(OpenAICompatBackend)

        mock_item = MagicMock()
        mock_item.type = "computer_call"
        mock_item.call_id = "test_call"
        mock_item.actions = None
        mock_item.action = None

        mock_response = MagicMock()
        mock_response.output = [mock_item]

        results = backend._extract_computer_calls(mock_response)
        assert results == []

    def test_extract_computer_calls_filters_none_in_list(self):
        """Regression: None values within actions list should be skipped."""
        from unittest.mock import MagicMock

        backend = OpenAICompatBackend.__new__(OpenAICompatBackend)

        mock_action = MagicMock()
        mock_action.type = "click"
        mock_action.x = 100
        mock_action.y = 200
        mock_action.button = "left"

        mock_item = MagicMock()
        mock_item.type = "computer_call"
        mock_item.call_id = "test_call"
        mock_item.actions = [None, mock_action, None]
        mock_item.action = None

        mock_response = MagicMock()
        mock_response.output = [mock_item]

        results = backend._extract_computer_calls(mock_response)
        assert len(results) == 1
        assert results[0]["action_type"] == "click"


class TestCallParameters:
    async def test_chat_call_passes_correct_parameters(self, backend: OpenAICompatBackend):
        """Verify that _chat_call sends correct model, max_tokens, temperature."""
        mock_create = AsyncMock(return_value=_make_chat_response("test"))
        with patch.object(backend._client.chat.completions, "create", mock_create):
            await backend._chat_call([{"role": "user", "content": "hello"}], temperature=0.5)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o"
        assert call_kwargs["max_tokens"] == 4096
        assert call_kwargs["temperature"] == 0.5


# ===================================================================
# GPT-5.4 Computer Use path tests
# ===================================================================


from device_use.actions.models import (
    ClickAction,
    DragAction,
    HotkeyAction,
    MoveAction,
    ScreenshotAction,
    ScrollAction,
    WaitAction,
    parse_action,
)
from device_use.backends.openai_compat import _supports_computer_use

# ---------------------------------------------------------------------------
# _supports_computer_use
# ---------------------------------------------------------------------------


class TestSupportsComputerUse:
    def test_gpt54(self):
        assert _supports_computer_use("gpt-5.4") is True

    def test_gpt54_pro(self):
        assert _supports_computer_use("gpt-5.4-pro") is True

    def test_computer_use_preview(self):
        assert _supports_computer_use("computer-use-preview") is True

    def test_gpt4o_not_supported(self):
        assert _supports_computer_use("gpt-4o") is False

    def test_claude_not_supported(self):
        assert _supports_computer_use("claude-3-opus") is False


# ---------------------------------------------------------------------------
# _map_cu_action — all action types
# ---------------------------------------------------------------------------


class TestMapCUAction:
    """Test _map_cu_action() for every GPT-5.4 CU action type."""

    def test_click(self):
        cu = {"action_type": "click", "x": 100, "y": 200}
        result = OpenAICompatBackend._map_cu_action(cu)
        action = parse_action(result["action"])
        assert isinstance(action, ClickAction)
        assert action.x == 100
        assert action.y == 200
        assert action.button == "left"

    def test_double_click(self):
        cu = {"action_type": "double_click", "x": 50, "y": 60}
        result = OpenAICompatBackend._map_cu_action(cu)
        action = parse_action(result["action"])
        assert action.action_type.value == "double_click"

    def test_right_click_via_action_type(self):
        cu = {"action_type": "right_click", "x": 10, "y": 20}
        result = OpenAICompatBackend._map_cu_action(cu)
        action = parse_action(result["action"])
        assert isinstance(action, ClickAction)
        assert action.button == "right"

    def test_right_click_via_button_field(self):
        cu = {"action_type": "click", "x": 10, "y": 20, "button": "right"}
        result = OpenAICompatBackend._map_cu_action(cu)
        action = parse_action(result["action"])
        assert isinstance(action, ClickAction)
        assert action.button == "right"

    def test_middle_click_via_button_field(self):
        cu = {"action_type": "click", "x": 10, "y": 20, "button": "middle"}
        result = OpenAICompatBackend._map_cu_action(cu)
        action = parse_action(result["action"])
        assert isinstance(action, ClickAction)
        assert action.button == "middle"

    def test_scroll(self):
        cu = {"action_type": "scroll", "x": 10, "y": 20, "scroll_x": 0, "scroll_y": -120}
        result = OpenAICompatBackend._map_cu_action(cu)
        action = parse_action(result["action"])
        assert isinstance(action, ScrollAction)
        assert action.x == 10
        assert action.y == 20
        assert action.clicks == -1

    def test_scroll_large_delta(self):
        cu = {"action_type": "scroll", "x": 0, "y": 0, "scroll_x": 0, "scroll_y": -360}
        result = OpenAICompatBackend._map_cu_action(cu)
        action = parse_action(result["action"])
        assert action.clicks == -3

    def test_scroll_up(self):
        cu = {"action_type": "scroll", "x": 0, "y": 0, "scroll_x": 0, "scroll_y": 120}
        result = OpenAICompatBackend._map_cu_action(cu)
        action = parse_action(result["action"])
        assert action.clicks == 1

    def test_scroll_zero(self):
        cu = {"action_type": "scroll", "x": 0, "y": 0, "scroll_x": 0, "scroll_y": 0}
        result = OpenAICompatBackend._map_cu_action(cu)
        action = parse_action(result["action"])
        assert action.clicks == 0

    def test_scroll_negative_truncation(self):
        """Regression: -121 // 120 = -2 (floor), but int(-121/120) = -1 (truncate)."""
        cu = {"action_type": "scroll", "x": 0, "y": 0, "scroll_x": 0, "scroll_y": -121}
        result = OpenAICompatBackend._map_cu_action(cu)
        action = parse_action(result["action"])
        assert action.clicks == -1  # truncate toward zero, not floor

    def test_scroll_positive_truncation(self):
        """Positive scroll_y=121 should also truncate to 1, not round up."""
        cu = {"action_type": "scroll", "x": 0, "y": 0, "scroll_x": 0, "scroll_y": 121}
        result = OpenAICompatBackend._map_cu_action(cu)
        action = parse_action(result["action"])
        assert action.clicks == 1

    def test_drag(self):
        cu = {
            "action_type": "drag",
            "path": [{"x": 10, "y": 20}, {"x": 30, "y": 40}],
        }
        result = OpenAICompatBackend._map_cu_action(cu)
        action = parse_action(result["action"])
        assert isinstance(action, DragAction)
        assert action.start_x == 10
        assert action.start_y == 20
        assert action.end_x == 30
        assert action.end_y == 40

    def test_drag_multi_point_path(self):
        cu = {
            "action_type": "drag",
            "path": [{"x": 1, "y": 2}, {"x": 5, "y": 5}, {"x": 10, "y": 20}],
        }
        result = OpenAICompatBackend._map_cu_action(cu)
        action = parse_action(result["action"])
        assert action.start_x == 1
        assert action.start_y == 2
        assert action.end_x == 10
        assert action.end_y == 20

    def test_drag_empty_path(self):
        cu = {"action_type": "drag", "path": []}
        result = OpenAICompatBackend._map_cu_action(cu)
        action = parse_action(result["action"])
        assert isinstance(action, DragAction)
        assert action.start_x == 0

    def test_move(self):
        cu = {"action_type": "move", "x": 50, "y": 60}
        result = OpenAICompatBackend._map_cu_action(cu)
        action = parse_action(result["action"])
        assert isinstance(action, MoveAction)
        assert action.x == 50
        assert action.y == 60

    def test_keypress(self):
        cu = {"action_type": "keypress", "keys": ["ctrl", "s"]}
        result = OpenAICompatBackend._map_cu_action(cu)
        action = parse_action(result["action"])
        assert isinstance(action, HotkeyAction)
        assert action.keys == ["ctrl", "s"]

    def test_type(self):
        cu = {"action_type": "type", "text": "hello world"}
        result = OpenAICompatBackend._map_cu_action(cu)
        action = parse_action(result["action"])
        assert action.text == "hello world"

    def test_wait(self):
        cu = {"action_type": "wait"}
        result = OpenAICompatBackend._map_cu_action(cu)
        action = parse_action(result["action"])
        assert isinstance(action, WaitAction)

    def test_screenshot(self):
        cu = {"action_type": "screenshot"}
        result = OpenAICompatBackend._map_cu_action(cu)
        action = parse_action(result["action"])
        assert isinstance(action, ScreenshotAction)

    def test_call_id_propagated(self):
        cu = {"action_type": "click", "x": 1, "y": 2, "call_id": "call_abc123"}
        result = OpenAICompatBackend._map_cu_action(cu)
        assert result["call_id"] == "call_abc123"

    def test_result_structure(self):
        cu = {"action_type": "click", "x": 1, "y": 2}
        result = OpenAICompatBackend._map_cu_action(cu)
        assert "reasoning" in result
        assert "action" in result
        assert "done" in result
        assert "confidence" in result
        assert result["done"] is False


# ---------------------------------------------------------------------------
# _plan_native with mocked response
# ---------------------------------------------------------------------------


def _make_cu_response(
    actions,
    call_id="call_123",
    response_id="resp_abc",
    pending_safety_checks=None,
):
    """Create a mock Responses API response with computer_call."""
    action_objs = [SimpleNamespace(**a) for a in actions]

    computer_call = SimpleNamespace(
        type="computer_call",
        call_id=call_id,
        actions=action_objs,
        action=action_objs[0] if action_objs else None,
        pending_safety_checks=pending_safety_checks or [],
    )

    return SimpleNamespace(
        id=response_id,
        output=[computer_call],
        output_text="",
    )


def _make_text_response_cu(text, response_id="resp_text"):
    """Create a mock response with no computer_call (task done)."""
    return SimpleNamespace(
        id=response_id,
        output=[SimpleNamespace(type="message", content=text)],
        output_text=text,
    )


class TestPlanNative:
    @pytest.fixture
    def cu_backend(self):
        return OpenAICompatBackend(model="gpt-5.4", api_key="sk-test")

    @pytest.mark.asyncio
    async def test_returns_mapped_action(self, cu_backend):
        mock_resp = _make_cu_response(
            [
                {"type": "click", "x": 100, "y": 200, "button": "left"},
            ]
        )
        cu_backend._responses_create = AsyncMock(return_value=mock_resp)

        result = await cu_backend._plan_native(b"fake_png", "click the button")
        assert result["action"]["action_type"] == "click"
        assert result["call_id"] == "call_123"
        assert result["done"] is False

    @pytest.mark.asyncio
    async def test_batched_actions(self, cu_backend):
        mock_resp = _make_cu_response(
            [
                {"type": "click", "x": 10, "y": 20, "button": "left"},
                {"type": "type", "text": "hello"},
            ]
        )
        cu_backend._responses_create = AsyncMock(return_value=mock_resp)

        result = await cu_backend._plan_native(b"fake_png", "type in field")
        assert result["action"]["action_type"] == "click"
        assert len(result["_remaining_actions"]) == 1
        assert result["_remaining_actions"][0]["action"]["text"] == "hello"

    @pytest.mark.asyncio
    async def test_no_computer_call_returns_done(self, cu_backend):
        mock_resp = _make_text_response_cu("Task completed successfully")
        cu_backend._responses_create = AsyncMock(return_value=mock_resp)

        result = await cu_backend._plan_native(b"fake_png", "do something")
        assert result["done"] is True
        assert result["data"]["response"] == "Task completed successfully"


# ---------------------------------------------------------------------------
# pending_safety_checks detection
# ---------------------------------------------------------------------------


class TestPendingSafetyChecks:
    @pytest.fixture
    def cu_backend(self):
        return OpenAICompatBackend(model="gpt-5.4", api_key="sk-test")

    @pytest.mark.asyncio
    async def test_safety_checks_detected(self, cu_backend):
        mock_resp = _make_cu_response(
            [{"type": "click", "x": 1, "y": 2, "button": "left"}],
            pending_safety_checks=[{"id": "sc_1", "code": "malicious_instructions"}],
        )
        cu_backend._responses_create = AsyncMock(return_value=mock_resp)

        result = await cu_backend._computer_use_step(b"png", "task")
        assert result.has_safety_checks is True

    @pytest.mark.asyncio
    async def test_no_safety_checks_clean(self, cu_backend):
        mock_resp = _make_cu_response(
            [{"type": "click", "x": 1, "y": 2, "button": "left"}],
            pending_safety_checks=[],
        )
        cu_backend._responses_create = AsyncMock(return_value=mock_resp)

        result = await cu_backend._computer_use_step(b"png", "task")
        assert result.has_safety_checks is False

    @pytest.mark.asyncio
    async def test_cu_loop_aborts_on_safety_checks(self, cu_backend):
        mock_resp = _make_cu_response(
            [{"type": "click", "x": 1, "y": 2, "button": "left"}],
            pending_safety_checks=[{"id": "sc_1", "code": "unsafe"}],
        )
        cu_backend._responses_create = AsyncMock(return_value=mock_resp)

        actions = await cu_backend.run_cu_loop(
            task="test",
            take_screenshot=AsyncMock(return_value=b"png"),
            execute_action=AsyncMock(),
            max_turns=5,
        )
        assert len(actions) == 0  # Aborted before executing any action


# ---------------------------------------------------------------------------
# Batched actions in run_cu_loop
# ---------------------------------------------------------------------------


class TestCULoopBatched:
    @pytest.mark.asyncio
    async def test_all_actions_executed(self):
        cu_backend = OpenAICompatBackend(model="gpt-5.4", api_key="sk-test")

        # First turn: batch of 2 actions. Second turn: no actions (done).
        call_count = 0

        async def mock_responses_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_cu_response(
                    [
                        {"type": "click", "x": 10, "y": 20, "button": "left"},
                        {"type": "type", "text": "hello"},
                    ]
                )
            return _make_text_response_cu("done")

        cu_backend._responses_create = mock_responses_create

        executed = []

        async def mock_execute(action):
            executed.append(action)

        actions = await cu_backend.run_cu_loop(
            task="type in field",
            take_screenshot=AsyncMock(return_value=b"png"),
            execute_action=mock_execute,
            max_turns=5,
        )
        assert len(actions) == 2


# ---------------------------------------------------------------------------
# Session management for GPT-5.4
# ---------------------------------------------------------------------------


class TestCUSessionManagement:
    def test_reset_session_clears_response_id(self):
        cu_backend = OpenAICompatBackend(model="gpt-5.4", api_key="sk-test")
        cu_backend._previous_response_id = "resp_old"
        cu_backend.reset_session()
        assert cu_backend._previous_response_id is None

    def test_supports_grounding_for_cu_model(self):
        cu_backend = OpenAICompatBackend(model="gpt-5.4", api_key="sk-test")
        assert cu_backend.supports_grounding is True

    def test_native_cu_flag_set(self):
        cu_backend = OpenAICompatBackend(model="gpt-5.4", api_key="sk-test")
        assert cu_backend._native_cu is True

    def test_native_cu_flag_not_set_for_legacy(self):
        legacy = OpenAICompatBackend(model="gpt-4o", api_key="sk-test")
        assert legacy._native_cu is False
