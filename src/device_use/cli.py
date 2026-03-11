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
    run_parser = subparsers.add_parser(
        "run", help="Execute a task on instrument software"
    )
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
    run_parser.add_argument(
        "--max-steps", type=int, default=30, help="Maximum agent steps"
    )

    # interactive
    interactive_parser = subparsers.add_parser(
        "interactive", help="Interactive REPL mode"
    )
    interactive_parser.add_argument(
        "--profile", "-p", required=True, help="Device profile"
    )
    interactive_parser.add_argument(
        "--backend",
        "-b",
        default="claude",
        choices=["claude", "openai"],
    )
    interactive_parser.add_argument("--model", "-m", help="Model name override")

    # instruments — middleware layer
    subparsers.add_parser(
        "instruments", help="List registered instruments and tools"
    )

    # status — architecture overview
    subparsers.add_parser(
        "status", help="Show architecture status and connections"
    )

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

    print(
        f"Profile: {profile.name} "
        f"({'hardware' if profile.hardware_connected else 'software'})"
    )
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
    print(f"  {'-'*60}")
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
    print(f"\n  Instruments:")
    for info in orch.registry.list_instruments():
        inst = orch.registry.get_instrument(info.name)
        status = "connected" if inst.connected else "offline"
        modes = ", ".join(m.value for m in info.supported_modes)
        print(f"    {info.name:<16} {info.vendor:<10} [{modes}] {status}")

    # External tools
    print(f"\n  External Tools:")
    print(f"    PubChem        NCBI PUG REST      active")
    tu_status = "active" if _TU_AVAILABLE else "install: pip install tooluniverse"
    print(f"    ToolUniverse   Harvard (600+)     {tu_status}")

    # Stats
    tools = orch.registry.list_tools()
    print(f"\n  Total tools: {len(tools)}")
    print(f"  Control modes: API (gRPC) | GUI (Computer Use) | Offline (local)")
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
