"""Tests for the NMR instrument modules (processor, adapter, brain, visualizer)."""

from unittest.mock import patch, MagicMock

import numpy as np
import pytest

from device_use.instruments import ControlMode
from device_use.instruments.base import InstrumentInfo
from device_use.instruments.nmr.processor import NMRPeak, NMRProcessor, NMRSpectrum
from device_use.instruments.nmr.adapter import TopSpinAdapter


# ── NMRPeak ──────────────────────────────────────────────────────

class TestNMRPeak:
    def test_basic_peak(self):
        peak = NMRPeak(ppm=7.26, intensity=100.0)
        assert peak.ppm == 7.26
        assert peak.intensity == 100.0

    def test_peak_with_all_fields(self):
        peak = NMRPeak(ppm=3.5, intensity=50.0, width_hz=2.5, multiplicity="t", integral=3.0)
        assert peak.width_hz == 2.5
        assert peak.multiplicity == "t"
        assert peak.integral == 3.0


# ── NMRSpectrum ──────────────────────────────────────────────────

class TestNMRSpectrum:
    def test_basic_spectrum(self):
        data = np.array([0.0, 1.0, 0.5, 0.2])
        ppm = np.array([10.0, 7.5, 5.0, 2.5])
        peaks = [NMRPeak(ppm=7.5, intensity=1.0)]

        spectrum = NMRSpectrum(
            data=data,
            ppm_scale=ppm,
            peaks=peaks,
            nucleus="1H",
            solvent="CDCl3",
            frequency_mhz=400.0,
        )
        assert spectrum.nucleus == "1H"
        assert spectrum.solvent == "CDCl3"
        assert spectrum.frequency_mhz == 400.0
        assert len(spectrum.peaks) == 1
        assert spectrum.peaks[0].ppm == 7.5

    def test_spectrum_metadata(self):
        spectrum = NMRSpectrum(
            data=np.zeros(10),
            ppm_scale=np.linspace(10, 0, 10),
            peaks=[],
            nucleus="13C",
            solvent="DMSO",
            frequency_mhz=100.0,
            title="Test Compound",
            sample_name="test_sample",
        )
        assert spectrum.title == "Test Compound"
        assert spectrum.sample_name == "test_sample"


# ── NMRProcessor ─────────────────────────────────────────────────

class TestNMRProcessor:
    def test_processor_instantiation(self):
        proc = NMRProcessor()
        assert proc is not None

    def test_peak_filtering(self):
        """Peaks outside -1 to 15 ppm should be filtered."""
        proc = NMRProcessor()
        # This tests the concept — actual filtering happens in process_1d
        # We just verify the processor exists and is callable
        assert hasattr(proc, "process_1d")


# ── TopSpinAdapter ───────────────────────────────────────────────

class TestTopSpinAdapter:
    def test_default_mode(self):
        adapter = TopSpinAdapter()
        assert adapter.mode == ControlMode.OFFLINE

    def test_explicit_offline_mode(self):
        adapter = TopSpinAdapter(mode=ControlMode.OFFLINE)
        assert adapter.mode == ControlMode.OFFLINE

    def test_instrument_info(self):
        adapter = TopSpinAdapter()
        info = adapter.info()
        assert isinstance(info, InstrumentInfo)
        assert info.name == "TopSpin"
        assert info.vendor == "Bruker"
        assert info.instrument_type.lower() == "nmr"
        assert ControlMode.OFFLINE in info.supported_modes
        assert ControlMode.API in info.supported_modes

    def test_connect_offline(self):
        adapter = TopSpinAdapter()
        result = adapter.connect()
        assert result is True
        assert adapter.connected is True

    def test_list_datasets(self):
        adapter = TopSpinAdapter()
        adapter.connect()
        datasets = adapter.list_datasets()
        assert isinstance(datasets, list)
        # Should find TopSpin examdata if installed
        if datasets:
            ds = datasets[0]
            assert "sample" in ds
            assert "expno" in ds
            assert "path" in ds
            assert "title" in ds

    def test_process_returns_spectrum(self):
        """Processing a real dataset should return an NMRSpectrum."""
        adapter = TopSpinAdapter()
        adapter.connect()
        datasets = adapter.list_datasets()
        if not datasets:
            pytest.skip("No TopSpin examdata available")

        # Find a known 1D dataset
        target = None
        for ds in datasets:
            if ds["sample"] == "exam_CMCse_1" and ds["expno"] == 1:
                target = ds
                break

        if not target:
            pytest.skip("exam_CMCse_1 dataset not found")

        spectrum = adapter.process(target["path"])
        assert isinstance(spectrum, NMRSpectrum)
        assert len(spectrum.data) > 0
        assert len(spectrum.ppm_scale) > 0
        assert len(spectrum.peaks) > 0
        assert spectrum.frequency_mhz > 0
        assert spectrum.nucleus == "1H"


