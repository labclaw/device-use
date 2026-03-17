"""Tests for the Claude VisionBackend."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from device_use.backends.claude import ClaudeBackend, _strip_markdown_fences

# ---------------------------------------------------------------------------
# _strip_markdown_fences
# ---------------------------------------------------------------------------


class TestStripMarkdownFences:
    def test_strip_json_fences(self):
        text = '```json\n{"key": "value"}\n```'
        assert _strip_markdown_fences(text) == '{"key": "value"}'

    def test_strip_plain_fences(self):
        text = '```\n{"key": "value"}\n```'
        assert _strip_markdown_fences(text) == '{"key": "value"}'

    def test_no_fences(self):
        text = '{"key": "value"}'
        assert _strip_markdown_fences(text) == '{"key": "value"}'

    def test_whitespace(self):
        text = '  ```json\n{"a": 1}\n```  '
        assert _strip_markdown_fences(text) == '{"a": 1}'


# ---------------------------------------------------------------------------
# ClaudeBackend
# ---------------------------------------------------------------------------


class TestClaudeBackend:
    def test_init_defaults(self):
        with patch("device_use.backends.claude.AsyncAnthropic"):
            backend = ClaudeBackend()
        assert backend._model == "claude-sonnet-4-20250514"
        assert backend._max_tokens == 4096
        assert backend.system_prompt == ""

    def test_supports_grounding(self):
        with patch("device_use.backends.claude.AsyncAnthropic"):
            backend = ClaudeBackend()
        assert backend.supports_grounding is True

    def test_encode_image(self):
        with patch("device_use.backends.claude.AsyncAnthropic"):
            backend = ClaudeBackend()
        result = backend._encode_image(b"\x89PNG")
        assert isinstance(result, str)
        import base64

        assert base64.standard_b64decode(result) == b"\x89PNG"

    def test_make_image_content(self):
        with patch("device_use.backends.claude.AsyncAnthropic"):
            backend = ClaudeBackend()
        content = backend._make_image_content(b"\x89PNG")
        assert content["type"] == "image"
        assert content["source"]["type"] == "base64"
        assert content["source"]["media_type"] == "image/png"

    @pytest.mark.asyncio
    async def test_observe_success(self):
        mock_client = MagicMock()
        mock_response = SimpleNamespace(
            content=[SimpleNamespace(text='{"description": "screen", "elements": []}')]
        )
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("device_use.backends.claude.AsyncAnthropic", return_value=mock_client):
            backend = ClaudeBackend()
        result = await backend.observe(b"\x89PNG", context="test context")
        assert result["description"] == "screen"
        assert result["elements"] == []

    @pytest.mark.asyncio
    async def test_observe_json_error(self):
        mock_client = MagicMock()
        mock_response = SimpleNamespace(content=[SimpleNamespace(text="not valid json")])
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("device_use.backends.claude.AsyncAnthropic", return_value=mock_client):
            backend = ClaudeBackend()
        result = await backend.observe(b"\x89PNG")
        assert result["description"] == "not valid json"
        assert result["elements"] == []

    @pytest.mark.asyncio
    async def test_plan_success(self):
        plan_json = json.dumps(
            {
                "reasoning": "click button",
                "action": {"action_type": "click", "x": 10, "y": 20},
                "done": False,
                "confidence": 0.9,
            }
        )
        mock_client = MagicMock()
        mock_response = SimpleNamespace(content=[SimpleNamespace(text=plan_json)])
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("device_use.backends.claude.AsyncAnthropic", return_value=mock_client):
            backend = ClaudeBackend()
        result = await backend.plan(b"\x89PNG", "click the button")
        assert result["reasoning"] == "click button"
        assert result["done"] is False

    @pytest.mark.asyncio
    async def test_plan_with_history(self):
        plan_json = json.dumps({"done": True, "data": {}})
        mock_client = MagicMock()
        mock_response = SimpleNamespace(content=[SimpleNamespace(text=plan_json)])
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("device_use.backends.claude.AsyncAnthropic", return_value=mock_client):
            backend = ClaudeBackend()
        history = [{"step": 0, "action": "click", "result": "ok"}]
        result = await backend.plan(b"\x89PNG", "task", history=history)
        assert result["done"] is True

    @pytest.mark.asyncio
    async def test_plan_json_error(self):
        mock_client = MagicMock()
        mock_response = SimpleNamespace(content=[SimpleNamespace(text="invalid json")])
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("device_use.backends.claude.AsyncAnthropic", return_value=mock_client):
            backend = ClaudeBackend()
        result = await backend.plan(b"\x89PNG", "task")
        assert result["done"] is False
        assert result["confidence"] == 0.0
        assert result["action"]["action_type"] == "wait"

    @pytest.mark.asyncio
    async def test_locate_success(self):
        mock_client = MagicMock()
        mock_response = SimpleNamespace(content=[SimpleNamespace(text='{"x": 100, "y": 200}')])
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("device_use.backends.claude.AsyncAnthropic", return_value=mock_client):
            backend = ClaudeBackend()
        result = await backend.locate(b"\x89PNG", "the OK button")
        assert result == (100, 200)

    @pytest.mark.asyncio
    async def test_locate_not_found(self):
        mock_client = MagicMock()
        mock_response = SimpleNamespace(content=[SimpleNamespace(text='{"x": null, "y": null}')])
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("device_use.backends.claude.AsyncAnthropic", return_value=mock_client):
            backend = ClaudeBackend()
        result = await backend.locate(b"\x89PNG", "missing element")
        assert result is None

    @pytest.mark.asyncio
    async def test_locate_parse_error(self):
        mock_client = MagicMock()
        mock_response = SimpleNamespace(content=[SimpleNamespace(text="broken")])
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("device_use.backends.claude.AsyncAnthropic", return_value=mock_client):
            backend = ClaudeBackend()
        result = await backend.locate(b"\x89PNG", "element")
        assert result is None

    @pytest.mark.asyncio
    async def test_call_with_system_prompt(self):
        mock_client = MagicMock()
        mock_response = SimpleNamespace(content=[SimpleNamespace(text='{"done": true}')])
        mock_client.messages.create = AsyncMock(return_value=mock_response)

        with patch("device_use.backends.claude.AsyncAnthropic", return_value=mock_client):
            backend = ClaudeBackend()
        backend.system_prompt = "You are an expert"
        await backend.observe(b"\x89PNG")
        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "You are an expert"
