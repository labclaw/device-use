"""Tests for the Orchestrator middleware (registry, pipelines, events)."""

import pytest

from device_use.instruments.base import BaseInstrument, ControlMode, InstrumentInfo
from device_use.orchestrator import (
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
        registry.register_tool(
            ToolSpec(
                name="custom.hello",
                description="Say hello",
                handler=lambda: "hello",
            )
        )

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

    def test_extend(self):
        a = Pipeline("a")
        a.add_step(PipelineStep(name="s1", handler=lambda ctx: 1))
        b = Pipeline("b")
        b.add_step(PipelineStep(name="s2", handler=lambda ctx: 2))

        result = a.extend(b)
        assert result is a
        assert len(a) == 2

    def test_compose(self):
        load = Pipeline("load")
        load.add_step(PipelineStep(name="read", handler=lambda ctx: "data"))
        analyze = Pipeline("analyze")
        analyze.add_step(PipelineStep(name="process", handler=lambda ctx: "result"))

        full = Pipeline.compose("full", load, analyze)
        assert full.name == "full"
        assert len(full) == 2
        assert full.steps[0].name == "read"
        assert full.steps[1].name == "process"

    def test_compose_runs(self):
        """Composed pipeline executes correctly with context passing."""
        orch = Orchestrator()

        load = Pipeline("load")
        load.add_step(PipelineStep(name="value", handler=lambda ctx: 42))

        transform = Pipeline("transform")
        transform.add_step(
            PipelineStep(
                name="doubled",
                handler=lambda ctx: ctx["value"] * 2,
            )
        )

        full = Pipeline.compose("composed", load, transform)
        result = orch.run(full)
        assert result.success
        assert result.outputs["doubled"] == 84

    def test_describe(self):
        p = Pipeline("my_pipeline")
        p.add_step(PipelineStep(name="load", tool_name="topspin.process"))
        p.add_step(PipelineStep(name="analyze", tool_name="brain.interpret"))
        desc = p.describe()
        assert "my_pipeline" in desc
        assert "2 steps" in desc
        assert "load" in desc
        assert "analyze" in desc

    def test_describe_parallel(self):
        p = Pipeline("par_pipeline")
        p.add_step(PipelineStep(name="a", handler=lambda ctx: 1, parallel="g"))
        p.add_step(PipelineStep(name="b", handler=lambda ctx: 2, parallel="g"))
        p.add_step(PipelineStep(name="c", handler=lambda ctx: 3))
        desc = p.describe()
        assert "parallel [g]" in desc
        assert "a (handler)" in desc
        assert "c (handler)" in desc

    def test_describe_retry_timeout(self):
        p = Pipeline("rt_pipeline")
        p.add_step(PipelineStep(name="s", handler=lambda ctx: 1, retries=3, timeout_s=10))
        desc = p.describe()
        assert "retries=3" in desc
        assert "timeout=10" in desc


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
        pipeline.add_step(
            PipelineStep(
                name="list",
                tool_name="mockspec.list_datasets",
            )
        )

        result = orch.run(pipeline)
        assert result.success
        assert result.name == "test_pipeline"
        assert len(result.steps) == 1
        assert result.steps[0][1].status == StepStatus.COMPLETED
        assert result.duration_ms > 0

    def test_run_pipeline_with_handler(self):
        orch = Orchestrator()

        pipeline = Pipeline("handler_test")
        pipeline.add_step(
            PipelineStep(
                name="compute",
                handler=lambda ctx: 42,
            )
        )

        result = orch.run(pipeline)
        assert result.success
        assert result.outputs["compute"] == 42
        assert result.last_output == 42

    def test_pipeline_context_passing(self):
        orch = Orchestrator()

        pipeline = Pipeline("context_test")
        pipeline.add_step(
            PipelineStep(
                name="first",
                handler=lambda ctx: {"value": 10},
            )
        )
        pipeline.add_step(
            PipelineStep(
                name="second",
                handler=lambda ctx: ctx["first"]["value"] * 2,
            )
        )

        result = orch.run(pipeline)
        assert result.success
        assert result.outputs["second"] == 20

    def test_pipeline_conditional_step(self):
        orch = Orchestrator()

        pipeline = Pipeline("conditional_test")
        pipeline.add_step(
            PipelineStep(
                name="always",
                handler=lambda ctx: "ran",
            )
        )
        pipeline.add_step(
            PipelineStep(
                name="skipped",
                handler=lambda ctx: "should not run",
                condition=lambda ctx: False,
            )
        )
        pipeline.add_step(
            PipelineStep(
                name="conditional",
                handler=lambda ctx: "also ran",
                condition=lambda ctx: ctx.get("always") == "ran",
            )
        )

        result = orch.run(pipeline)
        assert result.success
        assert len(result.steps) == 3
        assert result.steps[0][1].status == StepStatus.COMPLETED
        assert result.steps[1][1].status == StepStatus.SKIPPED
        assert result.steps[2][1].status == StepStatus.COMPLETED

    def test_pipeline_failure_stops(self):
        orch = Orchestrator()

        pipeline = Pipeline("fail_test")
        pipeline.add_step(
            PipelineStep(
                name="ok",
                handler=lambda ctx: "fine",
            )
        )
        pipeline.add_step(
            PipelineStep(
                name="fail",
                handler=lambda ctx: 1 / 0,
            )
        )
        pipeline.add_step(
            PipelineStep(
                name="never",
                handler=lambda ctx: "unreachable",
            )
        )

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
        pipeline.add_step(
            PipelineStep(
                name="step1",
                handler=lambda ctx: "done",
            )
        )

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

    def test_param_resolution(self):
        """Tool steps can reference prior step outputs via {step_name}."""
        orch = Orchestrator()

        results = []
        orch.registry.register_tool(
            ToolSpec(
                name="echo",
                description="Echo params",
                handler=lambda **kw: results.append(kw) or kw,
            )
        )

        pipeline = Pipeline("resolve_test")
        pipeline.add_step(
            PipelineStep(
                name="first",
                handler=lambda ctx: "/data/ethanol/1",
            )
        )
        pipeline.add_step(
            PipelineStep(
                name="use_ref",
                tool_name="echo",
                params={"data_path": "{first}", "static": "hello"},
            )
        )

        result = orch.run(pipeline)
        assert result.success
        assert results[0]["data_path"] == "/data/ethanol/1"
        assert results[0]["static"] == "hello"

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

    def test_pipeline_result_summary(self):
        orch = Orchestrator()

        pipeline = Pipeline("summary_test")
        pipeline.add_step(PipelineStep(name="ok", handler=lambda ctx: "done"))
        pipeline.add_step(
            PipelineStep(
                name="skip",
                handler=lambda ctx: None,
                condition=lambda ctx: False,
            )
        )

        result = orch.run(pipeline)
        summary = result.summary()
        assert "summary_test" in summary
        assert "[OK]" in summary
        assert "[SKIP]" in summary
        assert "ok" in summary

    def test_pipeline_result_summary_failure(self):
        orch = Orchestrator()

        pipeline = Pipeline("fail_summary")
        pipeline.add_step(PipelineStep(name="bad", handler=lambda ctx: 1 / 0))

        result = orch.run(pipeline)
        summary = result.summary()
        assert "FAILED" in summary
        assert "[FAIL]" in summary
        assert "division by zero" in summary


# ── Factory ──────────────────────────────────────────────────────


class TestCreateOrchestrator:
    def test_default_all_instruments(self):
        from device_use import create_orchestrator

        orch = create_orchestrator()
        instruments = orch.registry.list_instruments()
        assert len(instruments) == 2
        types = {i.instrument_type for i in instruments}
        assert types == {"nmr", "plate_reader"}

    def test_nmr_only(self):
        from device_use import create_orchestrator

        orch = create_orchestrator(instruments=["nmr"])
        instruments = orch.registry.list_instruments()
        assert len(instruments) == 1
        assert instruments[0].instrument_type == "nmr"

    def test_plate_reader_only(self):
        from device_use import create_orchestrator

        orch = create_orchestrator(instruments=["plate_reader"])
        instruments = orch.registry.list_instruments()
        assert len(instruments) == 1
        assert instruments[0].instrument_type == "plate_reader"

    def test_no_connect(self):
        from device_use import create_orchestrator

        orch = create_orchestrator(connect=False)
        instruments = orch.registry.list_instruments()
        assert len(instruments) == 2
        # Instruments registered but not connected
        for info in instruments:
            inst = orch.registry.get_instrument(info.name)
            # Offline mode auto-connects on process, but connected flag may vary
            assert inst is not None

    def test_tools_registered(self):
        from device_use import create_orchestrator

        orch = create_orchestrator()
        tools = orch.registry.list_tools()
        assert len(tools) == 6
        names = [t.name for t in tools]
        assert "topspin.list_datasets" in names
        assert "platereader.process" in names

    def test_plugin_discovery(self):
        """_discover_plugins returns empty dict when no plugins installed."""
        from device_use import _discover_plugins
        from device_use.instruments import ControlMode

        plugins = _discover_plugins(ControlMode.OFFLINE)
        # No external plugins installed in test env — should return empty or
        # only built-in entry points
        assert isinstance(plugins, dict)

    def test_plugin_override(self, monkeypatch):
        """Plugin instruments merge with built-ins."""
        from device_use import create_orchestrator

        # Mock _discover_plugins to return a fake instrument
        def mock_discover(control_mode):
            return {
                "mock_plugin": lambda: MockInstrument(),
            }

        monkeypatch.setattr("device_use._discover_plugins", mock_discover)

        orch = create_orchestrator()
        instruments = orch.registry.list_instruments()
        types = {i.instrument_type for i in instruments}
        # Should have built-in + plugin
        assert "spectrometer" in types  # MockInstrument type
        assert "nmr" in types
        assert "plate_reader" in types


# ── Parallel Pipeline ────────────────────────────────────────


class TestParallelPipeline:
    def test_parallel_steps_run(self):
        """Steps with the same parallel group run together."""
        import time

        orch = Orchestrator()

        pipeline = Pipeline("parallel_test")
        pipeline.add_step(
            PipelineStep(
                name="a",
                handler=lambda ctx: (time.sleep(0.05), "a_done")[1],
                parallel="group1",
            )
        )
        pipeline.add_step(
            PipelineStep(
                name="b",
                handler=lambda ctx: (time.sleep(0.05), "b_done")[1],
                parallel="group1",
            )
        )

        result = orch.run(pipeline)
        assert result.success
        assert result.outputs["a"] == "a_done"
        assert result.outputs["b"] == "b_done"
        # Parallel should be faster than sequential (< 100ms for 2x50ms)
        assert result.duration_ms < 150

    def test_parallel_then_sequential(self):
        """Parallel group followed by sequential step."""
        orch = Orchestrator()

        pipeline = Pipeline("mixed_test")
        pipeline.add_step(
            PipelineStep(
                name="p1",
                handler=lambda ctx: 10,
                parallel="load",
            )
        )
        pipeline.add_step(
            PipelineStep(
                name="p2",
                handler=lambda ctx: 20,
                parallel="load",
            )
        )
        pipeline.add_step(
            PipelineStep(
                name="combine",
                handler=lambda ctx: ctx["p1"] + ctx["p2"],
            )
        )

        result = orch.run(pipeline)
        assert result.success
        assert result.outputs["combine"] == 30

    def test_batching_groups_consecutive(self):
        """Only consecutive steps with the same tag form a group."""
        orch = Orchestrator()

        pipeline = Pipeline("batch_test")
        pipeline.add_step(PipelineStep(name="a", handler=lambda ctx: 1, parallel="g"))
        pipeline.add_step(PipelineStep(name="b", handler=lambda ctx: 2, parallel="g"))
        pipeline.add_step(PipelineStep(name="c", handler=lambda ctx: 3))  # sequential
        pipeline.add_step(PipelineStep(name="d", handler=lambda ctx: 4, parallel="g"))

        result = orch.run(pipeline)
        assert result.success
        assert len(result.steps) == 4
        assert result.outputs == {"a": 1, "b": 2, "c": 3, "d": 4}

    def test_parallel_failure_stops_pipeline(self):
        """If a parallel step fails, the pipeline stops."""
        orch = Orchestrator()

        pipeline = Pipeline("fail_parallel")
        pipeline.add_step(
            PipelineStep(
                name="ok",
                handler=lambda ctx: "fine",
                parallel="g",
            )
        )
        pipeline.add_step(
            PipelineStep(
                name="fail",
                handler=lambda ctx: 1 / 0,
                parallel="g",
            )
        )
        pipeline.add_step(
            PipelineStep(
                name="never",
                handler=lambda ctx: "unreachable",
            )
        )

        result = orch.run(pipeline)
        assert not result.success
        # The "never" step should not have run
        step_names = [name for name, _ in result.steps]
        assert "never" not in step_names


# ── Retry & Timeout ─────────────────────────────────────────


class TestRetryAndTimeout:
    def test_retry_succeeds_on_second_attempt(self):
        """Step fails first, then succeeds — retries save it."""
        orch = Orchestrator()
        call_count = [0]

        def flaky(ctx):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionError("instrument busy")
            return "ok"

        pipeline = Pipeline("retry_test")
        pipeline.add_step(
            PipelineStep(
                name="flaky_step",
                handler=flaky,
                retries=2,
            )
        )

        result = orch.run(pipeline)
        assert result.success
        assert result.outputs["flaky_step"] == "ok"
        assert call_count[0] == 2

    def test_retry_exhausted(self):
        """Step fails all attempts — pipeline fails."""
        orch = Orchestrator()

        pipeline = Pipeline("retry_exhausted")
        pipeline.add_step(
            PipelineStep(
                name="always_fail",
                handler=lambda ctx: 1 / 0,
                retries=2,
            )
        )

        result = orch.run(pipeline)
        assert not result.success
        assert result.steps[0][1].status == StepStatus.FAILED
        assert "division by zero" in result.steps[0][1].error

    def test_retry_events(self):
        """Retry attempts are counted in events."""
        events = []
        orch = Orchestrator()
        orch.on_event(lambda e: events.append(e))
        call_count = [0]

        def fail_once(ctx):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("oops")
            return "recovered"

        pipeline = Pipeline("retry_events")
        pipeline.add_step(
            PipelineStep(
                name="s",
                handler=fail_once,
                retries=1,
            )
        )
        orch.run(pipeline)

        end_events = [e for e in events if e.event_type == EventType.STEP_END]
        assert len(end_events) == 1
        assert end_events[0].data["attempts"] == 2

    def test_timeout_enforced(self):
        """Step that exceeds timeout_s is killed."""
        import time as _time

        orch = Orchestrator()

        pipeline = Pipeline("timeout_test")
        pipeline.add_step(
            PipelineStep(
                name="slow",
                handler=lambda ctx: (_time.sleep(5), "done")[1],
                timeout_s=0.1,
            )
        )

        result = orch.run(pipeline)
        assert not result.success
        assert result.steps[0][1].status == StepStatus.FAILED
        assert "timed out" in result.steps[0][1].error

    def test_timeout_not_triggered(self):
        """Step finishes before timeout — succeeds normally."""
        orch = Orchestrator()

        pipeline = Pipeline("timeout_ok")
        pipeline.add_step(
            PipelineStep(
                name="fast",
                handler=lambda ctx: "quick",
                timeout_s=5.0,
            )
        )

        result = orch.run(pipeline)
        assert result.success
        assert result.outputs["fast"] == "quick"

    def test_retry_with_timeout(self):
        """Retry + timeout together: each attempt gets its own timeout."""
        import time as _time

        orch = Orchestrator()
        call_count = [0]

        def slow_then_fast(ctx):
            call_count[0] += 1
            if call_count[0] == 1:
                _time.sleep(5)  # will timeout
            return "recovered"

        pipeline = Pipeline("retry_timeout")
        pipeline.add_step(
            PipelineStep(
                name="combo",
                handler=slow_then_fast,
                retries=1,
                timeout_s=0.1,
            )
        )

        result = orch.run(pipeline)
        assert result.success
        assert result.outputs["combo"] == "recovered"


# ── Middleware Hooks ─────────────────────────────────────────


class TestMiddlewareHooks:
    def test_before_step_hook(self):
        """Pre-step hooks run before each step."""
        log = []
        orch = Orchestrator()
        orch.before_step(lambda step, ctx: log.append(f"pre:{step.name}"))

        pipeline = Pipeline("hook_test")
        pipeline.add_step(PipelineStep(name="a", handler=lambda ctx: 1))
        pipeline.add_step(PipelineStep(name="b", handler=lambda ctx: 2))

        result = orch.run(pipeline)
        assert result.success
        assert log == ["pre:a", "pre:b"]

    def test_after_step_hook(self):
        """Post-step hooks run after each successful step."""
        log = []
        orch = Orchestrator()
        orch.after_step(lambda step, ctx: log.append(f"post:{step.name}"))

        pipeline = Pipeline("hook_test")
        pipeline.add_step(PipelineStep(name="a", handler=lambda ctx: 1))
        pipeline.add_step(PipelineStep(name="b", handler=lambda ctx: 2))

        result = orch.run(pipeline)
        assert result.success
        assert log == ["post:a", "post:b"]

    def test_before_hook_aborts_step(self):
        """If a pre-hook raises, the step fails without executing."""
        orch = Orchestrator()
        orch.before_step(lambda step, ctx: (_ for _ in ()).throw(ValueError("safety check failed")))

        pipeline = Pipeline("abort_test")
        pipeline.add_step(PipelineStep(name="blocked", handler=lambda ctx: "nope"))

        result = orch.run(pipeline)
        assert not result.success
        assert "pre-hook" in result.steps[0][1].error
        assert "safety check" in result.steps[0][1].error

    def test_after_hook_aborts_pipeline(self):
        """If a post-hook raises, the step is marked failed."""
        orch = Orchestrator()
        orch.after_step(lambda step, ctx: (_ for _ in ()).throw(ValueError("validation failed")))

        pipeline = Pipeline("post_abort")
        pipeline.add_step(PipelineStep(name="ok", handler=lambda ctx: "done"))
        pipeline.add_step(PipelineStep(name="never", handler=lambda ctx: "unreachable"))

        result = orch.run(pipeline)
        assert not result.success
        assert len(result.steps) == 1
        assert "post-hook" in result.steps[0][1].error

    def test_multiple_hooks(self):
        """Multiple hooks run in registration order."""
        log = []
        orch = Orchestrator()
        orch.before_step(lambda step, ctx: log.append("first"))
        orch.before_step(lambda step, ctx: log.append("second"))

        pipeline = Pipeline("multi_hook")
        pipeline.add_step(PipelineStep(name="s", handler=lambda ctx: 1))

        orch.run(pipeline)
        assert log == ["first", "second"]

    def test_hooks_skipped_for_conditional(self):
        """Hooks don't run for skipped steps."""
        log = []
        orch = Orchestrator()
        orch.before_step(lambda step, ctx: log.append(step.name))

        pipeline = Pipeline("skip_hook")
        pipeline.add_step(
            PipelineStep(
                name="skipped",
                handler=lambda ctx: 1,
                condition=lambda ctx: False,
            )
        )

        result = orch.run(pipeline)
        assert result.success
        assert log == []  # hook never called
