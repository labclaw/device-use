"""Spectral Library — match unknown NMR spectra against known compounds.

A lightweight fingerprint-matching system that compares peak positions
to identify compounds without requiring AI.  Useful for QC, batch
screening, and building reference databases.

Usage:
    from device_use.instruments.nmr.library import SpectralLibrary

    lib = SpectralLibrary.from_examdata()  # load TopSpin example data
    matches = lib.match(unknown_spectrum, top_k=3)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from device_use.instruments.nmr.processor import NMRSpectrum

logger = logging.getLogger(__name__)


@dataclass
class LibraryEntry:
    """A reference compound in the spectral library."""

    name: str
    peaks: list[float]  # sorted ppm positions
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class MatchResult:
    """Result of matching a spectrum against the library."""

    entry: LibraryEntry
    score: float  # 0.0 to 1.0 (Jaccard similarity)
    matched_peaks: int
    total_peaks: int


class SpectralLibrary:
    """In-memory spectral library with peak-fingerprint matching.

    Each entry is a list of peak positions (ppm). Matching uses Jaccard
    similarity with a configurable tolerance window.
    """

    def __init__(self, tolerance_ppm: float = 0.05) -> None:
        self.tolerance_ppm = tolerance_ppm
        self._entries: list[LibraryEntry] = []

    def add(self, name: str, peaks: list[float], **metadata: Any) -> None:
        """Add a compound to the library."""
        self._entries.append(
            LibraryEntry(
                name=name,
                peaks=sorted(peaks),
                metadata=metadata,
            )
        )

    def add_spectrum(self, spectrum: NMRSpectrum, name: str = "", **metadata: Any) -> None:
        """Add a processed NMR spectrum to the library."""
        entry_name = name or spectrum.title or spectrum.sample_name or "unknown"
        peaks = [p.ppm for p in spectrum.peaks]
        self.add(entry_name, peaks, **metadata)

    def match(self, spectrum: NMRSpectrum, top_k: int = 5) -> list[MatchResult]:
        """Match a spectrum against all library entries.

        Returns top_k matches sorted by Jaccard similarity score.
        """
        query_peaks = [p.ppm for p in spectrum.peaks]
        return self.match_peaks(query_peaks, top_k=top_k)

    def match_peaks(self, query_peaks: list[float], top_k: int = 5) -> list[MatchResult]:
        """Match a list of peak positions against the library."""
        results = []
        for entry in self._entries:
            score, matched = self._jaccard(query_peaks, entry.peaks)
            results.append(
                MatchResult(
                    entry=entry,
                    score=score,
                    matched_peaks=matched,
                    total_peaks=len(set(query_peaks) | set(entry.peaks)),
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def _jaccard(self, peaks_a: list[float], peaks_b: list[float]) -> tuple[float, int]:
        """Compute Jaccard similarity between two peak lists.

        Two peaks are considered matching if they're within tolerance_ppm
        of each other. Returns (score, num_matched).
        """
        if not peaks_a and not peaks_b:
            return 1.0, 0
        if not peaks_a or not peaks_b:
            return 0.0, 0

        matched = 0
        used_b = set()
        for pa in peaks_a:
            for j, pb in enumerate(peaks_b):
                if j not in used_b and abs(pa - pb) <= self.tolerance_ppm:
                    matched += 1
                    used_b.add(j)
                    break

        union = len(peaks_a) + len(peaks_b) - matched
        score = matched / union if union > 0 else 0.0
        return score, matched

    def __len__(self) -> int:
        return len(self._entries)

    def list_entries(self) -> list[str]:
        """List all compound names in the library."""
        return [e.name for e in self._entries]

    @classmethod
    def from_examdata(cls, tolerance_ppm: float = 0.05) -> SpectralLibrary:
        """Build a library from TopSpin example data.

        Processes all available datasets and adds them as reference entries.
        """
        from device_use.instruments.nmr.processor import NMRProcessor

        lib = cls(tolerance_ppm=tolerance_ppm)
        processor = NMRProcessor()

        # Find available datasets
        from pathlib import Path

        examdata = Path("/opt/topspin5.0.0/examdata")
        if not examdata.exists():
            logger.warning("TopSpin examdata not found at %s", examdata)
            return lib

        for sample_dir in sorted(examdata.iterdir()):
            if not sample_dir.is_dir() or sample_dir.name.startswith("."):
                continue

            # Look for experiment directories with fid files
            for expno_dir in sorted(sample_dir.iterdir()):
                if not expno_dir.is_dir():
                    continue
                fid_path = expno_dir / "fid"
                if not fid_path.exists():
                    continue

                try:
                    dic, fid = processor.read_bruker(str(expno_dir))
                    spectrum = processor.process_1d(dic, fid, dataset_path=str(expno_dir))
                    if spectrum.peaks:
                        lib.add_spectrum(
                            spectrum,
                            name=spectrum.title or sample_dir.name,
                            sample=sample_dir.name,
                            expno=expno_dir.name,
                            path=str(expno_dir),
                        )
                except Exception as exc:
                    logger.debug("Skipping %s: %s", expno_dir, exc)

        logger.info("Loaded %d entries from examdata", len(lib))
        return lib
