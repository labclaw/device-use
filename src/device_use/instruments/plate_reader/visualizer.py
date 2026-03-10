"""Plate reader visualization — 96-well heatmap plots."""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from device_use.instruments.plate_reader.models import PlateReading


def plot_plate_heatmap(
    reading: "PlateReading",
    output_path: str | None = "output/plate_heatmap.png",
    title: str | None = None,
) -> bytes:
    """Generate a publication-quality heatmap of plate reader data.

    Args:
        reading: PlateReading with well data.
        output_path: Save path, or None for bytes only.
        title: Override plot title.

    Returns:
        PNG image bytes.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    rows = sorted(set(w.row for w in reading.plate.wells))
    cols = sorted(set(w.col for w in reading.plate.wells))

    # Build 2D array
    data = np.zeros((len(rows), len(cols)))
    for i, r in enumerate(rows):
        for j, c in enumerate(cols):
            well = reading.plate.get_well(f"{r}{c}")
            data[i, j] = well.value if well else 0

    fig, ax = plt.subplots(figsize=(10, 5))

    cmap = "YlGn" if reading.mode.value == "fluorescence" else "YlOrRd"
    im = ax.imshow(data, cmap=cmap, aspect="auto", interpolation="nearest")

    # Labels
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels([str(c) for c in cols])
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(rows)
    ax.xaxis.set_ticks_position("top")
    ax.xaxis.set_label_position("top")

    # Annotate each well
    for i in range(len(rows)):
        for j in range(len(cols)):
            val = data[i, j]
            text = f"{val:.2f}" if val < 100 else f"{val:.0f}"
            color = "white" if val > (data.max() * 0.6) else "black"
            ax.text(j, i, text, ha="center", va="center",
                    fontsize=6, color=color)

    # Colorbar
    cbar = plt.colorbar(im, ax=ax, fraction=0.02, pad=0.04)
    unit = "RFU" if reading.mode.value == "fluorescence" else "OD"
    cbar.set_label(unit)

    plot_title = title or f"{reading.protocol} ({reading.wavelength_nm} nm)"
    ax.set_title(plot_title, pad=15, fontsize=12, fontweight="bold")

    plt.tight_layout()

    # Save to bytes
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)
    png_bytes = buf.getvalue()

    # Optionally save to file
    if output_path:
        from pathlib import Path
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(png_bytes)

    return png_bytes
