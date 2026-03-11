"""Tests for the agent loop, history, prompts, and result model."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from device_use.core.agent import DeviceAgent
from device_use.core.history import AgentHistory, HistoryEntry
from device_use.core.models import ActionResult, ActionRequest, ActionType, DeviceProfile
from device_use.core.prompts import PromptBuilder
from device_use.core.result import AgentResult


# --- Mock VisionBackend ---


class MockBackend:
    """Mock VisionBackend that returns canned responses."""

    def __init__(self, plan_responses: list[dict] | None = None):
        self._plan_responses = plan_responses or []
        self._plan_idx = 0
        self.observe_calls = 0
        self.plan_calls = 0

    @property
    def supports_grounding(self) -> bool:
        return True

    async def observe(self, screenshot, context=""):
        self.observe_calls += 1
        return {"description": "Mock observation", "elements": []}

    async def plan(self, screenshot, task, history=None):
        self.plan_calls += 1
        if self._plan_idx < len(self._plan_responses):
            resp = self._plan_responses[self._plan_idx]
            self._plan_idx += 1
            return resp
        return {"done": True, "data": {"status": "completed"}}

    async def locate(self, screenshot, element_description):
        return (100, 200)


# --- AgentHistory ---


class TestAgentHistory:
    def test_add_entry(self):
        history = AgentHistory(max_images=3)
        entry = HistoryEntry(step=0, action={"type": "click"})
        history.add(entry)
        assert len(history) == 1
        assert history.latest is entry

    def test_empty_history(self):
        history = AgentHistory()
        assert len(history) == 0
        assert history.latest is None

    def test_compact_drops_old_images(self):
        history = AgentHistory(max_images=2)
        for i in range(5):
            history.add(HistoryEntry(
                step=i,
                action={"type": "click"},
                screenshot=b"img_data",
            ))
        history.compact()

        # Only latest 2 should have screenshots
        screenshots = [e.screenshot for e in history.entries]
        assert screenshots[:3] == [None, None, None]
        assert screenshots[3] is not None
        assert screenshots[4] is not None

    def test_compact_preserves_text(self):
        history = AgentHistory(max_images=1)
        for i in range(3):
            history.add(HistoryEntry(
                step=i,
                action={"type": "click"},
                observation=f"Observation {i}",
                reasoning=f"Reasoning {i}",
                screenshot=b"img",
            ))
        history.compact()

        # All text preserved
        for i, entry in enumerate(history.entries):
            assert entry.observation == f"Observation {i}"
            assert entry.reasoning == f"Reasoning {i}"

    def test_to_messages(self):
        history = AgentHistory()
        history.add(HistoryEntry(
            step=0,
            action={"type": "click"},
            observation="Saw button",
            reasoning="Need to click",
            screenshot=b"img",
        ))
        messages = history.to_messages()
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        content = messages[0]["content"]
        assert any(c["type"] == "text" for c in content)
        img_parts = [c for c in content if c["type"] == "image"]
        assert len(img_parts) == 1
        assert img_parts[0]["source"]["type"] == "base64"
        assert img_parts[0]["source"]["media_type"] == "image/png"

    def test_to_messages_no_screenshot(self):
        history = AgentHistory()
        history.add(HistoryEntry(step=0, action={"type": "click"}))
        messages = history.to_messages()
        content = messages[0]["content"]
        assert not any(c.get("type") == "image" for c in content)

    def test_clear(self):
        history = AgentHistory()
        history.add(HistoryEntry(step=0, action={}))
        history.clear()
        assert len(history) == 0


# --- PromptBuilder ---


class TestPromptBuilder:
    def test_system_prompt_software(self):
        profile = DeviceProfile(name="fiji", software="FIJI")
        builder = PromptBuilder(profile)
        prompt = builder.system_prompt()
        assert "FIJI" in prompt
        assert "can be undone" in prompt
        assert "CRITICAL" not in prompt  # no hardware warning

    def test_system_prompt_hardware(self):
        profile = DeviceProfile(
            name="gen5", software="Gen5", hardware_connected=True
        )
        builder = PromptBuilder(profile)
        prompt = builder.system_prompt()
        assert "physical hardware" in prompt
        assert "real-world consequences" in prompt

    def test_system_prompt_includes_elements(self):
        from device_use.core.models import UIElement
        profile = DeviceProfile(
            name="test", software="App",
            ui_elements=[UIElement(name="btn", description="A button")],
        )
        builder = PromptBuilder(profile)
        prompt = builder.system_prompt()
        assert "btn" in prompt
        assert "A button" in prompt

    def test_observation_prompt(self):
        profile = DeviceProfile(name="test", software="App")
        builder = PromptBuilder(profile)
        prompt = builder.observation_prompt("Open file", step=3)
        assert "Open file" in prompt
        assert "3" in prompt

    def test_planning_prompt(self):
        profile = DeviceProfile(name="test", software="App")
        builder = PromptBuilder(profile)
        prompt = builder.planning_prompt("Open file", "Saw menu", step=1)
        assert "Open file" in prompt
        assert "Saw menu" in prompt
        assert "JSON" in prompt

    def test_verification_prompt(self):
        profile = DeviceProfile(name="test", software="App")
        builder = PromptBuilder(profile)
        prompt = builder.verification_prompt("Open file", "Clicked File menu")
        assert "Clicked File menu" in prompt


# --- AgentResult ---


class TestAgentResult:
    def test_success_result(self):
        result = AgentResult(
            success=True,
            task="Open image",
            steps=5,
            duration_ms=3000.0,
        )
        assert result.success is True
        assert result.action_count == 0
        assert result.success_rate == 1.0  # success with no actions = 100%

    def test_with_actions(self):
        req = ActionRequest(action_type=ActionType.CLICK)
        actions = [
            ActionResult(success=True, action=req),
            ActionResult(success=True, action=req),
            ActionResult(success=False, action=req, error="failed"),
        ]
        result = AgentResult(
            success=False,
            task="task",
            actions=actions,
        )
        assert result.action_count == 3
        assert abs(result.success_rate - 2/3) < 0.01


# --- DeviceAgent ---


class TestDeviceAgent:
    @pytest.mark.asyncio
    async def test_task_completes_immediately(self):
        """Backend says done on first plan → agent returns success."""
        profile = DeviceProfile(name="test", software="App")
        backend = MockBackend(plan_responses=[
            {"done": True, "data": {"result": "image opened"}},
        ])
        # Need non-empty screenshot for plan to work
        agent = DeviceAgent(profile, backend, max_steps=10)
        # Override _capture_screenshot to return non-empty bytes
        agent._capture_screenshot = _mock_capture
        result = await agent.execute("Open image")
        assert result.success is True
        assert result.steps == 1
        assert backend.observe_calls == 1
        assert backend.plan_calls == 1

    @pytest.mark.asyncio
    async def test_task_with_actions(self):
        """Backend plans actions then completes."""
        profile = DeviceProfile(name="test", software="App")
        backend = MockBackend(plan_responses=[
            {
                "reasoning": "Click File menu",
                "action": {"action_type": "click", "x": 50, "y": 10, "description": "File menu"},
                "done": False,
                "confidence": 0.9,
            },
            {
                "reasoning": "Click Open",
                "action": {"action_type": "click", "x": 50, "y": 40, "description": "Open item"},
                "done": False,
                "confidence": 0.8,
            },
            {"done": True, "data": {"file": "opened"}},
        ])
        agent = DeviceAgent(profile, backend, max_steps=10)
        agent._capture_screenshot = _mock_capture
        # Disable settle delay for fast tests
        agent._executor._settle_delay = 0
        result = await agent.execute("Open a file")
        assert result.success is True
        assert result.steps == 3
        assert len(result.actions) == 2

    @pytest.mark.asyncio
    async def test_task_fails(self):
        """Backend returns error → agent reports failure."""
        profile = DeviceProfile(name="test", software="App")
        backend = MockBackend(plan_responses=[
            {"done": False, "error": "Cannot find the application window"},
        ])
        agent = DeviceAgent(profile, backend, max_steps=10)
        agent._capture_screenshot = _mock_capture
        result = await agent.execute("Do something")
        assert result.success is False
        assert "Cannot find" in result.error

    @pytest.mark.asyncio
    async def test_max_steps_reached(self):
        """Agent hits max_steps → returns failure."""
        profile = DeviceProfile(name="test", software="App")
        # Backend never says done
        backend = MockBackend(plan_responses=[
            {
                "reasoning": f"Step action",
                "action": {"action_type": "wait", "seconds": 0.01},
                "done": False,
            }
            for _ in range(5)
        ])
        agent = DeviceAgent(profile, backend, max_steps=3)
        agent._capture_screenshot = _mock_capture
        agent._executor._settle_delay = 0
        result = await agent.execute("Infinite task")
        assert result.success is False
        assert "Max steps" in result.error

    @pytest.mark.asyncio
    async def test_history_compaction(self):
        """History compacts old screenshots during execution."""
        profile = DeviceProfile(name="test", software="App")
        backend = MockBackend(plan_responses=[
            {
                "reasoning": f"Step {i}",
                "action": {"action_type": "wait", "seconds": 0.01},
                "done": False,
            }
            for i in range(8)
        ] + [{"done": True}])
        agent = DeviceAgent(profile, backend, max_steps=10, max_images=3)
        agent._capture_screenshot = _mock_capture
        agent._executor._settle_delay = 0
        await agent.execute("Long task")

        # History should have entries but only latest 3 with screenshots
        entries_with_images = [
            e for e in agent.history.entries if e.screenshot is not None
        ]
        assert len(entries_with_images) <= 3

    @pytest.mark.asyncio
    async def test_invalid_action_continues(self):
        """Invalid action data doesn't crash the agent."""
        profile = DeviceProfile(name="test", software="App")
        backend = MockBackend(plan_responses=[
            {
                "reasoning": "Bad action",
                "action": {"action_type": "fly_to_moon"},
                "done": False,
            },
            {"done": True},
        ])
        agent = DeviceAgent(profile, backend, max_steps=10)
        agent._capture_screenshot = _mock_capture
        agent._executor._settle_delay = 0
        result = await agent.execute("Do task")
        assert result.success is True  # Eventually completes after skipping bad action


