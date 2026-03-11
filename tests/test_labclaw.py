"""Tests for LabClaw integration -- GUIDriver and DeviceUsePlugin."""

from __future__ import annotations

import pytest

from device_use.core.models import DeviceProfile
from device_use.core.result import AgentResult
from device_use.integrations.labclaw import (
    DeviceDriver,
    DevicePlugin,
    DeviceUsePlugin,
    GUIDriver,
    create_plugin,
)


# --- Mock VisionBackend ---


class MockBackend:
    """Minimal VisionBackend for testing."""

    @property
    def supports_grounding(self) -> bool:
        return True

    async def observe(self, screenshot, context=""):
        return {"description": "mock", "elements": []}

    async def plan(self, screenshot, task, history=None):
        return {"done": True, "data": {"result": "ok"}}

    async def locate(self, screenshot, element_description):
        return (0, 0)


# --- Fixtures ---


@pytest.fixture
def profile():
    return DeviceProfile(name="test-instrument", software="TestApp")


@pytest.fixture
def backend():
    return MockBackend()


@pytest.fixture
def driver(profile, backend):
    return GUIDriver(profile=profile, backend=backend)


@pytest.fixture
def plugin(backend):
    return DeviceUsePlugin(backend=backend)


# --- Protocol compliance ---


class TestProtocolCompliance:
    def test_guidriver_is_device_driver(self, driver):
        """GUIDriver satisfies the DeviceDriver protocol."""
        assert isinstance(driver, DeviceDriver)

    def test_plugin_is_device_plugin(self, plugin):
        """DeviceUsePlugin satisfies the DevicePlugin protocol."""
        assert isinstance(plugin, DevicePlugin)


# --- GUIDriver ---


class TestGUIDriver:
    def test_not_connected_initially(self, driver):
        assert driver.is_connected is False

    async def test_connect_succeeds(self, driver):
        result = await driver.connect()
        assert result is True
        assert driver.is_connected is True

    async def test_disconnect(self, driver):
        await driver.connect()
        await driver.disconnect()
        assert driver.is_connected is False

    async def test_write_executes_task(self, driver):
        await driver.connect()
        # Patch screenshot so the agent loop can proceed
        driver._agent._capture_screenshot = _mock_capture
        result = await driver.write({"task": "Click the start button"})
        assert result["success"] is True
        assert "data" in result
        assert "steps" in result
        assert "duration_ms" in result

    async def test_write_not_connected(self, driver):
        result = await driver.write({"task": "anything"})
        assert result["success"] is False
        assert result["error"] == "Not connected"

    async def test_write_empty_task(self, driver):
        await driver.connect()
        result = await driver.write({})
        assert result["success"] is False
        assert "No task" in result["error"]

    async def test_write_blank_task(self, driver):
        await driver.connect()
        result = await driver.write({"task": ""})
        assert result["success"] is False
        assert "No task" in result["error"]

    async def test_read_connected(self, driver):
        await driver.connect()
        result = await driver.read()
        assert result["status"] == "connected"
        assert result["profile"] == "test-instrument"

    async def test_read_not_connected(self, driver):
        result = await driver.read()
        assert "error" in result


# --- DeviceUsePlugin ---


class TestDeviceUsePlugin:
    def test_name(self, plugin):
        assert plugin.name == "device-use"

    def test_version(self, plugin):
        assert plugin.version == "0.1.0"

    def test_create_driver_with_profile_object(self, plugin, profile):
        driver = plugin.create_driver({"profile": profile})
        assert isinstance(driver, GUIDriver)
        assert driver.is_connected is False

    def test_create_driver_with_profile_dict(self, plugin):
        driver = plugin.create_driver({
            "profile": {"name": "from-dict", "software": "DictApp"},
        })
        assert isinstance(driver, GUIDriver)

    def test_create_driver_with_explicit_backend(self, profile):
        plugin = DeviceUsePlugin()  # no default backend
        backend = MockBackend()
        driver = plugin.create_driver({"profile": profile, "backend": backend})
        assert isinstance(driver, GUIDriver)

    def test_create_driver_no_backend_raises(self, profile):
        plugin = DeviceUsePlugin()  # no default backend
        with pytest.raises(ValueError, match="No VisionBackend"):
            plugin.create_driver({"profile": profile})

    def test_create_driver_bad_profile_type_raises(self, plugin):
        with pytest.raises(TypeError, match="Expected DeviceProfile"):
            plugin.create_driver({"profile": 42})


# --- create_plugin entry point ---


class TestCreatePlugin:
    def test_returns_plugin(self):
        plugin = create_plugin()
        assert isinstance(plugin, DeviceUsePlugin)
        assert isinstance(plugin, DevicePlugin)

    def test_with_backend(self):
        backend = MockBackend()
        plugin = create_plugin(backend=backend)
        assert plugin._backend is backend


# --- Helpers ---


async def _mock_capture() -> bytes:
    """Return a minimal valid PNG for testing."""
    from conftest import _create_minimal_png
    return _create_minimal_png()
