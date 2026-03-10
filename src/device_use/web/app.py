"""FastAPI web application for device-use NMR demo.

Provides a browser UI for the same pipeline as the CLI:
  1. List datasets
  2. Process NMR data
  3. Visualize spectrum
  4. AI analysis (streaming)
  5. PubChem cross-reference

Run:
    python -m device_use.web.app
    # or: uvicorn device_use.web.app:app --reload --port 8420
"""

from __future__ import annotations

import base64
import io
import json
import logging
import sys
import time
import warnings
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

warnings.filterwarnings("ignore", category=UserWarning, module="nmrglue")
warnings.filterwarnings("ignore", category=RuntimeWarning, module="scipy")

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from device_use.instruments.nmr.adapter import TopSpinAdapter
from device_use.instruments.nmr.processor import NMRProcessor
from device_use.instruments.plate_reader import PlateReaderAdapter
from device_use.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Device-Use | AI Scientist",
    description="ROS for Lab Instruments — NMR Demo",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singletons
_adapter: TopSpinAdapter | None = None
_orchestrator: Orchestrator | None = None


def _get_adapter() -> TopSpinAdapter:
    global _adapter
    if _adapter is None:
        _adapter = TopSpinAdapter()
        _adapter.connect()
    return _adapter


def _get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
        _orchestrator.register(_get_adapter())
        _orchestrator.register(PlateReaderAdapter())
    return _orchestrator


# ── API Endpoints ──────────────────────────────────────────────

@app.get("/api/status")
def get_status():
    orch = _get_orchestrator()
    adapter = _get_adapter()
    info = adapter.info()

    instruments = orch.registry.list_instruments()
    tools = orch.registry.list_tools()

    return {
        "instrument": info.name,
        "vendor": info.vendor,
        "version": info.version,
        "mode": adapter.mode.value,
        "connected": adapter.connected,
        "supported_modes": [m.value for m in info.supported_modes],
        "orchestrator": {
            "instruments": len(instruments),
            "registered_tools": [t.name for t in tools],
        },
    }


@app.get("/api/datasets")
def list_datasets():
    adapter = _get_adapter()
    return adapter.list_datasets()


@app.get("/api/process/{sample}/{expno}")
def process_dataset(sample: str, expno: int):
    adapter = _get_adapter()
    datasets = adapter.list_datasets()

    # Find matching dataset
    match = None
    for ds in datasets:
        if ds["sample"] == sample and ds["expno"] == expno:
            match = ds
            break
    if not match:
        raise HTTPException(404, f"Dataset {sample}/{expno} not found")

    t0 = time.time()
    spectrum = adapter.process(match["path"])
    dt = time.time() - t0

    # Generate plot as base64 PNG
    from device_use.instruments.nmr.visualizer import plot_spectrum

    png_bytes = plot_spectrum(spectrum, output_path=None)
    plot_b64 = base64.b64encode(png_bytes).decode()

    # Peak list
    max_int = max(p.intensity for p in spectrum.peaks) if spectrum.peaks else 1.0
    peaks = [
        {
            "ppm": round(p.ppm, 3),
            "intensity": round(p.intensity / max_int * 100, 1),
        }
        for p in spectrum.peaks
    ]

    return {
        "sample": sample,
        "expno": expno,
        "title": spectrum.title,
        "nucleus": spectrum.nucleus,
        "solvent": spectrum.solvent,
        "frequency_mhz": round(spectrum.frequency_mhz, 1),
        "num_peaks": len(spectrum.peaks),
        "peaks": peaks,
        "plot_base64": plot_b64,
        "processing_time_s": round(dt, 2),
    }


@app.get("/api/analyze/{sample}/{expno}")
def analyze_stream(sample: str, expno: int, formula: str = ""):
    """Stream AI analysis as Server-Sent Events."""
    adapter = _get_adapter()
    datasets = adapter.list_datasets()

    match = None
    for ds in datasets:
        if ds["sample"] == sample and ds["expno"] == expno:
            match = ds
            break
    if not match:
        raise HTTPException(404, f"Dataset {sample}/{expno} not found")

    spectrum = adapter.process(match["path"])

    from device_use.instruments.nmr.brain import NMRBrain

    brain = NMRBrain()

    def event_stream():
        yield f"data: {json.dumps({'type': 'start'})}\n\n"
        t0 = time.time()
        try:
            for chunk in brain.interpret_spectrum(
                spectrum,
                molecular_formula=formula or None,
                stream=True,
            ):
                yield f"data: {json.dumps({'type': 'chunk', 'text': chunk})}\n\n"
            dt = time.time() - t0
            yield f"data: {json.dumps({'type': 'done', 'time_s': round(dt, 1)})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/pubchem/{name}")
