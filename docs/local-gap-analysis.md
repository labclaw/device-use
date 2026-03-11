# Local Gap Analysis: What Actually Makes This Hard

## The Real Gap

```
Cloud Side (SOLVED):                    Local Side (THE GAP):
┌──────────────────────┐                ┌──────────────────────┐
│ ToolUniverse ✅       │                │ Screen → Elements  ❓ │
│ K-Dense Skills ✅     │   MCP/HTTP     │ Elements → Actions ❓ │
│ LLM Reasoning ✅      │ ◄──────────► │ Actions → GUI Ops  ❓ │
│ Experiment Design ✅  │                │ GUI Ops → Verify   ❓ │
│ Data Analysis ✅      │                │ Monitor → Complete ❓ │
│ Iteration Logic ✅    │                │ Export → Parse     ❓ │
└──────────────────────┘                └──────────────────────┘
```

Cloud gives us an `ExperimentProtocol` (structured JSON: temperatures, times, well layout, etc.).
We need to turn that into GUI clicks on StepOne Software. That's the entire gap.

---

## The 6 Hard Problems (in priority order)

### Problem 1: Can We Even See the UI Elements?

**StepOne Software v2.x is a .NET / WinForms application** (likely — Applied Biosystems uses standard Windows frameworks).

Before writing any code, we need to answer ONE question:

> **Does `pywinauto` / UI Automation expose StepOne's controls?**

This determines our ENTIRE architecture:

| Scenario | Probability | What It Means |
|----------|-------------|---------------|
| **A: Full UIA coverage** | ~40% | We can use `pywinauto` for almost everything. Template matching as backup. VLM only for error recovery. **Easy mode.** |
| **B: Partial UIA coverage** | ~40% | Standard controls (menus, buttons, text fields) work. Custom controls (96-well plate layout, thermal profile editor) don't. **Hybrid approach needed.** |
| **C: Minimal UIA coverage** | ~20% | Custom UI framework, nothing exposed. Must rely entirely on screenshot + OmniParser + coordinates. **Hard mode.** |

**How to find out: 10 minutes of testing.**

```bash
# On the Windows PC with StepOne Software running:
pip install pywinauto
python -c "
from pywinauto import Desktop
app = Desktop(backend='uia').window(title_re='.*StepOne.*')
app.print_control_identifiers()
"
```

This prints the entire control tree. From that output, we know:
- Which buttons/menus have names → direct automation
- Which controls are custom → need screenshot-based approach
- Whether the 96-well plate grid is a standard DataGrid or custom paint

**This is Day 1, Task 1. Everything else depends on this answer.**

### Problem 2: The 96-Well Plate Layout

The hardest single UI interaction in the entire demo:

```
┌─┬─┬─┬─┬─┬─┬─┬─┬─┬──┬──┬──┐
│ │1│2│3│4│5│6│7│8│9 │10│11│12│
├─┼─┼─┼─┼─┼─┼─┼─┼─┼──┼──┼──┤
│A│●│●│●│ │ │ │ │ │  │  │  │  │  ← Sample 1 (triplicate)
├─┼─┼─┼─┼─┼─┼─┼─┼─┼──┼──┼──┤
│B│●│●│●│ │ │ │ │ │  │  │  │  │  ← Sample 2 (triplicate)
├─┼─┼─┼─┼─┼─┼─┼─┼─┼──┼──┼──┤
│C│○│○│○│ │ │ │ │ │  │  │  │  │  ← NTC (No Template Control)
├─┼─┼─┼─┼─┼─┼─┼─┼─┼──┼──┼──┤
│D│ │ │ │ │ │ │ │ │  │  │  │  │
└─┴─┴─┴─┴─┴─┴─┴─┴─┴──┴──┴──┘
```

Why it's hard:
- 96 small cells in a grid → precise pixel targeting
- Need to select cells, then assign sample names and targets
- Often involves click-drag to select ranges
- Custom painted control (unlikely to have UIA support)

**Simplification for v1 demo:**
- Use ONLY 6-12 wells (not 96) — perfectly valid for a demo
- Use a FIXED layout (always A1-A3, B1-B3, C1-C3)
- Pre-calculate pixel coordinates from a reference screenshot
- Skip "assign by drag" — use right-click menu + keyboard input instead

