"""Integration tests — multi-instrument pipelines through the orchestrator."""

from device_use.instruments import ControlMode
from device_use.instruments.nmr.adapter import TopSpinAdapter
from device_use.instruments.plate_reader import PlateReaderAdapter, PlateReading
from device_use.orchestrator import (
    EventType,
    Orchestrator,
    Pipeline,
    PipelineStep,
    StepStatus,
)


class TestMultiInstrumentPipeline:
    """End-to-end test: register two instruments, run cross-instrument pipeline."""

    def _make_orchestrator(self):
        orch = Orchestrator()
        orch.register(TopSpinAdapter(mode=ControlMode.OFFLINE))
        orch.register(PlateReaderAdapter(mode=ControlMode.OFFLINE))
        return orch

    def test_both_instruments_register(self):
        orch = self._make_orchestrator()
        instruments = orch.registry.list_instruments()
        assert len(instruments) == 2
        types = {i.instrument_type for i in instruments}
        assert types == {"nmr", "plate_reader"}

    def test_both_connect(self):
        orch = self._make_orchestrator()
        results = orch.connect_all()
        assert all(results.values())

    def test_tool_namespacing(self):
        """Each instrument gets its own namespace in the tool registry."""
        orch = self._make_orchestrator()
        tools = orch.registry.list_tools()
        names = [t.name for t in tools]
        assert "topspin.list_datasets" in names
        assert "platereader.list_datasets" in names
        # No collisions
        assert len(names) == len(set(names))

    def test_cross_instrument_pipeline(self):
        """Pipeline that uses both NMR and plate reader in sequence."""
        orch = self._make_orchestrator()
        orch.connect_all()

        pipeline = Pipeline("cross_instrument")
        pipeline.add_step(
            PipelineStep(
                name="nmr_data",
                tool_name="topspin.list_datasets",
            )
        )
        pipeline.add_step(
            PipelineStep(
                name="plate_data",
                tool_name="platereader.list_datasets",
            )
        )
        pipeline.add_step(
            PipelineStep(
                name="summary",
                handler=lambda ctx: {
                    "nmr_datasets": len(ctx["nmr_data"]),
                    "plate_datasets": len(ctx["plate_data"]),
                    "total": len(ctx["nmr_data"]) + len(ctx["plate_data"]),
                },
            )
        )

        result = orch.run(pipeline)
        assert result.success
        assert result.last_output["nmr_datasets"] > 0
        assert result.last_output["plate_datasets"] == 2
        assert result.last_output["total"] > 2

    def test_event_stream_across_instruments(self):
        """Events fire correctly for multi-instrument registration + pipeline."""
        events = []
        orch = Orchestrator()
        orch.on_event(lambda e: events.append(e))

        orch.register(TopSpinAdapter(mode=ControlMode.OFFLINE))
        orch.register(PlateReaderAdapter(mode=ControlMode.OFFLINE))

        pipeline = Pipeline("event_test")
        pipeline.add_step(
            PipelineStep(
                name="step1",
                handler=lambda ctx: "done",
            )
        )
        orch.run(pipeline)

        event_types = [e.event_type for e in events]
        # Two instrument registrations
        assert event_types.count(EventType.INSTRUMENT_REGISTERED) == 2
        # Pipeline lifecycle
        assert EventType.PIPELINE_START in event_types
        assert EventType.PIPELINE_END in event_types

    def test_nmr_process_through_orchestrator(self):
        """Process NMR data via orchestrator tool call."""
        orch = self._make_orchestrator()
        orch.connect_all()

        datasets = orch.call_tool("topspin.list_datasets")
        assert len(datasets) > 0

        first = datasets[0]
        spectrum = orch.call_tool(
            "topspin.process",
            data_path=first["path"],
        )
        assert hasattr(spectrum, "peaks")
        assert len(spectrum.peaks) > 0

    def test_plate_reader_process_through_orchestrator(self):
        """Process plate reader data via orchestrator tool call."""
        orch = self._make_orchestrator()
        orch.connect_all()

        datasets = orch.call_tool("platereader.list_datasets")
        assert len(datasets) == 2

        reading = orch.call_tool(
            "platereader.process",
            data_path="ELISA_IL6_plate1",
        )
        assert isinstance(reading, PlateReading)
        assert len(reading.plate.wells) == 96

    def test_tools_for_type_filtering(self):
        """Registry can filter tools by instrument type."""
        orch = self._make_orchestrator()
        nmr_tools = orch.registry.tools_for_type("nmr")
        plate_tools = orch.registry.tools_for_type("plate_reader")
        assert len(nmr_tools) == 3
        assert len(plate_tools) == 3
        assert all("topspin" in t.name for t in nmr_tools)
        assert all("platereader" in t.name for t in plate_tools)

    def test_conditional_cross_instrument(self):
        """Conditional step based on NMR results decides whether to run plate reader."""
        orch = self._make_orchestrator()
        orch.connect_all()

        pipeline = Pipeline("conditional_cross")
        pipeline.add_step(
            PipelineStep(
                name="nmr_check",
                tool_name="topspin.list_datasets",
            )
        )
        pipeline.add_step(
            PipelineStep(
                name="plate_if_nmr",
                tool_name="platereader.list_datasets",
                condition=lambda ctx: len(ctx.get("nmr_check", [])) > 0,
            )
        )
        pipeline.add_step(
            PipelineStep(
                name="skip_if_no_nmr",
                handler=lambda ctx: "should not run",
                condition=lambda ctx: len(ctx.get("nmr_check", [])) == 0,
            )
        )

        result = orch.run(pipeline)
        assert result.success
        assert result.steps[1][1].status == StepStatus.COMPLETED
        assert result.steps[2][1].status == StepStatus.SKIPPED


class TestInstrumentTemplate:
    """Verify the template adapter works with the orchestrator."""

    def test_template_registers(self):
        from device_use.instruments.template import InstrumentTemplate

        orch = Orchestrator()
        template = InstrumentTemplate()
        orch.register(template)

        instruments = orch.registry.list_instruments()
        assert len(instruments) == 1
        assert instruments[0].name == "MyInstrument"

        tools = orch.registry.list_tools()
        assert len(tools) == 3  # list_datasets, acquire, process

    def test_three_instruments_together(self):
        """Three instrument types can coexist."""
        from device_use.instruments.template import InstrumentTemplate

        orch = Orchestrator()
        orch.register(TopSpinAdapter(mode=ControlMode.OFFLINE))
        orch.register(PlateReaderAdapter(mode=ControlMode.OFFLINE))
        orch.register(InstrumentTemplate())

        instruments = orch.registry.list_instruments()
        assert len(instruments) == 3
        assert len(orch.registry.list_tools()) == 9
