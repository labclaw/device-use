# Device-Use Demos — Multi-Instrument AI Science

## Quick Start

```bash
# 1. Setup (one time)
python -m venv .venv
source .venv/bin/activate
pip install nmrglue numpy scipy matplotlib anthropic fastapi uvicorn
pip install tooluniverse  # optional: Harvard's 600+ scientific tools

# 2. Start here
python demos/01_quickstart.py              # 30-second intro — no setup needed

# 3. Explore demos
python demos/02_identify.py --dataset exam_CMCse_1 --formula C13H20O
python demos/04_dnmr.py
python demos/03_batch.py
python demos/06_ai_scientist.py            # full AI scientist pipeline
python demos/05_blind_challenge.py          # blind NMR identification quiz
python demos/08_pipeline.py                # orchestrator middleware demo
python demos/09_multi_instrument.py        # NMR + plate reader together
python demos/10_lab_report.py              # raw data → paper-ready report
python demos/07_gui_live.py                # live GUI operation of TopSpin

# 4. Web GUI
./demos/run_web.sh    # open http://localhost:8420
```

## Prerequisites

- **TopSpin 5.0.0** installed at `/opt/topspin5.0.0/` (for examdata)
- **Python 3.11+** with the packages listed above
- **ANTHROPIC_API_KEY** (optional — demos use cached responses without it)

## Shared Library (`demos/lib/`)

All demos share infrastructure extracted into `demos/lib/`:

- **`terminal.py`** — ANSI color constants and formatting helpers (`banner()`, `step()`, `ok()`, `warn()`, `err()`, `info()`, `section()`, `finale()`, `simulate_stream()`)
- **`runner.py`** — `DemoRunner` class with shared argparse (`--mode`, `--dataset`, `--expno`, `--formula`, `--output`, `--no-brain`), auto-fallback connection, dataset selection
- **`recorder.py`** — `DemoRecorder` for capturing screenshots and assembling GIFs (macOS `screencapture` / Linux `scrot`)

## Demo 1: Quickstart (`01_quickstart.py`)

```bash
python demos/01_quickstart.py
```

The simplest possible demo — no API key, no TopSpin, no setup. Shows the core pattern: create orchestrator → register instruments → connect → process data → done. Run this first.

## Demo 2: Identify Unknown Compound (`02_identify.py`)

```bash
python demos/02_identify.py --dataset exam_CMCse_1 --formula C13H20O
python demos/02_identify.py --dataset Strychnine --expno 10 --formula C21H22N2O2
python demos/02_identify.py --dataset Guaiol --formula C15H26O
```

Pipeline: Load FID → Process (FT + Phase + Baseline) → Peak Pick → AI Analysis → Next Experiment

## Demo 3: Batch Analysis + PubChem (`03_batch.py`)

```bash
python demos/03_batch.py
```

Processes all 8 unique compounds, generates spectrum plots, cross-references with PubChem API for compound verification.

## Demo 4: Dynamic NMR Temperature Series (`04_dnmr.py`)

```bash
python demos/04_dnmr.py
```

Processes Me₂NCOMe at 5 temperatures (T=10 to 420K), generates overlay plot showing N-methyl peak coalescence. Reveals amide rotation barrier.

## Demo 5: Blind NMR Challenge (`05_blind_challenge.py`)

```bash
python demos/05_blind_challenge.py
```

Strips all metadata and sends ONLY peak lists to Claude. AI must identify compounds from chemical shifts alone — like a chemistry quiz for AI.

## Demo 6: Full AI Scientist Pipeline (`06_ai_scientist.py`)

```bash
python demos/06_ai_scientist.py
```

The flagship demo — complete autonomous scientific workflow:
1. Instrument connection via device-use middleware
2. NMR signal processing (FT → Phase → Baseline → Peaks)
3. AI compound identification (Cloud Brain)
4. PubChem cross-reference (NCBI verification)
5. ToolUniverse tool discovery (600+ scientific tools)
6. Autonomous experiment planning

## Demo 7: Live GUI Operation (`07_gui_live.py`) ⭐ NEW

```bash
python demos/07_gui_live.py
python demos/07_gui_live.py --mode gui     # requires TopSpin running
python demos/07_gui_live.py --mode offline  # fallback without TopSpin
```

