# Device-Use Demos — TopSpin AI Scientist

## Quick Start

```bash
# 1. Setup (one time)
python -m venv .venv
source .venv/bin/activate
pip install nmrglue numpy scipy matplotlib anthropic fastapi uvicorn

# 2. Run any demo
python demos/topspin_identify.py --dataset exam_CMCse_1 --formula C13H20O
python demos/topspin_dnmr.py
python demos/topspin_batch.py

# 3. Web GUI
./demos/run_web.sh    # open http://localhost:8420
```

## Prerequisites

- **TopSpin 5.0.0** installed at `/opt/topspin5.0.0/` (for examdata)
- **Python 3.11+** with the packages listed above
- **ANTHROPIC_API_KEY** (optional — demos use cached responses without it)

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

## Architecture

```
Cloud Brain (Claude AI)     ← Any AI agent
        ↕
   Orchestrator             ← device-use middleware
        ↕
TopSpin (API/GUI/Offline)   ← Any control mode
```

Three control modes for the same instrument:
- **API**: gRPC to running TopSpin (port 3081)
- **GUI**: Computer Use visual automation (coming soon)
- **Offline**: nmrglue processing (no TopSpin needed)

## Output

All demos save spectrum plots to `output/`:
- `output/exam_CMCse_1_spectrum.png` — Alpha Ionone
- `output/exam_CMCse_3_spectrum.png` — Strychnine
- `output/dnmr_temperature_overlay.png` — DNMR series
