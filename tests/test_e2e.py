"""End-to-end tests: profile -> agent -> execute -> result.

Tests the full pipeline with mock VLM backend and mocked pyautogui.
No real instruments, API keys, or display required.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from device_use import list_profiles, load_profile
from device_use.core.agent import DeviceAgent
from device_use.core.result import AgentResult

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _mock_capture() -> bytes:
    from .conftest import _create_minimal_png

    return _create_minimal_png()


def _cli_env() -> dict[str, str]:
    env = os.environ.copy()
    src_path = str(REPO_ROOT / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{src_path}{os.pathsep}{existing}" if existing else src_path
    return env


class MockBackend:
    """Mock VisionBackend that executes a scripted multi-step plan."""

    def __init__(self, plan_responses: list[dict] | None = None):
        self._plan_responses = plan_responses or [{"done": True, "data": {"status": "completed"}}]
        self._idx = 0
        self.observe_calls = 0
        self.plan_calls = 0

    @property
    def supports_grounding(self) -> bool:
        return True

    async def observe(self, screenshot, context=""):
        self.observe_calls += 1
        return {"description": "Mock screen state", "elements": []}

    async def plan(self, screenshot, task, history=None):
        self.plan_calls += 1
        if self._idx < len(self._plan_responses):
            resp = self._plan_responses[self._idx]
            self._idx += 1
            return resp
        return {"done": True, "data": {"status": "completed"}}

    async def locate(self, screenshot, element_description):
        return (100, 200)


# ---------------------------------------------------------------------------
# E2E: FIJI profile (software-only, no hardware)
# ---------------------------------------------------------------------------


class TestE2EFiji:
    """Full pipeline with imagej-fiji profile."""

    @pytest.mark.asyncio
    async def test_load_and_execute_simple_task(self):
        """Load FIJI profile, create agent, execute task, verify result."""
        profile = load_profile("imagej-fiji")
        assert profile.name == "imagej-fiji"
        assert profile.software == "FIJI"
        assert profile.hardware_connected is False

        backend = MockBackend()
        agent = DeviceAgent(profile, backend, max_steps=10)
        agent._capture_screenshot = _mock_capture
        agent._executor._settle_delay = 0

        result = await agent.execute("Open an image file")
        assert isinstance(result, AgentResult)
        assert result.success is True
        assert result.steps == 1
        assert result.task == "Open an image file"
        assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_multi_step_task(self):
        """Agent executes multiple click actions then completes."""
        profile = load_profile("imagej-fiji")
        backend = MockBackend(
            plan_responses=[
                {
                    "reasoning": "Click File menu",
                    "action": {
                        "action_type": "click",
                        "x": 30,
                        "y": 10,
                        "description": "File menu",
                    },
                    "done": False,
                    "confidence": 0.95,
                },
                {
                    "reasoning": "Click Open",
                    "action": {
                        "action_type": "click",
                        "x": 30,
                        "y": 40,
                        "description": "Open item",
                    },
                    "done": False,
                    "confidence": 0.9,
                },
                {
                    "done": True,
                    "data": {"status": "File dialog opened"},
                },
            ]
        )

        agent = DeviceAgent(profile, backend, max_steps=10)
        agent._capture_screenshot = _mock_capture
        agent._executor._settle_delay = 0

        result = await agent.execute("Open File > Open dialog")
        assert result.success is True
        assert result.steps == 3
        assert result.action_count == 2
        assert result.data == {"status": "File dialog opened"}
        assert backend.observe_calls == 3
        assert backend.plan_calls == 3

    @pytest.mark.asyncio
    async def test_workflows_loaded(self):
        """FIJI profile includes predefined workflows."""
        profile = load_profile("imagej-fiji")
        workflow_names = [w.name for w in profile.workflows]
        assert "open_image" in workflow_names
        assert "adjust_brightness_contrast" in workflow_names
        assert "measure_selection" in workflow_names

    @pytest.mark.asyncio
    async def test_safety_level_normal(self):
        """FIJI uses normal safety (no hardware confirmation required)."""
        profile = load_profile("imagej-fiji")
        from device_use.core.models import SafetyLevel

        assert profile.safety_level == SafetyLevel.NORMAL
        assert profile.safety.max_actions_per_minute == 60


# ---------------------------------------------------------------------------
# E2E: Gen5 profile (hardware-connected plate reader)
# ---------------------------------------------------------------------------


class TestE2EGen5:
    """Full pipeline with biotek-gen5 profile (hardware mode)."""

    @pytest.mark.asyncio
    async def test_load_and_execute(self):
        """Load Gen5 profile, verify hardware mode, run task."""
        profile = load_profile("biotek-gen5")
        assert profile.name == "biotek-gen5"
        assert profile.software == "Gen5"
        assert profile.hardware_connected is True

        from device_use.core.models import SafetyLevel

        assert profile.safety_level == SafetyLevel.STRICT

        backend = MockBackend()
        agent = DeviceAgent(profile, backend, max_steps=5)
        agent._capture_screenshot = _mock_capture
        agent._executor._settle_delay = 0

        result = await agent.execute("Export results to Excel")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_safety_bounds_present(self):
        """Gen5 profile has temperature and shake speed bounds."""
        profile = load_profile("biotek-gen5")
        bounds = profile.safety.bounds
        assert bounds["temperature_min"] == 4
        assert bounds["temperature_max"] == 45
        assert bounds["shake_speed_max"] == 1000

    @pytest.mark.asyncio
    async def test_requires_confirmation_actions(self):
        """Gen5 requires confirmation for destructive actions."""
        profile = load_profile("biotek-gen5")
        assert "start_read" in profile.safety.requires_confirmation
        assert "delete_data" in profile.safety.requires_confirmation

    @pytest.mark.asyncio
    async def test_hardware_rate_limit(self):
        """Gen5 has a lower rate limit than software-only profiles."""
        profile = load_profile("biotek-gen5")
        assert profile.safety.max_actions_per_minute == 10


# ---------------------------------------------------------------------------
# E2E: LabClaw integration
# ---------------------------------------------------------------------------


class TestE2ELabClaw:
    """LabClaw plugin and GUIDriver end-to-end."""

    @pytest.mark.asyncio
    async def test_plugin_create_driver(self):
        """Plugin creates GUIDriver from profile name + backend."""
        from device_use.integrations.labclaw import create_plugin

        plugin = create_plugin()
        assert plugin.name == "device-use"
        assert plugin.version == "0.1.0"

        backend = MockBackend()
        driver = plugin.create_driver({"profile": "biotek-gen5", "backend": backend})
        assert not driver.is_connected

    @pytest.mark.asyncio
    async def test_driver_connect_write_read_disconnect(self):
        """Full driver lifecycle: connect -> write -> read -> disconnect."""
        from device_use.integrations.labclaw import create_plugin

        plugin = create_plugin()
        backend = MockBackend()
        driver = plugin.create_driver({"profile": "imagej-fiji", "backend": backend})

        # Connect
        connected = await driver.connect()
        assert connected is True
        assert driver.is_connected

        # Read status
        status = await driver.read()
        assert status["status"] == "connected"
        assert status["profile"] == "imagej-fiji"

        # Patch the internal agent to return a valid screenshot
        driver._agent._capture_screenshot = _mock_capture
        driver._agent._executor._settle_delay = 0

        # Write (execute task)
        result = await driver.write({"task": "Open file"})
        assert result["success"] is True

        # Disconnect
        await driver.disconnect()
        assert not driver.is_connected

    @pytest.mark.asyncio
    async def test_driver_write_without_connect(self):
        """Write without connect returns error."""
        from device_use.integrations.labclaw import create_plugin

        plugin = create_plugin()
        backend = MockBackend()
        driver = plugin.create_driver({"profile": "imagej-fiji", "backend": backend})

        result = await driver.write({"task": "Do something"})
        assert result["success"] is False
        assert "Not connected" in result["error"]


# ---------------------------------------------------------------------------
# E2E: CLI
# ---------------------------------------------------------------------------


class TestCLI:
    """CLI command tests."""

    def test_list_profiles_output(self):
        """'device-use list-profiles' prints profile table."""
        result = subprocess.run(
            [sys.executable, "-m", "device_use.cli", "list-profiles"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=REPO_ROOT,
            env=_cli_env(),
        )
        assert result.returncode == 0
        output = result.stdout
        # Header
        assert "Name" in output
        assert "Software" in output
        assert "Hardware" in output
        # Profiles
        assert "imagej-fiji" in output
        assert "FIJI" in output
        assert "biotek-gen5" in output
        assert "Gen5" in output

    def test_help_output(self):
        """'device-use --help' shows usage."""
        result = subprocess.run(
            [sys.executable, "-m", "device_use.cli", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=REPO_ROOT,
            env=_cli_env(),
        )
        assert result.returncode == 0
        assert "GUI agent for scientific instruments" in result.stdout

    def test_run_subcommand_requires_profile(self):
        """'device-use run' without --profile fails."""
        result = subprocess.run(
            [sys.executable, "-m", "device_use.cli", "run", "some task"],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=REPO_ROOT,
            env=_cli_env(),
        )
        assert result.returncode != 0
        assert "profile" in result.stderr.lower()


# ---------------------------------------------------------------------------
# E2E: list_profiles API
# ---------------------------------------------------------------------------


class TestListProfiles:
    """Verify list_profiles returns all built-in profiles."""

    def test_returns_both_profiles(self):
        profiles = list_profiles()
        names = [p["name"] for p in profiles]
        assert "imagej-fiji" in names
        assert "biotek-gen5" in names

    def test_profile_dict_structure(self):
        profiles = list_profiles()
        for p in profiles:
            assert "name" in p
            assert "path" in p
            assert "software" in p
            assert "hardware_connected" in p


# ---------------------------------------------------------------------------
# E2E: Error handling
# ---------------------------------------------------------------------------


class TestE2EErrors:
    """Error paths in the full pipeline."""

    @pytest.mark.asyncio
    async def test_max_steps_reached(self):
        """Agent fails gracefully when max steps exceeded."""
        profile = load_profile("imagej-fiji")
        backend = MockBackend(
            plan_responses=[
                {
                    "reasoning": "Keep waiting",
                    "action": {"action_type": "wait", "seconds": 0.001},
                    "done": False,
                }
                for _ in range(10)
            ]
        )
        agent = DeviceAgent(profile, backend, max_steps=3)
        agent._capture_screenshot = _mock_capture
        agent._executor._settle_delay = 0

        result = await agent.execute("Impossible task")
        assert result.success is False
        assert "Max steps" in result.error
        assert result.steps == 3

    @pytest.mark.asyncio
    async def test_backend_error_propagated(self):
        """Backend returning error -> agent reports failure."""
        profile = load_profile("imagej-fiji")
        backend = MockBackend(
            plan_responses=[{"done": False, "error": "Application window not found"}]
        )
        agent = DeviceAgent(profile, backend, max_steps=5)
        agent._capture_screenshot = _mock_capture
        agent._executor._settle_delay = 0

        result = await agent.execute("Do something")
        assert result.success is False
        assert "not found" in result.error

    def test_load_nonexistent_profile(self):
        """Loading a non-existent profile raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_profile("nonexistent-instrument-xyz")

    @pytest.mark.asyncio
    async def test_invalid_action_skipped(self):
        """Invalid action type doesn't crash; agent continues."""
        profile = load_profile("imagej-fiji")
        backend = MockBackend(
            plan_responses=[
                {
                    "reasoning": "Invalid action",
                    "action": {"action_type": "teleport"},
                    "done": False,
                },
                {"done": True, "data": {"status": "recovered"}},
            ]
        )
        agent = DeviceAgent(profile, backend, max_steps=5)
        agent._capture_screenshot = _mock_capture
        agent._executor._settle_delay = 0

        result = await agent.execute("Test error recovery")
        assert result.success is True
        assert result.data == {"status": "recovered"}