The showstopper demo — AI operates TopSpin visually like a human scientist:
1. **Detect** — Find TopSpin window on screen
2. **Open** — Type `re <path>` into TopSpin CLI
3. **Process** — Run efp → apbk → ppf, screenshot after each step
4. **Extract** — Read processed data via nmrglue
5. **Visualize** — Generate spectrum plot
6. **Brain** — Claude analyzes spectrum (if API key available)
7. **Record** — Save session as animated GIF

Each step captures verification screenshots to `output/gui_session/`, giving visual proof the AI operated TopSpin.

## Demo 8: Orchestrator Pipeline (`08_pipeline.py`)

```bash
python demos/08_pipeline.py
python demos/08_pipeline.py --dataset exam_CMCse_3 --expno 10
```

Shows the core middleware pattern: instruments register with the orchestrator, pipelines define multi-step workflows declaratively, events stream to listeners. The demo runs a 4-step pipeline (process → visualize → interpret → PubChem) with real-time event logging.

## Demo 9: Multi-Instrument Orchestration (`09_multi_instrument.py`)

```bash
python demos/09_multi_instrument.py
```

The "ROS for Lab Instruments" demo — orchestrates TWO different instrument types through the same BaseInstrument abstraction:
1. NMR Spectrometer (TopSpin) — chemical structure analysis
2. Plate Reader (Gen5) — ELISA / cell viability assays

Both instruments register with the same Orchestrator, share the same Pipeline engine. Shows Z-factor calculation, signal/noise ratios, and cross-instrument summaries.

## Demo 10: AI Lab Report Generator (`10_lab_report.py`)

```bash
python demos/10_lab_report.py
python demos/10_lab_report.py --output my_report.md
```

The capstone demo — from raw data to paper-ready report, zero manual work:
1. Process data from BOTH instruments (NMR + Plate Reader)
2. AI analyzes NMR spectrum (compound identification, peak assignment)
3. Cross-reference on PubChem (CID, molecular formula, SMILES)
4. Generate publication-quality plots (spectrum + heatmaps)
5. Compute assay statistics (signal/noise, Z-factor)
6. Write structured lab report combining all findings

Output: `output/lab_report.md` + 3 PNG plots

## Demo 11: Reaction Monitoring (`11_reaction_monitor.py`)

```bash
python demos/11_reaction_monitor.py
```

Simulates autonomous reaction monitoring — the killer use case for AI-native labs. Processes multiple NMR acquisitions from DNMR temperature series data, tracks peak evolution, detects coalescence trends, and generates a reaction progress dashboard.

## Demo 12: Real-Time Event Stream (`12_streaming.py`)

```bash
python demos/12_streaming.py
```

Shows the key differentiator of device-use as middleware: events stream in real-time with colored timestamps as instruments process data. Runs two parallel pipelines (NMR multi-sample + plate reader QC) and displays a complete event audit trail.

## Demo 13: Spectral Compare (`13_compare.py`)

```bash
python demos/13_compare.py
```

Side-by-side spectral comparison of multiple compounds.

## Demo 14: Spectral Library (`14_library.py`)

```bash
python demos/14_library.py
```

Spectral library fingerprint matching — build a reference library from examdata and match unknowns.

## Demo 15: Showcase (`15_showcase.py`)

```bash
python demos/15_showcase.py
```

All features in one script — the pitch demo for presentations.

## Demo 16: Benchmark (`16_benchmark.py`)

```bash
python demos/16_benchmark.py
```

Performance benchmark — measures processing throughput across all examdata.

## Architecture

```
Cloud Brain (Claude / GPT / Gemini)
        ↕
   device-use middleware (this project)
    ↕         ↕         ↕            ↕          ↕
 TopSpin   Plate     PubChem    ToolUniverse  K-Dense
  (NMR)   Reader    (NCBI)     (Harvard)    (Analyst)
```

Three control modes for the same instrument:
- **API**: gRPC to running TopSpin (port 3081)
- **GUI**: Computer Use visual automation (Anthropic Computer Use API)
- **Offline**: nmrglue processing (no TopSpin needed)

All demos accept `--mode auto|api|gui|offline` via the shared `DemoRunner`.

## Output

All demos save spectrum plots to `output/`:
- `output/exam_CMCse_1_spectrum.png` — Alpha Ionone
- `output/exam_CMCse_3_spectrum.png` — Strychnine
- `output/dnmr_temperature_overlay.png` — DNMR series
- `output/gui_session/` — GUI demo screenshots + GIF
