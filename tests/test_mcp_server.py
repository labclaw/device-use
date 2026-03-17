"""Tests for the MCP server integration."""

import json

import pytest

from device_use.integrations import mcp_server


@pytest.fixture(autouse=True)
def _reset_orchestrator():
    """Ensure each test gets a fresh orchestrator."""
    mcp_server._orchestrator = None
    yield
    mcp_server._orchestrator = None


class TestMCPTools:
    def test_list_instruments(self):
        result = json.loads(mcp_server.list_instruments())
        assert isinstance(result, list)
        assert len(result) == 2
        types = {i["type"] for i in result}
        assert types == {"nmr", "plate_reader"}

    def test_list_tools(self):
        result = json.loads(mcp_server.list_tools())
        assert isinstance(result, list)
        assert len(result) == 6
        names = {t["name"] for t in result}
        assert "topspin.list_datasets" in names
        assert "platereader.process" in names

    def test_call_tool_list_datasets(self):
        result = json.loads(mcp_server.call_tool("topspin.list_datasets"))
        assert isinstance(result, list)
        assert len(result) > 0
        assert "sample" in result[0]

    def test_call_tool_with_params(self):
        result = json.loads(
            mcp_server.call_tool(
                "platereader.process",
                json.dumps({"data_path": "elisa_il6"}),
            )
        )
        # Returns a PlateReading — serialized via default=str
        assert result is not None

    def test_nmr_list_datasets(self):
        result = json.loads(mcp_server.nmr_list_datasets())
        assert isinstance(result, list)
        assert len(result) > 0

    def test_nmr_process(self):
        # Get a dataset path first
        datasets = json.loads(mcp_server.nmr_list_datasets())
        path = datasets[0]["path"]

        result = json.loads(mcp_server.nmr_process(path))
        assert "peaks" in result
        assert "title" in result
        assert "num_peaks" in result

    def test_nmr_identify(self):
        datasets = json.loads(mcp_server.nmr_list_datasets())
        # Find a dataset with a cached demo response (e.g. exam_CMCse_1 = alpha ionone)
        cmcse1 = [d for d in datasets if "CMCse_1" in d.get("sample", "")]
        if not cmcse1:
            pytest.skip("exam_CMCse_1 dataset not found")
        path = cmcse1[0]["path"]

        result = mcp_server.nmr_identify(path)
        assert isinstance(result, str)
        assert len(result) > 50  # should be a real analysis

    def test_plate_reader_list_assays(self):
        result = json.loads(mcp_server.plate_reader_list_assays())
        assert isinstance(result, list)

    def test_plate_reader_process(self):
        result = json.loads(mcp_server.plate_reader_process("elisa_il6"))
        assert "protocol" in result
        assert "wavelength_nm" in result
        assert "num_wells" in result
        assert "summary" in result

    def test_run_pipeline(self):
        steps = json.dumps(
            [
                {"name": "list", "tool_name": "topspin.list_datasets"},
            ]
        )
        result = json.loads(mcp_server.run_pipeline(steps))
        assert result["success"] is True
        assert result["pipeline"] == "mcp_pipeline"
        assert len(result["steps"]) == 1
        assert result["steps"][0]["status"] == "completed"

    def test_run_pipeline_failure(self):
        steps = json.dumps(
            [
                {"name": "bad", "tool_name": "nonexistent.tool"},
            ]
        )
        result = json.loads(mcp_server.run_pipeline(steps))
        assert result["success"] is False
        assert result["steps"][0]["status"] == "failed"


class TestMCPResources:
    def test_status_resource(self):
        result = json.loads(mcp_server.get_status())
        assert result["instruments"] == 2
        assert result["tools"] == 6
        assert len(result["instrument_details"]) == 2
