"""Tests for the Plate Reader instrument adapter."""

import pytest

from device_use.instruments import ControlMode
from device_use.instruments.plate_reader import (
    PlateFormat,
    PlateReaderAdapter,
    PlateReading,
    ReadingMode,
    Well,
    WellPlate,
)


# ── Models ───────────────────────────────────────────────────────────

class TestWell:
    def test_name(self):
        w = Well(row="A", col=1, value=0.5)
        assert w.name == "A1"

    def test_name_double_digit(self):
        w = Well(row="H", col=12, value=0.1)
        assert w.name == "H12"


class TestWellPlate:
    def test_get_well(self):
        plate = WellPlate(
            format=PlateFormat.PLATE_96,
            wells=[
                Well(row="A", col=1, value=1.0),
                Well(row="A", col=2, value=2.0),
                Well(row="B", col=1, value=3.0),
            ],
        )
        assert plate.get_well("A2").value == 2.0
        assert plate.get_well("Z9") is None

    def test_column(self):
        plate = WellPlate(
            format=PlateFormat.PLATE_96,
            wells=[
                Well(row="A", col=1, value=1.0),
                Well(row="B", col=1, value=2.0),
                Well(row="A", col=2, value=3.0),
            ],
        )
        col1 = plate.column(1)
        assert len(col1) == 2
        assert all(w.col == 1 for w in col1)

    def test_row(self):
        plate = WellPlate(
            format=PlateFormat.PLATE_96,
            wells=[
                Well(row="A", col=1, value=1.0),
                Well(row="A", col=2, value=2.0),
                Well(row="B", col=1, value=3.0),
            ],
        )
        row_a = plate.row("A")
        assert len(row_a) == 2


# ── Adapter ──────────────────────────────────────────────────────────

class TestPlateReaderAdapter:
    def test_info(self):
        adapter = PlateReaderAdapter()
        info = adapter.info()
        assert info.name == "PlateReader"
        assert info.vendor == "BioTek"
        assert info.instrument_type == "plate_reader"
        assert ControlMode.OFFLINE in info.supported_modes

    def test_connect_offline(self):
        adapter = PlateReaderAdapter(mode=ControlMode.OFFLINE)
        assert adapter.connect() is True
        assert adapter.connected is True

    def test_mode(self):
        adapter = PlateReaderAdapter(mode=ControlMode.OFFLINE)
        assert adapter.mode == ControlMode.OFFLINE

    def test_list_datasets(self):
        adapter = PlateReaderAdapter(mode=ControlMode.OFFLINE)
        adapter.connect()
        datasets = adapter.list_datasets()
        assert len(datasets) == 2
        assert any("ELISA" in d["name"] for d in datasets)
        assert any("Viability" in d["name"] for d in datasets)

    def test_process_elisa(self):
        adapter = PlateReaderAdapter(mode=ControlMode.OFFLINE)
        adapter.connect()
        reading = adapter.process("ELISA_IL6_plate1")
        assert isinstance(reading, PlateReading)
        assert reading.mode == ReadingMode.ABSORBANCE
        assert reading.wavelength_nm == 450
        assert len(reading.plate.wells) == 96

    def test_process_viability(self):
        adapter = PlateReaderAdapter(mode=ControlMode.OFFLINE)
        adapter.connect()
        reading = adapter.process("CellViability_DrugScreen")
        assert isinstance(reading, PlateReading)
        assert reading.mode == ReadingMode.FLUORESCENCE
        assert reading.wavelength_nm == 530

    def test_process_auto_connects(self):
        adapter = PlateReaderAdapter(mode=ControlMode.OFFLINE)
        # Don't call connect() — should auto-connect
        reading = adapter.process("ELISA")
        assert adapter.connected is True
        assert isinstance(reading, PlateReading)

    def test_acquire_offline_raises(self):
        adapter = PlateReaderAdapter(mode=ControlMode.OFFLINE)
        adapter.connect()
        with pytest.raises(RuntimeError, match="OFFLINE"):
            adapter.acquire()

    def test_blank_correction(self):
        adapter = PlateReaderAdapter(mode=ControlMode.OFFLINE)
        reading = adapter.process("ELISA")
        # Blank wells (col 11-12) should have low values
        blank = reading.plate.get_well("A12")
        standard = reading.plate.get_well("A1")
        assert standard.value > blank.value

        # All wells should have blank_corrected set
        for w in reading.plate.wells:
            assert w.blank_corrected is not None

        # blank_corrected = value - blank_avg
        blank_wells = [w for w in reading.plate.wells if w.col >= 11]
        blank_avg = sum(w.value for w in blank_wells) / len(blank_wells)
        sample = reading.plate.get_well("C5")
        assert abs(sample.blank_corrected - (sample.value - blank_avg)) < 1e-3

    def test_csv_export(self):
        adapter = PlateReaderAdapter(mode=ControlMode.OFFLINE)
        reading = adapter.process("ELISA")
        csv_text = PlateReaderAdapter.reading_to_csv(reading)
        assert "Protocol: ELISA Demo" in csv_text
        assert "Wavelength: 450nm" in csv_text
        lines = csv_text.strip().split("\n")
        # Header + blank + 8 data rows + column header = 11 lines min
        assert len(lines) >= 10


# ── Orchestrator Integration ─────────────────────────────────────────

class TestPlateReaderOrchestration:
    def test_register_with_orchestrator(self):
        from device_use.orchestrator import Orchestrator

        orch = Orchestrator()
        adapter = PlateReaderAdapter(mode=ControlMode.OFFLINE)
        orch.register(adapter)

        instruments = orch.registry.list_instruments()
        assert len(instruments) == 1
        assert instruments[0].name == "PlateReader"

        tools = orch.registry.list_tools()
        tool_names = [t.name for t in tools]
        assert "platereader.list_datasets" in tool_names
        assert "platereader.acquire" in tool_names
        assert "platereader.process" in tool_names

    def test_call_tool(self):
        from device_use.orchestrator import Orchestrator

        orch = Orchestrator()
        adapter = PlateReaderAdapter(mode=ControlMode.OFFLINE)
        orch.register(adapter)

        datasets = orch.call_tool("platereader.list_datasets")
        assert len(datasets) == 2

    def test_multi_instrument(self):
        """Orchestrator handles NMR + plate reader simultaneously."""
        from device_use.instruments.nmr.adapter import TopSpinAdapter
        from device_use.orchestrator import Orchestrator

        orch = Orchestrator()
        orch.register(TopSpinAdapter(mode=ControlMode.OFFLINE))
        orch.register(PlateReaderAdapter(mode=ControlMode.OFFLINE))

        instruments = orch.registry.list_instruments()
        assert len(instruments) == 2

        types = {i.instrument_type for i in instruments}
        assert "nmr" in types
        assert "plate_reader" in types

        # Both tools available
        tools = orch.registry.list_tools()
        tool_names = [t.name for t in tools]
        assert "topspin.list_datasets" in tool_names
        assert "platereader.list_datasets" in tool_names
