"""Tests for the AI Scientist Closed-Loop Demo (demos/17_ai_scientist_loop.py)."""

from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "demos"))

from device_use.instruments.nmr.processor import NMRPeak, NMRSpectrum

_demo = import_module("17_ai_scientist_loop")
Hypothesis = _demo.Hypothesis
Iteration = _demo.Iteration
AuditTrail = _demo.AuditTrail
parse_hypothesis = _demo.parse_hypothesis
calculate_peak_coverage = _demo.calculate_peak_coverage
calculate_grounding_score = _demo.calculate_grounding_score
build_constraints = _demo.build_constraints
generate_report = _demo.generate_report

# ── Shared test data ────────────────────────────────────────────

SAMPLE_AI_RESPONSE = """\
## Peak Analysis

| Chemical Shift (ppm) | Assignment | Reasoning |
|---|---|---|
| 7.29 | Residual CHCl3 (solvent) | Characteristic CDCl3 residual solvent peak |
| 6.62 | H-4 (=CH-C=O) | Downfield vinyl proton conjugated with carbonyl |
| 6.05 | H-3 (=CH-) | Second vinyl proton |
| 5.49 | H-2 (ring =CH-) | Trisubstituted olefinic proton |
| 2.23 | H-6ax/H-6eq | Alpha to carbonyl |
| 0.83 | Gem-dimethyl | Two equivalent methyl groups |

## Proposed Structure

**Alpha-Ionone** (trans-alpha-Ionone)
- IUPAC: (E)-4-(2,6,6-trimethylcyclohex-2-en-1-yl)but-3-en-2-one
- Molecular formula: C13H20O

## Confidence

**High** — The pattern is diagnostic for alpha-ionone.

## Recommended Next Steps

1. **13C{1H} NMR**
"""

_PEAKS = [
    NMRPeak(ppm=7.29, intensity=100.0), NMRPeak(ppm=6.62, intensity=80.0),
    NMRPeak(ppm=6.05, intensity=75.0),  NMRPeak(ppm=5.49, intensity=50.0),
    NMRPeak(ppm=2.23, intensity=90.0),  NMRPeak(ppm=2.02, intensity=85.0),
    NMRPeak(ppm=1.54, intensity=60.0),  NMRPeak(ppm=0.83, intensity=95.0),
]


@pytest.fixture
def sample_spectrum():
    return NMRSpectrum(
        data=np.zeros(1024), ppm_scale=np.linspace(12, 0, 1024), peaks=list(_PEAKS),
        nucleus="1H", solvent="CDCl3", frequency_mhz=400.0,
        title="Alpha Ionone", sample_name="exam_CMCse_1",
    )


@pytest.fixture
def sample_hypothesis():
    return Hypothesis(
        compound_name="Alpha-Ionone", confidence="High",
        raw_analysis=SAMPLE_AI_RESPONSE,
        peak_assignments=["7.29", "6.62", "6.05", "5.49", "2.23", "0.83"],
    )


def _make_iteration(hyp, *, score=0.85, formula=True, lib=0.75, pubchem=None):
    return Iteration(
        round=1, hypothesis=hyp, grounding_score=score,
        formula_match=formula,
        pubchem_data=pubchem or {"CID": 5282108, "MolecularFormula": "C13H20O"},
        library_score=lib, constraints=[],
    )


@pytest.fixture
def sample_iteration(sample_hypothesis):
    return _make_iteration(sample_hypothesis)


@pytest.fixture
def sample_audit_trail(sample_iteration, sample_hypothesis):
    return AuditTrail(
        question="What compound is in exam_CMCse_1?", dataset="exam_CMCse_1",
        formula="C13H20O", iterations=[sample_iteration], accepted=True,
        final_hypothesis=sample_hypothesis, total_time=4.2,
    )


# ── parse_hypothesis ────────────────────────────────────────────

