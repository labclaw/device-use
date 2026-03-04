"""LabClaw integration -- GUIDriver and DeviceUsePlugin.

GUIDriver implements the LabClaw DeviceDriver protocol for GUI-controlled instruments.
DeviceUsePlugin provides the plugin entry point for LabClaw's plugin system.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from device_use.backends.base import VisionBackend
from device_use.core.agent import DeviceAgent
from device_use.core.models import DeviceProfile
from device_use.core.result import AgentResult

logger = logging.getLogger(__name__)


# LabClaw protocol interfaces (defined here for independence)


@runtime_checkable
class DeviceDriver(Protocol):
    """LabClaw DeviceDriver protocol."""

    async def connect(self) -> bool: ...

    async def disconnect(self) -> None: ...

    async def write(self, command: dict[str, Any]) -> dict[str, Any]: ...

    async def read(self) -> dict[str, Any]: ...

    @property
    def is_connected(self) -> bool: ...


@runtime_checkable
class DevicePlugin(Protocol):
    """LabClaw DevicePlugin protocol."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def create_driver(self, config: dict[str, Any]) -> DeviceDriver: ...


class GUIDriver:
    """DeviceDriver implementation that uses DeviceAgent for GUI automation.

    Maps LabClaw's DeviceDriver protocol to DeviceAgent operations:
    - write(command) -> DeviceAgent.execute(task)
    - read() -> current connection status
    - connect() -> initialize agent
    - disconnect() -> cleanup
    """

    def __init__(self, profile: DeviceProfile, backend: VisionBackend):
        self._profile = profile
        self._backend = backend
        self._agent: DeviceAgent | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> bool:
        """Initialize the agent and verify the instrument window is available."""
        try:
            self._agent = DeviceAgent(self._profile, self._backend)
            self._connected = True
            logger.info("GUIDriver connected: %s", self._profile.name)
            return True
        except (ValueError, RuntimeError, OSError) as e:
            logger.error("GUIDriver connection failed: %s", e)
            return False

    async def disconnect(self) -> None:
        """Cleanup agent resources."""
        self._agent = None
        self._connected = False
        logger.info("GUIDriver disconnected: %s", self._profile.name)

    async def write(self, command: dict[str, Any]) -> dict[str, Any]:
        """Execute a GUI task via the agent.

        Args:
            command: Dict with at least {"task": "description of what to do"}.
                     Optional: {"max_steps": int, "timeout": float}

        Returns:
            Dict with {"success": bool, "data": dict, "error": str, ...}
        """
        if not self._connected or self._agent is None:
            return {"success": False, "error": "Not connected"}

        task = command.get("task", "")
        if not task:
            return {"success": False, "error": "No task specified in command"}

        result: AgentResult = await self._agent.execute(task)
        return {
            "success": result.success,
            "data": result.data,
            "error": result.error,
            "steps": result.steps,
            "duration_ms": result.duration_ms,
        }

    async def read(self) -> dict[str, Any]:
        """Read current connection status."""
        if not self._connected:
            return {"error": "Not connected"}
        return {"status": "connected", "profile": self._profile.name}


class DeviceUsePlugin:
    """LabClaw plugin that provides GUI-based device drivers."""

    def __init__(self, backend: VisionBackend | None = None):
        self._backend = backend

    @property
    def name(self) -> str:
        return "device-use"

    @property
    def version(self) -> str:
        return "0.1.0"

    def create_driver(self, config: dict[str, Any]) -> GUIDriver:
        """Create a GUIDriver from configuration.

        Args:
            config: Dict with {"profile": DeviceProfile | dict, "backend": VisionBackend}
                    "profile" can also be a string name (requires profiles.loader).
        """
        profile = config.get("profile")
        if isinstance(profile, str):
            from device_use.profiles.loader import load_profile

            profile = load_profile(profile)
        elif isinstance(profile, dict):
            profile = DeviceProfile(**profile)

        if not isinstance(profile, DeviceProfile):
            raise TypeError(
                f"Expected DeviceProfile, str, or dict for 'profile', got {type(profile)}"
            )

        backend = config.get("backend", self._backend)
        if backend is None:
            raise ValueError("No VisionBackend provided in config or plugin")

        return GUIDriver(profile=profile, backend=backend)


def create_plugin(**kwargs: Any) -> DeviceUsePlugin:
    """Entry point for LabClaw plugin discovery."""
    return DeviceUsePlugin(**kwargs)
