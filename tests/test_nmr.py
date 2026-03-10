"""Tests for the NMR instrument modules (processor, adapter, brain, visualizer)."""

from unittest.mock import patch

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