class TestParseHypothesis:
    def test_extracts_compound_name(self):
        assert "ionone" in parse_hypothesis(SAMPLE_AI_RESPONSE).compound_name.lower()

    @pytest.mark.parametrize("level", ["High", "Medium", "Low"])
    def test_extracts_confidence(self, level):
        resp = SAMPLE_AI_RESPONSE.replace("**High**", f"**{level}**")
        assert parse_hypothesis(resp).confidence == level

    def test_extracts_peak_assignments(self):
        hyp = parse_hypothesis(SAMPLE_AI_RESPONSE)
        assert len(hyp.peak_assignments) > 0
        assert any("7.29" in a for a in hyp.peak_assignments)

    def test_stores_raw_analysis(self):
        hyp = parse_hypothesis(SAMPLE_AI_RESPONSE)
        assert "Peak Analysis" in hyp.raw_analysis
        assert "Proposed Structure" in hyp.raw_analysis

    def test_empty_response_returns_defaults(self):
        hyp = parse_hypothesis("")
        assert isinstance(hyp, Hypothesis)
        assert isinstance(hyp.compound_name, str)
        assert isinstance(hyp.peak_assignments, list)

    def test_malformed_response_returns_defaults(self):
        hyp = parse_hypothesis("Plain text with no structure.")
        assert isinstance(hyp, Hypothesis)
        assert isinstance(hyp.compound_name, str)


# ── calculate_peak_coverage ─────────────────────────────────────

class TestCalculatePeakCoverage:
    def test_all_peaks_mentioned(self, sample_spectrum):
        assert calculate_peak_coverage(sample_spectrum, SAMPLE_AI_RESPONSE, top_n=6) >= 0.7

    def test_no_peaks_mentioned(self, sample_spectrum):
        assert calculate_peak_coverage(sample_spectrum, "Unknown compound.", top_n=5) == 0.0

    def test_some_peaks_mentioned(self, sample_spectrum):
        partial = "The peak at 7.29 ppm is solvent. The peak at 6.62 ppm is vinyl."
        cov = calculate_peak_coverage(sample_spectrum, partial, top_n=8)
        assert 0.0 < cov < 1.0

    def test_top_n_limits_denominator(self, sample_spectrum):
        cov = calculate_peak_coverage(sample_spectrum, SAMPLE_AI_RESPONSE, top_n=2)
        assert 0.0 <= cov <= 1.0


# ── calculate_grounding_score ───────────────────────────────────

class TestCalculateGroundingScore:
    def test_perfect_score(self):
        assert calculate_grounding_score(True, 1.0, 1.0) == pytest.approx(1.0)

    def test_formula_mismatch_penalty(self):
        delta = (calculate_grounding_score(True, 1.0, 1.0)
                 - calculate_grounding_score(False, 1.0, 1.0))
        assert delta == pytest.approx(0.3)

    def test_zero_coverage_penalty(self):
        delta = (calculate_grounding_score(True, 1.0, 1.0)
                 - calculate_grounding_score(True, 0.0, 1.0))
        assert delta == pytest.approx(0.4)

    def test_weighted_formula(self):
        score = calculate_grounding_score(True, 0.5, 0.5)
        assert score == pytest.approx(0.3 * 1.0 + 0.4 * 0.5 + 0.3 * 0.5)

    def test_all_zero(self):
        assert calculate_grounding_score(False, 0.0, 0.0) == pytest.approx(0.0)

    def test_return_type(self):
        assert isinstance(calculate_grounding_score(False, 0.3, 0.7), float)


# ── build_constraints ───────────────────────────────────────────

