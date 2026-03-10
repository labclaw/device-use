#!/usr/bin/env python3
"""
Device-Use Demo: Orchestrator Pipeline

Demonstrates the core middleware pattern — the Orchestrator runs
multi-step pipelines, routing tool calls to registered instruments,
emitting events at each step for monitoring and logging.

This is what makes device-use a middleware, not just scripts:
  - Instruments register themselves with the orchestrator
  - Pipelines define multi-step workflows declaratively
  - Events flow to listeners (logging, UI, alerts)
  - Tool routing abstracts instrument details from the brain

Usage:
    python demos/topspin_pipeline.py
    python demos/topspin_pipeline.py --dataset exam_CMCse_1
"""

import argparse
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning, module="nmrglue")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="scipy")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from device_use.instruments.nmr.adapter import TopSpinAdapter
from device_use.orchestrator import (
    Event,
    EventType,
    Orchestrator,
    Pipeline,
    PipelineStep,
    StepStatus,
    ToolSpec,
)


# ── Terminal styling ──────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"
RESET = "\033[0m"
CHECK = f"{GREEN}✓{RESET}"
ARROW = f"{CYAN}→{RESET}"

# Event icons
EVENT_ICONS = {
    EventType.PIPELINE_START: f"{BLUE}▶{RESET}",
    EventType.PIPELINE_END: f"{GREEN}■{RESET}",
    EventType.STEP_START: f"{CYAN}→{RESET}",
    EventType.STEP_END: f"{GREEN}✓{RESET}",
    EventType.STEP_ERROR: f"{RED}✗{RESET}",
    EventType.INSTRUMENT_REGISTERED: f"{MAGENTA}⚙{RESET}",
    EventType.INSTRUMENT_CONNECTED: f"{GREEN}⚡{RESET}",
    EventType.TOOL_CALLED: f"{YELLOW}⚒{RESET}",
}


def event_logger(event: Event):
    """Pretty-print orchestrator events in real time."""
    icon = EVENT_ICONS.get(event.event_type, "·")
    data = event.data

    if event.event_type == EventType.PIPELINE_START:
        print(f"\n  {icon} Pipeline {BOLD}{data['pipeline']}{RESET} started ({data['steps']} steps)")
    elif event.event_type == EventType.PIPELINE_END:
        status = f"{GREEN}SUCCESS{RESET}" if data['success'] else f"{RED}FAILED{RESET}"
        print(f"  {icon} Pipeline complete: {status} ({data['duration_ms']:.0f}ms)")
    elif event.event_type == EventType.STEP_START:
        desc = f" — {data['description']}" if data.get('description') else ""
        print(f"  {icon} Step: {BOLD}{data['step']}{RESET}{desc}")
    elif event.event_type == EventType.STEP_END:
        print(f"  {icon} Done ({data['duration_ms']:.0f}ms)")
    elif event.event_type == EventType.STEP_ERROR:
        print(f"  {icon} Error: {RED}{data['error']}{RESET}")
    elif event.event_type == EventType.INSTRUMENT_REGISTERED:
        print(f"  {icon} Registered: {BOLD}{data['instrument']}{RESET} ({data['type']})")
    elif event.event_type == EventType.INSTRUMENT_CONNECTED:
        print(f"  {icon} Connected: {BOLD}{data['instrument']}{RESET}")
    elif event.event_type == EventType.TOOL_CALLED:
        print(f"  {icon} Tool: {DIM}{data['tool']}{RESET}")


def banner():
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   {RESET}{BOLD}Orchestrator Pipeline Demo{RESET}{BOLD}{CYAN}                                 ║
║   {RESET}{DIM}Middleware in action — events, tools, pipelines{RESET}{BOLD}{CYAN}              ║
║                                                              ║
║   {RESET}{DIM}device-use | ROS for Lab Instruments{RESET}{BOLD}{CYAN}                        ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")


