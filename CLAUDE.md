# Device-Use — Development Guide

## What is this?

Device-use is middleware for scientific instruments — like ROS for robots, but for NMR spectrometers, microscopes, and lab equipment. It connects AI agents (Claude, GPT, Gemini) to physical instruments through a uniform abstraction layer.

## Architecture

```
Cloud Brain (Claude AI)     <- Any LLM
        |
   Orchestrator             <- Pipeline execution, tool routing, events
        |
   Instruments              <- BaseInstrument abstraction
    |       |       |
  API    GUI    Offline     <- Three control modes per instrument
```

## Project Structure

```
src/device_use/
  instruments/
    base.py              # BaseInstrument ABC, ControlMode enum
    nmr/
      adapter.py         # TopSpinAdapter (3 modes: API/GUI/Offline)
      processor.py       # NMR processing pipeline (nmrglue)
      brain.py           # Cloud Brain (Claude API + cache fallback)
      demo_cache.py      # Pre-cached expert responses for demos
      visualizer.py      # Publication-quality spectrum plots
      gui_automation.py  # Computer Use GUI automation
    plate_reader/
      adapter.py         # PlateReaderAdapter (absorbance/fluorescence)
      models.py          # Well, WellPlate, PlateReading data models
    template.py          # Copy-and-implement guide for new instruments
  orchestrator.py        # Pipeline + ToolRegistry + Events
  cli.py                 # CLI: instruments, status, demo, run, interactive
  tools/
    base.py              # BaseTool ABC
    pubchem.py           # PubChem PUG REST integration
    tooluniverse.py      # Harvard ToolUniverse (600+ tools)
  web/
    app.py               # FastAPI web GUI (port 8420)

demos/
  topspin_identify.py         # Single compound identification
  topspin_dnmr.py             # Dynamic NMR temperature series
  topspin_batch.py            # Batch analysis + PubChem
  topspin_blind_challenge.py  # Blind NMR identification quiz
  topspin_ai_scientist.py     # Full AI scientist pipeline (flagship)
  topspin_pipeline.py         # Orchestrator middleware demo
  multi_instrument_demo.py    # NMR + Plate Reader together
  run_web.sh                  # Web GUI launcher

tests/
  test_nmr.py              # NMR module tests
  test_plate_reader.py     # Plate reader tests (18 tests)
  test_orchestrator.py     # Pipeline + registry tests (22 tests)
  test_tools.py            # External tool tests
  test_web.py              # Web API endpoint tests (12 tests)
  test_integration.py      # Cross-instrument pipeline tests (11 tests)
```

## Development Conventions

- **Python 3.11+**, dependencies: nmrglue, numpy, scipy, matplotlib, anthropic, fastapi
- **TopSpin 5.0.0** examdata at `/opt/topspin5.0.0/examdata/`
- Install: `pip install -e ".[nmr,dev]"`
- Run demos: `python demos/<script>.py` or `python -m device_use demo`
- Run tests: `python -m pytest tests/ -m "not network"` (291 tests)
- CLI: `python -m device_use status` / `instruments` / `demo`
- Web GUI: `./demos/run_web.sh` (port 8420)

## Key Patterns

- **Graceful fallback**: All demos work without API key (cached responses)
- **Loose coupling**: Instruments implement BaseInstrument; tools implement BaseTool
- **Three control modes**: Same instrument, same output, different control paths
- **Streaming**: Brain responses stream via generators (CLI) or SSE (web)

## Git

- Branch: `feat/device-use-mvp`
- Remote: `git@github.com:labclaw/device-use.git`
- Small atomic commits, one logical change per commit
