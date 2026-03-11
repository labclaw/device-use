# device-use

**Like [browser-use](https://github.com/browser-use/browser-use), but for scientific instruments.**

Let AI agents operate any lab device through its GUI software — no API needed.

```
Your protocol: "Read OD600 for wells A1-H12"
    → Agent sees plate reader software on screen
    → Plans click sequence from device profile
    → Executes with safety checks
    → Reads and returns results
    → Logs everything for reproducibility
```

## The Problem

Self-driving lab papers assume instruments have APIs. Most don't.

```
Lab instrument software reality:

  Has API (~25%)              GUI-only (~40-50%)              Macro/script (~25-30%)
  ──────────────              ────────────────────            ─────────────────────
  Micro-Manager               cellSens (Olympus)              NIS-Elements (Nikon)
  MinKNOW (ONT)               Gen5 (BioTek/Agilent)           FlowJo
  BaseSpace (Illumina)        FACSDiva (BD)                   OPUS (Bruker)
  SoftMax Pro                 Kaluza (Beckman)                LAS X (Leica)
                              QuantStudio (Thermo)
                              pCLAMP (Molecular Devices)
                              Most legacy instruments

  SDL papers cover this →     ← Nobody covers this            ← Fragile workarounds
```

**~40-50% of lab instruments can only be operated by a human clicking through a GUI.** This is the biggest bottleneck in lab automation — not the AI, not the robotics, but the software interface.

## How It Works

device-use treats instrument software the same way browser-use treats web pages: the agent sees the screen, understands the state, and acts like a human operator would.

```
┌──────────────────────────────────────────────────────────────┐
│                     device-use                               │
│                                                              │
│  ┌──────────┐    ┌───────────┐    ┌───────────────────────┐  │
│  │ OBSERVE  │    │   PLAN    │    │       EXECUTE         │  │
│  │          │    │           │    │                       │  │
│  │ Screen   │───▶│ Protocol  │───▶│  Action + Safety      │  │
│  │ capture  │    │ to action │    │  + Verify feedback    │  │
│  │ + VLM    │    │ sequence  │    │  + Emergency stop     │  │
│  └──────────┘    └───────────┘    └───────────────────────┘  │
│       ▲                                      │               │
│       └──────────── feedback loop ───────────┘               │
└──────────────────────────────────────────────────────────────┘
        ▲                                      │
        │ semantic command                     │ physical control
        │ "read plate at 600nm"                ▼
┌───────────────┐                    ┌──────────────────┐
│  LabClaw L3   │                    │  Instrument GUI  │
│  ENGINE       │                    │  (Windows/macOS) │
└───────────────┘                    └──────────────────┘
```

Three components:

1. **Observer** — captures the screen and uses a VLM to understand instrument state (what mode is active, what parameters are set, what the readout shows)
2. **Planner** — translates a semantic command + device profile into a safe action sequence
3. **Executor** — performs mouse/keyboard actions with continuous verification and safety constraints

## Why Not Just Use Computer Use?

Claude Computer Use, UI-TARS, Agent-S3 all score ~72% on OSWorld. But lab instruments are not desktop apps:

| Generic computer use | device-use |
|---|---|
| Wrong click → refresh page | Wrong click → damaged sample, broken $500K instrument |
| No time constraints | Strict timing (reagent incubation, exposure windows) |
| Stateless (each page is independent) | Stateful (instrument configuration persists across operations) |
| Standard UI widgets | Specialized controls (waveform plots, heatmaps, 3D viewers, custom sliders) |
| Error = retry | Error = may be irreversible |
| No physical consequence | Controls physical hardware |

device-use adds the **safety layer**, **device profiles**, and **protocol awareness** that generic computer use lacks.

## Device Profiles

Every instrument gets a profile — a structured description of its software interface, capabilities, and constraints.

```yaml
# profiles/biotek-gen5.yaml
name: BioTek Gen5
vendor: Agilent (BioTek)
category: plate-reader
platform: windows

capabilities:
  - absorbance
  - fluorescence
  - luminescence

screens:
  main:
    description: "Main experiment window"
    elements:
      read-button: { type: button, label: "Read", location: toolbar }
      protocol-panel: { type: panel, location: left }
      plate-view: { type: grid, location: center, rows: 8, cols: 12 }

workflows:
  read-plate:
    steps:
      - navigate: protocol-panel
      - set: wavelength → {wavelength}
      - set: plate-type → {plate_type}
      - click: read-button
      - wait: read-complete indicator
      - extract: plate-view → results

safety:
  max-temperature: 45  # celsius
  requires-plate-loaded: true
  no-uv-without-cover: true
```

Profiles are community-contributed. Start with the instruments in your lab, share what works.

## Safety Model

Safety is not optional — it's the core differentiator.

```
┌─────────────────────────────────────────┐
│           SAFETY LAYERS                 │
│                                         │
│  L1  Action whitelist                   │
│      Only protocol-defined actions      │
│                                         │
│  L2  Parameter bounds                   │
│      Temperature, pressure, voltage,    │
│      motion range, exposure time        │
│                                         │
│  L3  State verification                 │
│      Confirm instrument responded       │
│      correctly before next step         │
│                                         │
│  L4  Human confirmation gate            │
│      High-risk actions require          │
│      explicit human approval            │
│                                         │
│  L5  Emergency stop                     │
│      Hardware kill switch, always       │
│      available, overrides everything    │
│                                         │
└─────────────────────────────────────────┘
```

## Quick Start

```bash
pip install device-use

# Initialize with a device profile
device-use init --profile biotek-gen5

# Run a protocol step
device-use run "Read absorbance at 600nm for all wells"

# Interactive mode (agent watches screen, you give commands)
device-use interactive --profile zeiss-zen
```

### Python API

```python
from device_use import DeviceAgent, load_profile

profile = load_profile("biotek-gen5")
agent = DeviceAgent(profile=profile, safety_level="strict")

# Agent sees the screen and executes
result = agent.execute("Read plate at OD600, wells A1-H12")

# Result includes the data + full action log
print(result.data)       # plate readings
print(result.actions)    # every click, keystroke, verification
print(result.duration)   # how long it took
```

### With LabClaw

```python
from labclaw.hardware import DeviceLayer
from device_use import DeviceAgent

# device-use is LabClaw's Layer 1 (HARDWARE) implementation
layer = DeviceLayer(
    agents={
        "plate-reader": DeviceAgent(profile="biotek-gen5"),
        "microscope": DeviceAgent(profile="zeiss-zen"),
    }
)

# LabClaw ENGINE sends semantic commands
# device-use translates to GUI actions
layer.execute("plate-reader", "read OD600 all wells")
```

## Supported Vision Backends

device-use is model-agnostic. Use any VLM that can understand screenshots:

| Backend | How | Best for |
|---|---|---|
| Claude Computer Use | Anthropic API with `computer-use` tool | Highest accuracy (OSWorld 72.5%) |
| UI-TARS | Local model (7B-72B) | On-premise / air-gapped labs |
| GPT-4o + OmniParser | Screenshot → structured elements → GPT-4o | Good balance of speed and accuracy |
| Qwen2.5-VL + GUI-Actor | Open-source VLM + grounding head | Fully open-source pipeline |
| Accessibility API | Windows UIA / macOS Accessibility | Fastest, no VLM needed (when supported) |

## Roadmap

- [ ] Core framework (observer, planner, executor, safety)
- [ ] First device profiles (Gen5, ZEN, NIS-Elements, FlowJo)
- [ ] Safety model implementation with emergency stop
- [ ] Claude Computer Use backend
- [ ] UI-TARS backend (local, air-gapped)
- [ ] Protocol → action sequence compiler
- [ ] LabClaw Layer 1 integration
- [ ] Device profile contribution guide
- [ ] Benchmark: instrument operation accuracy across 10 common lab tasks
- [ ] Windows + macOS support

## Related Work

**GUI Agents (generic desktop):**
- [Anthropic Computer Use](https://docs.anthropic.com/en/docs/agents-and-tools/computer-use) — 72.5% on OSWorld
- [Agent-S3](https://github.com/simular-ai/Agent-S) — 72.6% on OSWorld (first to surpass human-level)
- [UI-TARS](https://github.com/bytedance/UI-TARS) — end-to-end native GUI agent model
- [Microsoft UFO](https://github.com/microsoft/UFO) — Windows UI automation framework
- [OmniParser](https://github.com/microsoft/OmniParser) — pure-vision screen parsing

**Browser agents:**
- [browser-use](https://github.com/browser-use/browser-use) — the direct inspiration for this project
- [Playwright MCP](https://github.com/microsoft/playwright-mcp) — accessibility-tree based browser control

**Lab automation:**
- [AILA](https://www.nature.com/articles/s41467-025-64105-7) — LLM agent for atomic force microscopy (Nature Comms 2025)
- [Coscientist](https://www.nature.com/articles/s41586-023-06792-0) — autonomous chemical synthesis (Nature 2023)
- [Practical Laboratory Automation with AutoIt](https://www.wiley.com/en-us/Practical+Laboratory+Automation) — the pre-AI approach (Wiley, 2016)

**Standards:**
- [SiLA2](https://sila-standard.com/) — lab automation interoperability standard
- [OPC UA LADS](https://opcfoundation.org/markets-collaboration/lads/) — instrument information models

## Architecture

```
device-use/
├── src/device_use/
│   ├── core/
│   │   ├── observer.py       # Screen capture + VLM understanding
│   │   ├── planner.py        # Protocol → action sequence
│   │   ├── executor.py       # Mouse/keyboard with verification
│   │   └── safety.py         # Multi-layer safety model
│   ├── backends/
│   │   ├── claude.py          # Anthropic Computer Use
│   │   ├── uitars.py          # UI-TARS local model
│   │   ├── omniparser.py      # OmniParser + VLM
│   │   └── accessibility.py   # OS accessibility APIs
│   ├── profiles/
│   │   └── loader.py          # YAML profile loading + validation
│   └── integrations/
│       └── labclaw.py         # LabClaw Layer 1 adapter
├── profiles/                   # Community-contributed device profiles
│   ├── plate-readers/
│   ├── microscopes/
│   ├── flow-cytometers/
│   └── ...
└── tests/
```

## Working Demos (Multi-Instrument MVP)

Two instrument types, 11 demos, 302 tests — all running without API keys:

```bash
# Setup
pip install -e ".[nmr,dev]"

# Start here
python demos/quickstart.py                # 30-second intro, no setup needed

# NMR demos (Bruker TopSpin)
python demos/topspin_identify.py --dataset exam_CMCse_1 --formula C13H20O
python demos/topspin_dnmr.py              # Temperature-dependent dynamics
python demos/topspin_batch.py             # 8 compounds + PubChem
python demos/topspin_blind_challenge.py   # AI identifies unknowns from peaks alone
python demos/topspin_ai_scientist.py      # Full AI scientist pipeline
python demos/topspin_pipeline.py          # Orchestrator middleware demo

# Multi-instrument demos
python demos/multi_instrument_demo.py     # Two instruments, same Orchestrator
python demos/lab_report_demo.py           # Raw data → paper-ready report
python demos/streaming_demo.py            # Real-time event stream
python demos/topspin_compare.py           # Side-by-side spectral comparison

# Web GUI
./demos/run_web.sh                        # http://localhost:8420
```

**Architecture** — same abstraction, different instruments:
```
Cloud Brain (Claude AI)
        |
   Orchestrator (pipeline + registry + events)
        |                       |
   TopSpin NMR            Plate Reader
    |     |    |           |     |    |
  API   GUI  Offline    API   GUI  Offline
```

**External tools**: PubChem (NCBI) + ToolUniverse (Harvard, 600+ scientific tools)

See [demos/README.md](demos/README.md) for full documentation.

## Contributing

We need device profiles for every instrument in every lab. If you use a GUI-only instrument, your profile helps every lab with the same device.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the profile format and submission process.

## License

Apache 2.0

---

Part of [LabClaw](https://labclaw.org) — open-source infrastructure for AI-native scientific labs.

Built by [Agent Next](https://agent-next.com) — exploring the limits of autonomous agents.
