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
        mock_response = json.dumps({
            "description": "A file manager window",
            "elements": [
                {"name": "Open", "type": "button", "description": "Open file button"}
            ],
        })
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

    async def test_observe_with_invalid_json_fallback(
        self, backend: OpenAICompatBackend
    ):
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
        mock_response = json.dumps({
            "action": {
                "action_type": "click",
                "target": "Open button",
                "parameters": {},
            },
            "reasoning": "Need to click Open to load the file.",
            "done": False,
            "confidence": 0.85,
        })
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
        mock_response = json.dumps({
            "action": {"action_type": "type", "target": "filename field", "parameters": {"text": "image.tif"}},
            "reasoning": "Type filename after opening dialog.",
            "done": False,
            "confidence": 0.9,
        })
        history = [{"step": 0, "action": "click", "target": "Open button"}]
        with patch.object(
            backend._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=_make_chat_response(mock_response),
        ):
            result = await backend.plan(
                TINY_PNG, task="Open image.tif", history=history
            )

        assert result["action"]["action_type"] == "type"

    async def test_plan_with_invalid_json_fallback(
        self, backend: OpenAICompatBackend
    ):
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
    async def test_retry_on_rate_limit_then_success(
        self, backend: OpenAICompatBackend
    ):
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
                        request=SimpleNamespace(method="POST", url="https://api.openai.com/v1/chat/completions"),
                    ),
                    body=None,
                ),
                success_response,
            ]
        )
        with patch.object(
            backend._client.chat.completions, "create", mock_create
        ):
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
                request=SimpleNamespace(method="POST", url="https://api.openai.com/v1/chat/completions"),
            ),
            body=None,
        )
        mock_create = AsyncMock(side_effect=rate_limit_error)
        with patch.object(
            backend._client.chat.completions, "create", mock_create
        ), pytest.raises(RateLimitError):
            await backend.observe(TINY_PNG)

        # backoff max_tries=5 means up to 5 attempts
        assert mock_create.call_count == 5


class TestMarkdownFenceStripping:
    async def test_plan_with_markdown_fenced_json(
        self, backend: OpenAICompatBackend
    ):
        """VLM wraps JSON in ```json fences — should still parse."""
        fenced_json = '```json\n{"action": {"action_type": "click", "target": "button"}, "reasoning": "test", "done": false, "confidence": 0.8}\n```'
        with patch.object(
            backend._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=_make_chat_response(fenced_json),
        ):
            result = await backend.plan(TINY_PNG, task="Click")

        assert result["action"]["action_type"] == "click"
        assert result["confidence"] == 0.8

    async def test_observe_with_markdown_fenced_json(
        self, backend: OpenAICompatBackend
    ):
        fenced_json = '```json\n{"description": "Desktop window", "elements": []}\n```'
        with patch.object(
            backend._client.chat.completions,
            "create",
            new_callable=AsyncMock,
            return_value=_make_chat_response(fenced_json),
        ):
            result = await backend.observe(TINY_PNG)

        assert result["description"] == "Desktop window"


class TestCallParameters:
    async def test_call_passes_correct_parameters(
        self, backend: OpenAICompatBackend
    ):
        """Verify that _call sends correct model, max_tokens, temperature."""
        mock_create = AsyncMock(
            return_value=_make_chat_response("test")
        )
        with patch.object(
            backend._client.chat.completions, "create", mock_create
        ):
            await backend._call(
                [{"role": "user", "content": "hello"}], temperature=0.5
            )

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o"
        assert call_kwargs["max_tokens"] == 4096
        assert call_kwargs["temperature"] == 0.5
