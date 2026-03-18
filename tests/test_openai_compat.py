import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from openai import RateLimitError

from device_use.backends.openai_compat import (
    OpenAICompatBackend,
    _CUStepResult,
    _strip_markdown_fences,
    _supports_computer_use,
)


@pytest.fixture
def mock_async_openai():
    """Fixture to mock AsyncOpenAI client."""
    with patch("device_use.backends.openai_compat.AsyncOpenAI") as MockAsyncOpenAI:
        mock_client = MockAsyncOpenAI.return_value
        yield MockAsyncOpenAI, mock_client


class TestSupportsComputerUse:
    """Tests for the _supports_computer_use helper function."""

    @pytest.mark.parametrize(
        "model_name, expected",
        [
            ("gpt-5.4", True),
            ("gpt-5.4-pro", True),
            ("computer-use-preview", True),
            ("computer-use-preview-2025-03-11", True),
            ("gpt-5.4-something-else", True),  # Should match prefix
            ("gpt-4o", False),
            ("claude-3-opus-20240229", False),
            ("something-else", False),
            ("", False),
        ],
    )
    def test_supports_computer_use(self, model_name, expected):
        """Verify models that do and do not support computer use."""
        assert _supports_computer_use(model_name) == expected


class TestOpenAICompatBackendInitialization:
    """Tests for the initialization of OpenAICompatBackend."""

    @pytest.mark.parametrize(
        "model, expected_native_cu",
        [
            ("gpt-5.4", True),
            ("gpt-4o", False),
            ("computer-use-preview", True),
            ("some-other-model", False),
        ],
    )
    def test_initialization(self, mock_async_openai, model, expected_native_cu):
        MockAsyncOpenAI_class, mock_async_openai_instance = mock_async_openai
        MockAsyncOpenAI_class.reset_mock()
        backend = OpenAICompatBackend(model=model, api_key="test_key", base_url="http://test.url")

        assert backend._model == model
        assert backend._client == mock_async_openai_instance
        assert backend._max_tokens == 4096
        assert backend._native_cu == expected_native_cu
        assert backend.system_prompt == ""
        assert backend._previous_response_id is None

        MockAsyncOpenAI_class.assert_called_once_with(
            api_key="test_key", base_url="http://test.url"
        )

    def test_default_values(self, mock_async_openai):
        MockAsyncOpenAI_class, mock_async_openai_instance = mock_async_openai
        backend = OpenAICompatBackend(api_key="test_key")  # Add api_key here
        assert backend._model == "gpt-5.4"
        assert backend._max_tokens == 4096
        assert backend._native_cu is True  # gpt-5.4 is default

    def test_supports_grounding_property(self, mock_async_openai):
        MockAsyncOpenAI_class, mock_async_openai_instance = mock_async_openai
        cu_backend = OpenAICompatBackend(model="gpt-5.4", api_key="test_key")
        assert cu_backend.supports_grounding is True

        legacy_backend = OpenAICompatBackend(model="gpt-4o", api_key="test_key")
        assert legacy_backend.supports_grounding is False

    @pytest.fixture(autouse=True)
    def setup(self, mock_async_openai):
        MockAsyncOpenAI_class, self.mock_client = mock_async_openai
        self.cu_backend = OpenAICompatBackend(model="gpt-5.4", api_key="test_key")
        self.mock_responses_create = AsyncMock()
        self.mock_client.responses.create = self.mock_responses_create

    async def test_responses_create_success(self):
        mock_response = MagicMock(id="resp_123")
        self.mock_responses_create.return_value = mock_response

        response = await self.cu_backend._responses_create(test_arg="value")
        self.mock_responses_create.assert_called_once_with(test_arg="value")
        assert response == mock_response

    async def test_responses_create_retry_on_rate_limit(self):
        # Configure the mock to raise RateLimitError twice, then succeed
        self.mock_responses_create.side_effect = [
            RateLimitError("too fast", response=MagicMock(), body=""),
            RateLimitError("too fast", response=MagicMock(), body=""),
            MagicMock(id="resp_123_retried"),
        ]

        response = await self.cu_backend._responses_create(test_arg="value")
        assert self.mock_responses_create.call_count == 3
        assert response.id == "resp_123_retried"

    async def test_computer_use_step_initial_call(self):
        screenshot = b"fake_screenshot_bytes"
        task = "Perform this task"
        mock_response = MagicMock(id="cu_resp_1")
        mock_response.output = []  # No safety checks

        self.mock_responses_create.return_value = mock_response

        result = await self.cu_backend._computer_use_step(screenshot, task)

        self.mock_responses_create.assert_called_once()
        args, kwargs = self.mock_responses_create.call_args
        assert kwargs["model"] == "gpt-5.4"
        assert kwargs["tools"] == [{"type": "computer"}]
        assert "input" in kwargs
        input_content = kwargs["input"][0]["content"]
        assert any(item["text"] == task for item in input_content if item["type"] == "input_text")
        assert any(
            f"data:image/png;base64,{base64.b64encode(screenshot).decode('utf-8')}"
            in item["image_url"]
            for item in input_content
            if item["type"] == "input_image"
        )
        assert result.response == mock_response
        assert result.has_safety_checks is False
        assert self.cu_backend._previous_response_id == "cu_resp_1"

    async def test_computer_use_step_with_system_prompt(self):
        self.cu_backend.system_prompt = "You are a helpful assistant."
        screenshot = b"fake_screenshot_bytes"
        task = "Perform this task"
        mock_response = MagicMock(id="cu_resp_1")
        mock_response.output = []

        self.mock_responses_create.return_value = mock_response
        await self.cu_backend._computer_use_step(screenshot, task)

        args, kwargs = self.mock_responses_create.call_args
        assert kwargs["instructions"] == "You are a helpful assistant."

    async def test_computer_use_step_continuation_call(self):
        screenshot = b"fake_screenshot_bytes_cont"
        task = "Continue task"
        call_id = "call_abc"
        self.cu_backend._previous_response_id = "prev_resp_id"

        mock_response = MagicMock(id="cu_resp_2")
        mock_response.output = []
        self.mock_responses_create.return_value = mock_response

        result = await self.cu_backend._computer_use_step(screenshot, task, call_id)

        self.mock_responses_create.assert_called_once()
        args, kwargs = self.mock_responses_create.call_args
        assert kwargs["previous_response_id"] == "prev_resp_id"
        assert kwargs["input"][0]["type"] == "computer_call_output"
        assert kwargs["input"][0]["call_id"] == call_id
        assert "output" in kwargs["input"][0]
        assert (
            f"data:image/png;base64,{base64.b64encode(screenshot).decode('utf-8')}"
            in kwargs["input"][0]["output"]["image_url"]
        )
        assert result.response == mock_response
        assert result.has_safety_checks is False
        assert self.cu_backend._previous_response_id == "cu_resp_2"

    async def test_computer_use_step_with_pending_safety_checks(self):
        screenshot = b"fake_screenshot_bytes"
        task = "Perform this task"

        mock_safety_item = MagicMock(type="computer_call")
        mock_safety_item.pending_safety_checks = ["P2"]
        mock_response = MagicMock(id="cu_resp_3", output=[mock_safety_item])
        self.mock_responses_create.return_value = mock_response

        result = await self.cu_backend._computer_use_step(screenshot, task)
        assert result.has_safety_checks is True

    def test_extract_computer_calls_single_action(self):
        mock_action = MagicMock(type="click", x=10, y=20, button="left")
        mock_item = MagicMock(type="computer_call", call_id="c1", actions=[mock_action])
        mock_response = MagicMock(output=[mock_item])

        calls = self.cu_backend._extract_computer_calls(mock_response)
        assert len(calls) == 1
        assert calls[0]["call_id"] == "c1"
        assert calls[0]["action_type"] == "click"
        assert calls[0]["x"] == 10
        assert calls[0]["y"] == 20
        assert calls[0]["button"] == "left"

    def test_extract_computer_calls_multiple_actions(self):
        mock_action1 = MagicMock(type="click", x=10, y=20)
        mock_action2 = MagicMock(type="type", text="hello")
        mock_item = MagicMock(
            type="computer_call", call_id="c2", actions=[mock_action1, mock_action2]
        )
        mock_response = MagicMock(output=[mock_item])

        calls = self.cu_backend._extract_computer_calls(mock_response)
        assert len(calls) == 2
        assert calls[0]["action_type"] == "click"
        assert calls[1]["action_type"] == "type"
        assert calls[1]["text"] == "hello"

    def test_extract_computer_calls_legacy_single_action_field(self):
        # Simulate older SDK response where action might be a single field, not list
        mock_action = MagicMock(type="click", x=50, y=60)
        mock_item = MagicMock(type="computer_call", call_id="c3", action=mock_action, actions=[])
        mock_response = MagicMock(output=[mock_item])

        calls = self.cu_backend._extract_computer_calls(mock_response)
        assert len(calls) == 1
        assert calls[0]["action_type"] == "click"
        assert calls[0]["x"] == 50

    def test_extract_computer_calls_no_actions(self):
        mock_item = MagicMock(type="computer_call", call_id="c4", actions=[], action=None)
        mock_response = MagicMock(output=[mock_item])

        calls = self.cu_backend._extract_computer_calls(mock_response)
        assert len(calls) == 0

    def test_extract_computer_calls_non_computer_call_items(self):
        mock_item_cu = MagicMock(
            type="computer_call", call_id="c5", actions=[MagicMock(type="click")]
        )
        mock_item_other = MagicMock(type="message")
        mock_response = MagicMock(output=[mock_item_cu, mock_item_other])

        calls = self.cu_backend._extract_computer_calls(mock_response)
        assert len(calls) == 1
        assert calls[0]["action_type"] == "click"

    def test_extract_text_success(self):
        mock_response = MagicMock(output_text="Hello, World!")
        text = self.cu_backend._extract_text(mock_response)
        assert text == "Hello, World!"

    def test_extract_text_empty(self):
        mock_response = MagicMock(output_text="")
        text = self.cu_backend._extract_text(mock_response)
        assert text == ""

    def test_extract_text_missing_attribute(self):
        mock_response = MagicMock(spec=[])  # No output_text attribute
        text = self.cu_backend._extract_text(mock_response)
        assert text == ""

    def test_reset_session(self):
        self.cu_backend._previous_response_id = "some_id"
        self.cu_backend.reset_session()
        assert self.cu_backend._previous_response_id is None