def pubchem_lookup(name: str):
    """Look up a compound on PubChem."""
    from device_use.tools.pubchem import PubChemError, PubChemTool

    tool = PubChemTool()
    try:
        props = tool.lookup_by_name(name)
        return props
    except PubChemError as e:
        raise HTTPException(404, str(e))


@app.get("/api/tools")
def list_tools():
    """List available external tools."""
    from device_use.tools.tooluniverse import get_available_tools

    tools = get_available_tools()
    return {
        "tools": [
            {"name": t.name, "description": t.description}
            for t in tools
        ],
        "count": len(tools),
    }


@app.get("/api/architecture")
def get_architecture():
    """Return the device-use architecture overview."""
    from device_use.tools.tooluniverse import _TU_AVAILABLE

    return {
        "layers": [
            {"name": "Cloud Brain", "components": ["Claude AI", "GPT", "Gemini"],
             "status": "active"},
            {"name": "device-use middleware", "components": ["Orchestrator", "Event System"],
             "status": "active"},
            {"name": "Instruments", "components": [
                {"name": "TopSpin NMR", "modes": ["API", "GUI", "Offline"], "status": "connected"},
                {"name": "Plate Reader", "modes": ["Offline", "API", "GUI"], "status": "connected"},
            ]},
            {"name": "Tools", "components": [
                {"name": "PubChem", "status": "active"},
                {"name": "ToolUniverse", "status": "active" if _TU_AVAILABLE else "available"},
            ]},
        ],
    }


# ── Plate Reader API ──────────────────────────────────────────

@app.get("/api/plate-reader/datasets")
def plate_reader_datasets():
    """List plate reader datasets."""
    orch = _get_orchestrator()
    reader = orch.registry.get_instrument("PlateReader")
    if not reader:
        raise HTTPException(404, "PlateReader not registered")
    return reader.list_datasets()


@app.get("/api/plate-reader/process/{name}")
def plate_reader_process(name: str):
    """Process a plate reader dataset and return well data."""
    orch = _get_orchestrator()
    reader = orch.registry.get_instrument("PlateReader")
    if not reader:
        raise HTTPException(404, "PlateReader not registered")

    t0 = time.time()
    reading = reader.process(name)
    dt = time.time() - t0

    # Build heatmap data (8 rows x 12 cols)
    rows = sorted(set(w.row for w in reading.plate.wells))
    cols = sorted(set(w.col for w in reading.plate.wells))
    heatmap = []
    for r in rows:
        row_data = []
        for c in cols:
            well = reading.plate.get_well(f"{r}{c}")
            row_data.append(round(well.value, 4) if well else 0)
        heatmap.append(row_data)

    return {
        "name": name,
        "protocol": reading.protocol,
        "mode": reading.mode.value,
        "wavelength_nm": reading.wavelength_nm,
        "wells": len(reading.plate.wells),
        "rows": rows,
        "cols": cols,
        "heatmap": heatmap,
        "metadata": reading.metadata,
        "processing_time_s": round(dt, 4),
    }


# ── Frontend ──────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index():
    return _INDEX_HTML


