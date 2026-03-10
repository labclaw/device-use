"""device-use: Like browser-use, but for scientific instruments."""

# Lazy imports — allows instrument modules (nmr, etc.) to be used
# without installing GUI automation deps (pyautogui, mss, etc.)


def __getattr__(name):
    if name == "DeviceAgent":
        from device_use.core.agent import DeviceAgent

        return DeviceAgent
    if name == "AgentResult":
        from device_use.core.result import AgentResult

        return AgentResult
    if name in ("load_profile", "list_profiles"):
        from device_use.profiles import loader

        return getattr(loader, name)
    if name in ("ActionRequest", "ActionResult", "ActionType", "AgentState", "DeviceProfile", "SafetyLevel"):
        from device_use.core import models

        return getattr(models, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DeviceAgent",
    "DeviceProfile",
    "AgentResult",
    "ActionRequest",
    "ActionResult",
    "ActionType",
    "AgentState",
    "SafetyLevel",
    "load_profile",
    "list_profiles",
]
