"""LabClaw integration demo.

Shows how device-use integrates with LabClaw as a DeviceDriver.
Run: python examples/demo_labclaw.py
"""

import asyncio

from device_use import load_profile
from device_use.integrations.labclaw import DeviceUsePlugin, GUIDriver, create_plugin


class MockBackend:
    """Minimal mock backend for demo."""

    @property
    def supports_grounding(self):
        return True

    async def observe(self, screenshot, context=""):
        return {"description": "Gen5 main window", "elements": []}

    async def plan(self, screenshot, task, history=None):
        return {"done": True, "data": {"status": "task completed"}}

    async def locate(self, screenshot, desc):
        return None


async def main():
    # Using the plugin interface (as LabClaw would)
    plugin = create_plugin()
    print(f"Plugin: {plugin.name} v{plugin.version}")

    backend = MockBackend()

    # Create driver via plugin
    driver = plugin.create_driver(
        {
            "profile": "biotek-gen5",
            "backend": backend,
        }
    )

    # Connect
    connected = await driver.connect()
    print(f"Connected: {connected}")

    # Patch screenshot capture for demo (no real screen)
    async def mock_capture():
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100

    driver._agent._capture_screenshot = mock_capture
    driver._agent._executor._settle_delay = 0

    # Write (execute task)
    result = await driver.write({"task": "Read plate with current protocol"})
    print(f"Write result: {result}")

    # Read (get status)
    status = await driver.read()
    print(f"Read status: {status}")

    # Disconnect
    await driver.disconnect()
    print(f"Disconnected: {driver.is_connected}")


if __name__ == "__main__":
    asyncio.run(main())
