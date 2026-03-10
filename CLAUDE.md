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
  orchestrator.py        # Pipeline + ToolRegistry + Events
  tools/
    base.py              # BaseTool ABC
    pubchem.py           # PubChem PUG REST integration
    tooluniverse.py      # Harvard ToolUniverse (600+ tools)
  web/
    app.py               # FastAPI web GUI (port 8420)

demos/
  topspin_identify.py       # Single compound identification
  topspin_dnmr.py           # Dynamic NMR temperature series
  topspin_batch.py          # Batch analysis + PubChem
  topspin_blind_challenge.py # Blind NMR identification quiz
  topspin_ai_scientist.py   # Full AI scientist pipeline (flagship)
  run_web.sh                # Web GUI launcher

tests/
  test_nmr.py            # NMR module tests (25 tests)
  test_tools.py          # Tool integration tests
```

## Development Conventions

- **Python 3.11+**, dependencies: nmrglue, numpy, scipy, matplotlib, anthropic, fastapi
- **TopSpin 5.0.0** examdata at `/opt/topspin5.0.0/examdata/`
- Run demos with: `PYTHONPATH=src .venv/bin/python demos/<script>.py`
- Run tests with: `PYTHONPATH=src .venv/bin/python -m pytest tests/test_nmr.py tests/test_tools.py -m "not network"`
- Web GUI: `./demos/run_web.sh` or `PYTHONPATH=src uvicorn device_use.web.app:app --port 8420`

## Key Patterns

- **Graceful fallback**: All demos work without API key (cached responses)
- **Loose coupling**: Instruments implement BaseInstrument; tools implement BaseTool
- **Three control modes**: Same instrument, same output, different control paths
- **Streaming**: Brain responses stream via generators (CLI) or SSE (web)

## Git

- Branch: `feat/device-use-mvp`
- Remote: `git@github.com:labclaw/device-use.git`
- Small atomic commits, one logical change per commit
