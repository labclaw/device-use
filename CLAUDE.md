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
  __init__.py              # create_orchestrator() factory
  instruments/
    base.py                # BaseInstrument ABC, ControlMode enum
    nmr/
      adapter.py           # TopSpinAdapter (3 modes: API/GUI/Offline)
      processor.py         # NMR processing pipeline (nmrglue)
      brain.py             # NMRBrain (Claude API + cache fallback)
      demo_cache.py        # Pre-cached expert responses for demos
      visualizer.py        # Publication-quality spectrum plots
      library.py           # Spectral library + fingerprint matching
      gui_automation.py    # Computer Use GUI automation
    plate_reader/
      adapter.py           # PlateReaderAdapter (absorbance/fluorescence)
      models.py            # Well, WellPlate, PlateReading data models
      brain.py             # PlateReaderBrain (Claude API + cache fallback)
      visualizer.py        # 96-well heatmap plots
    template.py            # Copy-and-implement guide for new instruments
  orchestrator.py          # Pipeline + ToolRegistry + Events + Retry/Timeout
  integrations/
    labclaw.py             # LabClaw Layer 1 adapter
    mcp_server.py          # MCP server — Claude Code instrument integration
  cli.py                   # CLI: instruments, status, demo, run, interactive
  tools/
    base.py                # BaseTool ABC
    pubchem.py             # PubChem PUG REST integration
    tooluniverse.py        # Harvard ToolUniverse (600+ tools)
  web/
    app.py                 # FastAPI web GUI (port 8420)

demos/
  lib/
    __init__.py                 # Shared demo infrastructure
    terminal.py                 # ANSI color constants + formatting helpers
    runner.py                   # DemoRunner: shared argparse + connection
    recorder.py                 # DemoRecorder: screenshots + GIF assembly
  01_quickstart.py              # One-line setup, no API key needed
  02_identify.py                # Single compound identification
  03_batch.py                   # Batch analysis + PubChem
  04_dnmr.py                    # Dynamic NMR temperature series
  05_blind_challenge.py         # Blind NMR identification quiz
  06_ai_scientist.py            # Full AI scientist pipeline (flagship)
  07_gui_live.py                # Live GUI operation of TopSpin (showstopper)
  08_pipeline.py                # Orchestrator middleware demo
  09_multi_instrument.py        # NMR + Plate Reader together
  10_lab_report.py              # Raw data → paper-ready report
  11_reaction_monitor.py        # Autonomous reaction monitoring
  12_streaming.py               # Real-time event stream
  13_compare.py                 # Side-by-side spectral comparison
  14_library.py                 # Spectral library fingerprint matching
  15_showcase.py                # All features in one script (showcase)
  16_benchmark.py               # Performance benchmark

tests/
  test_nmr.py              # NMR module tests
  test_plate_reader.py     # Plate reader + brain tests (22 tests)
  test_orchestrator.py     # Pipeline + registry + parallel + retry + hooks (53 tests)
  test_mcp_server.py       # MCP server integration tests (12 tests)
  test_tools.py            # External tool tests
  test_web.py              # Web API endpoint tests (16 tests)
  test_integration.py      # Cross-instrument pipeline tests (11 tests)
```

## Development Conventions

- **Python 3.11+**, dependencies: nmrglue, numpy, scipy, matplotlib, anthropic, fastapi
- **TopSpin 5.0.0** examdata at `/opt/topspin5.0.0/examdata/`
- Install: `pip install -e ".[nmr,dev]"`
- Run demos: `python demos/<script>.py` or `python -m device_use demo`
- Run tests: `python -m pytest tests/` (355 tests)
- CLI: `python -m device_use status` / `instruments` / `demo`
- Web GUI: `./demos/run_web.sh` (port 8420)

## Key Patterns

- **One-line setup**: `from device_use import create_orchestrator; orch = create_orchestrator()`
- **Graceful fallback**: All demos work without API key (cached responses)
- **Loose coupling**: Instruments implement BaseInstrument; tools implement BaseTool
- **Three control modes**: Same instrument, same output, different control paths
- **Streaming**: Brain responses stream via generators (CLI) or SSE (web)
- **Event-driven**: All orchestrator actions emit events for monitoring/audit
- **Retry + timeout**: `PipelineStep(retries=2, timeout_s=10)` for flaky instruments
- **Parallel steps**: `PipelineStep(parallel="group1")` for concurrent execution
- **MCP server**: `python -m device_use.integrations.mcp_server` for Claude Code
- **Scaffold**: `device-use scaffold zeiss-zen` generates a new device package
- **Pipeline viz**: `pipeline.describe()` (plan) and `result.summary()` (results)
- **Middleware hooks**: `orch.before_step(fn)` / `orch.after_step(fn)` for safety/audit
- **Composition**: `Pipeline.compose("name", p1, p2)` for reusable sub-pipelines
- **Spectral library**: `SpectralLibrary.from_examdata()` for peak-fingerprint matching

## Git

- Branch: `feat/device-use-mvp`
- Remote: `git@github.com:labclaw/device-use.git`
- Small atomic commits, one logical change per commit
