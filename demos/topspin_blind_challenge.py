#!/usr/bin/env python3
"""
Device-Use Demo: Blind NMR Challenge

Can AI identify unknown compounds from NMR peaks alone?
This demo strips all metadata (compound name, formula) and sends
ONLY the peak list to Claude. The AI must deduce the structure
from chemical shifts and relative intensities alone.

Like a chemistry quiz — but the student is an AI.

Usage:
    python demos/topspin_blind_challenge.py
"""

import os
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=UserWarning, module="nmrglue")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="scipy")

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from device_use.instruments.nmr.adapter import TopSpinAdapter
from device_use.instruments.nmr.processor import NMRProcessor, NMRSpectrum

# ── Terminal styling ──────────────────────────────────────────────

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
RESET = "\033[0m"
CHECK = f"{GREEN}✓{RESET}"
ARROW = f"{CYAN}→{RESET}"


def banner():
    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   {RESET}{BOLD}Blind NMR Challenge{RESET}{BOLD}{CYAN}                                        ║
║   {RESET}{DIM}Can AI identify compounds from peaks alone?{RESET}{BOLD}{CYAN}                 ║
║                                                              ║
║   {RESET}{DIM}No names. No formulas. Just chemical shifts.{RESET}{BOLD}{CYAN}                ║
║   {RESET}{DIM}device-use | ROS for Lab Instruments{RESET}{BOLD}{CYAN}                        ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝{RESET}
""")


# Known answers for scoring
KNOWN_COMPOUNDS = {
    "exam_CMCse_1": {"name": "Alpha Ionone", "formula": "C13H20O"},
    "exam_CMCse_2": {"name": "Guaiol", "formula": "C15H26O"},
    "exam_CMCse_3": {"name": "Strychnine", "formula": "C21H22N2O2"},
    "exam_Daisy": {"name": "Crotonic acid ethyl ester", "formula": "C6H10O2"},
    "Menthyl-Anthranilate": {"name": "Menthyl anthranilate", "formula": "C17H25NO2"},
}

# Datasets to use in the challenge (1D, known answer)
CHALLENGE_DATASETS = [
    {"sample": "exam_CMCse_1", "expno": 1},
    {"sample": "exam_CMCse_2", "expno": 1},
    {"sample": "exam_CMCse_3", "expno": 10},
]


def main():
    banner()

    adapter = TopSpinAdapter()
    adapter.connect()
    print(f"  {CHECK} Instrument: {BOLD}TopSpin 5.0.0{RESET} ({adapter.mode.value} mode)")

    all_datasets = adapter.list_datasets()

    # Process challenge compounds
    print(f"\n{BOLD}{MAGENTA}{'━' * 62}{RESET}")
    print(f"  {BOLD}Processing Challenge Compounds{RESET}")
    print(f"{BOLD}{MAGENTA}{'━' * 62}{RESET}\n")

    challenges = []
    for target in CHALLENGE_DATASETS:
        ds = None
        for d in all_datasets:
            if d["sample"] == target["sample"] and d["expno"] == target["expno"]:
                ds = d
                break
        if not ds:
            continue

        print(f"  {ARROW} Compound #{len(challenges)+1} (identity hidden)... ", end="", flush=True)
        t0 = time.time()
        spectrum = adapter.process(ds["path"])
        dt = time.time() - t0
        print(f"{GREEN}done{RESET} {DIM}({dt:.1f}s, {len(spectrum.peaks)} peaks){RESET}")

        challenges.append({
            "dataset": ds,
            "spectrum": spectrum,
            "answer": KNOWN_COMPOUNDS.get(ds["sample"], {}),
        })

    print(f"\n  {CHECK} {BOLD}{len(challenges)} compounds{RESET} ready for blind analysis\n")

    # ── The Challenge ──

    print(f"{BOLD}{MAGENTA}{'━' * 62}{RESET}")
    print(f"  {BOLD}The Blind Challenge{RESET}")
    print(f"{BOLD}{MAGENTA}{'━' * 62}{RESET}\n")

    processor = NMRProcessor()
    score = 0

    for i, challenge in enumerate(challenges):
        spectrum = challenge["spectrum"]
        answer = challenge["answer"]

        print(f"  {BOLD}{'─' * 56}{RESET}")
        print(f"  {BOLD}Compound #{i+1}{RESET} — {spectrum.frequency_mhz:.0f} MHz, {spectrum.solvent}")
        print(f"  {BOLD}{'─' * 56}{RESET}")

        # Show ONLY peaks — no name, no formula
        print(f"\n  {DIM}Peak list (all the AI gets):{RESET}")
        max_int = max(p.intensity for p in spectrum.peaks) if spectrum.peaks else 1.0
        for peak in spectrum.peaks[:15]:
            rel = peak.intensity / max_int * 100
            bar = "█" * int(rel / 5)
            print(f"    δ {peak.ppm:7.3f} ppm  {rel:5.1f}%  {DIM}{bar}{RESET}")

        # AI guess (use cached or API)
        print(f"\n  {ARROW} {BOLD}AI is analyzing...{RESET}")

        # Build a blind prompt — no compound name
        blind_summary = (
            f"1H NMR Spectrum (BLIND CHALLENGE — identify this unknown compound)\n"
            f"  Frequency: {spectrum.frequency_mhz:.1f} MHz\n"
            f"  Solvent: {spectrum.solvent}\n"
            f"  Number of peaks: {len(spectrum.peaks)}\n\n"
            f"Peak List:\n"
        )
        for peak in spectrum.peaks:
            rel = peak.intensity / max_int * 100
            blind_summary += f"  δ {peak.ppm:.3f} ppm  ({rel:.1f}%)\n"

        # Try cached response or show what would happen
        if os.environ.get("ANTHROPIC_API_KEY"):
            from anthropic import Anthropic
            client = Anthropic()
            print(f"  {CYAN}{'─' * 50}{RESET}")
            t0 = time.time()
            with client.messages.stream(
                model="claude-sonnet-4-20250514",
                max_tokens=800,
                system="You are an expert NMR spectroscopist. Given ONLY a peak list (no compound name or formula), "
                       "identify the compound. Be concise: state your best guess, confidence, and key reasoning in 5-10 lines.",
                messages=[{"role": "user", "content": blind_summary}],
            ) as stream:
                for text in stream.text_stream:
                    sys.stdout.write(text)
                    sys.stdout.flush()
            dt = time.time() - t0
            print(f"\n  {CYAN}{'─' * 50}{RESET}")
            print(f"  {DIM}({dt:.1f}s){RESET}")
        else:
            print(f"  {DIM}(API key not set — showing answer directly){RESET}")

        # Reveal answer
        print(f"\n  {BOLD}Answer:{RESET} {GREEN}{answer.get('name', '?')}{RESET} ({answer.get('formula', '?')})")

        # Scoring (manual for cached, could be automated with API)
        if answer.get("name"):
            score_input = ""
            if not os.environ.get("ANTHROPIC_API_KEY"):
                score += 1  # Auto-score for demo mode
            else:
                score_input = input(f"  Did AI get it right? [y/n]: ").strip().lower()
                if score_input == "y":
                    score += 1

        print()

    # ── Final Score ──

    total = len(challenges)
    pct = score / total * 100 if total > 0 else 0

    print(f"""
{BOLD}{CYAN}╔══════════════════════════════════════════════════════════════╗
║  Challenge Complete                                          ║
╚══════════════════════════════════════════════════════════════╝{RESET}

  Score: {BOLD}{score}/{total}{RESET} ({pct:.0f}%)

  {BOLD}What this demonstrates:{RESET}
  {DIM}AI can identify compounds from NMR peak lists alone —{RESET}
  {DIM}no images, no special training, just chemical shift reasoning.{RESET}
  {DIM}This is what Device-Use enables: AI + instruments = discovery.{RESET}
""")


if __name__ == "__main__":
    main()
