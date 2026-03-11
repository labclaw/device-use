# Device-Use Demos — Multi-Instrument AI Science

## Quick Start

```bash
# 1. Setup (one time)
python -m venv .venv
source .venv/bin/activate
pip install nmrglue numpy scipy matplotlib anthropic fastapi uvicorn
pip install tooluniverse  # optional: Harvard's 600+ scientific tools

# 2. Start here
python demos/quickstart.py              # 30-second intro — no setup needed

# 3. Explore demos
python demos/topspin_identify.py --dataset exam_CMCse_1 --formula C13H20O
python demos/topspin_dnmr.py
python demos/topspin_batch.py
python demos/topspin_ai_scientist.py    # full AI scientist pipeline
python demos/topspin_blind_challenge.py # blind NMR identification quiz
python demos/topspin_pipeline.py        # orchestrator middleware demo
python demos/multi_instrument_demo.py   # NMR + plate reader together
python demos/lab_report_demo.py         # raw data → paper-ready report
python demos/streaming_demo.py          # real-time event-driven processing

# 4. Web GUI
./demos/run_web.sh    # open http://localhost:8420
```

## Prerequisites

- **TopSpin 5.0.0** installed at `/opt/topspin5.0.0/` (for examdata)
- **Python 3.11+** with the packages listed above
- **ANTHROPIC_API_KEY** (optional — demos use cached responses without it)

## Demo 0: Quickstart

```bash
python demos/quickstart.py
```

The simplest possible demo — no API key, no TopSpin, no setup. Shows the core pattern: create orchestrator → register instruments → connect → process data → done. Run this first.

## Demo 1: Identify Unknown Compound

```bash
python demos/topspin_identify.py --dataset exam_CMCse_1 --formula C13H20O
python demos/topspin_identify.py --dataset Strychnine --expno 10 --formula C21H22N2O2
python demos/topspin_identify.py --dataset Guaiol --formula C15H26O
```

Pipeline: Load FID → Process (FT + Phase + Baseline) → Peak Pick → AI Analysis → Next Experiment

## Demo 2: Dynamic NMR Temperature Series

```bash
python demos/topspin_dnmr.py
```

Processes Me₂NCOMe at 5 temperatures (T=10 to 420K), generates overlay plot showing N-methyl peak coalescence. Reveals amide rotation barrier.

## Demo 3: Batch Analysis + PubChem

```bash
python demos/topspin_batch.py
```

Processes all 8 unique compounds, generates spectrum plots, cross-references with PubChem API for compound verification.

## Demo 4: Blind NMR Challenge

```bash
python demos/topspin_blind_challenge.py
```

Strips all metadata and sends ONLY peak lists to Claude. AI must identify compounds from chemical shifts alone — like a chemistry quiz for AI.

## Demo 5: Full AI Scientist Pipeline

```bash
python demos/topspin_ai_scientist.py
```

The flagship demo — complete autonomous scientific workflow:
1. Instrument connection via device-use middleware
2. NMR signal processing (FT → Phase → Baseline → Peaks)
3. AI compound identification (Cloud Brain)
4. PubChem cross-reference (NCBI verification)
5. ToolUniverse tool discovery (600+ scientific tools)
6. Autonomous experiment planning

## Demo 6: Orchestrator Pipeline

```bash
python demos/topspin_pipeline.py
python demos/topspin_pipeline.py --dataset exam_CMCse_3 --expno 10
```

Shows the core middleware pattern: instruments register with the orchestrator, pipelines define multi-step workflows declaratively, events stream to listeners. The demo runs a 4-step pipeline (process → visualize → interpret → PubChem) with real-time event logging.

## Demo 7: Multi-Instrument Orchestration

```bash
python demos/multi_instrument_demo.py
```

The "ROS for Lab Instruments" demo — orchestrates TWO different instrument types through the same BaseInstrument abstraction:
1. NMR Spectrometer (TopSpin) — chemical structure analysis
2. Plate Reader (Gen5) — ELISA / cell viability assays

Both instruments register with the same Orchestrator, share the same Pipeline engine. Shows Z-factor calculation, signal/noise ratios, and cross-instrument summaries.

## Demo 8: AI Lab Report Generator

```bash
python demos/lab_report_demo.py
python demos/lab_report_demo.py --output my_report.md
```

The capstone demo — from raw data to paper-ready report, zero manual work:
1. Process data from BOTH instruments (NMR + Plate Reader)
2. AI analyzes NMR spectrum (compound identification, peak assignment)
3. Cross-reference on PubChem (CID, molecular formula, SMILES)
4. Generate publication-quality plots (spectrum + heatmaps)
5. Compute assay statistics (signal/noise, Z-factor)
6. Write structured lab report combining all findings

Output: `output/lab_report.md` + 3 PNG plots

## Demo 9: Real-Time Event Stream

```bash
python demos/streaming_demo.py
```

Shows the key differentiator of device-use as middleware: events stream in real-time with colored timestamps as instruments process data. Runs two parallel pipelines (NMR multi-sample + plate reader QC) and displays a complete event audit trail with timing, counts, and pass/fail metrics.

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

External tool integrations:
- **PubChem**: Compound metadata via PUG REST (CID, SMILES, InChI)
- **ToolUniverse**: 600+ scientific tools via Harvard's SDK
- **K-Dense**: Autonomous analysis agent architecture

## Output

All demos save spectrum plots to `output/`:
- `output/exam_CMCse_1_spectrum.png` — Alpha Ionone
- `output/exam_CMCse_3_spectrum.png` — Strychnine
- `output/dnmr_temperature_overlay.png` — DNMR series
