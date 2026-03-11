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
    "create_orchestrator",
]


def create_orchestrator(
    *,
    mode: str = "offline",
    instruments: list[str] | None = None,
    connect: bool = True,
) -> "Orchestrator":
    """Create an Orchestrator with auto-discovered instruments.

    This is the simplest way to get started with device-use:

        from device_use import create_orchestrator
        orch = create_orchestrator()

    Args:
        mode: Control mode for all instruments ("offline", "api", "gui").
        instruments: List of instrument types to register. If None, registers
            all available instruments. Options: "nmr", "plate_reader".
        connect: Whether to connect all instruments after registration.

    Returns:
        A configured Orchestrator ready to use.
    """
    from device_use.instruments import ControlMode
    from device_use.orchestrator import Orchestrator

    orch = Orchestrator()
    control_mode = ControlMode(mode)

    # Available instrument factories
    _factories = {}

    try:
        from device_use.instruments.nmr.adapter import TopSpinAdapter
        _factories["nmr"] = lambda: TopSpinAdapter(mode=control_mode)
    except ImportError:
        pass

    try:
        from device_use.instruments.plate_reader import PlateReaderAdapter
        _factories["plate_reader"] = lambda: PlateReaderAdapter(mode=control_mode)
    except ImportError:
        pass

    # Register requested or all available instruments
    targets = instruments or list(_factories.keys())
    for name in targets:
        if name in _factories:
            orch.register(_factories[name]())

    if connect:
        orch.connect_all()

    return orch
