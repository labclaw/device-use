"""Tests for the Orchestrator middleware (registry, pipelines, events)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from device_use.instruments.base import BaseInstrument, ControlMode, InstrumentInfo
from device_use.orchestrator import (
    Event,
    EventType,
    Orchestrator,
    Pipeline,
    PipelineStep,
    StepStatus,
    ToolRegistry,
    ToolSpec,
)


# ── Mock instrument for testing ──────────────────────────────────

class MockInstrument(BaseInstrument):
    """Minimal instrument for testing orchestrator registration."""

    def info(self) -> InstrumentInfo:
        return InstrumentInfo(
            name="MockSpec",
            vendor="TestCo",
            instrument_type="spectrometer",
            supported_modes=[ControlMode.OFFLINE],
            version="1.0",
        )

    @property
    def connected(self) -> bool:
        return True

    @property
    def mode(self) -> ControlMode:
        return ControlMode.OFFLINE

    def connect(self) -> bool:
        return True

    def list_datasets(self):
        return [{"sample": "test", "expno": 1, "path": "/tmp/test", "title": "Test"}]

    def acquire(self, **kwargs):
        return {"acquired": True}

    def process(self, data_path, **kwargs):
        return {"processed": True, "path": data_path}


# ── ToolRegistry ─────────────────────────────────────────────────

class TestToolRegistry:
    def test_register_instrument(self):
        registry = ToolRegistry()
        inst = MockInstrument()
        registry.register_instrument(inst)

        instruments = registry.list_instruments()
        assert len(instruments) == 1
        assert instruments[0].name == "MockSpec"

    def test_auto_registered_tools(self):
        registry = ToolRegistry()
        inst = MockInstrument()
        registry.register_instrument(inst)

        tools = registry.list_tools()
        tool_names = [t.name for t in tools]

        assert "mockspec.list_datasets" in tool_names
        assert "mockspec.acquire" in tool_names
        assert "mockspec.process" in tool_names

    def test_custom_tool(self):
        registry = ToolRegistry()
        registry.register_tool(ToolSpec(
            name="custom.hello",
            description="Say hello",
            handler=lambda: "hello",
        ))

        tool = registry.get_tool("custom.hello")
        assert tool is not None
        assert tool.handler() == "hello"

    def test_get_instrument(self):
        registry = ToolRegistry()
        inst = MockInstrument()
        registry.register_instrument(inst)

        found = registry.get_instrument("MockSpec")
        assert found is inst

    def test_get_nonexistent(self):
        registry = ToolRegistry()
        assert registry.get_instrument("nope") is None
        assert registry.get_tool("nope") is None

    def test_tools_for_type(self):
        registry = ToolRegistry()
        inst = MockInstrument()
        registry.register_instrument(inst)

        spec_tools = registry.tools_for_type("spectrometer")
        assert len(spec_tools) == 3

        nmr_tools = registry.tools_for_type("nmr")
        assert len(nmr_tools) == 0

    def test_event_listener(self):
        events = []
        registry = ToolRegistry()
        registry.add_listener(lambda e: events.append(e))

        inst = MockInstrument()
        registry.register_instrument(inst)

        assert len(events) == 1
        assert events[0].event_type == EventType.INSTRUMENT_REGISTERED
        assert events[0].data["instrument"] == "MockSpec"


# ── Pipeline ─────────────────────────────────────────────────────

class TestPipeline:
    def test_empty_pipeline(self):
        p = Pipeline("test")
        assert len(p) == 0
        assert p.name == "test"

    def test_add_steps(self):
        p = Pipeline("test")
        p.add_step(PipelineStep(name="a"))
        p.add_step(PipelineStep(name="b"))
        assert len(p) == 2

    def test_chaining(self):
        p = Pipeline("test")
        result = p.add_step(PipelineStep(name="a")).add_step(PipelineStep(name="b"))
        assert result is p
        assert len(p) == 2


# ── Orchestrator ─────────────────────────────────────────────────

class TestOrchestrator:
    def test_register_and_connect(self):
        orch = Orchestrator()
        inst = MockInstrument()
        orch.register(inst)

        instruments = orch.registry.list_instruments()
        assert len(instruments) == 1

    def test_call_tool(self):
        orch = Orchestrator()
        inst = MockInstrument()
        orch.register(inst)

        result = orch.call_tool("mockspec.list_datasets")
        assert isinstance(result, list)
        assert result[0]["sample"] == "test"

    def test_call_tool_not_found(self):
        orch = Orchestrator()
        with pytest.raises(KeyError, match="not found"):
            orch.call_tool("nonexistent.tool")

    def test_run_simple_pipeline(self):
        orch = Orchestrator()
        inst = MockInstrument()
        orch.register(inst)

        pipeline = Pipeline("test_pipeline")
        pipeline.add_step(PipelineStep(
            name="list",
            tool_name="mockspec.list_datasets",
        ))

        result = orch.run(pipeline)
        assert result.success
        assert result.name == "test_pipeline"
        assert len(result.steps) == 1
        assert result.steps[0][1].status == StepStatus.COMPLETED
        assert result.duration_ms > 0

    def test_run_pipeline_with_handler(self):
        orch = Orchestrator()

        pipeline = Pipeline("handler_test")
        pipeline.add_step(PipelineStep(
            name="compute",
            handler=lambda ctx: 42,
        ))

        result = orch.run(pipeline)
        assert result.success
        assert result.outputs["compute"] == 42
        assert result.last_output == 42

    def test_pipeline_context_passing(self):
        orch = Orchestrator()

        pipeline = Pipeline("context_test")
        pipeline.add_step(PipelineStep(
            name="first",
            handler=lambda ctx: {"value": 10},
        ))
        pipeline.add_step(PipelineStep(
            name="second",
            handler=lambda ctx: ctx["first"]["value"] * 2,
        ))

        result = orch.run(pipeline)
        assert result.success
        assert result.outputs["second"] == 20

    def test_pipeline_conditional_step(self):
        orch = Orchestrator()

        pipeline = Pipeline("conditional_test")
        pipeline.add_step(PipelineStep(
            name="always",
            handler=lambda ctx: "ran",
        ))
        pipeline.add_step(PipelineStep(
            name="skipped",
            handler=lambda ctx: "should not run",
            condition=lambda ctx: False,
        ))
        pipeline.add_step(PipelineStep(
            name="conditional",
            handler=lambda ctx: "also ran",
            condition=lambda ctx: ctx.get("always") == "ran",
        ))

        result = orch.run(pipeline)
        assert result.success
        assert len(result.steps) == 3
        assert result.steps[0][1].status == StepStatus.COMPLETED
        assert result.steps[1][1].status == StepStatus.SKIPPED
        assert result.steps[2][1].status == StepStatus.COMPLETED

    def test_pipeline_failure_stops(self):
        orch = Orchestrator()

        pipeline = Pipeline("fail_test")
        pipeline.add_step(PipelineStep(
            name="ok",
            handler=lambda ctx: "fine",
        ))
        pipeline.add_step(PipelineStep(
            name="fail",
            handler=lambda ctx: 1 / 0,
        ))
        pipeline.add_step(PipelineStep(
            name="never",
            handler=lambda ctx: "unreachable",
        ))

        result = orch.run(pipeline)
        assert not result.success
        assert len(result.steps) == 2  # stopped after failure
        assert result.steps[1][1].status == StepStatus.FAILED
        assert "division by zero" in result.steps[1][1].error

    def test_event_emission(self):
        events = []
        orch = Orchestrator()
        orch.on_event(lambda e: events.append(e))

        inst = MockInstrument()
        orch.register(inst)

        pipeline = Pipeline("event_test")
        pipeline.add_step(PipelineStep(
            name="step1",
            handler=lambda ctx: "done",
        ))

        orch.run(pipeline)

        event_types = [e.event_type for e in events]
        assert EventType.INSTRUMENT_REGISTERED in event_types
        assert EventType.PIPELINE_START in event_types
        assert EventType.STEP_START in event_types
        assert EventType.STEP_END in event_types
        assert EventType.PIPELINE_END in event_types

    def test_connect_all(self):
        orch = Orchestrator()
        inst = MockInstrument()
        orch.register(inst)

        results = orch.connect_all()
        assert results["MockSpec"] is True

    def test_pipeline_result_properties(self):
        orch = Orchestrator()

        pipeline = Pipeline("props_test")
        pipeline.add_step(PipelineStep(name="a", handler=lambda ctx: 1))
        pipeline.add_step(PipelineStep(name="b", handler=lambda ctx: 2))
        pipeline.add_step(PipelineStep(name="c", handler=lambda ctx: 3))

        result = orch.run(pipeline)
        assert result.success
        assert result.outputs == {"a": 1, "b": 2, "c": 3}
        assert result.last_output == 3