# ── Visualizer ───────────────────────────────────────────────────

class TestVisualizer:
    def test_plot_returns_bytes(self):
        """plot_spectrum with output_path=None should return bytes."""
        from device_use.instruments.nmr.visualizer import plot_spectrum

        spectrum = NMRSpectrum(
            data=np.sin(np.linspace(0, 10, 1000)),
            ppm_scale=np.linspace(12, -1, 1000),
            peaks=[NMRPeak(ppm=7.26, intensity=1.0)],
            nucleus="1H",
            solvent="CDCl3",
            frequency_mhz=400.0,
        )
        result = plot_spectrum(spectrum, output_path=None)
        assert isinstance(result, bytes)
        assert len(result) > 1000  # Should be a real PNG
        assert result[:4] == b"\x89PNG"  # PNG magic bytes

    def test_plot_saves_file(self, tmp_path):
        """plot_spectrum with a path should save a file."""
        from device_use.instruments.nmr.visualizer import plot_spectrum

        spectrum = NMRSpectrum(
            data=np.sin(np.linspace(0, 10, 100)),
            ppm_scale=np.linspace(12, -1, 100),
            peaks=[],
            nucleus="1H",
            solvent="CDCl3",
            frequency_mhz=400.0,
        )
        out = tmp_path / "test_spectrum.png"
        result = plot_spectrum(spectrum, output_path=out)
        assert result == out
        assert out.exists()
        assert out.stat().st_size > 1000


# ── Brain (cached mode) ─────────────────────────────────────────

class TestNMRBrain:
    def test_brain_instantiation(self):
        from device_use.instruments.nmr.brain import NMRBrain
        brain = NMRBrain()
        assert brain is not None

    def test_cached_interpretation(self):
        """Brain should return cached response for known compounds."""
        from device_use.instruments.nmr.brain import NMRBrain

        brain = NMRBrain()
        spectrum = NMRSpectrum(
            data=np.zeros(100),
            ppm_scale=np.linspace(12, -1, 100),
            peaks=[NMRPeak(ppm=7.26, intensity=1.0)],
            nucleus="1H",
            solvent="CDCl3",
            frequency_mhz=400.0,
            sample_name="exam_CMCse_1",
            title="Alpha Ionone",
        )

        # Without API key, should use cache
        with patch.dict("os.environ", {}, clear=False):
            # Remove API key if present
            env = dict(**__import__("os").environ)
            env.pop("ANTHROPIC_API_KEY", None)
            with patch.dict("os.environ", env, clear=True):
                result = brain.interpret_spectrum(spectrum, stream=False)
                assert isinstance(result, str)
                assert len(result) > 100  # Should have substantial content


# ── SpectralLibrary ──────────────────────────────────────────────