class TestMapCUAction:
    """Tests for _map_cu_action method."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_async_openai):
        MockAsyncOpenAI_class, mock_client = (
            mock_async_openai  # unpack here, not used directly in this fixture, but good practice
        )
        self.backend = OpenAICompatBackend(model="gpt-5.4", api_key="test_key")

    @pytest.mark.parametrize(
        "cu_action, expected_mapped_action",
        [
            (
                {"action_type": "click", "x": 100, "y": 200, "call_id": "c1"},
                {
                    "reasoning": "computer_use: click",
                    "action": {"action_type": "click", "coordinates": [100, 200]},
                    "done": False,
                    "confidence": 0.9,
                    "call_id": "c1",
                },
            ),
            (
                {"action_type": "double_click", "x": 50, "y": 60, "call_id": "c2"},
                {
                    "reasoning": "computer_use: double_click",
                    "action": {"action_type": "double_click", "coordinates": [50, 60]},
                    "done": False,
                    "confidence": 0.9,
                    "call_id": "c2",
                },
            ),
            (
                {"action_type": "right_click", "x": 10, "y": 20, "call_id": "c3"},
                {
                    "reasoning": "computer_use: right_click",
                    "action": {"action_type": "click", "button": "right", "coordinates": [10, 20]},
                    "done": False,
                    "confidence": 0.9,
                    "call_id": "c3",
                },
            ),
            (
                {"action_type": "click", "x": 10, "y": 20, "button": "right", "call_id": "c4"},
                {
                    "reasoning": "computer_use: click",
                    "action": {"action_type": "click", "button": "right", "coordinates": [10, 20]},
                    "done": False,
                    "confidence": 0.9,
                    "call_id": "c4",
                },
            ),
            (
                {"action_type": "type", "text": "hello", "call_id": "c5"},
                {
                    "reasoning": "computer_use: type",
                    "action": {"action_type": "type", "text": "hello"},
                    "done": False,
                    "confidence": 0.9,
                    "call_id": "c5",
                },
            ),
            (
                {"action_type": "keypress", "keys": ["ctrl", "c"], "call_id": "c6"},
                {
                    "reasoning": "computer_use: keypress",
                    "action": {"action_type": "hotkey", "keys": ["ctrl", "c"]},
                    "done": False,
                    "confidence": 0.9,
                    "call_id": "c6",
                },
            ),
            (
                {"action_type": "scroll", "x": 100, "y": 200, "scroll_y": 240, "call_id": "c7"},
                {
                    "reasoning": "computer_use: scroll",
                    "action": {"action_type": "scroll", "coordinates": [100, 200], "clicks": 2},
                    "done": False,
                    "confidence": 0.9,
                    "call_id": "c7",
                },
            ),
            (
                {"action_type": "scroll", "x": 100, "y": 200, "scroll_y": -60, "call_id": "c8"},
                {
                    "reasoning": "computer_use: scroll",
                    "action": {"action_type": "scroll", "coordinates": [100, 200], "clicks": -1},
                    "done": False,
                    "confidence": 0.9,
                    "call_id": "c8",
                },
            ),
            (
                {"action_type": "scroll", "x": 100, "y": 200, "scroll_y": 0, "call_id": "c9"},
                {
                    "reasoning": "computer_use: scroll",
                    "action": {"action_type": "scroll", "coordinates": [100, 200], "clicks": 0},
                    "done": False,
                    "confidence": 0.9,
                    "call_id": "c9",
                },
            ),
            (
                {
                    "action_type": "drag",
                    "path": [
                        {"x": 10, "y": 20},
                        {"x": 30, "y": 40},
                        {"x": 100, "y": 200},
                    ],
                    "call_id": "c10",
                },
                {
                    "reasoning": "computer_use: drag",
                    "action": {
                        "action_type": "drag",
                        "start_x": 10,
                        "start_y": 20,
                        "end_x": 100,
                        "end_y": 200,
                    },
                    "done": False,
                    "confidence": 0.9,
                    "call_id": "c10",
                },
            ),
            (
                {"action_type": "move", "x": 300, "y": 400, "call_id": "c11"},
                {
                    "reasoning": "computer_use: move",
                    "action": {"action_type": "move", "coordinates": [300, 400]},
                    "done": False,
                    "confidence": 0.9,
                    "call_id": "c11",
                },
            ),
            (
                {"action_type": "screenshot", "call_id": "c12"},
                {
                    "reasoning": "computer_use: screenshot",
                    "action": {"action_type": "screenshot"},
                    "done": False,
                    "confidence": 0.9,
                    "call_id": "c12",
                },
            ),
            (
                {"action_type": "wait", "call_id": "c13"},
                {
                    "reasoning": "computer_use: wait",
                    "action": {"action_type": "wait", "seconds": 1},
                    "done": False,
                    "confidence": 0.9,
                    "call_id": "c13",
                },
            ),
            # Drag with insufficient path
            (
                {"action_type": "drag", "path": [{"x": 10, "y": 20}], "call_id": "c14"},
                {
                    "reasoning": "computer_use: drag",
                    "action": {
                        "action_type": "drag",
                        "start_x": 0,
                        "start_y": 0,
                        "end_x": 0,
                        "end_y": 0,
                    },
                    "done": False,
                    "confidence": 0.9,
                    "call_id": "c14",
                },
            ),
            # Drag with no path
            (
                {"action_type": "drag", "call_id": "c15"},
                {
                    "reasoning": "computer_use: drag",
                    "action": {
                        "action_type": "drag",
                        "start_x": 0,
                        "start_y": 0,
                        "end_x": 0,
                        "end_y": 0,
                    },
                    "done": False,
                    "confidence": 0.9,
                    "call_id": "c15",
                },
            ),
        ],
    )
    def test_map_cu_action(self, cu_action, expected_mapped_action):
        mapped = self.backend._map_cu_action(cu_action)
        assert mapped == expected_mapped_action


class TestRunCULoop:
    """Tests for run_cu_loop method."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_async_openai):
        _, self.mock_client = mock_async_openai
        self.cu_backend = OpenAICompatBackend(model="gpt-5.4")
        self.mock_responses_create = AsyncMock()
        self.mock_client.responses.create = self.mock_responses_create
        self.mock_take_screenshot = AsyncMock(return_value=b"fake_screenshot")
        self.mock_execute_action = AsyncMock()
        self.cu_backend._map_cu_action = MagicMock(
            side_effect=lambda x: {"action_type": x["action_type"], "call_id": x["call_id"]}
        )

        # Patch asyncio.sleep to prevent actual delays during tests
        self._sleep_patch = patch(
            "device_use.backends.openai_compat.asyncio.sleep", new_callable=AsyncMock
        )
        self.mock_sleep = self._sleep_patch.start()
        yield
        self._sleep_patch.stop()

    async def test_run_cu_loop_basic_flow(self):
        # Simulate two turns
        # Turn 1: model returns a click action
        mock_response_1 = MagicMock(
            id="resp_1",
            output=[
                MagicMock(
                    type="computer_call",
                    call_id="call_1",
                    actions=[MagicMock(type="click")],
                    pending_safety_checks=[],
                )
            ],
        )
        # Turn 2: model returns a type action, then no actions (task done)
        mock_response_2 = MagicMock(
            id="resp_2",
            output=[
                MagicMock(
                    type="computer_call",
                    call_id="call_2",
                    actions=[MagicMock(type="type")],
                    pending_safety_checks=[],
                )
            ],
        )
        mock_response_3 = MagicMock(id="resp_3", output=[])  # Task done

        self.mock_responses_create.side_effect = [mock_response_1, mock_response_2, mock_response_3]

        all_actions = await self.cu_backend.run_cu_loop(
            "task", self.mock_take_screenshot, self.mock_execute_action
        )

        assert self.mock_take_screenshot.call_count == 3
        assert self.mock_responses_create.call_count == 3
        assert self.mock_execute_action.call_count == 2
        assert len(all_actions) == 2
        assert all_actions[0]["action_type"] == "click"
        assert all_actions[1]["action_type"] == "type"
        assert self.mock_sleep.call_count == 0  # No inter-action delay (1 action per turn)

    async def test_run_cu_loop_max_turns_reached(self):
        mock_cu_item = MagicMock(
            type="computer_call",
            call_id="call_n",
            actions=[MagicMock(type="click")],
            pending_safety_checks=[],
        )
        mock_response = MagicMock(id="resp_n", output=[mock_cu_item])
        self.mock_responses_create.side_effect = [mock_response] * 3

        all_actions = await self.cu_backend.run_cu_loop(
            "task", self.mock_take_screenshot, self.mock_execute_action, max_turns=2
        )

        assert self.mock_take_screenshot.call_count == 2
        assert self.mock_responses_create.call_count == 2
        assert self.mock_execute_action.call_count == 2
        assert len(all_actions) == 2

    async def test_run_cu_loop_safety_checks_abort(self):
        mock_safety_item = MagicMock(type="computer_call")
        mock_safety_item.pending_safety_checks = ["P1"]
        mock_response = MagicMock(id="resp_safety", output=[mock_safety_item])

        self.mock_responses_create.return_value = mock_response

        all_actions = await self.cu_backend.run_cu_loop(
            "task", self.mock_take_screenshot, self.mock_execute_action
        )

        assert self.mock_take_screenshot.call_count == 1
        assert self.mock_responses_create.call_count == 1
        assert self.mock_execute_action.call_count == 0
        assert len(all_actions) == 0

    async def test_run_cu_loop_no_actions_ends_loop(self):
        mock_response_1 = MagicMock(id="resp_1", output=[])
        self.mock_responses_create.return_value = mock_response_1

        all_actions = await self.cu_backend.run_cu_loop(
            "task", self.mock_take_screenshot, self.mock_execute_action
        )

        assert self.mock_take_screenshot.call_count == 1
        assert self.mock_responses_create.call_count == 1
        assert self.mock_execute_action.call_count == 0
        assert len(all_actions) == 0

    async def test_run_cu_loop_inter_action_delay(self):
        mock_action1 = MagicMock(type="click")
        mock_action2 = MagicMock(type="type")
        mock_response = MagicMock(
            id="resp_delay",
            output=[
                MagicMock(
                    type="computer_call",
                    call_id="call_d",
                    actions=[mock_action1, mock_action2],
                    pending_safety_checks=[],
                )
            ],
        )
        mock_response_done = MagicMock(id="resp_done", output=[])

        self.mock_responses_create.side_effect = [mock_response, mock_response_done]

        await self.cu_backend.run_cu_loop(
            "task", self.mock_take_screenshot, self.mock_execute_action
        )
        # Should sleep once after the first action in the batch
        self.mock_sleep.assert_called_once_with(0.12)

    async def test_run_cu_loop_no_inter_action_delay_for_wait_screenshot(self):
        mock_action1 = MagicMock(type="wait")
        mock_action2 = MagicMock(type="screenshot")
        mock_action3 = MagicMock(type="click")
        mock_response = MagicMock(
            id="resp_delay",
            output=[
                MagicMock(
                    type="computer_call",
                    call_id="call_d",
                    actions=[mock_action1, mock_action2, mock_action3],
                    pending_safety_checks=[],
                )
            ],
        )
        mock_response_done = MagicMock(id="resp_done", output=[])

        self.mock_responses_create.side_effect = [mock_response, mock_response_done]

        await self.cu_backend.run_cu_loop(
            "task", self.mock_take_screenshot, self.mock_execute_action
        )
        # wait and screenshot skip delay; click is last item so no delay after
        self.mock_sleep.assert_not_called()


