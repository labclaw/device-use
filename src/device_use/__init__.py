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


def _discover_plugins(control_mode) -> dict:
    """Discover instrument plugins via Python entry points.

    External instrument packages register via pyproject.toml:

        [project.entry-points."device_use.instruments"]
        my_instrument = "device_use_myinst:create_adapter"

    The entry point callable receives a ControlMode and returns a
    BaseInstrument instance.
    """
    import sys
    if sys.version_info >= (3, 12):
        from importlib.metadata import entry_points
    else:
        from importlib.metadata import entry_points

    plugins = {}
    try:
        eps = entry_points(group="device_use.instruments")
        for ep in eps:
            try:
                factory = ep.load()
                plugins[ep.name] = lambda f=factory: f(control_mode)
            except Exception:
                pass
    except Exception:
        pass
    return plugins


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

    Instruments are discovered from two sources:
      1. Built-in instruments (nmr, plate_reader) bundled in this package
      2. Plugin instruments installed via entry points (group: device_use.instruments)

    Args:
        mode: Control mode for all instruments ("offline", "api", "gui").
        instruments: List of instrument types to register. If None, registers
            all available instruments.
        connect: Whether to connect all instruments after registration.

    Returns:
        A configured Orchestrator ready to use.
    """
    from device_use.instruments import ControlMode
    from device_use.orchestrator import Orchestrator

    orch = Orchestrator()
    control_mode = ControlMode(mode)

    # Built-in instrument factories
    _factories: dict = {}

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

    # Merge plugin-discovered instruments (plugins override built-ins)
    _factories.update(_discover_plugins(control_mode))

    # Register requested or all available instruments
    targets = instruments or list(_factories.keys())
    for name in targets:
        if name in _factories:
            orch.register(_factories[name]())

    if connect:
        orch.connect_all()

    return orch