class TestBuildConstraints:
    def _iter(self, *, name="Unknown", conf="Low", assignments=None,
              score=0.2, formula=False, lib=0.0):
        return Iteration(
            round=1,
            hypothesis=Hypothesis(name, conf, "", assignments or []),
            grounding_score=score, formula_match=formula,
            pubchem_data=None, library_score=lib, constraints=[],
        )

    def test_low_score_mentions_issues(self, sample_spectrum):
        text = build_constraints(self._iter(), sample_spectrum).lower()
        assert "score" in text or "low" in text or "mismatch" in text

    def test_formula_mismatch_mentioned(self, sample_spectrum):
        text = build_constraints(
            self._iter(name="Ethanol", conf="Medium", score=0.4, lib=0.3),
            sample_spectrum,
        ).lower()
        assert "formula" in text or "mismatch" in text

    def test_unexplained_peaks_listed(self, sample_spectrum):
        text = build_constraints(
            self._iter(name="Ethanol", assignments=["7.29"], score=0.3,
                       formula=True, lib=0.2),
            sample_spectrum,
        ).lower()
        assert "peak" in text or "unexplained" in text or "unassigned" in text

    def test_returns_string(self, sample_spectrum, sample_iteration):
        assert isinstance(build_constraints(sample_iteration, sample_spectrum), str)


# ── generate_report ─────────────────────────────────────────────

class TestGenerateReport:
    def _report(self, audit, spectrum, tmp_path):
        report_path = generate_report(
            audit, spectrum, str(tmp_path / "spectrum.png"), tmp_path,
        )
        return report_path.read_text()

    def test_contains_imrad_sections(self, sample_audit_trail, sample_spectrum, tmp_path):
        lower = self._report(sample_audit_trail, sample_spectrum, tmp_path).lower()
        assert "introduction" in lower or "background" in lower
        assert "method" in lower
        assert "result" in lower
        assert "discussion" in lower or "conclusion" in lower

    def test_contains_peak_table(self, sample_audit_trail, sample_spectrum, tmp_path):
        report = self._report(sample_audit_trail, sample_spectrum, tmp_path)
        assert "ppm" in report.lower()
        assert "7.29" in report or "6.62" in report

    def test_contains_grounding_verification(self, sample_audit_trail, sample_spectrum, tmp_path):
        lower = self._report(sample_audit_trail, sample_spectrum, tmp_path).lower()
        assert "grounding" in lower or "verification" in lower or "score" in lower

    def test_contains_audit_trail(self, sample_audit_trail, sample_spectrum, tmp_path):
        lower = self._report(sample_audit_trail, sample_spectrum, tmp_path).lower()
        assert "audit" in lower or "iteration" in lower or "round" in lower

    def test_ends_with_device_use_attribution(self, sample_audit_trail, sample_spectrum, tmp_path):
        assert "device-use" in self._report(sample_audit_trail, sample_spectrum, tmp_path).lower()

    def test_report_is_markdown(self, sample_audit_trail, sample_spectrum, tmp_path):
        assert self._report(sample_audit_trail, sample_spectrum, tmp_path).count("#") >= 3

    def test_report_references_compound(self, sample_audit_trail, sample_spectrum, tmp_path):
        assert "ionone" in self._report(sample_audit_trail, sample_spectrum, tmp_path).lower()


# ── Data structure sanity ───────────────────────────────────────

class TestDataStructures:
    def test_hypothesis_fields(self, sample_hypothesis):
        assert sample_hypothesis.compound_name == "Alpha-Ionone"
        assert sample_hypothesis.confidence == "High"
        assert isinstance(sample_hypothesis.raw_analysis, str)
        assert len(sample_hypothesis.peak_assignments) == 6

    def test_iteration_fields(self, sample_iteration):
        assert sample_iteration.round == 1
        assert isinstance(sample_iteration.hypothesis, Hypothesis)
        assert sample_iteration.grounding_score == 0.85
        assert sample_iteration.formula_match is True
        assert isinstance(sample_iteration.pubchem_data, dict)

    def test_audit_trail_fields(self, sample_audit_trail):
        assert sample_audit_trail.dataset == "exam_CMCse_1"
        assert sample_audit_trail.formula == "C13H20O"
        assert len(sample_audit_trail.iterations) == 1
        assert sample_audit_trail.accepted is True
        assert sample_audit_trail.final_hypothesis is not None
        assert sample_audit_trail.total_time == 4.2
