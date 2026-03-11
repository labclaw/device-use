#!/usr/bin/env python3
"""
Device-Use Demo 17: AI Scientist Closed-Loop

Autonomous scientific reasoning: OBSERVE -> HYPOTHESIZE -> VERIFY -> ITERATE -> REPORT

Usage:
    python demos/17_ai_scientist_loop.py
    python demos/17_ai_scientist_loop.py --dataset exam_CMCse_1 --formula C13H20O
    python demos/17_ai_scientist_loop.py --no-brain
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning, module="nmrglue")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="scipy")

sys.path.insert(0, str(Path(__file__).parent / "lib"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from device_use.instruments import ControlMode  # noqa: E402, I001
from device_use.instruments.nmr.adapter import TopSpinAdapter  # noqa: E402
from device_use.instruments.nmr.brain import NMRBrain  # noqa: E402
from device_use.instruments.nmr.library import SpectralLibrary  # noqa: E402
from device_use.instruments.nmr.processor import NMRSpectrum  # noqa: E402
from device_use.instruments.nmr.visualizer import plot_spectrum  # noqa: E402
from device_use.tools.pubchem import PubChemTool, PubChemError  # noqa: E402
from lib.terminal import (  # noqa: E402
    ARROW, BOLD, CYAN, DIM, GREEN, RED, RESET, STAR, YELLOW,
    banner as _lib_banner, done, err, finale, info, ok, phase,
    progress, section, warn,
)


# ── Data Structures ──────────────────────────────────────────────


@dataclass
class Hypothesis:
    compound_name: str
    confidence: str  # "High", "Medium", "Low"
    raw_analysis: str
    peak_assignments: list[str]


@dataclass
class Iteration:
    round: int
    hypothesis: Hypothesis
    grounding_score: float
    formula_match: bool
    pubchem_data: dict | None
    library_score: float
    constraints: list[str]


@dataclass
class AuditTrail:
    question: str
    dataset: str
    formula: str
    iterations: list[Iteration] = field(default_factory=list)
    accepted: bool = False
    final_hypothesis: Hypothesis | None = None
    total_time: float = 0.0


# ── Hypothesis Parsing ───────────────────────────────────────────


def parse_hypothesis(text: str) -> Hypothesis:
    """Extract structured hypothesis from AI response text."""
    return Hypothesis(
        compound_name=_extract_compound_name(text),
        confidence=_extract_confidence(text),
        raw_analysis=text,
        peak_assignments=_extract_peak_assignments(text),
    )


def _extract_compound_name(text: str) -> str:
    """Pull the most likely compound name from AI response."""
    m = re.search(
        r"##\s*Proposed\s+Structure.*?\n\*\*(.+?)\*\*",
        text, re.IGNORECASE | re.DOTALL,
    )
    if m:
        return re.sub(r"\s*\(.*?\)\s*$", "", m.group(1).strip())
    for pat in [
        r"(?:compound|structure|identified as|propose)[:\s]+\*\*(.+?)\*\*",
        r"\*\*([A-Z][a-z][\w\s-]+?)\*\*\s*[\n(]",
    ]:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    m = re.search(r"\*\*([A-Za-z][\w\s-]{2,30}?)\*\*", text)
    return m.group(1).strip() if m else "Unknown"


def _extract_confidence(text: str) -> str:
    """Extract confidence level (High/Medium/Low) from response."""
    m = re.search(
        r"##\s*Confidence.*?\n\*\*(High|Medium|Low)\*\*",
        text, re.IGNORECASE | re.DOTALL,
    )
    if m:
        return m.group(1).capitalize()
    m = re.search(
        r"confidence[:\s]*\*{0,2}(high|medium|low)\*{0,2}",
        text, re.IGNORECASE,
    )
    return m.group(1).capitalize() if m else "Medium"


def _extract_peak_assignments(text: str) -> list[str]:
    """Extract lines containing peak assignments (delta/ppm notation or table rows)."""
    return [
        line.strip().lstrip("|").strip()
        for line in text.split("\n")
        if re.search(
            r"[δd]\s*\d+\.?\d*|[\d.]+\s*ppm|\|\s*\d+\.\d+\s*\|",
            line, re.IGNORECASE,
        )
        and line.strip()
        and "---" not in line
    ]


# ── Grounding Verification ───────────────────────────────────────


def _peak_mentioned_in_text(ppm: float, text: str, tolerance: float = 0.1) -> bool:
    """Check whether a peak at *ppm* is mentioned (exactly or approximately) in *text*."""
    if f"{ppm:.1f}" in text or f"{ppm:.2f}" in text:
        return True
    return any(
        abs(float(m.group(1)) - ppm) <= tolerance
        for m in re.finditer(r"(\d+\.\d+)", text)
    )


def calculate_peak_coverage(
    spectrum: NMRSpectrum, response_text: str, top_n: int = 10,
) -> float:
    """Fraction of top peaks (by intensity) mentioned in the AI response."""
    if not spectrum.peaks:
        return 0.0
    top_peaks = sorted(
        spectrum.peaks, key=lambda p: p.intensity, reverse=True,
    )[:top_n]
    mentioned = sum(
        1 for peak in top_peaks
        if _peak_mentioned_in_text(peak.ppm, response_text)
    )
    return mentioned / len(top_peaks)


def calculate_grounding_score(
    formula_match: bool, peak_coverage: float, library_score: float,
) -> float:
    """Weighted grounding score: 0.3*formula + 0.4*peaks + 0.3*library."""
    return (
        0.3 * (1.0 if formula_match else 0.0)
        + 0.4 * peak_coverage
        + 0.3 * library_score
    )


def verify_with_pubchem(
    compound_name: str, expected_formula: str,
) -> tuple[dict | None, bool]:
    """PubChem lookup + formula match check. Returns (data, matches)."""
    try:
        data = PubChemTool().lookup_by_name(compound_name)
        pc = re.sub(r"\s+", "", data.get("MolecularFormula", ""))
        expected = re.sub(r"\s+", "", expected_formula)
        return data, pc == expected
    except PubChemError:
        return None, False


# ── Constraint Builder ───────────────────────────────────────────


def build_constraints(iteration: Iteration, spectrum: NMRSpectrum) -> str:
    """Build a constraint string for the next AI iteration."""
    issues = []
    if not iteration.formula_match:
        issues.append("PubChem formula does not match expected formula")
    if iteration.grounding_score < 0.5:
        issues.append("low peak coverage in analysis")

    top_peaks = sorted(spectrum.peaks, key=lambda p: p.intensity, reverse=True)[:10]
    raw = iteration.hypothesis.raw_analysis
    unexplained = [
        f"{peak.ppm:.2f}" for peak in top_peaks
        if not _peak_mentioned_in_text(peak.ppm, raw)
    ]

    name = iteration.hypothesis.compound_name
    issues_str = "; ".join(issues) if issues else "low overall grounding score"
    peaks_str = ", ".join(unexplained[:5]) if unexplained else "none"
    return (
        f"Previous hypothesis '{name}' had grounding score "
        f"{iteration.grounding_score:.2f}. Issues: {issues_str}. "
        f"Unexplained peaks at: {peaks_str} ppm. "
        f"Please propose a DIFFERENT compound or refine the analysis."
    )


# ── Score Bar Rendering ──────────────────────────────────────────


def score_bar(score: float, width: int = 20) -> str:
    """Render a visual score bar with color coding."""
    filled = int(score * width)
    if score >= 0.7:
        color = GREEN
    elif score >= 0.4:
        color = YELLOW
    else:
        color = RED
    bar = f"{color}{'█' * filled}{DIM}{'░' * (width - filled)}{RESET}"
    return f"{bar} {BOLD}{score:.2f}{RESET}"


# ── Report Generation ────────────────────────────────────────────


def generate_report(
    audit: AuditTrail, spectrum: NMRSpectrum,
    spectrum_image: str, output_path: Path,
    threshold: float = 0.7,
) -> Path:
    """Generate an IMRAD markdown report from the audit trail."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    final = audit.final_hypothesis
    last = audit.iterations[-1] if audit.iterations else None
    status = "ACCEPTED" if audit.accepted else "INCONCLUSIVE"
    max_int = max(p.intensity for p in spectrum.peaks) if spectrum.peaks else 1.0

    sections = [
        "# AI Scientist Report\n",
        f"**Date:** {now}  \n**Question:** {audit.question}  \n"
        f"**Dataset:** {audit.dataset}  \n"
        f"**Molecular Formula:** {audit.formula}  \n"
        f"**Status:** {status}  \n"
        f"**Total Time:** {audit.total_time:.1f}s  \n"
        f"**Iterations:** {len(audit.iterations)}  \n",
        "---\n\n## Introduction\n",
        "This report documents an autonomous NMR compound identification\n"
        "conducted by the device-use AI Scientist pipeline. The system\n"
        "processes raw NMR data, generates structural hypotheses via AI,\n"
        "and verifies them against external databases in a closed loop.\n",
        "## Methods\n",
        "- **Instrument:** Bruker TopSpin 5.0.0 (Offline mode)\n"
        "- **Processing:** nmrglue (FT, ACME phase, polynomial baseline)\n"
        "- **Peak picking:** threshold-based downward search\n"
        "- **AI Engine:** NMRBrain (Claude API / cached demo responses)\n"
        "- **Verification:** PubChem PUG REST, Spectral Library matching\n"
        "- **Grounding:** 0.3*formula + 0.4*peak_coverage + 0.3*library\n",
        f"## Results\n\n"
        f"- Nucleus: {spectrum.nucleus}\n"
        f"- Frequency: {spectrum.frequency_mhz:.1f} MHz\n"
        f"- Solvent: {spectrum.solvent}\n"
        f"- Peaks detected: {len(spectrum.peaks)}\n\n"
        f"![Spectrum]({spectrum_image})\n\n"
        "### Peak Table\n\n"
        "| # | ppm | Relative Intensity |\n"
        "|---|-----|-------------------|\n"
        + "\n".join(
            f"| {i} | {p.ppm:.3f} | {p.intensity / max_int * 100:.1f}% |"
            for i, p in enumerate(spectrum.peaks[:20], 1)
        ) + "\n",
    ]

    if final:
        assignments = "\n".join(
            f"- {a}" for a in final.peak_assignments[:10]
        )
        sections.append(
            f"## Analysis\n\n"
            f"- **Compound:** {final.compound_name}\n"
            f"- **Confidence:** {final.confidence}\n\n"
            f"### Key Peak Assignments\n\n{assignments}\n"
        )

    sections.append("## Verification\n")
    if last and last.pubchem_data:
        pc = last.pubchem_data
        rows = "\n".join(
            f"| {k} | {pc.get(k, 'N/A')} |"
            for k in ["CID", "IUPACName", "MolecularFormula",
                       "MolecularWeight", "CanonicalSMILES"]
        )
        sections.append(
            f"| Property | Value |\n|----------|-------|\n{rows}\n\n"
            f"**Formula match:** {'Yes' if last.formula_match else 'No'}  \n"
            f"**Grounding score:** {last.grounding_score:.2f}  \n"
        )
    else:
        sections.append(
            "PubChem verification was not available for this compound.\n"
        )

    trail_rows = "\n".join(
        f"| {it.round} | {it.hypothesis.compound_name} "
        f"| {it.grounding_score:.2f} "
        f"| {'Match' if it.formula_match else 'Mismatch'} "
        f"| {'Yes' if it.grounding_score >= threshold else 'No'} |"
        for it in audit.iterations
    )
    sections.append(
        "## Audit Trail\n\n"
        "| Round | Compound | Score | Formula | Accepted |\n"
        "|-------|----------|-------|---------|----------|\n"
        f"{trail_rows}\n"
    )

    sections.append("## Conclusion\n")
    if audit.accepted and final and last:
        sections.append(
            f"The compound was identified as **{final.compound_name}** "
            f"with {final.confidence.lower()} confidence and a grounding "
            f"score of {last.grounding_score:.2f} after "
            f"{len(audit.iterations)} iteration(s).\n"
        )
    else:
        score_val = f"{last.grounding_score:.2f}" if last else "0.00"
        sections.append(
            f"Identification was inconclusive after {len(audit.iterations)} "
            f"iteration(s). Best hypothesis: "
            f"**{final.compound_name if final else 'N/A'}** "
            f"(grounding score {score_val}).\n"
        )
    sections.append(
        "---\n\n"
        "*Generated with device-use | AI Scientist Closed-Loop Pipeline*\n"
    )

    report_path = output_path / "report.md"
    report_path.write_text("\n".join(sections))
    return report_path


