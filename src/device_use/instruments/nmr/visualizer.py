"""NMR spectrum visualization — publication-quality plots."""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from device_use.instruments.nmr.processor import NMRSpectrum


def plot_spectrum(
    spectrum: NMRSpectrum,
    output_path: str | Path | None = "spectrum.png",
    title: str | None = None,
    annotate_peaks: bool = True,
    ppm_range: tuple[float, float] | None = None,
) -> Path | bytes:
    """Generate a publication-quality NMR spectrum plot.

    Args:
        output_path: File path to save, or None to return PNG bytes.

    Returns the path to the saved image, or bytes if output_path is None.
    """
    return_bytes = output_path is None
    if not return_bytes:
        output_path = Path(output_path)

    fig, ax = plt.subplots(1, 1, figsize=(14, 5))

    ppm = spectrum.ppm_scale
    data = spectrum.data

    # Filter to ppm range
    if ppm_range:
        mask = (ppm >= ppm_range[0]) & (ppm <= ppm_range[1])
    else:
        mask = (ppm >= -0.5) & (ppm <= 12.0)
    ppm_plot = ppm[mask]
    data_plot = data[mask]

    # Normalize
    data_max = np.max(np.abs(data_plot)) if len(data_plot) > 0 else 1.0
    data_norm = data_plot / data_max

    # Plot spectrum
    ax.plot(ppm_plot, data_norm, color="#1a1a2e", linewidth=0.6)
    ax.fill_between(ppm_plot, 0, data_norm, alpha=0.08, color="#0066cc")

    # Annotate peaks
    if annotate_peaks and spectrum.peaks:
        peak_max = max(p.intensity for p in spectrum.peaks) if spectrum.peaks else 1.0
        for peak in spectrum.peaks:
            rel = peak.intensity / peak_max
            if rel > 0.01 and ppm_plot.min() <= peak.ppm <= ppm_plot.max():
                y_pos = peak.intensity / data_max
                ax.annotate(
                    f"{peak.ppm:.2f}",
                    xy=(peak.ppm, y_pos),
                    xytext=(0, 12),
                    textcoords="offset points",
                    fontsize=7,
                    ha="center",
                    color="#cc3300",
                    fontweight="bold",
                )
                ax.plot(peak.ppm, y_pos, "v", color="#cc3300", markersize=4)

    # Style — NMR convention: high ppm on left
    ax.invert_xaxis()
    ax.set_xlabel("Chemical Shift (ppm)", fontsize=12, fontweight="bold")
    ax.set_ylabel("Relative Intensity", fontsize=12)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.set_yticks([])

    # Title
    plot_title = title or _build_title(spectrum)
    ax.set_title(plot_title, fontsize=14, fontweight="bold", pad=15)

    # Subtitle with metadata
    subtitle = f"{spectrum.frequency_mhz:.0f} MHz | {spectrum.nucleus} | {spectrum.solvent}"
    ax.text(
        0.5, 1.02, subtitle,
        transform=ax.transAxes, ha="center", fontsize=10, color="#666666",
    )

    # Branding
    ax.text(
        0.99, 0.97, "Device-Use | AI Scientist",
        transform=ax.transAxes, ha="right", va="top",
        fontsize=8, color="#999999", style="italic",
    )

    plt.tight_layout()
    if return_bytes:
        import io
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=200, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        buf.seek(0)
        return buf.read()
    else:
        fig.savefig(str(output_path), dpi=200, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        return output_path


def _build_title(spectrum: NMRSpectrum) -> str:
    parts = []
    if spectrum.sample_name:
        parts.append(spectrum.sample_name)
    if spectrum.title:
        # Use first line of title
        first_line = spectrum.title.split("\n")[0].strip()
        if first_line and first_line != spectrum.sample_name:
            parts.append(first_line)
    return " — ".join(parts) if parts else "NMR Spectrum"
