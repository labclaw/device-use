"""Tests for remaining coverage gaps — second pass to reach 100%."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# ===========================================================================
# __init__.py — lazy imports, _discover_plugins, create_orchestrator
# ===========================================================================


class TestPackageInit:
    def test_getattr_device_agent(self):
        import device_use

        cls = device_use.DeviceAgent
        assert cls.__name__ == "DeviceAgent"

    def test_getattr_agent_result(self):
        import device_use

        cls = device_use.AgentResult
        assert cls.__name__ == "AgentResult"

    def test_getattr_load_profile(self):
        import device_use

        fn = device_use.load_profile
        assert callable(fn)

    def test_getattr_list_profiles(self):
        import device_use

        fn = device_use.list_profiles
        assert callable(fn)

    def test_getattr_models(self):
        import device_use

        assert device_use.ActionRequest is not None
        assert device_use.ActionResult is not None
        assert device_use.ActionType is not None
        assert device_use.DeviceProfile is not None
        assert device_use.SafetyLevel is not None

    def test_getattr_unknown_raises(self):
        import device_use

        with pytest.raises(AttributeError, match="no attribute"):
            _ = device_use.nonexistent_attr_xyz

    def test_discover_plugins(self):
        from device_use import _discover_plugins
        from device_use.instruments.base import ControlMode

        result = _discover_plugins(ControlMode.OFFLINE)
        assert isinstance(result, dict)

    def test_create_orchestrator(self):
        from device_use import create_orchestrator

        orch = create_orchestrator(mode="offline", connect=True)
        assert orch is not None


class TestMainModule:
    def test_main_module_imports(self):
        from device_use.__main__ import main

        assert callable(main)


# ===========================================================================
# NMR processor — read_bruker, process_1d, pick_peaks
# ===========================================================================


class TestNMRProcessorCoverage:
    def test_read_bruker(self, tmp_path):
        from device_use.instruments.nmr.processor import NMRProcessor

        p = NMRProcessor()
        with patch("nmrglue.bruker.read", return_value=({}, np.array([1.0 + 0j]))):
            dic, data = p.read_bruker(str(tmp_path))
        assert isinstance(dic, dict)

    def test_process_1d(self, tmp_path):
        from device_use.instruments.nmr.processor import NMRProcessor

        p = NMRProcessor()

        dic = {
            "acqus": {"TD": 1024, "BF1": 400.13, "SOLVENT": "CDCl3"},
        }
        fid = np.random.randn(1024) + 1j * np.random.randn(1024)

        dataset_path = tmp_path / "sample" / "1"
        title_dir = dataset_path / "pdata" / "1"
        title_dir.mkdir(parents=True)
        (title_dir / "title").write_text("Test Compound\nline2")

        with (
            patch("nmrglue.bruker.remove_digital_filter", return_value=fid),
            patch("nmrglue.proc_base.zf_size", return_value=fid),
            patch("nmrglue.proc_base.em", return_value=fid),
            patch("nmrglue.proc_base.fft", return_value=fid),
            patch("nmrglue.proc_base.rev", return_value=fid),
            patch("nmrglue.proc_autophase.autops", return_value=fid),
            patch("nmrglue.proc_bl.baseline_corrector", return_value=fid.real),
            patch(
                "nmrglue.bruker.guess_udic",
                return_value={
                    0: {
                        "sw": 4000,
                        "obs": 400.13,
                        "size": 1024,
                        "label": "1H",
                        "car": 4.7 * 400.13,
                        "complex": False,
                    }
                },
            ),
            patch("nmrglue.fileiobase.uc_from_udic") as mock_uc,
        ):
            mock_uc_obj = MagicMock()
            mock_uc_obj.ppm_scale.return_value = np.linspace(12, -1, 1024)
            mock_uc.return_value = mock_uc_obj

            with patch.object(p, "pick_peaks", return_value=[]):
                spectrum = p.process_1d(dic, fid, dataset_path=str(dataset_path))

        assert spectrum.nucleus == "1H"
        assert spectrum.solvent == "CDCl3"
        assert spectrum.title == "Test Compound"
        assert spectrum.sample_name == "sample"

    def test_process_1d_no_title_file(self, tmp_path):
        from device_use.instruments.nmr.processor import NMRProcessor

        p = NMRProcessor()

        dic = {"acqus": {"TD": 512, "BF1": 400.13, "SOLVENT": "DMSO"}}
        fid = np.random.randn(512) + 1j * np.random.randn(512)

        with (
            patch("nmrglue.bruker.remove_digital_filter", return_value=fid),
            patch("nmrglue.proc_base.zf_size", return_value=fid),
            patch("nmrglue.proc_base.em", return_value=fid),
            patch("nmrglue.proc_base.fft", return_value=fid),
            patch("nmrglue.proc_base.rev", return_value=fid),
            patch("nmrglue.proc_autophase.autops", side_effect=Exception("phase fail")),
            patch("nmrglue.proc_bl.baseline_corrector", return_value=fid.real),
            patch(
                "nmrglue.bruker.guess_udic",
                return_value={
                    0: {
                        "sw": 4000,
                        "obs": 400.13,
                        "size": 512,
                        "label": "1H",
                        "car": 4.7 * 400.13,
                        "complex": False,
                    }
                },
            ),
            patch("nmrglue.fileiobase.uc_from_udic") as mock_uc,
        ):
            mock_uc_obj = MagicMock()
            mock_uc_obj.ppm_scale.return_value = np.linspace(12, -1, 512)
            mock_uc.return_value = mock_uc_obj

            with patch.object(p, "pick_peaks", return_value=[]):
                spectrum = p.process_1d(dic, fid, dataset_path=str(tmp_path / "nonexistent" / "1"))

        assert spectrum.title == ""

    def test_pick_peaks(self):
        from device_use.instruments.nmr.processor import NMRProcessor, NMRSpectrum

        p = NMRProcessor()
        ppm = np.linspace(12, -1, 1000)
        data = np.zeros(1000)
        data[300] = 100.0
        data[990] = 50.0

        spectrum = NMRSpectrum(data=data, ppm_scale=ppm, peaks=[], nucleus="1H")

        with patch("nmrglue.peakpick.pick", return_value=[[300], [990]]):
            peaks = p.pick_peaks(spectrum)

        assert len(peaks) >= 1
        assert all(-1.0 <= pk.ppm <= 15.0 for pk in peaks)


# ===========================================================================
# NMR brain — API paths (with mocked client)
# ===========================================================================


class TestNMRBrainAPIPaths:
    def test_brain_with_api_key(self):
        from device_use.instruments.nmr.brain import NMRBrain

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.Anthropic") as mock_cls,
        ):
            brain = NMRBrain()
        assert brain._use_api is True
        assert brain.client is not None

    def test_build_summary(self):
        from device_use.instruments.nmr.brain import NMRBrain
        from device_use.instruments.nmr.processor import NMRPeak, NMRSpectrum

        with patch.dict("os.environ", {}, clear=True):
            brain = NMRBrain()
        spectrum = NMRSpectrum(
            data=np.array([1.0]),
            ppm_scale=np.array([7.0]),
            peaks=[NMRPeak(ppm=7.0, intensity=100.0)],
            nucleus="1H",
            frequency_mhz=400.0,
            solvent="CDCl3",
            title="test",
            sample_name="sample",
        )
        result = brain._build_summary(spectrum)
        assert isinstance(result, str)
        assert "400.0" in result

    def test_call(self):
        from device_use.instruments.nmr.brain import NMRBrain

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.Anthropic"),
        ):
            brain = NMRBrain()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="Analysis result")]
            brain.client.messages.create.return_value = mock_response
            result = brain._call("system", "user msg")
        assert result == "Analysis result"

    def test_stream(self):
        from device_use.instruments.nmr.brain import NMRBrain

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.Anthropic"),
        ):
            brain = NMRBrain()
            mock_stream = MagicMock()
            mock_stream.__enter__ = MagicMock(return_value=mock_stream)
            mock_stream.__exit__ = MagicMock(return_value=False)
            mock_stream.text_stream = iter(["chunk1", "chunk2"])
            brain.client.messages.stream.return_value = mock_stream
            chunks = list(brain._stream("system", "user msg"))
        assert chunks == ["chunk1", "chunk2"]

    def test_interpret_with_api(self):
        from device_use.instruments.nmr.brain import NMRBrain
        from device_use.instruments.nmr.processor import NMRPeak, NMRSpectrum

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.Anthropic"),
        ):
            brain = NMRBrain()
            brain._call = MagicMock(return_value="API analysis")
            spectrum = NMRSpectrum(
                data=np.array([1.0]),
                ppm_scale=np.array([7.0]),
                peaks=[NMRPeak(ppm=7.0, intensity=100.0)],
                nucleus="1H",
                frequency_mhz=400.0,
                solvent="CDCl3",
            )
            result = brain.interpret_spectrum(
                spectrum, molecular_formula="C9H8O4", context="extra context"
            )
        assert result == "API analysis"

    def test_interpret_with_api_stream(self):
        from device_use.instruments.nmr.brain import NMRBrain
        from device_use.instruments.nmr.processor import NMRSpectrum

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.Anthropic"),
        ):
            brain = NMRBrain()
            brain._stream = MagicMock(return_value=iter(["chunk"]))
            spectrum = NMRSpectrum(
                data=np.array([1.0]),
                ppm_scale=np.array([7.0]),
                peaks=[],
                nucleus="1H",
                frequency_mhz=400.0,
                solvent="CDCl3",
            )
            result = brain.interpret_spectrum(spectrum, stream=True)
        assert brain._stream.called

    def test_suggest_with_api(self):
        from device_use.instruments.nmr.brain import NMRBrain
        from device_use.instruments.nmr.processor import NMRSpectrum

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.Anthropic"),
        ):
            brain = NMRBrain()
            brain._call = MagicMock(return_value="Next experiment")
            spectrum = NMRSpectrum(
                data=np.array([1.0]),
                ppm_scale=np.array([7.0]),
                peaks=[],
                nucleus="1H",
                frequency_mhz=400.0,
                solvent="CDCl3",
            )
            result = brain.suggest_next_experiment(spectrum, hypothesis="is aspirin")
        assert result == "Next experiment"

    def test_suggest_with_api_stream(self):
        from device_use.instruments.nmr.brain import NMRBrain
        from device_use.instruments.nmr.processor import NMRSpectrum

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.Anthropic"),
        ):
            brain = NMRBrain()
            brain._stream = MagicMock(return_value=iter(["chunk"]))
            spectrum = NMRSpectrum(
                data=np.array([1.0]),
                ppm_scale=np.array([7.0]),
                peaks=[],
                nucleus="1H",
                frequency_mhz=400.0,
                solvent="CDCl3",
            )
            result = brain.suggest_next_experiment(spectrum, stream=True)
        assert brain._stream.called

    def test_compare_spectra_with_api(self):
        from device_use.instruments.nmr.brain import NMRBrain
        from device_use.instruments.nmr.processor import NMRSpectrum

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.Anthropic"),
        ):
            brain = NMRBrain()
            brain._call = MagicMock(return_value="Comparison result")
            s1 = NMRSpectrum(
                data=np.array([1.0]),
                ppm_scale=np.array([7.0]),
                peaks=[],
                nucleus="1H",
                frequency_mhz=400.0,
                solvent="CDCl3",
            )
            s2 = NMRSpectrum(
                data=np.array([2.0]),
                ppm_scale=np.array([7.0]),
                peaks=[],
                nucleus="1H",
                frequency_mhz=400.0,
                solvent="CDCl3",
            )
            result = brain.compare_spectra(s1, s2, context="Batch QC")
        assert result == "Comparison result"


# ===========================================================================
# NMR adapter — list_examdata iteration, process routing
# ===========================================================================


class TestNMRAdapterExtended:
    def test_list_examdata_with_data(self, tmp_path):
        from device_use.instruments.nmr.adapter import TopSpinAdapter

        examdata = tmp_path / "examdata"
        examdata.mkdir()
        sample = examdata / "test_sample"
        sample.mkdir()
        expno = sample / "1"
        expno.mkdir()
        (expno / "fid").write_bytes(b"FID_DATA")
        title_dir = expno / "pdata" / "1"
        title_dir.mkdir(parents=True)
        (title_dir / "title").write_text("Test Title\nmore")
        (sample / "notes").mkdir()
        (examdata / "README.txt").write_text("info")

        adapter = TopSpinAdapter(topspin_dir=str(tmp_path))
        datasets = adapter.list_examdata()
        assert len(datasets) == 1
        assert datasets[0]["sample"] == "test_sample"
        assert datasets[0]["expno"] == 1
        assert datasets[0]["title"] == "Test Title"

    def test_process_via_nmrglue(self, tmp_path):
        from device_use.instruments.nmr.adapter import TopSpinAdapter

        adapter = TopSpinAdapter(topspin_dir=str(tmp_path))
        mock_spectrum = MagicMock()
        with (
            patch.object(adapter.processor, "read_bruker", return_value=({}, np.array([1.0]))),
            patch.object(adapter.processor, "process_1d", return_value=mock_spectrum),
        ):
            result = adapter._process_via_nmrglue("some/path")
        assert result is mock_spectrum

    def test_connect_gui_success(self, tmp_path):
        from device_use.instruments.nmr.adapter import TopSpinAdapter

        adapter = TopSpinAdapter(topspin_dir=str(tmp_path), mode="gui")
        mock_gui = MagicMock()
        mock_gui.available = True
        mock_gui.command_mode_available = True
        mock_gui.detect_topspin_window.return_value = True

        # The import is inside _connect_gui as
        # `from device_use.instruments.nmr.gui_automation import ...`
        with patch(
            "device_use.instruments.nmr.gui_automation.TopSpinGUIAutomation",
            return_value=mock_gui,
        ):
            # Need to patch at the actual import location
            with patch.dict(
                "sys.modules",
                {
                    "device_use.instruments.nmr.gui_automation": MagicMock(
                        TopSpinGUIAutomation=MagicMock(return_value=mock_gui)
                    )
                },
            ):
                result = adapter._connect_gui()
        assert result is True

    def test_connect_gui_exception(self, tmp_path):
        from device_use.instruments.nmr.adapter import TopSpinAdapter

        adapter = TopSpinAdapter(topspin_dir=str(tmp_path), mode="gui")
        with patch.dict(
            "sys.modules",
            {
                "device_use.instruments.nmr.gui_automation": MagicMock(
                    TopSpinGUIAutomation=MagicMock(side_effect=RuntimeError("no gui"))
                )
            },
        ):
            result = adapter._connect_gui()
        assert result is False


# ===========================================================================
# NMR library — match, _jaccard, list_entries
# ===========================================================================


class TestSpectralLibraryExtended:
    def test_add_and_match(self):
        from device_use.instruments.nmr.library import SpectralLibrary

        lib = SpectralLibrary(tolerance_ppm=0.1)
        lib.add("aspirin", [2.1, 7.0, 8.0])
        lib.add("caffeine", [3.3, 3.5, 7.5])

        results = lib.match_peaks([7.0, 8.0, 2.1], top_k=2)
        assert len(results) == 2
        assert results[0].entry.name == "aspirin"
        assert results[0].score > 0.5

    def test_jaccard_both_empty(self):
        from device_use.instruments.nmr.library import SpectralLibrary

        lib = SpectralLibrary()
        score, matched = lib._jaccard([], [])
        assert score == 1.0
        assert matched == 0

    def test_jaccard_one_empty(self):
        from device_use.instruments.nmr.library import SpectralLibrary

        lib = SpectralLibrary()
        score, matched = lib._jaccard([1.0, 2.0], [])
        assert score == 0.0

    def test_list_entries(self):
        from device_use.instruments.nmr.library import SpectralLibrary

        lib = SpectralLibrary()
        lib.add("test", [1.0])
        assert lib.list_entries() == ["test"]


# ===========================================================================
# Plate reader brain — API paths
# ===========================================================================


class TestPlateReaderBrainAPI:
    def test_interpret_reading_with_api(self):
        from device_use.instruments.plate_reader.brain import PlateReaderBrain

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.Anthropic"),
        ):
            brain = PlateReaderBrain()
            mock_response = MagicMock()
            mock_response.content = [MagicMock(text="Analysis")]
            brain.client.messages.create.return_value = mock_response
            reading = MagicMock()
            reading.protocol = "Custom Protocol"
            result = brain.interpret_reading(reading)
        assert result == "Analysis"

    def test_interpret_reading_with_api_stream(self):
        from device_use.instruments.plate_reader.brain import PlateReaderBrain

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.Anthropic"),
        ):
            brain = PlateReaderBrain()
            mock_stream = MagicMock()
            mock_stream.__enter__ = MagicMock(return_value=mock_stream)
            mock_stream.__exit__ = MagicMock(return_value=False)
            mock_stream.text_stream = iter(["part1", "part2"])
            brain.client.messages.stream.return_value = mock_stream
            reading = MagicMock()
            reading.protocol = "Custom Protocol"
            result = list(brain.interpret_reading(reading, stream=True))
        assert result == ["part1", "part2"]


# ===========================================================================
# web/app — process, analyze, pubchem, plate reader endpoints
# ===========================================================================


class TestWebAppExtended:
    def test_get_status(self):
        from fastapi.testclient import TestClient

        from device_use.web.app import app

        client = TestClient(app)
        resp = client.get("/api/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "instrument" in data

    def test_list_datasets(self):
        from fastapi.testclient import TestClient

        from device_use.web.app import app

        client = TestClient(app)
        resp = client.get("/api/datasets")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_process_dataset_not_found(self):
        from fastapi.testclient import TestClient

        from device_use.web.app import app

        client = TestClient(app)
        resp = client.get("/api/process/nonexistent_sample/999")
        assert resp.status_code == 404

    def test_analyze_not_found(self):
        from fastapi.testclient import TestClient

        from device_use.web.app import app

        client = TestClient(app)
        resp = client.get("/api/analyze/nonexistent_sample/999")
        assert resp.status_code == 404

    def test_pubchem_lookup_success(self):
        from fastapi.testclient import TestClient

        from device_use.web.app import app

        client = TestClient(app)
        # The import is lazy inside the endpoint, patch at the source module
        with patch(
            "device_use.tools.pubchem.PubChemTool.lookup_by_name",
            return_value={"CID": 2244, "name": "aspirin"},
        ):
            resp = client.get("/api/pubchem/aspirin")
        assert resp.status_code == 200

    def test_pubchem_lookup_error(self):
        from fastapi.testclient import TestClient

        from device_use.tools.pubchem import PubChemError
        from device_use.web.app import app

        client = TestClient(app)
        with patch(
            "device_use.tools.pubchem.PubChemTool.lookup_by_name",
            side_effect=PubChemError("Not found"),
        ):
            resp = client.get("/api/pubchem/nonexistent_compound_xyz")
        assert resp.status_code == 404

    def test_plate_reader_datasets(self):
        from fastapi.testclient import TestClient

        from device_use.web.app import app

        client = TestClient(app)
        resp = client.get("/api/plate-reader/datasets")
        assert resp.status_code == 200

    def test_plate_reader_process(self):
        from fastapi.testclient import TestClient

        from device_use.web.app import app

        client = TestClient(app)
        resp = client.get("/api/plate-reader/process/elisa_standard_curve")
        assert resp.status_code == 200
        data = resp.json()
        assert "protocol" in data
        assert "heatmap" in data

    def test_plate_reader_analyze(self):
        from fastapi.testclient import TestClient

        from device_use.web.app import app

        client = TestClient(app)
        resp = client.get("/api/plate-reader/analyze/elisa_standard_curve")
        assert resp.status_code == 200


# ===========================================================================
# Orchestrator — describe, _execute_step, _resolve_params, connect_all
# ===========================================================================


class TestOrchestratorExtended:
    def test_pipeline_describe_with_description(self):
        from device_use.orchestrator import Pipeline, PipelineStep

        p = Pipeline("test_pipe", description="A test pipeline")
        p.add_step(
            PipelineStep(
                name="step1",
                tool_name="some_tool",
                retries=2,
                timeout_s=10.0,
            )
        )
        p.add_step(
            PipelineStep(
                name="step2",
                tool_name="other_tool",
                condition=lambda ctx: True,
            )
        )
        text = p.describe()
        assert "test_pipe" in text
        assert "A test pipeline" in text
        assert "retries=2" in text
        assert "timeout=10.0s" in text
        assert "conditional" in text

    def test_pipeline_describe_parallel(self):
        from device_use.orchestrator import Pipeline, PipelineStep

        p = Pipeline("par_pipe")
        p.add_step(PipelineStep(name="a", tool_name="t1", parallel="group1"))
        p.add_step(
            PipelineStep(name="b", tool_name="t2", parallel="group1", retries=1, timeout_s=5.0)
        )
        text = p.describe()
        assert "parallel" in text
        assert "group1" in text

    def test_execute_step_no_tool_no_handler(self):
        from device_use.orchestrator import Orchestrator, PipelineStep

        orch = Orchestrator()
        step = PipelineStep(name="bad_step")
        with pytest.raises(ValueError, match="neither tool_name nor handler"):
            orch._execute_step(step, {})

    def test_resolve_params_ref_found(self):
        from device_use.orchestrator import Orchestrator

        result = Orchestrator._resolve_params(
            {"data": "{step1}", "literal": 42},
            {"step1": "output_value"},
        )
        assert result["data"] == "output_value"
        assert result["literal"] == 42

    def test_resolve_params_ref_not_found(self):
        from device_use.orchestrator import Orchestrator

        result = Orchestrator._resolve_params(
            {"data": "{missing_step}"},
            {},
        )
        assert result["data"] == "{missing_step}"

    def test_connect_all(self):
        from device_use.orchestrator import Orchestrator

        orch = Orchestrator()
        mock_inst = MagicMock()
        mock_inst.info.return_value = MagicMock(
            name="TestInst", vendor="V", version="1", supported_modes=[]
        )
        mock_inst.connect.return_value = True
        orch.register(mock_inst)
        results = orch.connect_all()
        assert len(results) >= 1

    def test_orchestrator_emit_catches_errors(self):
        from device_use.orchestrator import Event, EventType, Orchestrator

        orch = Orchestrator()

        def bad_listener(event):
            raise RuntimeError("listener crash")

        orch.registry.add_listener(bad_listener)
        # Should not raise
        orch._emit(Event(event_type=EventType.STEP_START, data={}))

    def test_pipeline_result_last_output(self):
        from device_use.orchestrator import (
            PipelineResult,
            StepResult,
            StepStatus,
        )

        pr = PipelineResult(name="test")
        pr.steps.append(
            (
                "s1",
                StepResult(status=StepStatus.COMPLETED, output="data"),
            )
        )
        assert pr.last_output == "data"


# ===========================================================================
# Agent — remaining branches (execute exception, _remaining_actions, etc.)
# ===========================================================================


class TestAgentBranches:
    @pytest.mark.asyncio
    async def test_execute_exception_returns_failure(self):
        from device_use.core.agent import DeviceAgent
        from device_use.core.models import DeviceProfile

        profile = DeviceProfile(name="test", software="App")
        backend = MagicMock()
        backend.supports_grounding = True

        agent = DeviceAgent(profile, backend, max_steps=3)
        agent._capture_screenshot = AsyncMock(side_effect=RuntimeError("screenshot broken"))

        result = await agent.execute("test task")
        assert result.success is False
        assert "screenshot broken" in result.error

    @pytest.mark.asyncio
    async def test_max_steps_reached(self):
        from device_use.core.agent import DeviceAgent
        from device_use.core.models import DeviceProfile

        profile = DeviceProfile(name="test", software="App")
        backend = MagicMock()
        backend.supports_grounding = True
        backend.observe = AsyncMock(return_value={"description": "screen"})
        backend.plan = AsyncMock(
            return_value={
                "done": False,
                "reasoning": "step",
                "action": {"action_type": "wait", "seconds": 0},
                "confidence": 0.9,
            }
        )

        agent = DeviceAgent(profile, backend, max_steps=2)
        agent._capture_screenshot = AsyncMock(return_value=b"\x89PNG")
        agent._executor._settle_delay = 0

        result = await agent.execute("infinite task")
        assert result.success is False
        assert "Max steps" in result.error


# ===========================================================================
# Safety guard — line 63 (rate limit check_action_rate)
# ===========================================================================


class TestSafetyGuardLine63:
    def test_rate_limit_with_auto_approve(self):
        from device_use.core.models import ActionRequest, ActionType, DeviceProfile
        from device_use.safety.guard import SafetyGuard

        profile = DeviceProfile(name="test", software="App")
        profile.safety.max_actions_per_minute = 1
        guard = SafetyGuard(profile, auto_approve=True)

        action = ActionRequest(action_type=ActionType.CLICK)
        guard.record_action(action)
        guard.record_action(action)

        verdict = guard.check(action)
        assert verdict.allowed is False


# ===========================================================================
# CLI — line 584 (scaffold with output_dir default)
# ===========================================================================


class TestCLILine584:
    def test_scaffold_with_default_output(self, tmp_path, capsys):
        from device_use import cli

        cli._scaffold("my-device", str(tmp_path))
        out = capsys.readouterr().out
        assert "device_use_my_device" in out


# ===========================================================================
# Executor — line 172 (ValueError in dispatch) + lines 116-119 (error handling)
# ===========================================================================


class TestExecutorLine172:
    def test_dispatch_raises_value_error(self):
        import device_use.actions.executor as executor_mod
        from device_use.actions.executor import ActionExecutor

        orig_pag = executor_mod._pyautogui
        orig_clip = executor_mod._pyperclip
        orig_fail = executor_mod._FailSafeException

        mock_pag = MagicMock()

        class _FakeFailSafe(Exception):
            pass

        mock_pag.FailSafeException = _FakeFailSafe
        executor_mod._pyautogui = mock_pag
        executor_mod._pyperclip = MagicMock()
        executor_mod._FailSafeException = _FakeFailSafe

        try:
            ex = ActionExecutor(settle_delay=0)
            action = MagicMock(spec=[])
            action.action_type = "click"
            action.description = "test"
            with pytest.raises(ValueError, match="Unknown action type"):
                ex._dispatch(action)
        finally:
            executor_mod._pyautogui = orig_pag
            executor_mod._pyperclip = orig_clip
            executor_mod._FailSafeException = orig_fail

    def test_execute_catches_dispatch_error(self):
        import device_use.actions.executor as executor_mod
        from device_use.actions.executor import ActionExecutor
        from device_use.actions.models import WaitAction

        orig_pag = executor_mod._pyautogui
        orig_clip = executor_mod._pyperclip
        orig_fail = executor_mod._FailSafeException

        mock_pag = MagicMock()

        class _FakeFailSafe(Exception):
            pass

        mock_pag.FailSafeException = _FakeFailSafe
        executor_mod._pyautogui = mock_pag
        executor_mod._pyperclip = MagicMock()
        executor_mod._FailSafeException = _FakeFailSafe

        try:
            ex = ActionExecutor(settle_delay=0)
            action = WaitAction(seconds=0.001, description="wait")
            with patch.object(ex, "_dispatch", side_effect=RuntimeError("dispatch broke")):
                result = ex.execute(action)
            assert result.success is False
            assert "dispatch broke" in result.error
        finally:
            executor_mod._pyautogui = orig_pag
            executor_mod._pyperclip = orig_clip
            executor_mod._FailSafeException = orig_fail


# ===========================================================================
# Template instrument — line 80 (acquire GUI mode)
# ===========================================================================


class TestTemplateInstrumentLine80:
    def test_acquire_gui_raises(self):
        from device_use.instruments.base import ControlMode
        from device_use.instruments.template import InstrumentTemplate

        t = InstrumentTemplate(mode=ControlMode.GUI)
        with pytest.raises(NotImplementedError):
            t.acquire()


# ===========================================================================
# MCP server — lines 294, 298
# ===========================================================================


class TestMCPServerRemaining:
    def test_plate_reader_process_mcp(self):
        from device_use.integrations import mcp_server

        mock_orch = MagicMock()
        # Use real adapter to get real reading object
        from device_use.instruments.plate_reader.adapter import PlateReaderAdapter

        adapter = PlateReaderAdapter()
        adapter.connect()
        reading = adapter.process("elisa_standard_curve")

        mock_orch.call_tool.return_value = reading
        with patch.object(mcp_server, "_get_orchestrator", return_value=mock_orch):
            result = mcp_server.plate_reader_process("elisa_standard_curve")
        data = json.loads(result)
        assert "protocol" in data


# ===========================================================================
# Retriever — line 251 (exception in retrieve_docs)
# ===========================================================================


class TestRetrieverLine251:
    def test_retrieve_docs_missing_index(self, tmp_path):
        from device_use.knowledge.retriever import retrieve_docs

        result = retrieve_docs("nonexistent-device", "test query", skills_dir=tmp_path)
        assert result == ""


# ===========================================================================
# Skills context — lines 160-161 (RAG failure)
# ===========================================================================


class TestSkillsContextEdges:
    def test_build_prompt_with_profile_and_science(self, tmp_path):
        from device_use.skills.context import SkillContext

        device_dir = tmp_path / "devices" / "my-device"
        device_dir.mkdir(parents=True)
        (device_dir / "SOUL.md").write_text("# My Device\nYou control this device.")
        import yaml

        (device_dir / "profile.yaml").write_text(
            yaml.dump(
                {
                    "software": "TopSpin 5",
                    "commands": {"open": "re {path}"},
                    "command_bar": {"location": "bottom", "submit_key": "Enter"},
                    "delays": {"process": 2},
                    "safety": {"forbidden_commands": ["halt"]},
                }
            )
        )
        (device_dir / "science.md").write_text("# NMR Science\nNMR is great.")

        ctx = SkillContext("my-device", skills_dir=tmp_path)
        prompt = ctx.build_prompt(task="Process data", user_context="User is a chemist")
        assert "My Device" in prompt
        assert "TopSpin 5" in prompt
        assert "NMR Science" in prompt
        assert "User is a chemist" in prompt

    def test_build_prompt_rag_failure(self, tmp_path):
        from device_use.skills.context import SkillContext

        device_dir = tmp_path / "devices" / "my-device"
        device_dir.mkdir(parents=True)
        (device_dir / "SOUL.md").write_text("# My Device")

        ctx = SkillContext("my-device", skills_dir=tmp_path)
        with patch(
            "device_use.knowledge.retriever.retrieve_docs",
            side_effect=RuntimeError("RAG broken"),
        ):
            prompt = ctx.build_prompt(task="test")
        assert "My Device" in prompt


# ===========================================================================
# Tools — tooluniverse remaining lines
# ===========================================================================


class TestToolUniverseRemaining:
    def test_connect_success(self):
        from device_use.tools.tooluniverse import ToolUniverseTool

        tool = ToolUniverseTool()
        mock_tu = MagicMock()
        with (
            patch("device_use.tools.tooluniverse._TU_AVAILABLE", True),
            patch("device_use.tools.tooluniverse._ToolUniverse", return_value=mock_tu),
        ):
            tool.connect()
        assert tool.connected is True

    def test_execute_spec_empty_name(self):
        from device_use.tools.tooluniverse import ToolUniverseTool

        tool = ToolUniverseTool()
        tool._connected = True
        tool._tu = MagicMock()
        tool._tu.tool_specification.return_value = {"spec": "data"}
        # spec action passes empty string when no tool_name given
        result = tool.execute(action="spec")
        tool._tu.tool_specification.assert_called_once_with("", format="openai")


# ===========================================================================
# PubChem — remaining uncovered lines
# ===========================================================================


class TestPubChemRemaining:
    def test_lookup_by_name(self):
        from device_use.tools.pubchem import PubChemTool

        tool = PubChemTool()
        with patch.object(tool, "lookup_by_name", return_value={"CID": 2244, "name": "aspirin"}):
            result = tool.execute(name="aspirin")
        assert result["CID"] == 2244


# ===========================================================================
# OpenAI compat backend — native CU paths
# ===========================================================================


class TestOpenAICompatBackend:
    def test_observe_native(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        with patch("device_use.backends.openai_compat.AsyncOpenAI"):
            backend = OpenAICompatBackend(model="gpt-5.4")

        backend._native_cu = True
        mock_response = MagicMock()
        backend._responses_create = AsyncMock(return_value=mock_response)
        backend._extract_text = MagicMock(
            return_value='{"description": "screen state", "elements": []}'
        )

        result = asyncio.run(backend.observe(b"\x89PNG", context="test"))
        assert result["description"] == "screen state"

    def test_observe_native_json_error(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        with patch("device_use.backends.openai_compat.AsyncOpenAI"):
            backend = OpenAICompatBackend(model="gpt-5.4")

        backend._native_cu = True
        mock_response = MagicMock()
        backend._responses_create = AsyncMock(return_value=mock_response)
        backend._extract_text = MagicMock(return_value="not json")

        result = asyncio.run(backend.observe(b"\x89PNG"))
        assert result["description"] == "not json"

    def test_plan_native(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        with patch("device_use.backends.openai_compat.AsyncOpenAI"):
            backend = OpenAICompatBackend(model="gpt-5.4")

        backend._native_cu = True
        backend._plan_native = AsyncMock(
            return_value={"action": {"action_type": "click"}, "done": False}
        )

        result = asyncio.run(backend.plan(b"\x89PNG", "click button"))
        assert "action" in result

    def test_plan_legacy(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        with patch("device_use.backends.openai_compat.AsyncOpenAI"):
            backend = OpenAICompatBackend(model="gpt-4o")

        backend._native_cu = False
        backend._plan_legacy = AsyncMock(
            return_value={"action": {"action_type": "click"}, "done": False}
        )

        result = asyncio.run(backend.plan(b"\x89PNG", "click button"))
        assert "action" in result

    def test_locate_native(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        with patch("device_use.backends.openai_compat.AsyncOpenAI"):
            backend = OpenAICompatBackend(model="gpt-5.4")

        backend._native_cu = True
        mock_response = MagicMock()
        backend._responses_create = AsyncMock(return_value=mock_response)
        backend._extract_text = MagicMock(return_value='{"x": 100, "y": 200}')

        result = asyncio.run(backend.locate(b"\x89PNG", "button"))
        assert result == (100, 200)

    def test_locate_native_not_found(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        with patch("device_use.backends.openai_compat.AsyncOpenAI"):
            backend = OpenAICompatBackend(model="gpt-5.4")

        backend._native_cu = True
        mock_response = MagicMock()
        backend._responses_create = AsyncMock(return_value=mock_response)
        backend._extract_text = MagicMock(return_value='{"x": null, "y": null}')

        result = asyncio.run(backend.locate(b"\x89PNG", "nonexistent"))
        assert result is None

    def test_locate_native_json_error(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        with patch("device_use.backends.openai_compat.AsyncOpenAI"):
            backend = OpenAICompatBackend(model="gpt-5.4")

        backend._native_cu = True
        mock_response = MagicMock()
        backend._responses_create = AsyncMock(return_value=mock_response)
        backend._extract_text = MagicMock(return_value="not json")

        result = asyncio.run(backend.locate(b"\x89PNG", "button"))
        assert result is None

    def test_locate_no_native(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        with patch("device_use.backends.openai_compat.AsyncOpenAI"):
            backend = OpenAICompatBackend(model="gpt-4o")

        backend._native_cu = False

        result = asyncio.run(backend.locate(b"\x89PNG", "button"))
        assert result is None

    def test_map_cu_action_click(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        result = OpenAICompatBackend._map_cu_action(
            {"action_type": "click", "x": 100, "y": 200, "button": "left"}
        )
        assert result["action"]["coordinates"] == [100, 200]

    def test_map_cu_action_right_click(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        result = OpenAICompatBackend._map_cu_action(
            {"action_type": "right_click", "x": 100, "y": 200}
        )
        assert result["action"]["button"] == "right"

    def test_map_cu_action_double_click(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        result = OpenAICompatBackend._map_cu_action(
            {"action_type": "double_click", "x": 50, "y": 60}
        )
        assert result["action"]["action_type"] == "double_click"

    def test_map_cu_action_type(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        result = OpenAICompatBackend._map_cu_action({"action_type": "type", "text": "hello"})
        assert result["action"]["text"] == "hello"

    def test_map_cu_action_keypress(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        result = OpenAICompatBackend._map_cu_action(
            {"action_type": "keypress", "keys": ["ctrl", "s"]}
        )
        assert result["action"]["action_type"] == "hotkey"
        assert result["action"]["keys"] == ["ctrl", "s"]

    def test_map_cu_action_scroll(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        result = OpenAICompatBackend._map_cu_action(
            {"action_type": "scroll", "x": 500, "y": 500, "scroll_y": -240}
        )
        assert result["action"]["clicks"] == -2

    def test_map_cu_action_drag(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        result = OpenAICompatBackend._map_cu_action(
            {
                "action_type": "drag",
                "path": [{"x": 10, "y": 20}, {"x": 100, "y": 200}],
            }
        )
        assert result["action"]["start_x"] == 10
        assert result["action"]["end_x"] == 100

    def test_map_cu_action_drag_no_path(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        result = OpenAICompatBackend._map_cu_action({"action_type": "drag", "path": []})
        assert result["action"]["start_x"] == 0

    def test_map_cu_action_move(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        result = OpenAICompatBackend._map_cu_action({"action_type": "move", "x": 300, "y": 400})
        assert result["action"]["coordinates"] == [300, 400]

    def test_map_cu_action_screenshot(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        result = OpenAICompatBackend._map_cu_action({"action_type": "screenshot"})
        assert result["action"]["action_type"] == "screenshot"

    def test_map_cu_action_wait(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        result = OpenAICompatBackend._map_cu_action({"action_type": "wait"})
        assert result["action"]["seconds"] == 1


# ===========================================================================
# A11y operator — can only test construction failure on Linux
# ===========================================================================


class TestA11yOperator:
    def test_init_fails_on_linux(self):
        """AccessibilityOperator requires macOS frameworks — fails on Linux."""
        from device_use.operators.a11y import AccessibilityOperator

        # On Linux, find_library("CoreFoundation") returns None,
        # causing LoadLibrary to fail with OSError or TypeError
        with pytest.raises((OSError, TypeError, AttributeError)):
            AccessibilityOperator(pid=1)