# ── CLI & Main ───────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Device-Use Demo 17: AI Scientist Closed-Loop",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s --dataset exam_CMCse_1 --formula C13H20O\n"
            "  %(prog)s --dataset Strychnine --expno 10 --formula C21H22N2O2\n"
            "  %(prog)s --no-brain\n"
        ),
    )
    parser.add_argument("--question", default="What is this unknown compound?")
    parser.add_argument("--dataset", default="exam_CMCse_1")
    parser.add_argument("--expno", type=int, default=1)
    parser.add_argument("--formula", default="C13H20O")
    parser.add_argument("--max-iterations", type=int, default=3)
    parser.add_argument(
        "--threshold", type=float, default=0.7,
        help="Grounding score threshold",
    )
    parser.add_argument("--topspin-dir", default="/opt/topspin5.0.0")
    parser.add_argument("--output", default="output/ai_scientist")
    parser.add_argument(
        "--no-brain", action="store_true",
        help="Skip AI, use library matching only",
    )
    return parser.parse_args()


def find_dataset(
    adapter: TopSpinAdapter, name: str, expno: int,
) -> tuple[str, dict] | None:
    """Find a dataset by name/title match and experiment number."""
    for ds in adapter.list_datasets():
        if (name.lower() in ds["sample"].lower()
                or name.lower() in ds["title"].lower()) and ds["expno"] == expno:
            return ds["path"], ds
    return None