### Problem 3: OmniParser V2 on Scientific UI

OmniParser was trained on general desktop/web UIs. Scientific instrument software has:
- Dense numeric displays (temperatures, Ct values, cycle counts)
- Custom chart widgets (amplification curves, melt curves)
- Domain-specific iconography (well plate symbols, fluorescence channel icons)
- Small, tightly-packed controls

**Expected accuracy on StepOne Software:**

| Element Type | OmniParser Accuracy (est.) | Fallback |
|-------------|---------------------------|----------|
| Menu items | 90%+ | Template match |
| Buttons (Start Run, etc.) | 85%+ | Template match |
| Text fields | 80%+ | OCR direct |
| Dropdown menus | 75%+ | UIA |
| 96-well grid cells | 30-50% | Fixed coordinates |
| Chart elements | 20-40% | Not needed for operation |
| Tab controls | 85%+ | Template match |

**Key insight: We probably don't need OmniParser for most of the demo.**

For a fixed workflow on known software:
1. Template matching handles ~70% of cases (buttons, tabs, menus)
2. UIA handles text fields and dropdowns (if accessible)
3. Fixed coordinates handle the well plate (for v1)
4. OmniParser is the BACKUP, not the primary

OmniParser becomes essential only when we want to handle UNKNOWN software or UNEXPECTED popups.

### Problem 4: Timing and State Detection

qPCR run: ~1-2 hours. During this time:
- The software shows real-time fluorescence curves
- Status bar shows "Cycle X/40, XX:XX remaining"
- Various dialogs can pop up (lid open warning, temperature error)

**For the demo, we need:**
1. **"Run started" detection**: Screen change after clicking Start Run
2. **"Run complete" detection**: Dialog or status bar change
3. **Progress reporting**: OCR the cycle counter (optional for demo)
4. **Error detection**: Unexpected dialog popup

**Simplification:** For the demo, we can use the StepOne's **Run tab** which shows a clear status indicator. Simple approach:
- After clicking "Start Run", wait for the status indicator to change
- Poll every 30 seconds: screenshot → check for "Complete" text (OCR) or status indicator color change
- Don't need fancy state machine — just OCR/template match for key text strings

### Problem 5: Data Export Pathway

After run completes, getting data out:

```
StepOne Software → File → Export → Save As Dialog → .xlsx file
```

This is actually one of the EASIER parts:
- File menu: standard Windows menu (UIA or keyboard shortcut Ctrl+S / File→Export)
- Save dialog: standard Windows FileDialog → pywinauto handles perfectly
- .xlsx parsing: `openpyxl` / `pandas` — trivial

**StepOne export format:**
- Standard Excel with sheets: "Results", "Amplification Data", "Melt Curve"
- "Results" sheet has: Well, Sample Name, Target, Ct (threshold cycle)
- This is clean, structured data → easy for cloud analysis

### Problem 6: Integration (Local ↔ Cloud)

**Minimum viable integration:**

```
Cloud (Python server)                Local (Python on Windows PC)
┌─────────────────────┐              ┌─────────────────────┐
│ FastAPI server       │    HTTP      │ Requests client     │
│                     │ ◄──────────► │                     │
│ POST /design        │              │ GET /design         │
│ → returns protocol  │              │ → receive protocol  │
│                     │              │ → execute GUI ops   │
│ POST /analyze       │              │ → export data       │
│ → returns analysis  │              │ POST /analyze       │
│                     │              │ → send data         │
│ GET /status         │              │ POST /status        │
│ → returns next step │              │ → report progress   │
└─────────────────────┘              └─────────────────────┘
```

For the demo, we DON'T need MCP. A simple HTTP API is sufficient and much faster to build.

MCP is the right long-term architecture, but for the WOW demo:
- 3 API endpoints on the cloud
- 3 API calls from the local agent
- That's it

**We can wrap this in MCP later without changing the core logic.**

---

## Minimum Viable WOW Demo

### What "wow" actually requires:

The audience needs to see **ONE continuous flow** from AI thought → physical instrument action → data → AI analysis. The "wow" comes from the SEAMLESSNESS, not the complexity.

### The Minimum Loop:

