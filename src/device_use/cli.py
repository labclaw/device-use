"""CLI for device-use: list-profiles, run, interactive."""

import argparse
import asyncio
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="device-use",
        description="GUI agent for scientific instruments",
    )
    subparsers = parser.add_subparsers(dest="command")

    # list-profiles
    subparsers.add_parser("list-profiles", help="Show available device profiles")

    # run
    run_parser = subparsers.add_parser("run", help="Execute a task on instrument software")
    run_parser.add_argument("task", help="Task description")
    run_parser.add_argument(
        "--profile", "-p", required=True, help="Device profile name or YAML path"
    )
    run_parser.add_argument(
        "--backend",
        "-b",
        default="claude",
        choices=["claude", "openai"],
        help="VLM backend",
    )
    run_parser.add_argument("--model", "-m", help="Model name override")
    run_parser.add_argument("--max-steps", type=int, default=30, help="Maximum agent steps")

    # interactive
    interactive_parser = subparsers.add_parser("interactive", help="Interactive REPL mode")
    interactive_parser.add_argument("--profile", "-p", required=True, help="Device profile")
    interactive_parser.add_argument(
        "--backend",
        "-b",
        default="claude",
        choices=["claude", "openai"],
    )
    interactive_parser.add_argument("--model", "-m", help="Model name override")

    # instruments — middleware layer
    subparsers.add_parser("instruments", help="List registered instruments and tools")

    # status — architecture overview
    subparsers.add_parser("status", help="Show architecture status and connections")

    # demo — run a demo pipeline
    demo_parser = subparsers.add_parser(
        "demo", help="Run a demo pipeline (nmr, plate-reader, multi)"
    )
    demo_parser.add_argument(
        "name",
        nargs="?",
        default="multi",
        choices=["nmr", "plate-reader", "multi"],
        help="Demo to run (default: multi)",
    )

    # scaffold — generate a new device package
    scaffold_parser = subparsers.add_parser(
        "scaffold", help="Generate a new device package (collection)"
    )
    scaffold_parser.add_argument("device_name", help="Device name (e.g. 'zeiss-zen', 'flowjo')")
    scaffold_parser.add_argument(
        "--output", "-o", default=".", help="Output directory (default: current)"
    )

    args = parser.parse_args()

    if args.command == "list-profiles":
        _list_profiles()
    elif args.command == "run":
        asyncio.run(_run(args))
    elif args.command == "interactive":
        asyncio.run(_interactive(args))
    elif args.command == "instruments":
        _instruments()
    elif args.command == "status":
        _status()
    elif args.command == "demo":
        _demo(args.name)
    elif args.command == "scaffold":
        _scaffold(args.device_name, args.output)
    else:
        _hero()


def _list_profiles():
    from device_use.profiles.loader import list_profiles

    profiles = list_profiles()
    if not profiles:
        print("No profiles found.")
        return
    print(f"{'Name':<25} {'Software':<15} {'Hardware':<10}")
    print("-" * 50)
    for p in profiles:
        hw = "Yes" if p["hardware_connected"] else "No"
        print(f"{p['name']:<25} {p['software']:<15} {hw:<10}")


def _create_backend(args):
    """Create VLM backend from CLI args."""
    if args.backend == "claude":
        from device_use.backends.claude import ClaudeBackend

        model = args.model or "claude-sonnet-4-20250514"
        return ClaudeBackend(model=model)
    else:
        from device_use.backends.openai_compat import OpenAICompatBackend

        model = args.model or "gpt-4o"
        return OpenAICompatBackend(model=model)


async def _run(args):
    from device_use.core.agent import DeviceAgent
    from device_use.profiles.loader import load_profile

    profile = load_profile(args.profile)
    backend = _create_backend(args)
    agent = DeviceAgent(profile, backend, max_steps=args.max_steps)

    print(f"Profile: {profile.name} ({'hardware' if profile.hardware_connected else 'software'})")
    print(f"Task: {args.task}")
    print(f"Backend: {args.backend}")
    print("-" * 50)

    result = await agent.execute(args.task)

    print(f"\nResult: {'SUCCESS' if result.success else 'FAILED'}")
    print(f"Steps: {result.steps}")
    print(f"Actions: {result.action_count}")
    print(f"Duration: {result.duration_ms:.0f}ms")
    if result.error:
        print(f"Error: {result.error}")