def main() -> None:
    args = parse_args()
    t_start = time.time()
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    _lib_banner("AI Scientist Closed-Loop",
                "Observe -> Hypothesize -> Verify -> Iterate -> Report")
    print(f"  {STAR} {BOLD}Question:{RESET} {args.question}")
    print(f"  {STAR} {BOLD}Dataset:{RESET}  {args.dataset} (expno {args.expno})")
    print(f"  {STAR} {BOLD}Formula:{RESET}  {args.formula}")
    print(f"  {STAR} {BOLD}Threshold:{RESET} {args.threshold}  "
          f"{BOLD}Max iter:{RESET} {args.max_iterations}")

    audit = AuditTrail(
        question=args.question, dataset=args.dataset, formula=args.formula,
    )

    # ── Phase 1: OBSERVE ──
    phase(1, "OBSERVE", "Connect, load, process, extract")

    progress("Connecting to TopSpin (offline)...")
    t0 = time.time()
    adapter = TopSpinAdapter(topspin_dir=args.topspin_dir, mode=ControlMode.OFFLINE)
    if not adapter.connect():
        done(time.time() - t0)
        err(f"Cannot connect to TopSpin at {args.topspin_dir}")
        sys.exit(1)
    done(time.time() - t0)

    inst = adapter.info()
    ok(f"Instrument: {BOLD}{inst.name} {inst.version}{RESET}")
    ok(f"Mode: {BOLD}{adapter.mode.value.upper()}{RESET}")

    result = find_dataset(adapter, args.dataset, args.expno)
    if not result:
        err(f"Dataset '{args.dataset}' (expno={args.expno}) not found")
        for ds in adapter.list_datasets():
            info(f"  {ds['sample']}/{ds['expno']}: {ds['title']}")
        sys.exit(1)
    dataset_path, ds_info = result
    ok(f"Dataset: {BOLD}{ds_info['sample']}/{ds_info['expno']}{RESET}")
    info(f"  Title: {ds_info['title']}")

    progress("Processing FID -> Spectrum...")
    t0 = time.time()
    spectrum = adapter.process(dataset_path)
    done(time.time() - t0)
    ok(f"Peaks: {BOLD}{len(spectrum.peaks)}{RESET} | "
       f"{spectrum.frequency_mhz:.0f} MHz | {spectrum.solvent}")

    section("Top Peaks")
    max_int = max(p.intensity for p in spectrum.peaks) if spectrum.peaks else 1.0
    for peak in sorted(spectrum.peaks, key=lambda p: p.intensity, reverse=True)[:8]:
        rel = peak.intensity / max_int * 100
        print(f"    d {peak.ppm:7.3f} ppm  {rel:5.1f}%  {DIM}{'█' * int(rel / 5)}{RESET}")

    spectrum_image = str(output_dir / "spectrum.png")
    plot_spectrum(spectrum, output_path=spectrum_image)
    ok(f"Spectrum plot: {BOLD}{spectrum_image}{RESET}")

    section("Library Matching (non-AI baseline)")
    progress("Building spectral library...")
    t0 = time.time()
    library = SpectralLibrary.from_examdata()
    done(time.time() - t0)
    matches = library.match(spectrum, top_k=3)
    best_library_score = matches[0].score if matches else 0.0
    for i, m in enumerate(matches):
        marker = STAR if i == 0 else ARROW
        print(f"  {marker} {BOLD}{m.entry.name}{RESET}  "
              f"score={m.score:.3f}  ({m.matched_peaks}/{m.total_peaks} peaks)")

    # ── No-brain shortcut ──
    if args.no_brain:
        phase(2, "RESULT (no-brain mode)", "Library matching only")
        if matches:
            best = matches[0]
            hyp = Hypothesis(
                compound_name=best.entry.name,
                confidence="Medium" if best.score > 0.5 else "Low",
                raw_analysis=f"Library match: {best.entry.name} ({best.score:.3f})",
                peak_assignments=[],
            )
            pc_data, fm = verify_with_pubchem(best.entry.name, args.formula)
            gs = calculate_grounding_score(fm, best.score, best.score)
            audit.iterations.append(Iteration(
                round=1, hypothesis=hyp, grounding_score=gs,
                formula_match=fm, pubchem_data=pc_data,
                library_score=best.score, constraints=[],
            ))
            audit.accepted = gs >= args.threshold
            audit.final_hypothesis = hyp
            ok(f"Best match: {BOLD}{best.entry.name}{RESET}")
            print(f"    Grounding: {score_bar(gs)}")
        else:
            warn("No library matches found")
        audit.total_time = time.time() - t_start
        rp = generate_report(
            audit, spectrum, spectrum_image, output_dir, args.threshold,
        )
        ok(f"Report: {BOLD}{rp}{RESET}")
        finale([
            "Library matching only (--no-brain)",
            f"Best: {BOLD}{matches[0].entry.name if matches else 'none'}{RESET}",
            f"Report: {BOLD}{rp}{RESET}",
        ], title="AI Scientist (Library Only)")
        return

    # ── Phases 2-4: Closed Loop ──
    has_api = bool(os.environ.get("ANTHROPIC_API_KEY"))
    brain = NMRBrain()
    if not has_api:
        info("No ANTHROPIC_API_KEY -- using cached demo responses")
        info("Multi-iteration refinement requires ANTHROPIC_API_KEY")
    constraints: list[str] = []

    for iteration_num in range(1, args.max_iterations + 1):
        phase(2, f"HYPOTHESIZE (round {iteration_num}/{args.max_iterations})",
              "AI interprets spectrum and proposes structure")
        if constraints:
            section("Constraints from previous round")
            for c in constraints:
                print(f"    {DIM}{c}{RESET}")
            print()

        context = " ".join(constraints)
        if args.formula:
            context = f"Molecular formula: {args.formula}. " + context

        progress("AI analyzing spectrum...")
        print()
        print(f"  {CYAN}{'─' * 56}{RESET}")
        t0 = time.time()
        response_text = ""
        for chunk in brain.interpret_spectrum(
            spectrum, molecular_formula=args.formula,
            context=context.strip(), stream=True,
        ):
            sys.stdout.write(chunk)
            sys.stdout.flush()
            response_text += chunk
        dt = time.time() - t0
        print(f"\n  {CYAN}{'─' * 56}{RESET}")
        info(f"  Analysis complete ({dt:.1f}s)")

        hypothesis = parse_hypothesis(response_text)
        print()
        ok(f"Proposed: {BOLD}{hypothesis.compound_name}{RESET}")
        ok(f"Confidence: {BOLD}{hypothesis.confidence}{RESET}")
        ok(f"Peak assignments: {len(hypothesis.peak_assignments)} lines")

        # Phase 3: VERIFY
        phase(3, f"VERIFY (round {iteration_num})", "PubChem + formula + peaks")
        progress(f"PubChem: '{hypothesis.compound_name}'...")
        t0 = time.time()
        pubchem_data, formula_match = verify_with_pubchem(
            hypothesis.compound_name, args.formula,
        )
        done(time.time() - t0)

        if pubchem_data:
            pc_formula = pubchem_data.get("MolecularFormula", "?")
            ok(f"CID: {pubchem_data.get('CID', '?')}  IUPAC: "
               f"{pubchem_data.get('IUPACName', '?')}")
            ok(f"Formula: {pc_formula} (expected: {args.formula})  "
               f"Weight: {pubchem_data.get('MolecularWeight', '?')}")
            if formula_match:
                ok(f"Formula match: {GREEN}YES{RESET}")
            else:
                warn(f"Formula match: {RED}NO{RESET} "
                     f"({pc_formula} != {args.formula})")
        else:
            warn("PubChem lookup failed -- compound may not be in database")

        peak_coverage = calculate_peak_coverage(spectrum, response_text)
        ok(f"Peak coverage: {peak_coverage:.0%} of top 10 peaks explained")
        lib_score = best_library_score if best_library_score > 0 else 0.5
        grounding = calculate_grounding_score(
            formula_match, peak_coverage, lib_score,
        )

        section("Grounding Score")
        print(f"    Formula match  (0.3): "
              f"{score_bar(1.0 if formula_match else 0.0)}")
        print(f"    Peak coverage  (0.4): {score_bar(peak_coverage)}")
        print(f"    Library score  (0.3): {score_bar(lib_score)}")
        print(f"    {'─' * 40}")
        print(f"    {BOLD}Combined:          {score_bar(grounding)}{RESET}")

        iteration = Iteration(
            round=iteration_num, hypothesis=hypothesis,
            grounding_score=grounding, formula_match=formula_match,
            pubchem_data=pubchem_data, library_score=lib_score,
            constraints=list(constraints),
        )
        audit.iterations.append(iteration)

        # Phase 4: EVALUATE
        phase(4, f"EVALUATE (round {iteration_num})", "Accept or refine?")
        if grounding >= args.threshold:
            ok(f"Score {BOLD}{grounding:.2f}{RESET} >= "
               f"threshold {args.threshold:.2f}")
            ok(f"{GREEN}ACCEPTED{RESET}: "
               f"{BOLD}{hypothesis.compound_name}{RESET}")
            audit.accepted = True
            audit.final_hypothesis = hypothesis
            break

        warn(f"Score {BOLD}{grounding:.2f}{RESET} < "
             f"threshold {args.threshold:.2f}")
        if iteration_num >= args.max_iterations:
            warn(f"Max iterations ({args.max_iterations}) reached")
            audit.final_hypothesis = hypothesis
            break
        if not has_api:
            warn("Cached mode -- cannot refine without ANTHROPIC_API_KEY")
            audit.final_hypothesis = hypothesis
            break
        constraints = [build_constraints(iteration, spectrum)]
        info("Refining with new constraints...")

    # ── Phase 5: REPORT ──
    audit.total_time = time.time() - t_start
    phase(5, "REPORT", "Generate IMRAD report with full audit trail")
    report_path = generate_report(
        audit, spectrum, spectrum_image, output_dir, args.threshold,
    )
    ok(f"Report saved: {BOLD}{report_path}{RESET}")

    section("Audit Trail Summary")
    print(f"  {'─' * 56}")
    print(f"  {'Round':>5}  {'Compound':<25} {'Score':>6}  "
          f"{'Formula':>8}  Status")
    print(f"  {'─' * 56}")
    for it in audit.iterations:
        fm = f"{GREEN}Match{RESET}" if it.formula_match else f"{RED}Miss{RESET} "
        st = (f"{GREEN}ACCEPT{RESET}" if it.grounding_score >= args.threshold
              else f"{YELLOW}REFINE{RESET}")
        print(f"  {it.round:>5}  {it.hypothesis.compound_name[:24]:<25} "
              f"{it.grounding_score:>6.2f}  {fm}  {st}")
    print(f"  {'─' * 56}")

    fn = audit.final_hypothesis.compound_name if audit.final_hypothesis else "N/A"
    ss = f"{GREEN}Accepted{RESET}" if audit.accepted else f"{YELLOW}Inconclusive{RESET}"
    bs = max((it.grounding_score for it in audit.iterations), default=0.0)
    finale([
        f"Question: {BOLD}{args.question}{RESET}",
        f"Compound: {BOLD}{fn}{RESET} ({ss})",
        f"Best grounding score: {BOLD}{bs:.2f}{RESET}",
        f"Iterations: {BOLD}{len(audit.iterations)}{RESET}",
        f"Total time: {BOLD}{audit.total_time:.1f}s{RESET}",
        f"Report: {BOLD}{report_path}{RESET}",
        f"Spectrum: {BOLD}{spectrum_image}{RESET}",
    ], title="AI Scientist Closed-Loop Complete")


if __name__ == "__main__":
    main()