class TestBatchedActionStopsOnFailure:
    """Batched GPT-5.4 actions must stop executing after a failure."""

    @pytest.mark.asyncio
    async def test_remaining_actions_skipped_after_primary_failure(self):
        """If the primary action fails, remaining batched actions are not executed."""
        profile = DeviceProfile(name="test", software="App")
        backend = MockBackend(plan_responses=[
            {
                "reasoning": "Click then type",
                "action": {"action_type": "click", "x": 50, "y": 50},
                "done": False,
                "_remaining_actions": [
                    {"action": {"action_type": "type", "text": "dangerous"}},
                ],
            },
            {"done": True},
        ])
        agent = DeviceAgent(profile, backend, max_steps=10)
        agent._capture_screenshot = _mock_capture
        agent._executor._settle_delay = 0

        # Make executor return failure for the primary click action
        from unittest.mock import MagicMock
        original_execute = agent._executor.execute
        call_count = 0

        def failing_execute(action):
            nonlocal call_count
            call_count += 1
            req = ActionRequest(action_type=ActionType.CLICK)
            return ActionResult(success=False, action=req, error="Click blocked")

        agent._executor.execute = failing_execute

        result = await agent.execute("Click and type")
        # Only 1 action should have been attempted (the primary click)
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_remaining_actions_stop_after_batched_failure(self):
        """If a batched action fails mid-sequence, subsequent ones are skipped."""
        profile = DeviceProfile(name="test", software="App")
        backend = MockBackend(plan_responses=[
            {
                "reasoning": "Three actions",
                "action": {"action_type": "click", "x": 10, "y": 10},
                "done": False,
                "_remaining_actions": [
                    {"action": {"action_type": "click", "x": 20, "y": 20}},
                    {"action": {"action_type": "type", "text": "should not run"}},
                ],
            },
            {"done": True},
        ])
        agent = DeviceAgent(profile, backend, max_steps=10)
        agent._capture_screenshot = _mock_capture
        agent._executor._settle_delay = 0

        call_count = 0

        def second_fails(action):
            nonlocal call_count
            call_count += 1
            req = ActionRequest(action_type=ActionType.CLICK)
            if call_count == 2:
                return ActionResult(success=False, action=req, error="Blocked")
            return ActionResult(success=True, action=req)

        agent._executor.execute = second_fails

        result = await agent.execute("Multi-action task")
        # Primary succeeds (1), first batched fails (2), third is skipped
        assert call_count == 2