_INDEX_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Device-Use | AI Scientist</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<style>
  :root {
    --bg: #0a0a1a;
    --surface: #12122a;
    --border: #2a2a4a;
    --text: #e0e0f0;
    --dim: #8888aa;
    --accent: #00d4ff;
    --green: #00ff88;
    --magenta: #ff44cc;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: 'SF Mono', 'Fira Code', monospace;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
  }
  .container { max-width: 1200px; margin: 0 auto; padding: 2rem; }

  /* Header */
  .header {
    text-align: center;
    padding: 2rem 0;
    border-bottom: 1px solid var(--border);
    margin-bottom: 2rem;
  }
  .header h1 {
    font-size: 2rem;
    background: linear-gradient(135deg, var(--accent), var(--magenta));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
  }
  .header .subtitle { color: var(--dim); font-size: 0.9rem; margin-top: 0.5rem; }

  /* Status bar */
  .status-bar {
    display: flex;
    gap: 1.5rem;
    padding: 1rem;
    background: var(--surface);
    border-radius: 8px;
    border: 1px solid var(--border);
    margin-bottom: 2rem;
    font-size: 0.85rem;
  }
  .status-item { display: flex; gap: 0.5rem; align-items: center; }
  .status-dot { width: 8px; height: 8px; border-radius: 50%; }
  .dot-green { background: var(--green); }
  .dot-yellow { background: #ffaa00; }

  /* Dataset grid */
  .datasets {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 1rem;
    margin-bottom: 2rem;
  }
  .dataset-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.2rem;
    cursor: pointer;
    transition: all 0.2s;
  }
  .dataset-card:hover {
    border-color: var(--accent);
    transform: translateY(-2px);
    box-shadow: 0 4px 20px rgba(0, 212, 255, 0.1);
  }
  .dataset-card.active {
    border-color: var(--accent);
    background: rgba(0, 212, 255, 0.05);
  }
  .dataset-card .name { font-weight: bold; font-size: 1rem; }
  .dataset-card .title { color: var(--dim); font-size: 0.8rem; margin-top: 0.3rem; }

  /* Result panel */
  .result-panel {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.5rem;
    display: none;
  }
  .result-panel.visible { display: block; }

  .result-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid var(--border);
  }

  /* Spectrum image */
  .spectrum-img {
    width: 100%;
    border-radius: 8px;
    margin: 1rem 0;
    background: white;
  }

  /* Peak table */
  .peak-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.85rem;
    margin: 1rem 0;
  }
  .peak-table th {
    text-align: left;
    padding: 0.5rem;
    border-bottom: 2px solid var(--border);
    color: var(--accent);
  }
  .peak-table td {
    padding: 0.5rem;
    border-bottom: 1px solid var(--border);
  }
  .peak-bar {
    height: 12px;
    background: linear-gradient(90deg, var(--accent), var(--magenta));
    border-radius: 2px;
  }

  /* AI Analysis */
  .ai-panel {
    background: rgba(0, 212, 255, 0.03);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 1.5rem;
    margin-top: 1rem;
    line-height: 1.6;
    font-size: 0.9rem;
    max-height: 600px;
    overflow-y: auto;
  }
  .ai-panel h2 { color: var(--accent); margin: 1rem 0 0.5rem; font-size: 1.1rem; }
  .ai-panel h3 { color: var(--green); margin: 0.8rem 0 0.4rem; font-size: 0.95rem; }
  .ai-panel table { border-collapse: collapse; width: 100%; margin: 0.5rem 0; font-size: 0.8rem; }
  .ai-panel th { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 2px solid var(--border); color: var(--accent); }
  .ai-panel td { padding: 0.4rem 0.6rem; border-bottom: 1px solid var(--border); }
  .ai-panel strong { color: var(--green); }
  .ai-panel code { background: rgba(255,255,255,0.05); padding: 0.1rem 0.3rem; border-radius: 3px; font-size: 0.85em; }
  .ai-panel ul, .ai-panel ol { margin: 0.3rem 0; padding-left: 1.5rem; }
  .ai-panel li { margin: 0.2rem 0; }
  .ai-panel p { margin: 0.4rem 0; }

  /* Buttons */
  .btn {
    padding: 0.7rem 1.5rem;
    border: 1px solid var(--accent);
    background: transparent;
    color: var(--accent);
    border-radius: 6px;
    cursor: pointer;
    font-family: inherit;
    font-size: 0.9rem;
    transition: all 0.2s;
  }
  .btn:hover {
    background: var(--accent);
    color: var(--bg);
  }
  .btn:disabled {
    opacity: 0.4;
    cursor: not-allowed;
  }
  .btn-row { display: flex; gap: 1rem; margin-top: 1rem; }

  /* Loading */
  .loading { color: var(--dim); animation: pulse 1.5s infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

  /* Metadata */
  .meta-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 1rem;
    margin: 1rem 0;
  }
  .meta-item { font-size: 0.85rem; }
  .meta-label { color: var(--dim); }
  .meta-value { font-weight: bold; color: var(--green); }

  /* Heatmap */
  .heatmap { display: inline-block; }
  .heatmap-row { display: flex; align-items: center; }
  .heatmap-cell {
    width: 38px; height: 38px;
    border: 1px solid var(--bg);
    border-radius: 4px;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.6rem; color: rgba(255,255,255,0.7);
    cursor: default; transition: transform 0.1s;
  }
  .heatmap-cell:hover { transform: scale(1.3); z-index: 1; }
  .heatmap-label {
    width: 24px; text-align: center;
    font-size: 0.75rem; color: var(--dim);
  }
  .heatmap-col-labels { display: flex; margin-left: 24px; }
  .heatmap-col-label {
    width: 38px; text-align: center;
    font-size: 0.7rem; color: var(--dim);
  }
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>DEVICE-USE</h1>
    <div class="subtitle">ROS for Lab Instruments — AI meets Physical Science</div>
    <div class="subtitle" style="margin-top: 0.3rem; font-size: 0.75rem; opacity: 0.5;">Cloud Brain ↔ device-use middleware ↔ TopSpin · Plate Reader · PubChem · ToolUniverse</div>
  </div>

  <div class="status-bar" id="statusBar">
    <div class="status-item">
      <div class="status-dot dot-yellow" id="statusDot"></div>
      <span id="statusText">Connecting...</span>
    </div>
  </div>

  <h3 style="margin-bottom: 1rem; color: var(--dim);">Select a Dataset</h3>
  <div class="datasets" id="datasets"></div>

  <div class="result-panel" id="resultPanel">
    <div class="result-header">
      <div>
        <h2 id="resultTitle" style="color: var(--accent);"></h2>
        <span id="resultSubtitle" style="color: var(--dim); font-size: 0.85rem;"></span>
      </div>
      <div class="btn-row">
        <button class="btn" id="btnAnalyze" onclick="runAnalysis()">AI Analysis</button>
        <button class="btn" id="btnPubchem" onclick="runPubchem()">PubChem</button>
        <button class="btn" id="btnTools" onclick="showTools()">Tools</button>
      </div>
    </div>

    <div class="meta-grid" id="metaGrid"></div>

    <img class="spectrum-img" id="spectrumImg" style="display:none;" />

    <h3 style="margin: 1rem 0 0.5rem; color: var(--dim);">Peak List</h3>
    <table class="peak-table" id="peakTable">
      <thead><tr><th>δ (ppm)</th><th>Rel. Intensity</th><th></th></tr></thead>
      <tbody></tbody>
    </table>

    <div class="ai-panel" id="aiPanel" style="display:none;"></div>
  </div>

  <!-- Plate Reader Section -->
  <h3 style="margin: 2rem 0 1rem; color: var(--dim);">Plate Reader</h3>
  <div class="datasets" id="plateDatasets"></div>

  <div class="result-panel" id="platePanel">
    <div class="result-header">
      <div>
        <h2 id="plateTitle" style="color: var(--magenta);"></h2>
        <span id="plateSubtitle" style="color: var(--dim); font-size: 0.85rem;"></span>
      </div>
    </div>
    <div class="meta-grid" id="plateMeta"></div>
    <div id="plateHeatmap" style="margin: 1rem 0;"></div>
  </div>
