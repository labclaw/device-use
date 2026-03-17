"""Additional NMR module coverage tests.

Covers adapter, brain, gui_automation, processor, demo_cache, visualizer, library.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from device_use.instruments.base import ControlMode
from device_use.instruments.nmr.adapter import TopSpinAdapter
from device_use.instruments.nmr.brain import (
    NMRBrain,
    _has_api_key,
    _resolve_compound_name,
    _simulate_stream,
)
from device_use.instruments.nmr.demo_cache import find_cached_response, get_dnmr_analysis
from device_use.instruments.nmr.gui_automation import TopSpinGUIAutomation
from device_use.instruments.nmr.library import SpectralLibrary
from device_use.instruments.nmr.processor import NMRPeak, NMRProcessor, NMRSpectrum
from device_use.instruments.nmr.visualizer import _build_title, plot_spectrum

# ===========================================================================
# adapter
# ===========================================================================


class TestTopSpinAdapterModes:
    def test_connect_api_fails_no_bruker(self):
        adapter = TopSpinAdapter(mode=ControlMode.API)
        result = adapter._connect_api()
        assert result is False
        assert adapter.connected is False

    def test_connect_gui_fails_no_gui(self):
        adapter = TopSpinAdapter(mode=ControlMode.GUI)
        # GUI automation not available in test environment
        result = adapter._connect_gui()
        assert result is False

    def test_connect_offline_no_examdata(self, tmp_path):
        adapter = TopSpinAdapter(topspin_dir=str(tmp_path), mode=ControlMode.OFFLINE)
        result = adapter.connect()
        assert result is False

    def test_connect_offline_with_examdata(self, tmp_path):
        (tmp_path / "examdata").mkdir()
        adapter = TopSpinAdapter(topspin_dir=str(tmp_path), mode=ControlMode.OFFLINE)
        result = adapter.connect()
        assert result is True
        assert adapter.connected is True

    def test_connect_default_returns_false(self):
        adapter = TopSpinAdapter(mode=ControlMode.OFFLINE)
        # Manually set mode to invalid value to test the default case
        adapter._mode = "invalid"
        result = adapter.connect()
        assert result is False

    def test_acquire_offline_raises(self, tmp_path):
        (tmp_path / "examdata").mkdir()
        adapter = TopSpinAdapter(topspin_dir=str(tmp_path))
        with pytest.raises(RuntimeError, match="offline"):
            adapter.acquire()

    def test_acquire_api_raises(self, tmp_path):
        adapter = TopSpinAdapter(topspin_dir=str(tmp_path), mode=ControlMode.API)
        with pytest.raises(NotImplementedError):
            adapter._acquire_api()

    def test_acquire_gui_raises(self, tmp_path):
        adapter = TopSpinAdapter(topspin_dir=str(tmp_path), mode=ControlMode.GUI)
        with pytest.raises(NotImplementedError):
            adapter._acquire_gui()

    def test_acquire_routes_to_api(self, tmp_path):
        adapter = TopSpinAdapter(topspin_dir=str(tmp_path), mode=ControlMode.API)
        with pytest.raises(NotImplementedError):
            adapter.acquire()

    def test_acquire_routes_to_gui(self, tmp_path):
        adapter = TopSpinAdapter(topspin_dir=str(tmp_path), mode=ControlMode.GUI)
        with pytest.raises(NotImplementedError):
            adapter.acquire()

    def test_list_examdata_empty(self, tmp_path):
        (tmp_path / "examdata").mkdir()
        adapter = TopSpinAdapter(topspin_dir=str(tmp_path))
        assert adapter.list_examdata() == []

    def test_list_examdata_no_dir(self, tmp_path):
        adapter = TopSpinAdapter(topspin_dir=str(tmp_path))
        assert adapter.list_examdata() == []

    def test_list_datasets_delegates(self, tmp_path):
        (tmp_path / "examdata").mkdir()
        adapter = TopSpinAdapter(topspin_dir=str(tmp_path))
        assert adapter.list_datasets() == []

    def test_process_delegates(self, tmp_path):
        adapter = TopSpinAdapter(topspin_dir=str(tmp_path))
        with patch.object(adapter, "process_dataset") as mock:
            mock.return_value = MagicMock()
            adapter.process("path")
            mock.assert_called_once_with("path")

    def test_process_dataset_api_mode(self, tmp_path):
        adapter = TopSpinAdapter(topspin_dir=str(tmp_path), mode=ControlMode.API)
        adapter._connected = True
        adapter._dp = MagicMock()
        mock_spectrum = MagicMock()
        with patch.object(adapter, "_process_via_nmrglue", return_value=mock_spectrum):
            adapter._process_via_api("some_path")
            adapter._dp.getNMRData.assert_called_once_with("some_path")

    def test_process_dataset_gui_mode(self, tmp_path):
        adapter = TopSpinAdapter(topspin_dir=str(tmp_path), mode=ControlMode.GUI)
        adapter._connected = True
        adapter._gui = MagicMock()
        mock_spectrum = MagicMock()
        with patch.object(adapter, "_process_via_nmrglue", return_value=mock_spectrum):
            adapter._process_via_gui("path")
            adapter._gui.open_dataset.assert_called_once_with("path")

    def test_process_dataset_gui_with_callback(self, tmp_path):
        adapter = TopSpinAdapter(topspin_dir=str(tmp_path), mode=ControlMode.GUI)
        adapter._connected = True
        adapter._gui = MagicMock()
        mock_spectrum = MagicMock()
        cb = MagicMock()
        with patch.object(adapter, "_process_via_nmrglue", return_value=mock_spectrum):
            adapter._process_via_gui("path", on_screenshot=cb)
            adapter._gui.process_spectrum.assert_called_once_with(verify=True, on_screenshot=cb)

    def test_mode_from_string(self, tmp_path):
        adapter = TopSpinAdapter(topspin_dir=str(tmp_path), mode="offline")
        assert adapter.mode == ControlMode.OFFLINE


# ===========================================================================
# brain
# ===========================================================================


class TestNMRBrain:
    def test_has_api_key_false(self):
        with patch.dict("os.environ", {}, clear=True):
            assert _has_api_key() is False

    def test_has_api_key_true(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            assert _has_api_key() is True

    def test_simulate_stream(self):
        chunks = list(_simulate_stream("hello world"))
        assert "".join(chunks) == "hello world"

    def test_resolve_compound_name_from_title(self):
        spectrum = MagicMock()
        spectrum.title = "alpha ionone"
        spectrum.sample_name = ""
        assert _resolve_compound_name(spectrum) == "alpha ionone"

    def test_resolve_compound_name_from_sample(self):
        spectrum = MagicMock()
        spectrum.title = ""
        spectrum.sample_name = "strychnine"
        assert _resolve_compound_name(spectrum) == "strychnine"

    def test_resolve_compound_name_empty(self):
        spectrum = MagicMock()
        spectrum.title = ""
        spectrum.sample_name = ""
        assert _resolve_compound_name(spectrum) == ""

    def test_brain_no_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            brain = NMRBrain()
        assert brain.client is None
        assert brain._use_api is False

    def test_interpret_cached(self):
        with patch.dict("os.environ", {}, clear=True):
            brain = NMRBrain()
        spectrum = MagicMock()
        spectrum.title = "alpha ionone"
        spectrum.sample_name = ""
        result = brain.interpret_spectrum(spectrum)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_interpret_cached_stream(self):
        with patch.dict("os.environ", {}, clear=True):
            brain = NMRBrain()
        spectrum = MagicMock()
        spectrum.title = "alpha ionone"
        spectrum.sample_name = ""
        gen = brain.interpret_spectrum(spectrum, stream=True)
        text = "".join(gen)
        assert len(text) > 0

    def test_interpret_no_cache_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            brain = NMRBrain()
        spectrum = MagicMock()
        spectrum.title = "unknown_compound_xyz"
        spectrum.sample_name = ""
        with pytest.raises(RuntimeError, match="No ANTHROPIC_API_KEY"):
            brain.interpret_spectrum(spectrum)

    def test_suggest_next_cached(self):
        with patch.dict("os.environ", {}, clear=True):
            brain = NMRBrain()
        spectrum = MagicMock()
        spectrum.title = "alpha ionone"
        spectrum.sample_name = ""
        result = brain.suggest_next_experiment(spectrum)
        assert isinstance(result, str)

    def test_compare_spectra_no_api_raises(self):
        with patch.dict("os.environ", {}, clear=True):
            brain = NMRBrain()
        s1 = MagicMock()
        s2 = MagicMock()
        with pytest.raises(RuntimeError, match="No ANTHROPIC_API_KEY"):
            brain.compare_spectra(s1, s2)


# ===========================================================================
# demo_cache
# ===========================================================================


class TestDemoCache:
    def test_get_dnmr_analysis(self):
        text = get_dnmr_analysis()
        assert isinstance(text, str)
        assert len(text) > 0

    def test_find_cached_response_exact(self):
        result = find_cached_response("alpha ionone", "interpret")
        assert result is not None

    def test_find_cached_response_substring(self):
        result = find_cached_response("ionone", "interpret")
        assert result is not None

    def test_find_cached_response_not_found(self):
        result = find_cached_response("nonexistent_compound_xyz123", "interpret")
        assert result is None

    def test_find_cached_response_wrong_type(self):
        result = find_cached_response("alpha ionone", "nonexistent_type")
        assert result is None


# ===========================================================================
# gui_automation
# ===========================================================================


class TestTopSpinGUIAutomation:
    def test_init_no_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        assert gui.available is False

    def test_command_mode_available(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        # Should be True on Linux
        assert gui.command_mode_available is True

    def test_detect_topspin_linux(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        mock_result = MagicMock()
        mock_result.stdout = "no topspin here"
        with patch("subprocess.run", return_value=mock_result):
            found = gui._detect_topspin_linux()
        assert found is False

    def test_detect_topspin_linux_found(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        mock_result = MagicMock()
        mock_result.stdout = "0x12345 0 10 20 800 600 host TopSpin 5.0.0"
        with patch("subprocess.run", return_value=mock_result):
            found = gui._detect_topspin_linux()
        assert found is True

    def test_detect_topspin_linux_timeout(self):
        import subprocess

        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("wmctrl", 5)):
            found = gui._detect_topspin_linux()
        assert found is False

    def test_detect_topspin_window_linux(self):
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("platform.system", return_value="Linux"),
        ):
            gui = TopSpinGUIAutomation()
        mock_result = MagicMock()
        mock_result.stdout = "no topspin"
        with (
            patch("platform.system", return_value="Linux"),
            patch("subprocess.run", return_value=mock_result),
        ):
            found = gui.detect_topspin_window()
        assert found is False

    def test_detect_topspin_window_unsupported(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        with patch("platform.system", return_value="Windows"):
            found = gui.detect_topspin_window()
        assert found is False

    def test_take_screenshot_unsupported(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        with patch("platform.system", return_value="Windows"):
            with pytest.raises(RuntimeError, match="not supported"):
                gui.take_screenshot()

    def test_send_to_computer_use_not_available(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        with pytest.raises(RuntimeError, match="not available"):
            gui.send_to_computer_use("click ok")

    def test_type_command_linux(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        with (
            patch("platform.system", return_value="Linux"),
            patch("subprocess.run") as mock_run,
        ):
            gui.type_command("efp")
        assert mock_run.call_count == 2

    def test_get_gui_status(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        status = gui.get_gui_status()
        assert status["available"] is False
        assert "model" in status

    def test_screenshot_linux_scrot(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        with (
            patch("platform.system", return_value="Linux"),
            patch("subprocess.run"),
            patch("pathlib.Path.read_bytes", return_value=b"PNG_DATA"),
            patch("pathlib.Path.unlink"),
        ):
            result = gui._screenshot_linux()
        assert result == b"PNG_DATA"

    def test_screenshot_linux_no_tool(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        with (
            patch("platform.system", return_value="Linux"),
            patch("subprocess.run", side_effect=FileNotFoundError),
            patch("pathlib.Path.unlink"),
        ):
            with pytest.raises(RuntimeError, match="No screenshot tool"):
                gui._screenshot_linux()

    def test_detect_topspin_macos(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        mock_result = MagicMock()
        mock_result.stdout = "TopSpin"
        with patch("subprocess.run", return_value=mock_result):
            found = gui._detect_topspin_macos()
        assert found is True

    def test_detect_topspin_macos_timeout(self):
        import subprocess

        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("osascript", 5)):
            found = gui._detect_topspin_macos()
        assert found is False

    def test_screenshot_macos(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        with (
            patch("subprocess.run"),
            patch("pathlib.Path.read_bytes", return_value=b"PNG"),
            patch("pathlib.Path.unlink"),
        ):
            result = gui._screenshot_macos()
        assert result == b"PNG"

    def test_take_screenshot_linux(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        with (
            patch("platform.system", return_value="Linux"),
            patch.object(gui, "_screenshot_linux", return_value=b"PNG"),
        ):
            result = gui.take_screenshot()
        assert result == b"PNG"

    def test_take_screenshot_macos(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        with (
            patch("platform.system", return_value="Darwin"),
            patch.object(gui, "_screenshot_macos", return_value=b"PNG"),
        ):
            result = gui.take_screenshot()
        assert result == b"PNG"

    def test_type_command_macos(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        with (
            patch("platform.system", return_value="Darwin"),
            patch("subprocess.run") as mock_run,
        ):
            gui.type_command("efp")
        mock_run.assert_called_once()

    def test_detect_topspin_window_macos(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        mock_result = MagicMock()
        mock_result.stdout = "TopSpin"
        with (
            patch("platform.system", return_value="Darwin"),
            patch("subprocess.run", return_value=mock_result),
        ):
            found = gui.detect_topspin_window()
        assert found is True

    def test_open_dataset(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        with patch.object(gui, "type_command") as mock_cmd:
            with patch("time.sleep"):
                gui.open_dataset("/data/test/1")
        mock_cmd.assert_called_once()

    def test_process_spectrum_without_verify(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        with (
            patch.object(gui, "type_command") as mock_cmd,
            patch("time.sleep"),
        ):
            gui.process_spectrum(verify=False)
        assert mock_cmd.call_count == 3

    def test_process_spectrum_with_verify(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        cb = MagicMock()
        with (
            patch.object(gui, "type_command"),
            patch.object(gui, "verify_step", return_value={"screenshot": b"img"}),
            patch("time.sleep"),
        ):
            gui.process_spectrum(verify=True, on_screenshot=cb)
        assert cb.call_count == 3

    def test_verify_step(self):
        with patch.dict("os.environ", {}, clear=True):
            gui = TopSpinGUIAutomation()
        with patch.object(gui, "take_screenshot", return_value=b"PNG"):
            result = gui.verify_step("test_label")
        assert result["label"] == "test_label"
        assert result["screenshot"] == b"PNG"

    def test_send_to_computer_use_with_client(self):
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            with patch("anthropic.Anthropic") as mock_cls:
                mock_client = MagicMock()
                mock_cls.return_value = mock_client
                mock_client.messages.create.return_value = MagicMock(
                    content=[MagicMock(text="click OK button")]
                )
                gui = TopSpinGUIAutomation()
                result = gui.send_to_computer_use("click ok", screenshot=b"PNG")
        assert result["response"] == "click OK button"


# ===========================================================================
# processor  (uncovered paths only)
# ===========================================================================


class TestNMRProcessorCoverage:
    def test_format_peak_list_empty(self):
        p = NMRProcessor()
        assert p.format_peak_list([]) == "No peaks detected."

    def test_format_peak_list(self):
        peaks = [NMRPeak(ppm=7.2, intensity=100.0), NMRPeak(ppm=3.1, intensity=50.0)]
        p = NMRProcessor()
        text = p.format_peak_list(peaks)
        assert "7.200" in text
        assert "3.100" in text

    def test_get_spectrum_summary(self):
        peaks = [NMRPeak(ppm=7.2, intensity=100.0)]
        spectrum = NMRSpectrum(
            data=np.array([1.0]),
            ppm_scale=np.array([7.2]),
            peaks=peaks,
            nucleus="1H",
            solvent="CDCl3",
            frequency_mhz=400.0,
            title="Test",
            sample_name="sample1",
        )
        p = NMRProcessor()
        summary = p.get_spectrum_summary(spectrum)
        assert "400.0 MHz" in summary
        assert "CDCl3" in summary


# ===========================================================================
# visualizer (uncovered paths)
# ===========================================================================


class TestVisualizerCoverage:
    def test_build_title_both(self):
        spectrum = MagicMock()
        spectrum.sample_name = "sample1"
        spectrum.title = "alpha ionone"
        title = _build_title(spectrum)
        assert "sample1" in title
        assert "alpha ionone" in title

    def test_build_title_sample_only(self):
        spectrum = MagicMock()
        spectrum.sample_name = "sample1"
        spectrum.title = ""
        title = _build_title(spectrum)
        assert title == "sample1"

    def test_build_title_empty(self):
        spectrum = MagicMock()
        spectrum.sample_name = ""
        spectrum.title = ""
        title = _build_title(spectrum)
        assert title == "NMR Spectrum"

    def test_build_title_same_name(self):
        spectrum = MagicMock()
        spectrum.sample_name = "sample1"
        spectrum.title = "sample1"
        title = _build_title(spectrum)
        assert title == "sample1"

    def test_plot_spectrum_returns_bytes(self):
        spectrum = NMRSpectrum(
            data=np.sin(np.linspace(0, 10, 100)),
            ppm_scale=np.linspace(0, 10, 100),
            peaks=[NMRPeak(ppm=5.0, intensity=0.8)],
            nucleus="1H",
            solvent="CDCl3",
            frequency_mhz=400.0,
        )
        result = plot_spectrum(spectrum, output_path=None)
        assert isinstance(result, bytes)
        assert result[:4] == b"\x89PNG"

    def test_plot_spectrum_custom_range(self):
        spectrum = NMRSpectrum(
            data=np.sin(np.linspace(0, 10, 100)),
            ppm_scale=np.linspace(0, 10, 100),
            peaks=[],
            nucleus="1H",
            solvent="CDCl3",
            frequency_mhz=400.0,
        )
        result = plot_spectrum(spectrum, output_path=None, ppm_range=(2.0, 8.0))
        assert isinstance(result, bytes)


# ===========================================================================
# library (uncovered path: from_examdata with no examdata dir)
# ===========================================================================


class TestSpectralLibraryCoverage:
    def test_from_examdata_no_dir(self, tmp_path):
        # The from_examdata method uses `from pathlib import Path` locally,
        # then checks `Path("/opt/topspin5.0.0/examdata").exists()`.
        # Since examdata doesn't exist in CI, the method returns empty lib.
        lib = SpectralLibrary.from_examdata()
        # In CI (no TopSpin), library should be empty
        assert isinstance(lib, SpectralLibrary)
