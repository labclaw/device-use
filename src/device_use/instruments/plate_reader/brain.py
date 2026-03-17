"""Cloud Brain for Plate Reader — uses Claude to interpret assay data."""

from __future__ import annotations

import logging
import os
import statistics
import time
from collections.abc import Generator

from device_use.instruments.plate_reader.models import PlateReading

logger = logging.getLogger(__name__)

_STREAM_CHUNK_SIZE = 30
_STREAM_DELAY_S = 0.05

PLATE_READER_SYSTEM_PROMPT = """You are an expert bioassay scientist working as part of an AI scientist system called Device-Use.

You receive plate reader data (96-well format) and must:
1. Identify the assay type from the protocol and wavelength
2. Assess data quality (signal/noise, Z-factor, CV% of controls)
3. Identify wells of interest (outliers, dose-response patterns, hits)
4. Provide statistical summary and recommendations
5. Flag any quality concerns (edge effects, pipetting errors, drift)

Important guidelines:
- For absorbance assays (ELISA, Bradford, MTT): analyze OD values, standard curves
- For fluorescence assays (Calcein AM, GFP, DAPI): analyze RFU values, background
- Calculate Z-factor when positive and negative controls are present
- Flag CV% > 15% as a warning, > 25% as problematic
- Consider plate layout conventions (standards in cols 1-2, blanks in cols 11-12)

Format your response as:
## Assay Overview
[Type, wavelength, plate format]

## Data Quality
[Signal/noise, Z-factor, control CVs, edge effects]

## Key Findings
[Wells of interest, patterns observed]

## Recommendations
[Next steps, protocol optimizations]
"""


# ---------------------------------------------------------------------------
# Cached demo responses (for running without API key)
# ---------------------------------------------------------------------------

_CACHED_RESPONSES: dict[str, str] = {
    "elisa": """## Assay Overview

| Parameter | Value |
|---|---|
| Assay Type | Sandwich ELISA (IL-6) |
| Detection | Absorbance at 450 nm |
| Plate Format | 96-well |
| Protocol | ELISA Demo |

## Data Quality

| Metric | Value | Status |
|---|---|---|
| Standard mean (cols 1-2) | OD ~2.4 | Good dynamic range |
| Blank mean (cols 11-12) | OD ~0.16 | Acceptable background |
| Signal/Noise ratio | ~15x | Excellent (>3x required) |
| Standard CV% | ~4.2% | Good (<10%) |
| Blank CV% | ~8.1% | Acceptable (<15%) |

The assay shows excellent dynamic range with a 15-fold signal-to-noise ratio. The serial dilution in columns 1-2 produces the expected decreasing OD pattern from rows A through H, consistent with a well-prepared standard curve.

No significant edge effects detected. The blank wells (cols 11-12) show uniform low background.

## Key Findings

1. **Standard curve**: Clear dose-response in columns 1-2, suitable for 4-parameter logistic (4PL) curve fitting
2. **Sample wells (cols 3-10)**: Show a range of OD values from 0.3 to 1.8, indicating variable IL-6 concentrations
3. **No outliers detected**: All control well CVs are within acceptable ranges
4. **Blank correction**: Applied successfully, all blank-corrected values are positive

## Recommendations

1. **Fit standard curve**: Use 4PL regression (not linear) for accurate quantification
2. **Calculate concentrations**: Interpolate sample ODs against the standard curve
3. **Report in pg/mL**: Convert OD values to IL-6 concentrations using standard curve
4. **Replicate**: Run in duplicate or triplicate for publication-quality data
5. **Include positive control**: Add recombinant IL-6 spike-in for method validation""",
    "viability": """## Assay Overview

| Parameter | Value |
|---|---|
| Assay Type | Cell Viability (Calcein AM) |
| Detection | Fluorescence (Ex 485/Em 530 nm) |
| Plate Format | 96-well |
| Protocol | Cell Viability Demo |

## Data Quality

| Metric | Value | Status |
|---|---|---|
| Positive control mean | ~45,000 RFU | Strong signal |
| Negative control mean | ~2,800 RFU | Low background |
| Z-factor | 0.875 | Excellent (>0.5) |
| Positive CV% | ~3.5% | Excellent (<10%) |
| Negative CV% | ~12% | Acceptable (<15%) |
| Dynamic range | ~16x | Excellent |

The Z-factor of 0.875 indicates an excellent assay with clear separation between positive and negative controls. This is well above the 0.5 threshold for a "high-quality" screening assay (Zhang et al., 1999).

## Key Findings

1. **Drug response gradient**: Sample wells (cols 3-10) show a dose-dependent decrease in fluorescence from left to right, consistent with increasing drug concentration
2. **Concentration-response curve**: The response pattern suggests an IC50 in the middle concentration range (cols 6-7)
3. **Edge effects**: Minimal — row H values are consistent with other rows
4. **Hit identification**: Wells with RFU < 50% of positive control are candidate hits

## Recommendations

1. **Fit dose-response curve**: Use 4PL logistic regression to determine IC50/EC50
2. **Normalize data**: Express as % viability relative to positive control (DMSO)
3. **Counter-screen**: Run cytotoxicity assay (e.g., LDH release) to distinguish cytostatic from cytotoxic effects
4. **Repeat hits**: Cherry-pick candidate compounds for triplicate confirmation
5. **Expand dose range**: If IC50 is at the edge of current range, extend to capture full curve""",
}