</div>

<script>
let currentSample = null;
let currentExpno = null;
let currentTitle = '';

async function init() {
  // Get instrument status
  try {
    const res = await fetch('/api/status');
    const status = await res.json();
    document.getElementById('statusDot').className = 'status-dot dot-green';
    document.getElementById('statusText').textContent =
      `${status.instrument} ${status.version} | ${status.mode.toUpperCase()} mode`;
  } catch (e) {
    document.getElementById('statusText').textContent = 'Connection failed';
  }

  // Load NMR datasets
  try {
    const res = await fetch('/api/datasets');
    const datasets = await res.json();
    const container = document.getElementById('datasets');
    datasets.forEach(ds => {
      const card = document.createElement('div');
      card.className = 'dataset-card';
      card.innerHTML = `
        <div class="name">${ds.sample}/${ds.expno}</div>
        <div class="title">${ds.title || 'No title'}</div>
      `;
      card.onclick = () => selectDataset(ds.sample, ds.expno, ds.title);
      container.appendChild(card);
    });
  } catch (e) {
    console.error('Failed to load NMR datasets:', e);
  }

  // Load plate reader datasets
  try {
    const res = await fetch('/api/plate-reader/datasets');
    const datasets = await res.json();
    const container = document.getElementById('plateDatasets');
    datasets.forEach(ds => {
      const card = document.createElement('div');
      card.className = 'dataset-card';
      card.innerHTML = `
        <div class="name">${ds.name}</div>
        <div class="title">${ds.protocol} · ${ds.mode} · ${ds.wavelength_nm}nm</div>
      `;
      card.onclick = () => selectPlate(ds.name);
      container.appendChild(card);
    });
  } catch (e) {
    console.error('Failed to load plate reader datasets:', e);
  }
}