class TestMaxCUTurnsForwarded:
    """Verify that max_cu_turns is forwarded from DeviceAgent to run_cu_loop."""

    def test_max_cu_turns_forwarded(self):
        """DeviceAgent(max_cu_turns=3) passes max_turns=3 to backend.run_cu_loop."""
        profile = DeviceProfile(name="test", software="App")
        backend = MockBackend()
        backend.run_cu_loop = AsyncMock(return_value=[])

        agent = DeviceAgent(profile, backend, max_cu_turns=3)
        asyncio.run(agent.run_cu_loop(
            task="test task",
            take_screenshot=AsyncMock(return_value=b"png"),
            execute_action=AsyncMock(),
        ))

        backend.run_cu_loop.assert_called_once()
        call_kwargs = backend.run_cu_loop.call_args
        assert call_kwargs.kwargs["max_turns"] == 3

    def test_max_cu_turns_default(self):
        """Default max_cu_turns=24 is forwarded correctly."""
        profile = DeviceProfile(name="test", software="App")
        backend = MockBackend()
        backend.run_cu_loop = AsyncMock(return_value=[])

        agent = DeviceAgent(profile, backend)
        assert agent.max_cu_turns == 24

        asyncio.run(agent.run_cu_loop(
            task="test",
            take_screenshot=AsyncMock(return_value=b"png"),
            execute_action=AsyncMock(),
        ))

        assert backend.run_cu_loop.call_args.kwargs["max_turns"] == 24

    def test_max_cu_turns_caps_loop(self):
        """Integration: run_cu_loop with real backend respects max_turns cap."""
        from device_use.backends.openai_compat import OpenAICompatBackend

        cu_backend = OpenAICompatBackend(model="gpt-5.4", api_key="sk-test")
        profile = DeviceProfile(name="test", software="App")
        agent = DeviceAgent(profile, cu_backend, max_cu_turns=3)

        from types import SimpleNamespace
        turn_count = 0

        async def mock_responses(**kwargs):
            nonlocal turn_count
            turn_count += 1
            action = SimpleNamespace(
                type="click", x=10, y=20, button="left",
            )
            call = SimpleNamespace(
                type="computer_call",
                call_id=f"call_{turn_count}",
                actions=[action],
                action=action,
                pending_safety_checks=[],
            )
            return SimpleNamespace(
                id=f"resp_{turn_count}",
                output=[call],
                output_text="",
            )

        cu_backend._responses_create = mock_responses

        actions = asyncio.run(agent.run_cu_loop(
            task="infinite task",
            take_screenshot=AsyncMock(return_value=b"png"),
            execute_action=AsyncMock(),
        ))

        # Should have executed exactly 3 turns (one action each)
        assert turn_count == 3
        assert len(actions) == 3


# Helper — uses _create_minimal_png from conftest

async def _mock_capture() -> bytes:
    """Return a minimal valid PNG for testing."""
    import struct, zlib
    def _create_minimal_png():
        sig = b'\x89PNG\r\n\x1a\n'
        ihdr_data = struct.pack('>IIBBBBB', 1, 1, 8, 2, 0, 0, 0)
        ihdr_crc = zlib.crc32(b'IHDR' + ihdr_data) & 0xffffffff
        ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
        raw = b'\x00\xff\x00\x00'
        compressed = zlib.compress(raw)
        idat_crc = zlib.crc32(b'IDAT' + compressed) & 0xffffffff
        idat = struct.pack('>I', len(compressed)) + b'IDAT' + compressed + struct.pack('>I', idat_crc)
        iend_crc = zlib.crc32(b'IEND') & 0xffffffff
        iend = struct.pack('>I', 0) + b'IEND' + struct.pack('>I', iend_crc)
        return sig + ihdr + idat + iend
    return _create_minimal_png()