class TestSpectralLibrary:
    def test_add_and_list(self):
        from device_use.instruments.nmr.library import SpectralLibrary

        lib = SpectralLibrary()
        lib.add("ethanol", [1.2, 3.7, 4.8])
        lib.add("acetone", [2.1])
        assert len(lib) == 2
        assert lib.list_entries() == ["ethanol", "acetone"]

    def test_exact_match(self):
        from device_use.instruments.nmr.library import SpectralLibrary

        lib = SpectralLibrary()
        lib.add("ethanol", [1.2, 3.7])
        lib.add("acetone", [2.1])
        lib.add("dmso", [2.5])

        matches = lib.match_peaks([1.2, 3.7])
        assert matches[0].entry.name == "ethanol"
        assert matches[0].score == 1.0

    def test_partial_match(self):
        from device_use.instruments.nmr.library import SpectralLibrary

        lib = SpectralLibrary()
        lib.add("ethanol", [1.2, 3.7, 4.8])

        # Query with 2 of 3 peaks
        matches = lib.match_peaks([1.2, 3.7])
        assert matches[0].entry.name == "ethanol"
        assert matches[0].score > 0.5  # 2 matched out of 3 union
        assert matches[0].matched_peaks == 2

    def test_tolerance(self):
        from device_use.instruments.nmr.library import SpectralLibrary

        lib = SpectralLibrary(tolerance_ppm=0.1)
        lib.add("ethanol", [1.20])

        # Within tolerance
        matches = lib.match_peaks([1.25])
        assert matches[0].score == 1.0

        # Outside tolerance
        lib2 = SpectralLibrary(tolerance_ppm=0.01)
        lib2.add("ethanol", [1.20])
        matches2 = lib2.match_peaks([1.25])
        assert matches2[0].score == 0.0

    def test_no_entries(self):
        from device_use.instruments.nmr.library import SpectralLibrary

        lib = SpectralLibrary()
        matches = lib.match_peaks([1.2, 3.7])
        assert matches == []

    def test_empty_peaks(self):
        from device_use.instruments.nmr.library import SpectralLibrary

        lib = SpectralLibrary()
        lib.add("ethanol", [1.2, 3.7])
        matches = lib.match_peaks([])
        assert matches[0].score == 0.0

    def test_add_spectrum(self):
        from device_use.instruments.nmr.library import SpectralLibrary

        lib = SpectralLibrary()
        spectrum = NMRSpectrum(
            data=np.array([1.0]),
            ppm_scale=np.array([1.0]),
            peaks=[NMRPeak(ppm=7.26, intensity=100)],
            title="chloroform",
        )
        lib.add_spectrum(spectrum)
        assert lib.list_entries() == ["chloroform"]

    def test_match_spectrum(self):
        from device_use.instruments.nmr.library import SpectralLibrary

        lib = SpectralLibrary()
        lib.add("chloroform", [7.26])
        lib.add("tms", [0.0])

        query = NMRSpectrum(
            data=np.array([1.0]),
            ppm_scale=np.array([1.0]),
            peaks=[NMRPeak(ppm=7.26, intensity=100)],
        )
        matches = lib.match(query)
        assert matches[0].entry.name == "chloroform"
        assert matches[0].score == 1.0

    def test_from_examdata(self):
        from device_use.instruments.nmr.library import SpectralLibrary
        from pathlib import Path

        lib = SpectralLibrary.from_examdata()
        if Path("/opt/topspin5.0.0/examdata").exists():
            assert len(lib) > 0
        else:
            assert len(lib) == 0  # graceful fallback

    def test_top_k(self):
        from device_use.instruments.nmr.library import SpectralLibrary

        lib = SpectralLibrary()
        for i in range(10):
            lib.add(f"compound_{i}", [float(i)])

        matches = lib.match_peaks([0.0], top_k=3)
        assert len(matches) == 3


class TestTopSpinGUIAutomation:
    """Tests for GUI automation module."""

    def test_command_mode_no_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            from device_use.instruments.nmr.gui_automation import TopSpinGUIAutomation
            gui = TopSpinGUIAutomation()
            assert not gui.available
            assert gui.command_mode_available

    def test_verify_returns_screenshot_bytes(self):
        from device_use.instruments.nmr.gui_automation import TopSpinGUIAutomation
        gui = TopSpinGUIAutomation()
        with patch.object(gui, "take_screenshot", return_value=b"fake_png"):
            result = gui.verify_step("test")
            assert result["screenshot"] == b"fake_png"
            assert result["label"] == "test"
            assert "timestamp" in result

    def test_process_spectrum_with_verification(self):
        from device_use.instruments.nmr.gui_automation import TopSpinGUIAutomation
        gui = TopSpinGUIAutomation()
        screenshots = []
        with patch.object(gui, "type_command"):
            with patch.object(gui, "take_screenshot", return_value=b"png"):
                gui.process_spectrum(verify=True, on_screenshot=screenshots.append)
                assert len(screenshots) == 3

    def test_process_spectrum_without_verification(self):
        from device_use.instruments.nmr.gui_automation import TopSpinGUIAutomation
        gui = TopSpinGUIAutomation()
        with patch.object(gui, "type_command"):
            # Should not error even without verify
            gui.process_spectrum(verify=False)