async function selectDataset(sample, expno, title) {
  currentSample = sample;
  currentExpno = expno;
  currentTitle = title;

  // Highlight active card
  document.querySelectorAll('.dataset-card').forEach(c => c.classList.remove('active'));
  event.currentTarget.classList.add('active');

  const panel = document.getElementById('resultPanel');
  panel.classList.add('visible');
  document.getElementById('resultTitle').textContent = `${sample}/${expno}`;
  document.getElementById('resultSubtitle').textContent = title;
  document.getElementById('aiPanel').style.display = 'none';

  // Process
  document.getElementById('metaGrid').innerHTML = '<span class="loading">Processing...</span>';
  document.getElementById('spectrumImg').style.display = 'none';
  document.getElementById('peakTable').querySelector('tbody').innerHTML = '';

  try {
    const res = await fetch(`/api/process/${sample}/${expno}`);
    const data = await res.json();

    // Metadata
    document.getElementById('metaGrid').innerHTML = `
      <div class="meta-item"><div class="meta-label">Frequency</div><div class="meta-value">${data.frequency_mhz} MHz</div></div>
      <div class="meta-item"><div class="meta-label">Nucleus</div><div class="meta-value">${data.nucleus}</div></div>
      <div class="meta-item"><div class="meta-label">Solvent</div><div class="meta-value">${data.solvent}</div></div>
      <div class="meta-item"><div class="meta-label">Peaks</div><div class="meta-value">${data.num_peaks}</div></div>
      <div class="meta-item"><div class="meta-label">Points</div><div class="meta-value">65,536</div></div>
      <div class="meta-item"><div class="meta-label">Time</div><div class="meta-value">${data.processing_time_s}s</div></div>
    `;

    // Spectrum plot
    const img = document.getElementById('spectrumImg');
    img.src = 'data:image/png;base64,' + data.plot_base64;
    img.style.display = 'block';

    // Peak table
    const tbody = document.getElementById('peakTable').querySelector('tbody');
    tbody.innerHTML = data.peaks.map(p => `
      <tr>
        <td>${p.ppm.toFixed(3)}</td>
        <td>${p.intensity.toFixed(1)}%</td>
        <td><div class="peak-bar" style="width: ${p.intensity}%"></div></td>
      </tr>
    `).join('');
  } catch (e) {
    document.getElementById('metaGrid').innerHTML = '<span style="color:red;">Processing failed</span>';
  }
}

async function runAnalysis() {
  if (!currentSample) return;

  const panel = document.getElementById('aiPanel');
  panel.style.display = 'block';
  panel.innerHTML = '<span class="loading">Claude is analyzing the spectrum...</span>';
  document.getElementById('btnAnalyze').disabled = true;

  try {
    const es = new EventSource(`/api/analyze/${currentSample}/${currentExpno}`);
    let text = '';

    es.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.type === 'chunk') {
        text += data.text;
        if (typeof marked !== 'undefined') {
          panel.innerHTML = marked.parse(text);
        } else {
          panel.innerText = text;
        }
        panel.scrollTop = panel.scrollHeight;
      } else if (data.type === 'done') {
        es.close();
        document.getElementById('btnAnalyze').disabled = false;
        if (typeof marked !== 'undefined') {
          panel.innerHTML = marked.parse(text) + `<p style="color:var(--dim);margin-top:1rem;">(${data.time_s}s)</p>`;
        }
      } else if (data.type === 'error') {
        es.close();
        document.getElementById('btnAnalyze').disabled = false;
        panel.innerHTML = `<span style="color:red;">Error: ${data.message}</span>`;
      }
    };

    es.onerror = () => {
      es.close();
      document.getElementById('btnAnalyze').disabled = false;
    };
  } catch (e) {
    panel.innerHTML = `<span style="color:red;">Error: ${e.message}</span>`;
    document.getElementById('btnAnalyze').disabled = false;
  }
}

async function showTools() {
  try {
    const res = await fetch('/api/tools');
    const data = await res.json();
    const panel = document.getElementById('aiPanel');
    panel.style.display = 'block';
    let html = '<h2>Available Tools (' + data.count + ')</h2>\\n';
    data.tools.forEach(t => {
      html += '\\n<span style="color:var(--green);">▸ ' + t.name + '</span>\\n  ' + t.description + '\\n';
    });
    html += '\\n<span style="color:var(--dim);">Install more: pip install tooluniverse (600+ scientific tools)</span>';
    panel.innerHTML = html;
  } catch (e) {
    console.error('Failed to load tools:', e);
  }
}

