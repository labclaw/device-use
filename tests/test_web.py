"""Tests for the FastAPI web application endpoints."""

import pytest
from fastapi.testclient import TestClient

from device_use.web.app import app


@pytest.fixture
def client():
    return TestClient(app)


# ── Status & Architecture ────────────────────────────────────────

class TestStatus:
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
    def test_datasets(self, client):
        res = client.get("/api/datasets")
        assert res.status_code == 200
        datasets = res.json()
        assert isinstance(datasets, list)
        assert len(datasets) > 0
        assert "sample" in datasets[0]
        assert "expno" in datasets[0]

    def test_process_dataset(self, client):
        # First get a dataset
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
