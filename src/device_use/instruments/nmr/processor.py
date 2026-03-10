"""NMR data processing using nmrglue — works offline without TopSpin."""

from dataclasses import dataclass, field
from pathlib import Path

import nmrglue as ng
import numpy as np


@dataclass
class NMRPeak:
    """A single NMR peak with chemical shift and properties."""

    ppm: float
    intensity: float
    width_hz: float = 0.0
    multiplicity: str = ""
    integral: float = 0.0


@dataclass
class NMRSpectrum:
    """Processed NMR spectrum with metadata."""

    data: np.ndarray
    ppm_scale: np.ndarray
    peaks: list[NMRPeak] = field(default_factory=list)
    nucleus: str = "1H"
    solvent: str = ""
    frequency_mhz: float = 0.0
    title: str = ""
    sample_name: str = ""


class NMRProcessor:
    """Process raw NMR FID data into spectra and peak lists.

    Uses nmrglue for all processing — no TopSpin GUI needed.
    """

    def __init__(self, line_broadening: float = 0.3):
        self.line_broadening = line_broadening

    def read_bruker(self, dataset_path: str | Path) -> tuple[dict, np.ndarray]:
        """Read a Bruker NMR dataset (FID + parameters)."""
        path = Path(dataset_path)
        dic, data = ng.bruker.read(str(path))
        return dic, data

    def process_1d(self, dic: dict, fid: np.ndarray, dataset_path: str | Path | None = None) -> NMRSpectrum:
        """Process a 1D FID into a phased spectrum with peak list."""
        # Remove digital filter artifact
        fid = ng.bruker.remove_digital_filter(dic, fid)

        # Zero fill to next power of 2
        td = dic["acqus"]["TD"]
        zf_size = max(65536, 2 ** int(np.ceil(np.log2(td))))
        fid = ng.proc_base.zf_size(fid, zf_size)

        # Apodization (exponential line broadening)
        sf = dic["acqus"]["BF1"]
        lb_rad = self.line_broadening * 2 * np.pi / sf
        fid = ng.proc_base.em(fid, lb=lb_rad)

        # Fourier transform
        spectrum = ng.proc_base.fft(fid)

        # Reverse (Bruker convention)
        spectrum = ng.proc_base.rev(spectrum)

        # Automatic phase correction (suppress scipy optimizer output)
        import io
        import contextlib
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                spectrum = ng.proc_autophase.autops(spectrum, "acme")
        except Exception:
            pass

        # Take real part
        spec_real = spectrum.real

        # Baseline correction (simple polynomial)
        spec_real = ng.proc_bl.baseline_corrector(spec_real, wd=20)

        # Build PPM scale
        udic = ng.bruker.guess_udic(dic, spec_real)
        uc = ng.fileiobase.uc_from_udic(udic)
        ppm = uc.ppm_scale()

        # Read metadata
        solvent = dic["acqus"].get("SOLVENT", "unknown")
        title = ""
        sample_name = ""
        base = Path(dataset_path) if dataset_path else Path(dic.get("_datadir", ""))
        title_path = base / "pdata" / "1" / "title"
        if title_path.exists():
            title = title_path.read_text().strip()
        if base.exists():
            sample_name = base.parent.name

        result = NMRSpectrum(
            data=spec_real,
            ppm_scale=ppm,
            nucleus="1H",
            solvent=solvent,
            frequency_mhz=sf,
            title=title,
            sample_name=sample_name,
        )

        # Pick peaks
        result.peaks = self.pick_peaks(result)

        return result

    def pick_peaks(
        self, spectrum: NMRSpectrum, threshold_fraction: float = 0.02
    ) -> list[NMRPeak]:
        """Pick peaks from a processed spectrum."""
        data = spectrum.data
        ppm = spectrum.ppm_scale

        # Threshold: fraction of max intensity
        threshold = np.max(np.abs(data)) * threshold_fraction

        # Find peaks using nmrglue
        peaks_idx = ng.peakpick.pick(data, pthres=threshold, algorithm="downward")

        peaks = []
        for idx_arr in peaks_idx:
            idx = int(idx_arr[0])
            if 0 <= idx < len(ppm):
                peak = NMRPeak(
                    ppm=float(ppm[idx]),
                    intensity=float(data[idx]),
                )
                # Filter: only keep peaks in reasonable ppm range
                if -1.0 <= peak.ppm <= 15.0:
                    peaks.append(peak)

        # Sort by chemical shift (high to low)
        peaks.sort(key=lambda p: p.ppm, reverse=True)
        return peaks

    def format_peak_list(self, peaks: list[NMRPeak], top_n: int = 20) -> str:
        """Format peak list as human-readable text for LLM analysis."""
        if not peaks:
            return "No peaks detected."

        lines = ["Chemical Shift (ppm) | Relative Intensity"]
        lines.append("-" * 45)

        # Normalize intensities
        max_int = max(p.intensity for p in peaks) if peaks else 1.0
        for peak in peaks[:top_n]:
            rel = peak.intensity / max_int * 100
            lines.append(f"  {peak.ppm:8.3f}           | {rel:6.1f}%")

        return "\n".join(lines)

    def get_spectrum_summary(self, spectrum: NMRSpectrum) -> str:
        """Generate a text summary of the spectrum for LLM context."""
        lines = [
            f"NMR Spectrum Summary",
            f"  Nucleus: {spectrum.nucleus}",
            f"  Frequency: {spectrum.frequency_mhz:.1f} MHz",
            f"  Solvent: {spectrum.solvent}",
            f"  Title: {spectrum.title}",
            f"  Sample: {spectrum.sample_name}",
            f"  Number of peaks: {len(spectrum.peaks)}",
            f"",
            self.format_peak_list(spectrum.peaks),
        ]
        return "\n".join(lines)