def main():
    parser = argparse.ArgumentParser(description="Orchestrator Pipeline Demo")
    parser.add_argument("--dataset", default="exam_CMCse_1")
    parser.add_argument("--expno", type=int, default=1)
    args = parser.parse_args()

    banner()

    # ── Initialize Orchestrator ──

    print(f"{BOLD}{MAGENTA}{'━' * 62}{RESET}")
    print(f"  {BOLD}Phase 1{RESET} {DIM}│{RESET} Initialize Orchestrator")
    print(f"{BOLD}{MAGENTA}{'━' * 62}{RESET}")

    orch = Orchestrator()
    orch.on_event(event_logger)

    # Register instrument
    nmr = TopSpinAdapter()
    nmr.connect()
    orch.register(nmr)

    # Register custom tools (beyond the auto-registered ones)
    from device_use.tools.pubchem import PubChemTool
    pubchem = PubChemTool()

    orch.registry.register_tool(ToolSpec(
        name="pubchem.lookup",
        description="Look up compound on PubChem by name",
        handler=lambda name: pubchem.lookup_by_name(name),
        parameters={"name": "Compound name"},
    ))

    # Show registered tools
    tools = orch.registry.list_tools()
    print(f"\n  {BOLD}Registered Tools:{RESET}")
    for tool in tools:
        print(f"    {DIM}• {tool.name}: {tool.description}{RESET}")

    # ── Find dataset ──

    print(f"\n{BOLD}{MAGENTA}{'━' * 62}{RESET}")
    print(f"  {BOLD}Phase 2{RESET} {DIM}│{RESET} Build & Run Pipeline")
    print(f"{BOLD}{MAGENTA}{'━' * 62}{RESET}")

    datasets = nmr.list_datasets()
    target_path = None
    target_name = args.dataset

    for ds in datasets:
        if ds["sample"] == args.dataset and ds["expno"] == args.expno:
            target_path = ds["path"]
            target_name = ds["title"] or ds["sample"]
            break

    if not target_path:
        print(f"  {RED}✗{RESET} Dataset {args.dataset}/{args.expno} not found")
        sys.exit(1)

    # ── Build Pipeline ──

    pipeline = Pipeline(
        name="nmr_analysis",
        description=f"Full NMR analysis of {target_name}",
    )

    # Step 1: Process NMR data
    pipeline.add_step(PipelineStep(
        name="process",
        description="Process raw FID → spectrum",
        tool_name="topspin.process",
        params={"data_path": target_path},
    ))

    # Step 2: Generate visualization
    pipeline.add_step(PipelineStep(
        name="visualize",
        description="Generate publication-quality plot",
        handler=lambda ctx: _visualize(ctx["process"]),
    ))

    # Step 3: AI interpretation
    pipeline.add_step(PipelineStep(
        name="interpret",
        description="Cloud Brain identifies compound",
        handler=lambda ctx: _interpret(ctx["process"]),
    ))

    # Step 4: PubChem cross-reference (conditional)
    pipeline.add_step(PipelineStep(
        name="pubchem",
        description="Cross-reference on PubChem",
        handler=lambda ctx: _pubchem_lookup(target_name),
        condition=lambda ctx: ctx.get("interpret") is not None,
    ))

    print(f"\n  {BOLD}Pipeline:{RESET} {pipeline.name} ({len(pipeline)} steps)")
    for i, step in enumerate(pipeline.steps):
        cond = " (conditional)" if step.condition else ""
        print(f"    {DIM}{i+1}. {step.name}: {step.description}{cond}{RESET}")

    # ── Execute Pipeline ──

    result = orch.run(pipeline)

    # ── Results ──

    print(f"\n{BOLD}{MAGENTA}{'━' * 62}{RESET}")
    print(f"  {BOLD}Phase 3{RESET} {DIM}│{RESET} Pipeline Results")
    print(f"{BOLD}{MAGENTA}{'━' * 62}{RESET}\n")

    for step_name, step_result in result.steps:
        status_str = {
            StepStatus.COMPLETED: f"{GREEN}completed{RESET}",
            StepStatus.FAILED: f"{RED}failed{RESET}",
            StepStatus.SKIPPED: f"{YELLOW}skipped{RESET}",
        }.get(step_result.status, step_result.status.value)

        print(f"  {step_name:20s} {status_str:30s} {DIM}{step_result.duration_ms:.0f}ms{RESET}")

        if step_result.status == StepStatus.FAILED:
            print(f"    {RED}Error: {step_result.error}{RESET}")

    # Show spectrum info from pipeline output
    spectrum = result.outputs.get("process")
    if spectrum:
        print(f"\n  {BOLD}Spectrum:{RESET}")
        print(f"    {spectrum.frequency_mhz:.0f} MHz | {spectrum.nucleus} | {spectrum.solvent}")
        print(f"    {len(spectrum.peaks)} peaks detected")

    # Show PubChem info
    pubchem_data = result.outputs.get("pubchem")
    if pubchem_data:
        print(f"\n  {BOLD}PubChem:{RESET}")
        print(f"    CID: {pubchem_data.get('CID', '?')}")
        print(f"    Formula: {pubchem_data.get('MolecularFormula', '?')}")

    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║  Pipeline Complete                                           ║
╚══════════════════════════════════════════════════════════════╝{RESET}

  Total time: {BOLD}{result.duration_ms:.0f}ms{RESET}
  Success: {BOLD}{GREEN if result.success else RED}{result.success}{RESET}

  {BOLD}What this demonstrates:{RESET}
  {DIM}• Orchestrator routes tool calls to registered instruments{RESET}
  {DIM}• Pipelines define declarative multi-step workflows{RESET}
  {DIM}• Events stream to listeners for monitoring and UI{RESET}
  {DIM}• Conditional steps skip when preconditions aren't met{RESET}
  {DIM}• This is the middleware pattern — instruments are interchangeable{RESET}
""")


# ── Pipeline step handlers ────────────────────────────────────────

def _visualize(spectrum):
    """Generate spectrum plot."""
    from device_use.instruments.nmr.visualizer import plot_spectrum
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)
    name = spectrum.sample_name or "pipeline"
    path = output_dir / f"{name}_pipeline.png"
    plot_spectrum(spectrum, output_path=path)
    return str(path)


def _interpret(spectrum):
    """Run AI interpretation."""
    from device_use.instruments.nmr.brain import NMRBrain
    brain = NMRBrain()
    return brain.interpret_spectrum(spectrum, stream=False)


def _pubchem_lookup(name):
    """Look up compound on PubChem."""
    from device_use.tools.pubchem import PubChemTool, PubChemError
    # Clean up the name
    clean = name.split(" in ")[0].split(" C")[0].strip()
    if not clean or len(clean) < 3:
        return None
    tool = PubChemTool()
    try:
        return tool.lookup_by_name(clean)
    except PubChemError:
        return None


if __name__ == "__main__":
    main()