async def _interactive(args):
    from device_use.core.agent import DeviceAgent
    from device_use.profiles.loader import load_profile

    profile = load_profile(args.profile)
    backend = _create_backend(args)

    print("device-use interactive mode")
    print(f"Profile: {profile.name}")
    print("Type 'quit' to exit\n")

    while True:
        try:
            task = input("task> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not task or task.lower() in ("quit", "exit", "q"):
            break

        agent = DeviceAgent(profile, backend)
        result = await agent.execute(task)
        print(
            f"  Result: {'OK' if result.success else 'FAIL'} "
            f"({result.steps} steps, {result.duration_ms:.0f}ms)"
        )
        if result.error:
            print(f"  Error: {result.error}")


def _instruments():
    """Show registered instruments and their tools."""
    from device_use import create_orchestrator

    orch = create_orchestrator()

    instruments = orch.registry.list_instruments()
    tools = orch.registry.list_tools()

    print(f"\nInstruments ({len(instruments)}):")
    print(f"  {'Name':<18} {'Vendor':<10} {'Type':<14} {'Modes'}")
    print(f"  {'-' * 60}")
    for inst in instruments:
        modes = ", ".join(m.value for m in inst.supported_modes)
        print(f"  {inst.name:<18} {inst.vendor:<10} {inst.instrument_type:<14} {modes}")

    print(f"\nTools ({len(tools)}):")
    for tool in tools:
        print(f"  {tool.name:<35} {tool.description}")


def _status():
    """Show architecture status with live connection checks."""
    from device_use import create_orchestrator
    from device_use.tools.tooluniverse import _TU_AVAILABLE

    print("""
╔══════════════════════════════════════════════════════════════╗
║              device-use — Architecture Status                ║
╚══════════════════════════════════════════════════════════════╝
""")

    # Cloud Brain
    import os

    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    brain_status = "ready" if has_key else "demo mode (no API key)"
    print(f"  Cloud Brain:     {brain_status}")

    # Orchestrator
    orch = create_orchestrator()
    print(f"  Orchestrator:    {len(orch.registry.list_tools())} tools registered")

    # Instruments
    print("\n  Instruments:")
    for info in orch.registry.list_instruments():
        inst = orch.registry.get_instrument(info.name)
        status = "connected" if inst.connected else "offline"
        modes = ", ".join(m.value for m in info.supported_modes)
        print(f"    {info.name:<16} {info.vendor:<10} [{modes}] {status}")

    # External tools
    print("\n  External Tools:")
    print("    PubChem        NCBI PUG REST      active")
    tu_status = "active" if _TU_AVAILABLE else "install: pip install tooluniverse"
    print(f"    ToolUniverse   Harvard (600+)     {tu_status}")

    # Stats
    tools = orch.registry.list_tools()
    print(f"\n  Total tools: {len(tools)}")
    print("  Control modes: API (gRPC) | GUI (Computer Use) | Offline (local)")
    print()


def _demo(name: str):
    """Run a demo pipeline."""
    import subprocess

    demo_map = {
        "nmr": "demos/topspin_identify.py",
        "plate-reader": "demos/multi_instrument_demo.py",
        "multi": "demos/multi_instrument_demo.py",
    }
    script = demo_map[name]
    subprocess.run([sys.executable, script])


def _scaffold(device_name: str, output_dir: str):
    """Generate a new device package (collection) with standard structure."""
    import os

    slug = device_name.lower().replace("-", "_").replace(" ", "_")
    pkg_name = f"device_use_{slug}"
    class_name = "".join(
        w.capitalize() for w in device_name.replace("-", " ").replace("_", " ").split()
    )
    root = os.path.join(output_dir, pkg_name)

    if os.path.exists(root):
        print(f"Error: {root} already exists")
        return

    dirs = [
        f"{root}/src/{pkg_name}",
        f"{root}/skills",
        f"{root}/mcp",
        f"{root}/docs",
        f"{root}/examples",
        f"{root}/tests",
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)

    # pyproject.toml
    _write(
        f"{root}/pyproject.toml",
        f'''[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "{pkg_name}"
version = "0.1.0"
description = "device-use adapter for {device_name}"
requires-python = ">=3.11"
dependencies = ["device-use"]

[project.entry-points."device_use.instruments"]
{slug} = "{pkg_name}:create_adapter"

[tool.hatch.build.targets.wheel]
packages = ["src/{pkg_name}"]
''',
    )

    # Main __init__.py with adapter factory
    _write(
        f"{root}/src/{pkg_name}/__init__.py",
        f'''"""device-use adapter for {device_name}."""

from {pkg_name}.adapter import {class_name}Adapter


def create_adapter(control_mode):
    """Entry point for device-use plugin discovery."""
    return {class_name}Adapter(mode=control_mode)


__all__ = ["{class_name}Adapter", "create_adapter"]
''',
    )

    # Adapter skeleton
    _write(
        f"{root}/src/{pkg_name}/adapter.py",
        f'''"""Adapter for {device_name} — implements BaseInstrument."""

from __future__ import annotations

from device_use.instruments.base import BaseInstrument, ControlMode, InstrumentInfo


class {class_name}Adapter(BaseInstrument):
    """Control {device_name} through the device-use middleware.

    Supports three control modes:
      - OFFLINE: Process local data files
      - API: Connect via instrument API/SDK
      - GUI: Visual automation via Computer Use
    """

    def __init__(self, mode: ControlMode = ControlMode.OFFLINE):
        self._mode = mode
        self._connected = False

    def info(self) -> InstrumentInfo:
        return InstrumentInfo(
            name="{class_name}",
            vendor="TODO",
            instrument_type="{slug}",
            supported_modes=[ControlMode.OFFLINE, ControlMode.API, ControlMode.GUI],
            version="0.1.0",
        )

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def mode(self) -> ControlMode:
        return self._mode

    def connect(self) -> bool:
        # TODO: Implement connection logic
        self._connected = True
        return True

    def list_datasets(self):
        # TODO: Return available datasets
        return []

    def acquire(self, **kwargs):
        # TODO: Acquire data from instrument
        raise NotImplementedError("Acquisition not yet implemented")

    def process(self, data_path, **kwargs):
        # TODO: Process raw data
        raise NotImplementedError("Processing not yet implemented")
''',
    )

    # MCP server
    _write(
        f"{root}/mcp/server.py",
        f'''"""MCP server for {device_name} — Claude Code integration."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("{slug}")


@mcp.tool()
def list_datasets() -> str:
    """List available {device_name} datasets."""
    from {pkg_name} import create_adapter
    from device_use.instruments.base import ControlMode
    import json
    adapter = create_adapter(ControlMode.OFFLINE)
    adapter.connect()
    return json.dumps(adapter.list_datasets(), indent=2, default=str)


if __name__ == "__main__":
    mcp.run()
''',
    )

    # Example script
    _write(
        f"{root}/examples/quickstart.py",
        f'''"""Quick start — process data with {device_name}."""

from device_use import create_orchestrator


def main():
    orch = create_orchestrator()
    instruments = orch.registry.list_instruments()
    print(f"Instruments: {{len(instruments)}}")
    for info in instruments:
        print(f"  {{info.name}} ({{info.instrument_type}})")


if __name__ == "__main__":
    main()
''',
    )

    # Test skeleton
    _write(
        f"{root}/tests/test_adapter.py",
        f'''"""Tests for {class_name}Adapter."""

from {pkg_name} import {class_name}Adapter, create_adapter
from device_use.instruments.base import ControlMode


class Test{class_name}Adapter:
    def test_info(self):
        adapter = {class_name}Adapter()
        info = adapter.info()
        assert info.name == "{class_name}"
        assert info.instrument_type == "{slug}"

    def test_connect(self):
        adapter = {class_name}Adapter()
        assert adapter.connect() is True
        assert adapter.connected is True

    def test_create_adapter_factory(self):
        adapter = create_adapter(ControlMode.OFFLINE)
        assert adapter.mode == ControlMode.OFFLINE
''',
    )

    # README
    _write(
        f"{root}/README.md",
        f"""# {pkg_name}

device-use adapter for **{device_name}**.

## Install

```bash
pip install -e .
```

Once installed, `create_orchestrator()` auto-discovers this instrument via entry points.

## Usage

```python
from device_use import create_orchestrator

orch = create_orchestrator()
# {class_name} is now available as a registered instrument
```

## Structure

```
{pkg_name}/
├── src/{pkg_name}/
│   ├── __init__.py       # Entry point + create_adapter()
│   └── adapter.py        # {class_name}Adapter (BaseInstrument)
├── skills/                # Claude Code skills
├── mcp/
│   └── server.py          # MCP server for Claude Code
├── docs/                  # Documentation
├── examples/
│   └── quickstart.py      # Quick start demo
└── tests/
    └── test_adapter.py    # Adapter tests
```
""",
    )

    # Skills placeholder
    _write(
        f"{root}/skills/README.md",
        f"""# Skills for {device_name}

Place Claude Code skills (`.md` files) here.

Skills are loaded by Claude Code to provide domain-specific knowledge
about operating {device_name}.
""",
    )

    print(f"  Created {pkg_name}/ with:")
    print(f"    src/{pkg_name}/adapter.py    {class_name}Adapter skeleton")
    print("    mcp/server.py                MCP server for Claude Code")
    print("    examples/quickstart.py       Quick start demo")
    print("    tests/test_adapter.py        Test skeleton")
    print("    pyproject.toml               Entry point registered")
    print("\n  Next steps:")
    print(f"    cd {pkg_name}")
    print("    pip install -e .")
    print("    python -m pytest tests/")


def _write(path: str, content: str):
    """Write a file, creating parent directories."""
    import os

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(content)


def _hero():
    """Show a quick overview when no command is given."""
    import time

    from device_use import create_orchestrator

    print("""
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ██████╗ ███████╗██╗   ██╗██╗ ██████╗███████╗               ║
║   ██╔══██╗██╔════╝██║   ██║██║██╔════╝██╔════╝               ║
║   ██║  ██║█████╗  ██║   ██║██║██║     █████╗                 ║
║   ██║  ██║██╔══╝  ╚██╗ ██╔╝██║██║     ██╔══╝                ║
║   ██████╔╝███████╗ ╚████╔╝ ██║╚██████╗███████╗              ║
║   ╚═════╝ ╚══════╝  ╚═══╝  ╚═╝ ╚═════╝╚══════╝  USE        ║
║                                                              ║
║   ROS for Lab Instruments — AI meets Physical Science        ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
""")

    t0 = time.time()
    orch = create_orchestrator()
    dt = time.time() - t0

    instruments = orch.registry.list_instruments()
    tools = orch.registry.list_tools()

    print(f"  Middleware ready in {dt:.2f}s")
    print(f"  {len(instruments)} instruments, {len(tools)} tools\n")

    for inst in instruments:
        obj = orch.registry.get_instrument(inst.name)
        status = "connected" if obj.connected else "offline"
        modes = ", ".join(m.value for m in inst.supported_modes)
        print(f"    {inst.name:<16} {inst.vendor:<10} [{modes}] {status}")

    # Quick data summary
    nmr_count = len(orch.call_tool("topspin.list_datasets"))
    plate_count = len(orch.call_tool("platereader.list_datasets"))
    print(f"\n  Data: {nmr_count} NMR datasets, {plate_count} plate assays")

    import os

    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    print(f"  AI:   {'Claude API ready' if has_key else 'demo mode (cached responses)'}")

    print("""
  Commands:
    python -m device_use status         Architecture overview
    python -m device_use instruments    List instruments + tools
    python -m device_use demo           Run multi-instrument demo

  Demos:
    python demos/quickstart.py          30-second intro
    python demos/topspin_identify.py    AI compound identification
    python demos/lab_report_demo.py     Raw data → paper-ready report
""")


if __name__ == "__main__":
    main()
