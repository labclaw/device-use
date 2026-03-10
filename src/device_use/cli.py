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
    elif args.command == "demo":
        _demo(args.name)
    else:
        parser.print_help()


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
    from device_use.instruments import ControlMode
    from device_use.instruments.nmr.adapter import TopSpinAdapter
    from device_use.instruments.plate_reader import PlateReaderAdapter
    from device_use.orchestrator import Orchestrator

    orch = Orchestrator()
    orch.register(TopSpinAdapter(mode=ControlMode.OFFLINE))
    orch.register(PlateReaderAdapter(mode=ControlMode.OFFLINE))

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


if __name__ == "__main__":
    main()