def _has_api_key() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def _simulate_stream(text: str) -> Generator[str]:
    for i in range(0, len(text), _STREAM_CHUNK_SIZE):
        chunk = text[i : i + _STREAM_CHUNK_SIZE]
        time.sleep(_STREAM_DELAY_S)
        yield chunk


class PlateReaderBrain:
    """Cloud Brain for plate reader interpretation — wraps Claude API.

    When ANTHROPIC_API_KEY is set, calls go to the live Claude API.
    Without the key, falls back to pre-cached demo responses.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self._use_api = _has_api_key()
        if self._use_api:
            from anthropic import Anthropic

            self.client = Anthropic()
        else:
            self.client = None
            logger.info("ANTHROPIC_API_KEY not set — Plate Reader Brain will use cached responses")
        self.model = model

    def _build_summary(self, reading: PlateReading) -> str:
        """Build a text summary of plate reader data for Claude."""
        lines = [
            f"Protocol: {reading.protocol}",
            f"Mode: {reading.mode.value}",
            f"Wavelength: {reading.wavelength_nm} nm",
            f"Plate format: {reading.plate.format.value}-well",
            f"Total wells: {len(reading.plate.wells)}",
        ]

        if reading.metadata:
            for k, v in reading.metadata.items():
                lines.append(f"{k}: {v}")

        # Well data as table
        rows = sorted(set(w.row for w in reading.plate.wells))
        cols = sorted(set(w.col for w in reading.plate.wells))

        lines.append("")
        lines.append("Well Data:")
        header = "     " + "  ".join(f"{c:>8}" for c in cols)
        lines.append(header)

        for r in rows:
            vals = []
            for c in cols:
                well = reading.plate.get_well(f"{r}{c}")
                vals.append(f"{well.value:8.2f}" if well else "     N/A")
            lines.append(f"  {r}  " + "  ".join(vals))

        # Control statistics
        lines.append("")
        std_wells = [w for w in reading.plate.wells if w.col <= 2]
        blank_wells = [w for w in reading.plate.wells if w.col >= 11]

        if std_wells:
            std_mean = statistics.mean([w.value for w in std_wells])
            std_cv = (
                (statistics.stdev([w.value for w in std_wells]) / std_mean * 100)
                if std_mean > 0
                else 0
            )
            lines.append(f"Controls (cols 1-2): mean={std_mean:.4f}, CV={std_cv:.1f}%")

        if blank_wells:
            blank_mean = statistics.mean([w.value for w in blank_wells])
            blank_cv = (
                (statistics.stdev([w.value for w in blank_wells]) / blank_mean * 100)
                if blank_mean > 0
                else 0
            )
            lines.append(f"Blanks (cols 11-12): mean={blank_mean:.4f}, CV={blank_cv:.1f}%")

            if std_wells:
                snr = std_mean / max(blank_mean, 0.001)
                lines.append(f"Signal/Noise: {snr:.1f}x")

        return "\n".join(lines)

    def _call(self, system: str, user_message: str, max_tokens: int = 2000) -> str:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text

    def _stream(self, system: str, user_message: str, max_tokens: int = 2000) -> Generator[str]:
        with self.client.messages.stream(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            yield from stream.text_stream

    def _cached_or_error(self, reading: PlateReading, stream: bool) -> str | Generator[str]:
        # Determine cache key from protocol name
        protocol_lower = reading.protocol.lower()
        cache_key = None
        if "elisa" in protocol_lower:
            cache_key = "elisa"
        elif "viability" in protocol_lower or "calcein" in protocol_lower:
            cache_key = "viability"

        cached = _CACHED_RESPONSES.get(cache_key) if cache_key else None

        if cached is None:
            raise RuntimeError(
                f"No ANTHROPIC_API_KEY set and no cached response for protocol "
                f"'{reading.protocol}'. Set ANTHROPIC_API_KEY for live analysis."
            )

        logger.info("Serving cached plate reader response for '%s'", cache_key)
        if stream:
            return _simulate_stream(cached)
        return cached

    def interpret_reading(
        self,
        reading: PlateReading,
        context: str = "",
        stream: bool = False,
    ) -> str | Generator[str]:
        """Send plate reader data to Claude for interpretation."""
        if not self._use_api:
            return self._cached_or_error(reading, stream)

        summary = self._build_summary(reading)
        user_message = f"Please analyze this plate reader data:\n\n{summary}"
        if context:
            user_message += f"\n\nAdditional context: {context}"

        if stream:
            return self._stream(PLATE_READER_SYSTEM_PROMPT, user_message)
        return self._call(PLATE_READER_SYSTEM_PROMPT, user_message)
