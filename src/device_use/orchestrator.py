"""Orchestrator — the middleware that connects AI brains to physical instruments.

Architecture:
    Cloud Brain (Claude, GPT, etc.)
            |
       Orchestrator  <-- this module
            |
    Instruments (NMR, Microscope, etc.)

The Orchestrator handles:
  1. Registry — instruments register themselves, orchestrator discovers them
  2. Pipelines — multi-step workflows (load -> process -> analyze -> recommend)
  3. Tool routing — route brain requests to the right instrument
  4. Events — steps emit events for logging/display
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

from device_use.instruments.base import BaseInstrument, InstrumentInfo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class EventType(str, Enum):
    """Event types emitted during pipeline execution."""
    PIPELINE_START = "pipeline_start"
    PIPELINE_END = "pipeline_end"
    STEP_START = "step_start"
    STEP_END = "step_end"
    STEP_ERROR = "step_error"
    INSTRUMENT_REGISTERED = "instrument_registered"
    INSTRUMENT_CONNECTED = "instrument_connected"
    TOOL_CALLED = "tool_called"


@dataclass
class Event:
    """An event emitted during orchestration."""
    event_type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


# Listener is any callable that accepts an Event
EventListener = Callable[[Event], None]


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

@dataclass
class ToolSpec:
    """A tool that can be called by the brain.

    Tools wrap instrument capabilities (e.g. "nmr.process", "nmr.list_datasets")
    into a flat namespace the brain can reference.
    """
    name: str
    description: str
    handler: Callable[..., Any]
    instrument_type: str = ""  # which instrument type this belongs to
    parameters: dict[str, str] = field(default_factory=dict)  # param_name -> description


class ToolRegistry:
    """Registry of available tools/instruments.

    Instruments register themselves and their tools. The orchestrator
    (and the brain) can look up tools by name or by instrument type.
    """

    def __init__(self) -> None:
        self._instruments: dict[str, BaseInstrument] = {}  # name -> instrument
        self._tools: dict[str, ToolSpec] = {}  # tool_name -> spec
        self._listeners: list[EventListener] = []

    def add_listener(self, listener: EventListener) -> None:
        self._listeners.append(listener)

    def _emit(self, event: Event) -> None:
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                logger.exception("Event listener failed")

    # -- Instrument registration --

    def register_instrument(self, instrument: BaseInstrument) -> None:
        """Register an instrument and auto-register its standard tools."""
        info = instrument.info()
        self._instruments[info.name] = instrument

        # Auto-register standard BaseInstrument methods as tools
        prefix = info.name.lower().replace(" ", "_")

        self._register_tool(ToolSpec(
            name=f"{prefix}.list_datasets",
            description=f"List available datasets on {info.name}",
            handler=instrument.list_datasets,
            instrument_type=info.instrument_type,
        ))
        self._register_tool(ToolSpec(
            name=f"{prefix}.acquire",
            description=f"Acquire data from {info.name}",
            handler=instrument.acquire,
            instrument_type=info.instrument_type,
            parameters={"kwargs": "Acquisition parameters"},
        ))
        self._register_tool(ToolSpec(
            name=f"{prefix}.process",
            description=f"Process data from {info.name}",
            handler=instrument.process,
            instrument_type=info.instrument_type,
            parameters={"data_path": "Path to raw data"},
        ))

        self._emit(Event(
            event_type=EventType.INSTRUMENT_REGISTERED,
            data={"instrument": info.name, "type": info.instrument_type},
        ))
        logger.info("Registered instrument: %s (%s)", info.name, info.instrument_type)

    def _register_tool(self, spec: ToolSpec) -> None:
        """Register a single tool spec."""
        self._tools[spec.name] = spec

    def register_tool(self, spec: ToolSpec) -> None:
        """Register a custom tool (not tied to standard instrument methods)."""
        self._register_tool(spec)

    # -- Lookups --

    def get_instrument(self, name: str) -> BaseInstrument | None:
        return self._instruments.get(name)

    def get_tool(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def list_instruments(self) -> list[InstrumentInfo]:
        return [inst.info() for inst in self._instruments.values()]

    def list_tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def tools_for_type(self, instrument_type: str) -> list[ToolSpec]:
        """List tools belonging to a specific instrument type (e.g. 'nmr')."""
        return [t for t in self._tools.values() if t.instrument_type == instrument_type]


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    """Result of executing a single pipeline step."""
    status: StepStatus
    output: Any = None
    error: str = ""
    duration_ms: float = 0


@dataclass
class PipelineStep:
    """A single step in a pipeline.

    A step can either:
      - Call a registered tool by name (tool_name + params), or
      - Run an arbitrary callable (handler)

    If both are provided, tool_name takes priority.

    Use ``parallel`` to group steps that can run concurrently.  Steps
    with the same ``parallel`` string run together in a thread pool.

    Use ``retries`` for automatic retry on failure (e.g. flaky instrument
    connections).  Use ``timeout_s`` to cap execution time.
    """
    name: str
    description: str = ""
    tool_name: str = ""  # registered tool to call
    handler: Callable[..., Any] | None = None  # or an inline callable
    params: dict[str, Any] = field(default_factory=dict)
    condition: Callable[[dict[str, Any]], bool] | None = None  # skip if returns False
    parallel: str = ""  # group name — steps in same group run concurrently
    retries: int = 0  # number of retry attempts on failure
    timeout_s: float = 0  # max seconds per attempt (0 = no limit)


@dataclass
class PipelineResult:
    """Result of running an entire pipeline."""
    name: str
    steps: list[tuple[str, StepResult]] = field(default_factory=list)  # (step_name, result)
    duration_ms: float = 0

    @property
    def success(self) -> bool:
        return all(r.status in (StepStatus.COMPLETED, StepStatus.SKIPPED)
                   for _, r in self.steps)

    @property
    def outputs(self) -> dict[str, Any]:
        """Map of step_name -> output for all completed steps."""
        return {name: r.output for name, r in self.steps
                if r.status == StepStatus.COMPLETED and r.output is not None}

    @property
    def last_output(self) -> Any:
        """Output of the last completed step."""
        for _, r in reversed(self.steps):
            if r.status == StepStatus.COMPLETED and r.output is not None:
                return r.output
        return None

    def summary(self) -> str:
        """Render a visual summary of pipeline execution."""
        status_icons = {
            StepStatus.COMPLETED: "[OK]",
            StepStatus.FAILED: "[FAIL]",
            StepStatus.SKIPPED: "[SKIP]",
            StepStatus.PENDING: "[..]",
            StepStatus.RUNNING: "[>>]",
        }
        result_line = "OK" if self.success else "FAILED"

        lines = [
            f"Pipeline: {self.name}  ({result_line}, {self.duration_ms:.0f}ms)",
            "",
        ]

        for i, (name, sr) in enumerate(self.steps):
            icon = status_icons.get(sr.status, "[??]")
            connector = "├──" if i < len(self.steps) - 1 else "└──"
            time_str = f" {sr.duration_ms:.0f}ms" if sr.duration_ms else ""
            error_str = f"  error: {sr.error}" if sr.error else ""
            lines.append(f"  {connector} {icon} {name}{time_str}{error_str}")

        return "\n".join(lines)


class Pipeline:
    """A sequence of steps to execute.

    Steps run sequentially. Each step receives a context dict containing
    outputs from all prior steps (keyed by step name). This lets later
    steps reference earlier results without tight coupling.

    Example:
        pipeline = Pipeline("nmr_analysis")
        pipeline.add_step(PipelineStep(
            name="load",
            tool_name="topspin.process",
            params={"data_path": "/data/ethanol/1"},
        ))
        pipeline.add_step(PipelineStep(
            name="analyze",
            handler=brain.interpret_spectrum,
            params={"molecular_formula": "C2H6O"},
        ))
    """

    def __init__(self, name: str, description: str = "") -> None:
        self.name = name
        self.description = description
        self.steps: list[PipelineStep] = []

    def add_step(self, step: PipelineStep) -> Pipeline:
        """Add a step. Returns self for chaining."""
        self.steps.append(step)
        return self

    def extend(self, other: Pipeline) -> Pipeline:
        """Append all steps from another pipeline. Returns self for chaining."""
        self.steps.extend(other.steps)
        return self

    @classmethod
    def compose(cls, name: str, *pipelines: Pipeline, description: str = "") -> Pipeline:
        """Compose multiple pipelines into one.

        Steps are concatenated in order. This enables building complex
        workflows from reusable sub-pipelines:

            load = Pipeline("load").add_step(...)
            analyze = Pipeline("analyze").add_step(...)
            full = Pipeline.compose("full_workflow", load, analyze)
        """
        composed = cls(name, description=description)
        for p in pipelines:
            composed.steps.extend(p.steps)
        return composed

    def __len__(self) -> int:
        return len(self.steps)

    def describe(self) -> str:
        """Render a visual plan of this pipeline before execution."""
        lines = [f"Pipeline: {self.name} ({len(self.steps)} steps)"]
        if self.description:
            lines.append(f"  {self.description}")
        lines.append("")

        # Group into batches for parallel display
        batches: list[list[PipelineStep]] = []
        for step in self.steps:
            if step.parallel and batches and batches[-1][0].parallel == step.parallel:
                batches[-1].append(step)
            else:
                batches.append([step])

        for bi, batch in enumerate(batches):
            is_last_batch = bi == len(batches) - 1

            if len(batch) > 1:
                # Parallel group
                lines.append(f"  {'├' if not is_last_batch else '└'}── parallel [{batch[0].parallel}]:")
                prefix = "  │   " if not is_last_batch else "      "
                for si, step in enumerate(batch):
                    branch = "├" if si < len(batch) - 1 else "└"
                    source = step.tool_name or "handler"
                    extra = ""
                    if step.retries:
                        extra += f" retries={step.retries}"
                    if step.timeout_s:
                        extra += f" timeout={step.timeout_s}s"
                    lines.append(f"{prefix}{branch}── {step.name} ({source}){extra}")
            else:
                step = batch[0]
                connector = "├" if not is_last_batch else "└"
                source = step.tool_name or "handler"
                extra = ""
                if step.retries:
                    extra += f" retries={step.retries}"
                if step.timeout_s:
                    extra += f" timeout={step.timeout_s}s"
                if step.condition:
                    extra += " conditional"
                lines.append(f"  {connector}── {step.name} ({source}){extra}")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    """The main coordinator — connects brains to instruments via pipelines.

    Usage:
        orch = Orchestrator()

        # Register instruments
        nmr = TopSpinAdapter(mode="offline")
        nmr.connect()
        orch.registry.register_instrument(nmr)

        # Build a pipeline
        pipeline = Pipeline("analyze_sample")
        pipeline.add_step(PipelineStep(
            name="process",
            tool_name="topspin.process",
            params={"data_path": "/data/ethanol/1"},
        ))
        pipeline.add_step(PipelineStep(
            name="interpret",
            handler=lambda ctx: brain.interpret_spectrum(ctx["process"]),
        ))

        # Run it
        result = orch.run(pipeline)
    """

    def __init__(self, registry: ToolRegistry | None = None) -> None:
        self.registry = registry or ToolRegistry()
        self._listeners: list[EventListener] = []

    # -- Event system --

    def on_event(self, listener: EventListener) -> None:
        """Register an event listener."""
        self._listeners.append(listener)
        self.registry.add_listener(listener)

    def _emit(self, event: Event) -> None:
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                logger.exception("Event listener failed")

    # -- Instrument convenience --

    def register(self, instrument: BaseInstrument) -> None:
        """Register an instrument (shorthand for registry.register_instrument)."""
        self.registry.register_instrument(instrument)

    def connect_all(self) -> dict[str, bool]:
        """Try to connect all registered instruments. Returns name -> success."""
        results: dict[str, bool] = {}
        for info in self.registry.list_instruments():
            inst = self.registry.get_instrument(info.name)
            if inst is None:
                continue
            ok = inst.connect()
            results[info.name] = ok
            if ok:
                self._emit(Event(
                    event_type=EventType.INSTRUMENT_CONNECTED,
                    data={"instrument": info.name},
                ))
                logger.info("Connected: %s", info.name)
            else:
                logger.warning("Failed to connect: %s", info.name)
        return results

    # -- Tool routing --

    def call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Call a registered tool by name. Raises KeyError if not found."""
        spec = self.registry.get_tool(tool_name)
        if spec is None:
            available = [t.name for t in self.registry.list_tools()]
            raise KeyError(
                f"Tool {tool_name!r} not found. Available: {available}"
            )
        self._emit(Event(
            event_type=EventType.TOOL_CALLED,
            data={"tool": tool_name, "params": kwargs},
        ))
        return spec.handler(**kwargs)

    # -- Pipeline execution --

    def run(self, pipeline: Pipeline) -> PipelineResult:
        """Execute a pipeline, passing context between steps.

        Each step's handler/tool receives the accumulated context dict
        as its first argument (if the handler accepts it) or as keyword
        params merged with step.params.

        For tool calls: step.params are passed as kwargs to the tool handler.
        For inline handlers: the handler is called with (context, **params).

        Steps with the same ``parallel`` group name run concurrently using
        a thread pool.  Steps without a parallel group run sequentially.
        """
        self._emit(Event(
            event_type=EventType.PIPELINE_START,
            data={"pipeline": pipeline.name, "steps": len(pipeline)},
        ))

        context: dict[str, Any] = {}
        result = PipelineResult(name=pipeline.name)
        pipeline_start = time.monotonic()
        failed = False

        # Group consecutive steps by their parallel tag
        batches = self._build_batches(pipeline.steps)

        for batch in batches:
            if failed:
                break

            if len(batch) == 1 and not batch[0].parallel:
                # Single sequential step
                step = batch[0]
                step_result = self._run_single_step(step, context, pipeline.name)
                result.steps.append((step.name, step_result))
                if step_result.status == StepStatus.COMPLETED:
                    context[step.name] = step_result.output
                elif step_result.status == StepStatus.FAILED:
                    failed = True
            else:
                # Parallel batch — run in thread pool
                step_results = self._run_parallel_batch(batch, context, pipeline.name)
                for step, sr in zip(batch, step_results):
                    result.steps.append((step.name, sr))
                    if sr.status == StepStatus.COMPLETED:
                        context[step.name] = sr.output
                    elif sr.status == StepStatus.FAILED:
                        failed = True

        result.duration_ms = (time.monotonic() - pipeline_start) * 1000

        self._emit(Event(
            event_type=EventType.PIPELINE_END,
            data={
                "pipeline": pipeline.name,
                "success": result.success,
                "duration_ms": result.duration_ms,
            },
        ))
        return result

    @staticmethod
    def _build_batches(steps: list[PipelineStep]) -> list[list[PipelineStep]]:
        """Group consecutive steps with the same parallel tag into batches."""
        batches: list[list[PipelineStep]] = []
        for step in steps:
            if step.parallel and batches and batches[-1][0].parallel == step.parallel:
                batches[-1].append(step)
            else:
                batches.append([step])
        return batches

    def _run_single_step(
        self, step: PipelineStep, context: dict[str, Any], pipeline_name: str
    ) -> StepResult:
        """Run one step, with optional retries and timeout."""
        if step.condition is not None and not step.condition(context):
            logger.info("Skipped step: %s", step.name)
            return StepResult(status=StepStatus.SKIPPED)

        self._emit(Event(
            event_type=EventType.STEP_START,
            data={"pipeline": pipeline_name, "step": step.name,
                  "description": step.description},
        ))

        attempts = 1 + step.retries
        last_error = ""
        step_start = time.monotonic()

        for attempt in range(attempts):
            if attempt > 0:
                logger.info("Retrying step %s (attempt %d/%d)",
                            step.name, attempt + 1, attempts)

            try:
                output = self._execute_step_with_timeout(step, context)
                duration_ms = (time.monotonic() - step_start) * 1000
                self._emit(Event(
                    event_type=EventType.STEP_END,
                    data={"pipeline": pipeline_name, "step": step.name,
                          "duration_ms": duration_ms,
                          "attempts": attempt + 1},
                ))
                logger.info("Completed step: %s (%.0fms, attempt %d)",
                            step.name, duration_ms, attempt + 1)
                return StepResult(status=StepStatus.COMPLETED, output=output,
                                  duration_ms=duration_ms)
            except Exception as exc:
                last_error = str(exc)
                if attempt < attempts - 1:
                    logger.warning("Step %s attempt %d failed: %s",
                                   step.name, attempt + 1, exc)
                    continue

        duration_ms = (time.monotonic() - step_start) * 1000
        self._emit(Event(
            event_type=EventType.STEP_ERROR,
            data={"pipeline": pipeline_name, "step": step.name,
                  "error": last_error, "attempts": attempts},
        ))
        logger.error("Step %s failed after %d attempts: %s",
                     step.name, attempts, last_error)
        return StepResult(status=StepStatus.FAILED, error=last_error,
                              duration_ms=duration_ms)

    def _run_parallel_batch(
        self, batch: list[PipelineStep], context: dict[str, Any],
        pipeline_name: str,
    ) -> list[StepResult]:
        """Run a batch of steps concurrently in a thread pool."""
        from concurrent.futures import ThreadPoolExecutor

        results: list[StepResult | None] = [None] * len(batch)

        def _run_one(idx: int, step: PipelineStep) -> None:
            results[idx] = self._run_single_step(step, context, pipeline_name)

        with ThreadPoolExecutor(max_workers=len(batch)) as pool:
            futures = [
                pool.submit(_run_one, i, step)
                for i, step in enumerate(batch)
            ]
            for f in futures:
                f.result()  # propagate exceptions

        return results  # type: ignore[return-value]

    def _execute_step_with_timeout(
        self, step: PipelineStep, context: dict[str, Any]
    ) -> Any:
        """Execute a step, enforcing timeout_s if set."""
        if step.timeout_s <= 0:
            return self._execute_step(step, context)

        from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self._execute_step, step, context)
            try:
                return future.result(timeout=step.timeout_s)
            except FuturesTimeout:
                future.cancel()
                raise TimeoutError(
                    f"Step {step.name!r} timed out after {step.timeout_s}s"
                )

    def _execute_step(self, step: PipelineStep, context: dict[str, Any]) -> Any:
        """Execute a single step, resolving tool or inline handler.

        For tool steps, params are resolved against context: any param value
        that is a string like "{step_name}" is replaced with that step's output.
        For handler steps, context is passed as the first argument.
        """
        params = self._resolve_params(step.params, context)

        if step.tool_name:
            # Route to registered tool
            return self.call_tool(step.tool_name, **params)

        if step.handler is not None:
            # Inline handler — pass context as first arg
            return step.handler(context, **params)

        raise ValueError(
            f"Step {step.name!r} has neither tool_name nor handler"
        )

    @staticmethod
    def _resolve_params(
        params: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        """Resolve param values against pipeline context.

        String values matching "{step_name}" are replaced with the output
        of that step. All other values pass through unchanged.
        """
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("{") and value.endswith("}"):
                ref = value[1:-1]
                if ref in context:
                    resolved[key] = context[ref]
                else:
                    resolved[key] = value  # keep as-is if not found
            else:
                resolved[key] = value
        return resolved