class TestPlanObserveLocate:
    """Tests for plan, observe, and locate methods."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_async_openai):
        MockAsyncOpenAI_class, self.mock_client = mock_async_openai
        self.cu_backend = OpenAICompatBackend(model="gpt-5.4", api_key="test_key")
        self.legacy_backend = OpenAICompatBackend(model="gpt-4o", api_key="test_key")
        self.mock_responses_create = AsyncMock()
        self.mock_client.responses.create = self.mock_responses_create
        self.mock_chat_completions_create = AsyncMock()
        self.mock_client.chat.completions.create = self.mock_chat_completions_create
        self.screenshot_bytes = b"fake_screenshot_data"

    async def test_observe_native_cu(self):
        mock_response = MagicMock(
            id="obs_resp",
            output_text="""
{"description": "screen", "elements": []}
""",
        )
        self.mock_responses_create.return_value = mock_response

        result = await self.cu_backend.observe(self.screenshot_bytes)
        self.mock_responses_create.assert_called_once()
        assert result == {"description": "screen", "elements": []}

    async def test_observe_native_cu_with_context(self):
        mock_response = MagicMock(
            id="obs_resp",
            output_text="""
{"description": "screen", "elements": []}
""",
        )
        self.mock_responses_create.return_value = mock_response

        await self.cu_backend.observe(self.screenshot_bytes, context="user wants to log in")
        args, kwargs = self.mock_responses_create.call_args
        prompt_content = kwargs["input"][0]["content"][0]["text"]
        assert "Context: user wants to log in" in prompt_content

    async def test_observe_native_cu_invalid_json(self):
        mock_response = MagicMock(id="obs_resp", output_text="Not valid JSON")
        self.mock_responses_create.return_value = mock_response

        result = await self.cu_backend.observe(self.screenshot_bytes)
        assert result == {"description": "Not valid JSON", "elements": []}

    async def test_observe_legacy(self):
        mock_choice = MagicMock()
        mock_choice.message.content = """
{"description": "legacy screen", "elements": []}
"""
        self.mock_chat_completions_create.return_value = MagicMock(choices=[mock_choice])

        result = await self.legacy_backend.observe(self.screenshot_bytes, context="context")
        self.mock_chat_completions_create.assert_called_once()
        args, kwargs = self.mock_chat_completions_create.call_args
        assert "Context: context" in kwargs["messages"][-1]["content"][0]["text"]
        assert result == {"description": "legacy screen", "elements": []}

    async def test_plan_native_initial(self):
        # Mock _computer_use_step to return a click action
        self.cu_backend._computer_use_step = AsyncMock(
            return_value=_CUStepResult(
                response=MagicMock(
                    output=[
                        MagicMock(
                            type="computer_call",
                            call_id="call_p1",
                            actions=[MagicMock(type="click", x=10, y=20)],
                        )
                    ]
                ),
                has_safety_checks=False,
            )
        )
        self.cu_backend._map_cu_action = MagicMock(
            return_value={
                "reasoning": "mapped click",
                "action": {"action_type": "click"},
                "done": False,
                "call_id": "call_p1",
            }
        )

        result = await self.cu_backend.plan(self.screenshot_bytes, "task")
        self.cu_backend._computer_use_step.assert_called_once()
        self.cu_backend._map_cu_action.assert_called_once()
        assert result["action"]["action_type"] == "click"
        assert result["call_id"] == "call_p1"

    async def test_plan_native_with_history_and_continuation(self):
        # Mock _computer_use_step to return a type action
        self.cu_backend._previous_response_id = "prev_resp_id_plan"
        self.cu_backend._computer_use_step = AsyncMock(
            return_value=_CUStepResult(
                response=MagicMock(
                    output=[
                        MagicMock(
                            type="computer_call",
                            call_id="call_p2",
                            actions=[MagicMock(type="type", text="test")],
                        )
                    ]
                ),
                has_safety_checks=False,
            )
        )
        self.cu_backend._map_cu_action = MagicMock(
            return_value={
                "reasoning": "mapped type",
                "action": {"action_type": "type"},
                "done": False,
                "call_id": "call_p2",
            }
        )
        history = [{"action": "click", "call_id": "call_prev"}]

        result = await self.cu_backend.plan(self.screenshot_bytes, "task", history)
        self.cu_backend._computer_use_step.assert_called_once()
        args, kwargs = self.cu_backend._computer_use_step.call_args
        assert args[2] == "call_prev"
        assert "Previous steps" in args[1]
        assert result["action"]["action_type"] == "type"

    async def test_plan_native_task_done_no_cu_actions(self):
        # Mock _computer_use_step to return no computer_call items
        self.cu_backend._computer_use_step = AsyncMock(
            return_value=_CUStepResult(
                response=MagicMock(output=[], output_text="Task finished."), has_safety_checks=False
            )
        )

        result = await self.cu_backend.plan(self.screenshot_bytes, "task")
        assert result["done"] is True
        assert result["reasoning"] == "Task finished."
        assert result["action"]["action_type"] == "wait"

    async def test_plan_native_remaining_actions(self):
        # Mock _computer_use_step to return multiple actions
        mock_action1 = MagicMock(type="click", x=10, y=20)
        mock_action2 = MagicMock(type="type", text="abc")
        self.cu_backend._computer_use_step = AsyncMock(
            return_value=_CUStepResult(
                response=MagicMock(
                    output=[
                        MagicMock(
                            type="computer_call",
                            call_id="call_p3",
                            actions=[mock_action1, mock_action2],
                        )
                    ]
                ),
                has_safety_checks=False,
            )
        )
        self.cu_backend._map_cu_action = MagicMock(
            side_effect=[
                {
                    "reasoning": "computer_use: click",
                    "action": {"action_type": "click"},
                    "done": False,
                    "confidence": 0.9,
                    "call_id": "call_p3",
                },
                {
                    "reasoning": "computer_use: type",
                    "action": {"action_type": "type"},
                    "done": False,
                    "confidence": 0.9,
                    "call_id": "call_p3",
                },
            ]
        )

        result = await self.cu_backend.plan(self.screenshot_bytes, "task")
        assert result["action"]["action_type"] == "click"
        assert "_remaining_actions" in result
        assert len(result["_remaining_actions"]) == 1
        assert result["_remaining_actions"][0]["action"]["action_type"] == "type"
        assert self.cu_backend._map_cu_action.call_count == 2

    async def test_plan_legacy(self):
        mock_choice = MagicMock()
        mock_choice.message.content = """
{"action": {"action_type": "type", "text": "hello"}, "reasoning": "type text", "done": false, "confidence": 0.8}
"""
        self.mock_chat_completions_create.return_value = MagicMock(choices=[mock_choice])

        result = await self.legacy_backend.plan(self.screenshot_bytes, "task", history=[])
        self.mock_chat_completions_create.assert_called_once()
        assert result["action"]["action_type"] == "type"
        assert result["reasoning"] == "type text"

    async def test_locate_native_cu_success(self):
        mock_response = MagicMock(
            id="loc_resp",
            output_text="""
{"x": 123, "y": 456}
""",
        )
        self.mock_responses_create.return_value = mock_response

        coords = await self.cu_backend.locate(self.screenshot_bytes, "button")
        self.mock_responses_create.assert_called_once()
        assert coords == (123, 456)

    async def test_locate_native_cu_null_coords(self):
        mock_response = MagicMock(
            id="loc_resp",
            output_text="""
{"x": null, "y": null}
""",
        )
        self.mock_responses_create.return_value = mock_response

        coords = await self.cu_backend.locate(self.screenshot_bytes, "button")
        assert coords is None

    async def test_locate_native_cu_invalid_json(self):
        mock_response = MagicMock(id="loc_resp", output_text="Not JSON")
        self.mock_responses_create.return_value = mock_response

        coords = await self.cu_backend.locate(self.screenshot_bytes, "button")
        assert coords is None

    async def test_locate_legacy_returns_none(self):
        coords = await self.legacy_backend.locate(self.screenshot_bytes, "button")
        assert coords is None


class TestLegacyChatCompletions:
    """Tests for legacy chat completions path."""

    @pytest.fixture(autouse=True)
    def setup(self, mock_async_openai):
        MockAsyncOpenAI_class, self.mock_client = mock_async_openai
        self.legacy_backend = OpenAICompatBackend(model="gpt-4o", api_key="test_key")
        self.mock_chat_completions_create = AsyncMock()
        self.mock_client.chat.completions.create = self.mock_chat_completions_create

    async def test_chat_call_success(self):
        mock_choice = MagicMock()
        mock_choice.message.content = "response content"
        self.mock_chat_completions_create.return_value = MagicMock(choices=[mock_choice])

        messages = [{"role": "user", "content": "test"}]
        result = await self.legacy_backend._chat_call(messages)
        self.mock_chat_completions_create.assert_called_once_with(
            model="gpt-4o", messages=messages, max_tokens=4096, temperature=0.0
        )
        assert result == "response content"

    async def test_chat_call_rate_limit_retry(self):
        self.mock_chat_completions_create.side_effect = [
            RateLimitError("too fast", response=MagicMock(), body=""),
            MagicMock(choices=[MagicMock(message=MagicMock(content="retried content"))]),
        ]

        messages = [{"role": "user", "content": "test"}]
        result = await self.legacy_backend._chat_call(messages)
        assert self.mock_chat_completions_create.call_count == 2
        assert result == "retried content"

    async def test_make_image_content(self):
        screenshot = b"image_data"
        text = "description"
        content = self.legacy_backend._make_image_content(screenshot, text)

        expected_b64 = base64.b64encode(screenshot).decode("utf-8")
        assert content == [
            {"type": "text", "text": text},
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{expected_b64}",
                    "detail": "high",
                },
            },
        ]


class TestStripMarkdownFences:
    """Tests for _strip_markdown_fences helper function."""

    @pytest.mark.parametrize(
        "input_text, expected_output",
        [
            (
                """```json
{"key": "value"}
```""",
                """{"key": "value"}""",
            ),
            (
                """```
plain text
```""",
                """plain text""",
            ),
            ("No fences here", "No fences here"),
            (
                """  ```json
{"key": "value"}
```  """,
                """{"key": "value"}""",
            ),
            (
                """```json
{
  "key": "value"
}
```""",
                """{
  "key": "value"
}""",
            ),
            (
                """```
""",
                """""",
            ),  # Empty content inside fences
            (
                """```json
""",
                """""",
            ),
            ("", ""),
            ("  ", ""),
            (
                """text before
```json
{"key": "value"}
```
text after""",
                """text before
```json
{"key": "value"}
```
text after""",
            ),  # Should not strip if not at start/end
            (
                """```json
{}""",
                """{}""",
            ),  # Missing closing fence
        ],
    )
    def test_strip_markdown_fences(self, input_text, expected_output):
        assert _strip_markdown_fences(input_text) == expected_output
