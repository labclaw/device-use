"""Tests for the FastAPI web application endpoints."""

import json
import pathlib
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from device_use.web.app import app

_skip_no_examdata = pytest.mark.skipif(
    not pathlib.Path("/opt/topspin5.0.0/examdata").exists(),
    reason="TopSpin examdata not installed",
)


@pytest.fixture
def client():
    return TestClient(app)


def _make_spectrum(peaks=None):
    """Build a mock NMRSpectrum for testing process_dataset."""
    import numpy as np

    from device_use.instruments.nmr.processor import NMRPeak, NMRSpectrum

    peak_list = (
        peaks
        if peaks is not None
        else [
            NMRPeak(ppm=1.23, intensity=100.0),
            NMRPeak(ppm=3.45, intensity=50.0),
        ]
    )
    return NMRSpectrum(
        data=np.zeros(1024),
        ppm_scale=np.linspace(10, 0, 1024),
        peaks=peak_list,
        nucleus="1H",
        solvent="CDCl3",
        frequency_mhz=400.13,
        title="Test Compound",
        sample_name="test_sample",
    )


def _parse_sse(content):
    """Parse SSE text content into a list of event dicts."""
    events = []
    for line in content.decode().split("\n"):
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


# ── Status & Architecture ────────────────────────────────────────


class TestStatus:
    @_skip_no_examdata
    def test_status(self, client):
        res = client.get("/api/status")
        assert res.status_code == 200
        data = res.json()
        assert data["instrument"] == "TopSpin"
        assert data["connected"] is True
        assert "mode" in data
        assert data["orchestrator"]["instruments"] == 2

    def test_architecture(self, client):
        res = client.get("/api/architecture")
        assert res.status_code == 200
        data = res.json()
        layers = data["layers"]
        assert len(layers) == 4
        instrument_names = [c["name"] for c in layers[2]["components"]]
        assert "TopSpin NMR" in instrument_names
        assert "Plate Reader" in instrument_names


# ── NMR Endpoints ────────────────────────────────────────────────


class TestNMREndpoints:
    @_skip_no_examdata
    def test_datasets(self, client):
        res = client.get("/api/datasets")
        assert res.status_code == 200
        datasets = res.json()
        assert isinstance(datasets, list)
        assert len(datasets) > 0
        assert "sample" in datasets[0]
        assert "expno" in datasets[0]

    @_skip_no_examdata
    def test_process_dataset(self, client):
        datasets = client.get("/api/datasets").json()
        ds = datasets[0]
        res = client.get(f"/api/process/{ds['sample']}/{ds['expno']}")
        assert res.status_code == 200
        data = res.json()
        assert data["sample"] == ds["sample"]
        assert "plot_base64" in data
        assert "peaks" in data
        assert data["num_peaks"] > 0
        assert data["frequency_mhz"] > 0

    def test_process_not_found(self, client):
        res = client.get("/api/process/nonexistent/999")
        assert res.status_code == 404

    @_skip_no_examdata
    def test_analyze_stream(self, client):
        datasets = client.get("/api/datasets").json()
        ds = datasets[0]
        res = client.get(f"/api/analyze/{ds['sample']}/{ds['expno']}")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")

    def test_analyze_not_found(self, client):
        res = client.get("/api/analyze/nonexistent/999")
        assert res.status_code == 404


# ── Plate Reader Endpoints ───────────────────────────────────────


class TestPlateReaderEndpoints:
    def test_datasets(self, client):
        res = client.get("/api/plate-reader/datasets")
        assert res.status_code == 200
        datasets = res.json()
        assert len(datasets) == 2
        names = [d["name"] for d in datasets]
        assert any("ELISA" in n for n in names)
        assert any("Viability" in n for n in names)

    def test_process_elisa(self, client):
        res = client.get("/api/plate-reader/process/ELISA_IL6_plate1")
        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "absorbance"
        assert data["wavelength_nm"] == 450
        assert data["wells"] == 96
        assert len(data["heatmap"]) == 8
        assert len(data["heatmap"][0]) == 12

    def test_process_viability(self, client):
        res = client.get("/api/plate-reader/process/CellViability_DrugScreen")
        assert res.status_code == 200
        data = res.json()
        assert data["mode"] == "fluorescence"
        assert data["metadata"]["excitation_nm"] == 485

    def test_analyze_elisa(self, client):
        res = client.get("/api/plate-reader/analyze/ELISA_IL6_plate1")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")

    def test_analyze_viability(self, client):
        res = client.get("/api/plate-reader/analyze/CellViability_DrugScreen")
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")