async function runPubchem() {
  if (!currentTitle) return;

  const name = currentTitle.split(' in ')[0].split(' C')[0].trim();
  if (!name) { alert('No compound name available'); return; }

  document.getElementById('btnPubchem').disabled = true;

  try {
    const res = await fetch(`/api/pubchem/${encodeURIComponent(name)}`);
    if (!res.ok) throw new Error('Not found on PubChem');
    const data = await res.json();

    const panel = document.getElementById('aiPanel');
    panel.style.display = 'block';
    const md = `## PubChem Result

| Property | Value |
|---|---|
| **CID** | ${data.CID} |
| **IUPAC** | ${data.IUPACName || 'N/A'} |
| **Formula** | ${data.MolecularFormula || 'N/A'} |
| **Weight** | ${data.MolecularWeight || 'N/A'} |
| **SMILES** | ${data.CanonicalSMILES || data.SMILES || 'N/A'} |
| **InChIKey** | ${data.InChIKey || 'N/A'} |`;
    panel.innerHTML = typeof marked !== 'undefined' ? marked.parse(md) : md;
  } catch (e) {
    const panel = document.getElementById('aiPanel');
    panel.style.display = 'block';
    panel.innerHTML = `<span style="color:var(--dim);">PubChem: ${e.message}</span>`;
  }
  document.getElementById('btnPubchem').disabled = false;
}

async function selectPlate(name) {
  // Highlight active card
  document.querySelectorAll('#plateDatasets .dataset-card').forEach(c => c.classList.remove('active'));
  event.currentTarget.classList.add('active');

  const panel = document.getElementById('platePanel');
  panel.classList.add('visible');
  document.getElementById('plateTitle').textContent = name;
  document.getElementById('plateMeta').innerHTML = '<span class="loading">Processing...</span>';
  document.getElementById('plateHeatmap').innerHTML = '';

  try {
    const res = await fetch(`/api/plate-reader/process/${encodeURIComponent(name)}`);
    const data = await res.json();

    document.getElementById('plateSubtitle').textContent = `${data.protocol} · ${data.mode}`;
    document.getElementById('plateMeta').innerHTML = `
      <div class="meta-item"><div class="meta-label">Mode</div><div class="meta-value">${data.mode}</div></div>
      <div class="meta-item"><div class="meta-label">Wavelength</div><div class="meta-value">${data.wavelength_nm} nm</div></div>
      <div class="meta-item"><div class="meta-label">Wells</div><div class="meta-value">${data.wells}</div></div>
    `;

    // Render heatmap
    const vals = data.heatmap.flat();
    const maxVal = Math.max(...vals);
    const minVal = Math.min(...vals);
    const range = maxVal - minVal || 1;

    let html = '<div class="heatmap">';
    // Column labels
    html += '<div class="heatmap-col-labels">';
    data.cols.forEach(c => { html += `<div class="heatmap-col-label">${c}</div>`; });
    html += '</div>';
    // Data rows
    data.rows.forEach((r, ri) => {
      html += '<div class="heatmap-row">';
      html += `<div class="heatmap-label">${r}</div>`;
      data.cols.forEach((c, ci) => {
        const v = data.heatmap[ri][ci];
        const norm = (v - minVal) / range;
        const hue = data.mode === 'fluorescence' ? 120 : 200; // green for fluorescence, blue for absorbance
        const light = 15 + norm * 50;
        const sat = 60 + norm * 40;
        html += `<div class="heatmap-cell" style="background:hsl(${hue},${sat}%,${light}%)" title="${r}${c}: ${v}">${v < 1 ? v.toFixed(2) : Math.round(v)}</div>`;
      });
      html += '</div>';
    });
    html += '</div>';

    document.getElementById('plateHeatmap').innerHTML = html;
  } catch (e) {
    document.getElementById('plateMeta').innerHTML = `<span style="color:red;">Failed: ${e.message}</span>`;
  }
}

init();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    import uvicorn

    print("\n  Device-Use Web GUI starting...")
    print("  Open http://localhost:8420 in your browser\n")
    uvicorn.run(app, host="0.0.0.0", port=8420, log_level="info")