```
┌─────────────────────────────────────────────────────┐
│                    WOW DEMO                          │
│                                                     │
│  1. User types: "Analyze GAPDH expression in my     │
│     hippocampus samples using qPCR"                 │
│                                                     │
│  2. [Cloud — 10 sec] AI designs experiment           │
│     → searches NCBI Gene for GAPDH                  │
│     → generates qPCR protocol                       │
│     → outputs: temp/time/cycles/layout              │
│                                                     │
│  3. [Local — 60 sec] Agent operates StepOne          │
│     → opens software                                │
│     → creates experiment                            │
│     → fills in parameters (from step 2)             │
│     → sets plate layout                             │
│     → clicks "Start Run"                            │
│     → shows real-time curve on screen               │
│                                                     │
│  4. [Wait — skip in demo, show "2 hours later"]      │
│     (or use pre-recorded data for the analysis step) │
│                                                     │
│  5. [Local — 15 sec] Agent exports data              │
│     → File → Export → saves .xlsx                   │
│                                                     │
│  6. [Cloud — 10 sec] AI analyzes results             │
│     → ΔΔCt calculation                              │
│     → generates bar chart                           │
│     → interprets: "GAPDH shows 2.3x upregulation"  │
│     → suggests: "Consider verifying with BDNF as    │
│       additional target gene"                       │
│                                                     │
│  Total visible demo time: ~2 minutes                 │
│  Actual wow moment: Step 3 (watching AI click GUI)  │
└─────────────────────────────────────────────────────┘
```

### The "Time Skip" Problem

The qPCR run takes 1-2 hours. Options for the demo:

| Approach | Wow Factor | Effort |
|----------|-----------|--------|
| **A: Real run, time-lapse** | ★★★★★ | Must wait. Edit the video. |
| **B: Pre-loaded data** | ★★★★ | Agent does setup+start, then we load pre-existing results file for analysis. Audience sees the full flow minus the wait. |
| **C: Simulation mode** | ★★★ | StepOne has a simulation mode (no instrument needed). Run is instant. Less impressive but fully reproducible. |
| **D: Split video** | ★★★★ | Record setup (1 min) + skip + record export/analysis (1 min). Honest and effective. |

**Recommendation: Approach B for live demos, Approach A for the showcase video.**

### What We Can Cut for v1:

| Feature | In v1? | Why |
|---------|--------|-----|
| Multi-instrument (qPCR + microscope) | ❌ | One instrument is wow enough |
| Primer design (K-Dense Primer3) | ❌ | Use pre-designed primers |
| ToolUniverse PubMed search | ✅ | Easy, impressive, already works |
| ToolUniverse NCBI Gene lookup | ✅ | Easy, impressive, already works |
| K-Dense qPCR analysis | ✅ | Core value of the loop |
| Real-time curve monitoring | ❌ | Nice-to-have, not essential for wow |
| Error recovery | ❌ | Don't demo errors |
| Iteration (second round) | ❌ | Mention it verbally, don't need to show it |
| MCP protocol | ❌ | HTTP is fine for demo |
| Web dashboard | ❌ | Terminal output is fine |

---

## Concrete Implementation: The 10-Day Sprint

### Day 1-2: Recon (THE MOST IMPORTANT DAYS)

```python
# recon.py — Run this on the Windows PC with StepOne Software

"""
Day 1 Objective: Answer the 3 critical unknowns
"""

# Test 1: UIA Control Tree
from pywinauto import Desktop
import json

app = Desktop(backend='uia').window(title_re='.*StepOne.*')
# Save full control tree
app.print_control_identifiers(filename='stepone_control_tree.txt')

# Test 2: Screenshot + OmniParser
import mss
from PIL import Image

with mss.mss() as sct:
    monitor = sct.monitors[1]
    img = sct.grab(monitor)
    Image.frombytes('RGB', img.size, img.bgra, 'raw', 'BGRX').save('stepone_screenshot.png')

# Send screenshot to OmniParser → see what it detects
# (OmniParser can run locally or via API)

# Test 3: Simple Automation
from pywinauto import Application
app = Application(backend='uia').connect(title_re='.*StepOne.*')

# Try clicking File menu
try:
    app.window(title_re='.*StepOne.*').menu_select("File->New Experiment")
    print("✅ Menu automation works!")
except Exception as e:
    print(f"❌ Menu automation failed: {e}")
    print("→ Need template matching or coordinate-based approach")

# Test 4: Template Matching Baseline
import pyautogui
# Screenshot a button, try to find it
location = pyautogui.locateOnScreen('templates/start_run_button.png', confidence=0.8)
if location:
    print(f"✅ Template matching works: {location}")
else:
    print("❌ Template matching failed — check resolution/scaling")
```