# ── Tools Endpoint ───────────────────────────────────────────────


class TestToolsEndpoint:
    def test_tools(self, client):
        res = client.get("/api/tools")
        assert res.status_code == 200
        data = res.json()
        assert data["count"] >= 1
        tool_names = [t["name"] for t in data["tools"]]
        assert "pubchem" in tool_names


# ── Frontend ─────────────────────────────────────────────────────


class TestFrontend:
    def test_homepage(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "DEVICE-USE" in res.text
        assert "plateDatasets" in res.text
        assert "selectPlate" in res.text
        assert "heatmap" in res.text


# ── Mocked NMR process_dataset (lines 115-141) ─────────────────


class TestProcessDatasetMocked:
    """Tests for process_dataset that do not require examdata."""

    @patch("device_use.web.app._get_adapter")
    def test_process_dataset_with_peaks(self, mock_get_adapter, client):
        spectrum = _make_spectrum()
        mock_adapter = MagicMock()
        mock_adapter.list_datasets.return_value = [
            {"sample": "test_sample", "expno": 1, "path": "/fake/path/1", "title": "Test"},
        ]
        mock_adapter.process.return_value = spectrum
        mock_get_adapter.return_value = mock_adapter

        with patch(
            "device_use.instruments.nmr.visualizer.plot_spectrum",
            return_value=b"\x89PNGfake",
        ):
            res = client.get("/api/process/test_sample/1")
        assert res.status_code == 200
        data = res.json()
        assert data["sample"] == "test_sample"
        assert data["expno"] == 1
        assert data["title"] == "Test Compound"
        assert data["nucleus"] == "1H"
        assert data["solvent"] == "CDCl3"
        assert data["frequency_mhz"] == 400.1
        assert data["num_peaks"] == 2
        assert len(data["peaks"]) == 2
        assert data["peaks"][0]["ppm"] == 1.23
        assert data["peaks"][0]["intensity"] == 100.0
        assert data["peaks"][1]["ppm"] == 3.45
        assert data["peaks"][1]["intensity"] == 50.0
        assert "plot_base64" in data
        assert "processing_time_s" in data

    @patch("device_use.web.app._get_adapter")
    def test_process_dataset_no_peaks(self, mock_get_adapter, client):
        spectrum = _make_spectrum(peaks=[])
        mock_adapter = MagicMock()
        mock_adapter.list_datasets.return_value = [
            {"sample": "empty", "expno": 2, "path": "/fake/path/2", "title": ""},
        ]
        mock_adapter.process.return_value = spectrum
        mock_get_adapter.return_value = mock_adapter

        with patch(
            "device_use.instruments.nmr.visualizer.plot_spectrum",
            return_value=b"\x89PNGfake",
        ):
            res = client.get("/api/process/empty/2")
        assert res.status_code == 200
        data = res.json()
        assert data["num_peaks"] == 0
        assert data["peaks"] == []

    @patch("device_use.web.app._get_adapter")
    def test_process_dataset_second_item_matches(self, mock_get_adapter, client):
        """Test dataset matching loop when match is the second entry."""
        spectrum = _make_spectrum()
        mock_adapter = MagicMock()
        mock_adapter.list_datasets.return_value = [
            {"sample": "other", "expno": 1, "path": "/fake/other/1", "title": "Other"},
            {"sample": "target", "expno": 5, "path": "/fake/target/5", "title": "Target"},
        ]
        mock_adapter.process.return_value = spectrum
        mock_get_adapter.return_value = mock_adapter

        with patch(
            "device_use.instruments.nmr.visualizer.plot_spectrum",
            return_value=b"\x89PNGfake",
        ):
            res = client.get("/api/process/target/5")
        assert res.status_code == 200
        assert res.json()["sample"] == "target"


# ── Mocked NMR analyze_stream (lines 163-190) ──────────────────


class TestAnalyzeStreamMocked:
    """Tests for analyze_stream SSE that do not require examdata."""

    @patch("device_use.web.app._get_adapter")
    def test_analyze_stream_sse_events(self, mock_get_adapter, client):
        spectrum = _make_spectrum()
        mock_adapter = MagicMock()
        mock_adapter.list_datasets.return_value = [
            {"sample": "s", "expno": 1, "path": "/fake/1", "title": "T"},
        ]
        mock_adapter.process.return_value = spectrum
        mock_get_adapter.return_value = mock_adapter

        mock_brain = MagicMock()
        mock_brain.interpret_spectrum.return_value = iter(["chunk1", "chunk2", "chunk3"])

        with patch("device_use.instruments.nmr.brain.NMRBrain", return_value=mock_brain):
            res = client.get("/api/analyze/s/1")

        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(res.content)
        types = [e["type"] for e in events]
        assert types[0] == "start"
        assert all(t == "chunk" for t in types[1:-1])
        assert types[-1] == "done"
        assert events[1]["text"] == "chunk1"
        assert "time_s" in events[-1]

    @patch("device_use.web.app._get_adapter")
    def test_analyze_stream_sse_error(self, mock_get_adapter, client):
        """Test the except branch in the SSE generator (lines 187-188)."""
        spectrum = _make_spectrum()
        mock_adapter = MagicMock()
        mock_adapter.list_datasets.return_value = [
            {"sample": "s", "expno": 1, "path": "/fake/1", "title": "T"},
        ]
        mock_adapter.process.return_value = spectrum
        mock_get_adapter.return_value = mock_adapter

        mock_brain = MagicMock()
        mock_brain.interpret_spectrum.side_effect = RuntimeError("brain exploded")

        with patch("device_use.instruments.nmr.brain.NMRBrain", return_value=mock_brain):
            res = client.get("/api/analyze/s/1")

        assert res.status_code == 200
        events = _parse_sse(res.content)
        types = [e["type"] for e in events]
        assert types[0] == "start"
        assert types[-1] == "error"
        assert "brain exploded" in events[-1]["message"]

    @patch("device_use.web.app._get_adapter")
    def test_analyze_stream_sse_with_formula(self, mock_get_adapter, client):
        """Test analyze_stream with formula query parameter."""
        spectrum = _make_spectrum()
        mock_adapter = MagicMock()
        mock_adapter.list_datasets.return_value = [
            {"sample": "s", "expno": 1, "path": "/fake/1", "title": "T"},
        ]
        mock_adapter.process.return_value = spectrum
        mock_get_adapter.return_value = mock_adapter

        mock_brain = MagicMock()
        mock_brain.interpret_spectrum.return_value = iter(["analysis"])

        with patch("device_use.instruments.nmr.brain.NMRBrain", return_value=mock_brain):
            res = client.get("/api/analyze/s/1?formula=C6H12O6")

        assert res.status_code == 200
        events = _parse_sse(res.content)
        assert events[0]["type"] == "start"
        mock_brain.interpret_spectrum.assert_called_once()
        call_kwargs = mock_brain.interpret_spectrum.call_args.kwargs
        assert call_kwargs.get("molecular_formula") == "C6H12O6"


# ── PubChem Endpoint (lines 196-203) ───────────────────────────


class TestPubChemEndpoint:
    def test_pubchem_lookup_success(self, client):
        with patch("device_use.tools.pubchem.PubChemTool") as mock_tool_cls:
            mock_tool = mock_tool_cls.return_value
            mock_tool.lookup_by_name.return_value = {
                "CID": 1234,
                "IUPACName": "test-name",
                "MolecularFormula": "C6H12O6",
            }
            res = client.get("/api/pubchem/glucose")
        assert res.status_code == 200
        data = res.json()
        assert data["CID"] == 1234
        assert data["IUPACName"] == "test-name"
        mock_tool.lookup_by_name.assert_called_once_with("glucose")

    def test_pubchem_lookup_not_found(self, client):
        from device_use.tools.pubchem import PubChemError

        with patch("device_use.tools.pubchem.PubChemTool") as mock_tool_cls:
            mock_tool = mock_tool_cls.return_value
            mock_tool.lookup_by_name.side_effect = PubChemError("Not found")
            res = client.get("/api/pubchem/nonexistent_xyz")
        assert res.status_code == 404
        assert "Not found" in res.json()["detail"]


# ── Plate Reader not registered (lines 270, 280, 324) ──────────


class TestPlateReaderNotRegistered:
    """Test 404 when PlateReader is not in the orchestrator registry."""

    @patch("device_use.web.app._get_orchestrator")
    def test_plate_reader_datasets_not_registered(self, mock_get_orch, client):
        orch = MagicMock()
        orch.registry.get_instrument.return_value = None
        mock_get_orch.return_value = orch

        res = client.get("/api/plate-reader/datasets")
        assert res.status_code == 404
        assert "PlateReader not registered" in res.json()["detail"]

    @patch("device_use.web.app._get_orchestrator")
    def test_plate_reader_process_not_registered(self, mock_get_orch, client):
        orch = MagicMock()
        orch.registry.get_instrument.return_value = None
        mock_get_orch.return_value = orch

        res = client.get("/api/plate-reader/process/ELISA_IL6_plate1")
        assert res.status_code == 404
        assert "PlateReader not registered" in res.json()["detail"]

    @patch("device_use.web.app._get_orchestrator")
    def test_plate_reader_analyze_not_registered(self, mock_get_orch, client):
        orch = MagicMock()
        orch.registry.get_instrument.return_value = None
        mock_get_orch.return_value = orch

        res = client.get("/api/plate-reader/analyze/ELISA_IL6_plate1")
        assert res.status_code == 404
        assert "PlateReader not registered" in res.json()["detail"]


# ── Plate Reader analyze SSE content (lines 340-341) ───────────


class TestPlateReaderAnalyzeMocked:
    """Tests for plate_reader_analyze SSE error handling."""

    @patch("device_use.web.app._get_orchestrator")
    def test_plate_reader_analyze_sse_events(self, mock_get_orch, client):
        from device_use.instruments.plate_reader.models import PlateReading

        mock_reader = MagicMock()
        reading = MagicMock(spec=PlateReading)
        mock_reader.process.return_value = reading
        orch = MagicMock()
        orch.registry.get_instrument.return_value = mock_reader
        mock_get_orch.return_value = orch

        mock_brain = MagicMock()
        mock_brain.interpret_reading.return_value = iter(["plate-chunk-1", "plate-chunk-2"])

        with patch(
            "device_use.instruments.plate_reader.brain.PlateReaderBrain",
            return_value=mock_brain,
        ):
            res = client.get("/api/plate-reader/analyze/ELISA_IL6_plate1")

        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(res.content)
        types = [e["type"] for e in events]
        assert types[0] == "start"
        assert all(t == "chunk" for t in types[1:-1])
        assert types[-1] == "done"
        assert events[1]["text"] == "plate-chunk-1"
        assert "time_s" in events[-1]

    @patch("device_use.web.app._get_orchestrator")
    def test_plate_reader_analyze_sse_error(self, mock_get_orch, client):
        """Test the except branch in plate_reader_analyze SSE (lines 340-341)."""
        from device_use.instruments.plate_reader.models import PlateReading

        mock_reader = MagicMock()
        reading = MagicMock(spec=PlateReading)
        mock_reader.process.return_value = reading
        orch = MagicMock()
        orch.registry.get_instrument.return_value = mock_reader
        mock_get_orch.return_value = orch

        mock_brain = MagicMock()
        mock_brain.interpret_reading.side_effect = RuntimeError("plate brain failed")

        with patch(
            "device_use.instruments.plate_reader.brain.PlateReaderBrain",
            return_value=mock_brain,
        ):
            res = client.get("/api/plate-reader/analyze/CellViability_DrugScreen")

        assert res.status_code == 200
        events = _parse_sse(res.content)
        types = [e["type"] for e in events]
        assert types[0] == "start"
        assert types[-1] == "error"
        assert "plate brain failed" in events[-1]["message"]
