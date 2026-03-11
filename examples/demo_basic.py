"""Basic device-use demo with mock VLM backend.

Demonstrates the agent loop without requiring real instruments or API keys.
Run: python examples/demo_basic.py
"""

import asyncio

from device_use import DeviceProfile, load_profile
from device_use.core.agent import DeviceAgent
from device_use.core.result import AgentResult


class DemoBackend:
    """Mock backend that simulates FIJI interaction."""

    def __init__(self):
        self._step = 0

    @property
    def supports_grounding(self) -> bool:
        return True

    async def observe(self, screenshot, context=""):
        return {
            "description": (
                f"FIJI main window with toolbar and menu bar visible. "
                f"Step {self._step}."
            ),
            "elements": [
                {"name": "File menu", "type": "menu", "location": "top-left"},
                {"name": "toolbar", "type": "toolbar", "location": "below menu"},
            ],
        }

    async def plan(self, screenshot, task, history=None):
        self._step += 1
        if self._step == 1:
            return {
                "reasoning": "Need to open File menu first",
                "action": {
                    "action_type": "click",
                    "x": 30,
                    "y": 10,
                    "description": "Click File menu",
                },
                "done": False,
                "confidence": 0.95,
            }
        elif self._step == 2:
            return {
                "reasoning": "Click Open to open file dialog",
                "action": {
                    "action_type": "click",
                    "x": 30,
                    "y": 40,
                    "description": "Click Open...",
                },
                "done": False,
                "confidence": 0.9,
            }
        else:
            return {
                "done": True,
                "data": {"status": "File dialog opened successfully"},
            }

    async def locate(self, screenshot, element_description):
        return (100, 100)


async def main():
    # Load FIJI profile
    profile = load_profile("imagej-fiji")
    print(f"Loaded profile: {profile.name}")
    print(f"  Software: {profile.software}")
    print(f"  Hardware connected: {profile.hardware_connected}")
    print(f"  Safety level: {profile.safety_level.value}")
    print(f"  Workflows: {[w.name for w in profile.workflows]}")
    print()

    # Create agent with mock backend
    backend = DemoBackend()
    agent = DeviceAgent(profile, backend, max_steps=10)

    # Override screenshot capture for demo (no actual screen)
    async def mock_capture():
        return b"\x89PNG\r\n\x1a\n" + b"\x00" * 100  # Fake PNG

    agent._capture_screenshot = mock_capture
    agent._executor._settle_delay = 0  # No delay in demo

    # Execute task
    print("Executing: 'Open File > Open dialog in FIJI'")
    print("-" * 50)
    result = await agent.execute("Open File > Open dialog in FIJI")

    print(f"\nResult: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"Steps: {result.steps}")
    print(f"Actions: {result.action_count}")
    print(f"Duration: {result.duration_ms:.0f}ms")
    if result.data:
        print(f"Data: {result.data}")


if __name__ == "__main__":
    asyncio.run(main())