**Day 1 deliverable:** A report with:
- Full UIA control tree (what's accessible)
- OmniParser detection results on StepOne screenshots
- Template matching accuracy for key UI elements
- Decision: Scenario A, B, or C

### Day 3-5: Core Agent (based on Day 1-2 findings)

```python
# stepone_agent.py — The core GUI automation agent

import asyncio
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional
import pyautogui
import mss
from PIL import Image

class StepOneState(Enum):
    UNKNOWN = "unknown"
    STARTUP = "startup"
    SETUP = "setup"
    PLATE_LAYOUT = "plate_layout"
    RUN_METHOD = "run_method"
    RUNNING = "running"
    COMPLETE = "complete"
    ANALYZING = "analyzing"
    ERROR = "error"

@dataclass
class QpcrProtocol:
    """Structured protocol from cloud brain"""
    experiment_name: str
    experiment_type: str = "Quantitation"  # or "Melt Curve", etc.
    reagent: str = "SYBR Green"
    # Thermal profile
    hold_temp: float = 95.0
    hold_time: str = "10:00"
    denature_temp: float = 95.0
    denature_time: str = "0:15"
    anneal_temp: float = 60.0
    anneal_time: str = "1:00"
    cycles: int = 40
    melt_curve: bool = True
    # Plate layout
    samples: dict = None  # {"A1-A3": "Treatment", "B1-B3": "Control", "C1-C3": "NTC"}
    target_gene: str = "GAPDH"

class StepOneAgent:
    """
    Controls StepOne Software v2.x through GUI automation.

    Strategy (determined by Day 1-2 recon):
    - Primary: pywinauto UIA (for standard controls)
    - Secondary: template matching (for custom controls)
    - Tertiary: fixed coordinates (for well plate grid)
    """

    def __init__(self, templates_dir: Path = Path("templates")):
        self.templates_dir = templates_dir
        self.state = StepOneState.UNKNOWN
        self.screenshot_dir = Path("screenshots")
        self.screenshot_dir.mkdir(exist_ok=True)

        # Will be populated during recon
        self.uia_available = {}  # control_name → bool
        self.well_coordinates = {}  # "A1" → (x, y) pixel coords

    async def capture(self) -> Image.Image:
        """Capture current screen"""
        with mss.mss() as sct:
            img = sct.grab(sct.monitors[1])
            return Image.frombytes('RGB', img.size, img.bgra, 'raw', 'BGRX')

    async def detect_state(self) -> StepOneState:
        """Detect current state of StepOne Software"""
        screenshot = await self.capture()

        # Strategy: check for known visual indicators
        # Option A: OCR-based (look for tab names, status text)
        # Option B: Template matching (check which tab is active)
        # Option C: UIA (read active tab control)

        # For v1: simple template matching
        if self._template_visible("templates/tab_setup_active.png"):
            return StepOneState.SETUP
        elif self._template_visible("templates/tab_run_active.png"):
            return StepOneState.RUNNING
        elif self._template_visible("templates/complete_indicator.png"):
            return StepOneState.COMPLETE

        return StepOneState.UNKNOWN

    def _template_visible(self, template_path: str, confidence: float = 0.8) -> bool:
        """Check if a template image is visible on screen"""
        try:
            location = pyautogui.locateOnScreen(template_path, confidence=confidence)
            return location is not None
        except Exception:
            return False

    async def execute_protocol(self, protocol: QpcrProtocol) -> bool:
        """
        Execute a complete qPCR protocol on StepOne Software.
        This is the core "bridge" — structured data → GUI actions.
        """
        steps = [
            ("Create new experiment", self._create_experiment),
            ("Set experiment type", self._set_experiment_type, protocol),
            ("Configure thermal profile", self._configure_thermal_profile, protocol),
            ("Set plate layout", self._set_plate_layout, protocol),
            ("Start run", self._start_run),
        ]

        for step_name, step_func, *args in steps:
            print(f"  → {step_name}...")

            # Capture before
            before = await self.capture()
            before.save(self.screenshot_dir / f"before_{step_name.replace(' ', '_')}.png")

            # Execute
            success = await step_func(*args)

            if not success:
                print(f"  ✗ Failed at: {step_name}")
                # Capture failure state
                fail = await self.capture()
                fail.save(self.screenshot_dir / f"FAIL_{step_name.replace(' ', '_')}.png")
                return False

            # Capture after
            after = await self.capture()
            after.save(self.screenshot_dir / f"after_{step_name.replace(' ', '_')}.png")

            # Brief pause between steps
            await asyncio.sleep(0.5)
            print(f"  ✓ {step_name}")

        return True

    async def _create_experiment(self) -> bool:
        """File → New Experiment"""
        # Try UIA first
        # try:
        #     app.menu_select("File->New Experiment")
        #     return True
        # except:
        #     pass

        # Fallback: keyboard shortcut
        pyautogui.hotkey('ctrl', 'n')
        await asyncio.sleep(1)  # Wait for dialog

        # Check if "New Experiment" dialog appeared
        return True  # TODO: verify with template/OCR

    async def _set_experiment_type(self, protocol: QpcrProtocol) -> bool:
        """Set experiment type and reagent in setup tab"""
        # TODO: implement based on recon findings
        # Option A (UIA): app.ComboBox('Experiment Type').select(protocol.experiment_type)
        # Option B (template): click dropdown template, then click option
        # Option C (coordinates): click at known dropdown location
        return True

    async def _configure_thermal_profile(self, protocol: QpcrProtocol) -> bool:
        """Set temperatures, times, and cycle count"""
        # This is the data-entry heavy part
        # Fields to fill: hold temp/time, denature temp/time, anneal temp/time, cycles

        # Strategy: Tab through fields + type values
        # OR: Click specific fields + type values
        # Depends on UIA availability

        return True

    async def _set_plate_layout(self, protocol: QpcrProtocol) -> bool:
        """Assign samples to wells"""
        # The hardest part — see Problem 2 analysis
        # v1 approach: use fixed well coordinates from reference screenshot

        if not protocol.samples:
            return True  # Skip if no layout specified

        # Click the "Plate Layout" tab
        # For each sample group:
        #   1. Click wells (using pre-calculated coordinates)
        #   2. Right-click → Assign Target/Sample
        #   3. Type sample name

        return True

    async def _start_run(self) -> bool:
        """Click Start Run and confirm"""
        # Find and click "Start Run" button
        location = pyautogui.locateOnScreen(
            str(self.templates_dir / 'start_run_button.png'),
            confidence=0.8
        )
        if location:
            pyautogui.click(pyautogui.center(location))
            await asyncio.sleep(2)

            # May need to confirm a dialog
            # Check for confirmation dialog and click OK

            return True
        return False

    async def wait_for_completion(self, poll_interval: int = 30) -> bool:
        """Poll until run completes"""
        while True:
            state = await self.detect_state()
            if state == StepOneState.COMPLETE:
                return True
            if state == StepOneState.ERROR:
                return False

            # Optional: OCR the progress text
            # e.g., "Cycle 23/40 - 35 min remaining"

            await asyncio.sleep(poll_interval)

    async def export_data(self, output_path: Path) -> Path:
        """Export results to xlsx"""
        # File → Export → Select format → Save
        pyautogui.hotkey('ctrl', 'e')  # or navigate via menu
        await asyncio.sleep(1)

        # Handle Save dialog (this is a standard Windows dialog)
        # pywinauto handles this perfectly:
        # from pywinauto import Desktop
        # save_dialog = Desktop(backend='uia').window(title='Save As')
        # save_dialog.Edit.set_text(str(output_path))
        # save_dialog.Button('Save').click()

        return output_path
```

### Day 6-7: Cloud Integration (Simple HTTP)

```python
# cloud_client.py — Minimal cloud integration

import httpx
from dataclasses import dataclass, asdict

@dataclass
class CloudDesignResponse:
    protocol: QpcrProtocol
    reasoning: str
    literature_refs: list

@dataclass
class CloudAnalysisResponse:
    ct_values: dict
    fold_changes: dict
    interpretation: str
    next_steps: list
    figures: list  # base64 encoded PNGs

class CloudBrainClient:
    """
    Talks to cloud server running ToolUniverse + K-Dense + LLM.
    For the demo, this can be a FastAPI server on the same network,
    or even on the same machine.
    """

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.client = httpx.AsyncClient(base_url=base_url)

    async def design_experiment(self, query: str) -> CloudDesignResponse:
        """Ask cloud brain to design an experiment"""
        resp = await self.client.post("/api/design", json={"query": query})
        return CloudDesignResponse(**resp.json())

    async def analyze_results(self, data_path: str) -> CloudAnalysisResponse:
        """Send data to cloud for analysis"""
        with open(data_path, 'rb') as f:
            resp = await self.client.post(
                "/api/analyze",
                files={"data": f}
            )
        return CloudAnalysisResponse(**resp.json())

    async def report_status(self, status: dict):
        """Report agent status to cloud"""
        await self.client.post("/api/status", json=status)


# cloud_server.py — FastAPI server (runs on cloud or local)

from fastapi import FastAPI, UploadFile
import anthropic

app = FastAPI()
claude = anthropic.Anthropic()

@app.post("/api/design")
async def design_experiment(request: dict):
    """
    Use Claude + ToolUniverse to design experiment.
    For demo: Claude generates protocol from natural language query.
    """
    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system="""You are a molecular biology expert.
        Design a qPCR experiment protocol.
        Output structured JSON with exact parameters for StepOnePlus.""",
        messages=[{"role": "user", "content": request["query"]}]
    )
    # Parse Claude's response into QpcrProtocol
    # ...
    return protocol

@app.post("/api/analyze")
async def analyze_results(data: UploadFile):
    """
    Analyze qPCR data using K-Dense skills.
    For demo: parse xlsx, calculate ΔΔCt, generate interpretation.
    """
    import pandas as pd

    df = pd.read_excel(data.file, sheet_name="Results")
    ct_values = df[['Well', 'Sample Name', 'Target', 'CT']].to_dict('records')

    # K-Dense analysis or direct Claude analysis
    response = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system="Analyze these qPCR results. Calculate ΔΔCt. Interpret.",
        messages=[{"role": "user", "content": str(ct_values)}]
    )

    return {"analysis": response.content[0].text}
```

### Day 8-10: Integration + Demo Recording

```python
# main.py — The complete demo script

import asyncio
from stepone_agent import StepOneAgent, QpcrProtocol
from cloud_client import CloudBrainClient

async def run_demo():
    """
    THE WOW DEMO — full closed loop
    """
    agent = StepOneAgent()
    cloud = CloudBrainClient()

    print("=" * 60)
    print("Device-Use: Physical AI Scientist Demo")
    print("=" * 60)

    # Step 1: User query → Cloud designs experiment
    query = "Analyze GAPDH expression in hippocampus samples, compare treatment vs control using qPCR"

    print(f"\n📋 User query: {query}")
    print("\n🧠 Cloud Brain designing experiment...")

    design = await cloud.design_experiment(query)
    print(f"   Protocol: {design.protocol}")
    print(f"   Reasoning: {design.reasoning}")

    # Step 2: Local agent operates StepOne Software
    print(f"\n🖥️  Device-Use Agent operating StepOne Software...")

    success = await agent.execute_protocol(design.protocol)

    if not success:
        print("❌ Failed to execute protocol")
        return

    print("✅ qPCR run started!")

    # Step 3: Wait for completion (demo: use pre-loaded data)
    print(f"\n⏳ qPCR running... (1.5 hours)")
    # In real demo: await agent.wait_for_completion()
    # In demo video: show "2 hours later..."

    # Step 4: Export data
    print(f"\n📊 Exporting results...")
    data_path = await agent.export_data(Path("results/experiment_001.xlsx"))

    # Step 5: Cloud analyzes
    print(f"\n🔬 Cloud Brain analyzing results...")
    analysis = await cloud.analyze_results(str(data_path))

    print(f"\n{'=' * 60}")
    print(f"RESULTS")
    print(f"{'=' * 60}")
    print(f"{analysis.interpretation}")
    print(f"\nNext steps: {analysis.next_steps}")
    print(f"\n{'=' * 60}")
    print("🔄 Loop complete. Ready for iteration.")

if __name__ == "__main__":
    asyncio.run(run_demo())
```

---

## What Can We Build WITHOUT the Physical Instrument?

This is critical: you might not have StepOne Software access every day.

### Development Strategy: Build in 3 Environments

```
Environment 1: Your Mac (TODAY)
├── Cloud server (FastAPI + Claude API)
├── Cloud analysis pipeline
├── Agent framework (abstract)
├── Data parsers (xlsx/csv)
├── Integration logic
└── Test with mock UI screenshots

Environment 2: Windows VM or Remote Desktop
├── StepOne Software (demo/simulator mode)
├── pywinauto testing
├── Template library building
├── OmniParser integration
└── Real GUI automation testing

Environment 3: Lab Windows PC (THE REAL THING)
├── StepOne Software + physical instrument
├── Full integration test
├── Demo recording
└── Template calibration
```

**What can be built TODAY on macOS:**

| Component | Can Build Now? | Notes |
|-----------|---------------|-------|
| Cloud server (FastAPI + Claude) | ✅ YES | Full implementation |
| ToolUniverse integration | ✅ YES | MCP client, works anywhere |
| K-Dense skill calls | ✅ YES | MCP client, works anywhere |
| Data parser (xlsx → structured) | ✅ YES | Pure Python |
| Agent framework (abstract classes) | ✅ YES | Platform-independent logic |
| Demo script (main.py) | ✅ YES | Orchestration logic |
| Template matching engine | ⚠️ PARTIAL | Need StepOne screenshots |
| pywinauto automation | ❌ NO | Windows only |
| OmniParser testing | ⚠️ PARTIAL | Can test with screenshots |

**~60% of the code can be written on macOS today.**

### Mock UI for Development

```python
# mock_stepone.py — Simulates StepOne Software for development

import tkinter as tk
from PIL import Image, ImageTk

class MockStepOneSoftware:
    """
    A simplified mock of StepOne Software for testing GUI automation.
    Replicates the key UI elements (tabs, buttons, fields)
    without needing real instrument software.
    """

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("StepOne Software v2.3 [MOCK]")
        self.root.geometry("1024x768")
        self._build_ui()

    def _build_ui(self):
        # Tab bar
        # Experiment type dropdown
        # Temperature fields
        # Well plate grid
        # Start Run button
        # Status bar
        pass

    def run(self):
        self.root.mainloop()
```

This mock lets us:
1. Test the GUI automation code locally
2. Build template images
3. Verify the agent framework
4. Record demo rehearsals

---

## Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|-----------|------------|
| StepOne Software uses custom UI framework with zero UIA | HIGH | 20% | Template matching + OmniParser backup |
| OmniParser can't detect StepOne UI elements | MEDIUM | 30% | Template matching (pre-recorded) is sufficient for demo |
| Well plate interaction requires sub-pixel precision | MEDIUM | 40% | Fixed coordinates + zoom-in screenshot verification |
| StepOne Software version mismatch (v2.2 vs v2.3) | LOW | 20% | Template re-calibration |
| Network issues between local and cloud | LOW | 10% | Can run cloud server locally |
| qPCR run fails during demo | MEDIUM | 15% | Use pre-loaded results file as backup |
| Windows display scaling messes up coordinates | HIGH | 50% | Force 100% DPI, or normalize coordinates |

**Biggest risk: Windows display scaling.** StepOne PCs often run at 100% DPI (standard lab setup), but we MUST verify this on Day 1.

---

## Summary: The Path Forward

```
Week 1 (Days 1-5): RECON + CORE AGENT
├── Day 1: pywinauto recon on StepOne Software [LAB PC]
├── Day 2: Template library + OmniParser test [LAB PC]
├── Day 3-4: Build agent framework + cloud server [MAC]
├── Day 5: First GUI automation test [LAB PC]
│
Week 2 (Days 6-10): INTEGRATION + DEMO
├── Day 6-7: Cloud integration (FastAPI + Claude) [MAC]
├── Day 8: Full pipeline test [LAB PC]
├── Day 9: Demo recording + polish [LAB PC]
├── Day 10: Backup paths + edge cases [MAC + LAB PC]
│
Deliverable: 2-minute demo video showing complete AI → instrument → data → analysis loop
```

The SINGLE most important action: **Run the pywinauto recon script on the lab PC.** That 10-minute test determines 80% of our architecture decisions.
