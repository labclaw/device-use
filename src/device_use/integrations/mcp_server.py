"""MCP Server — expose device-use instruments as Model Context Protocol tools.

Run as:
    python -m device_use.integrations.mcp_server

Or add to Claude Code's MCP config:
    {
      "mcpServers": {
        "device-use": {
          "command": "python",
          "args": ["-m", "device_use.integrations.mcp_server"]
        }
      }
    }
"""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "device-use",
    instructions="Scientific instrument control — NMR, plate readers, and more",
)

# Lazy-initialized orchestrator (created on first tool call)
_orchestrator = None


def _get_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        from device_use import create_orchestrator
        _orchestrator = create_orchestrator()
        logger.info(
            "Orchestrator ready: %d instruments, %d tools",
            len(_orchestrator.registry.list_instruments()),
            len(_orchestrator.registry.list_tools()),
        )
    return _orchestrator


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
def list_instruments() -> str:
    """List all registered scientific instruments and their capabilities."""
    orch = _get_orchestrator()
    instruments = orch.registry.list_instruments()
    result = []
    for info in instruments:
        inst = orch.registry.get_instrument(info.name)
        result.append({
            "name": info.name,
            "vendor": info.vendor,
            "type": info.instrument_type,
            "version": info.version,
            "modes": [m.value for m in info.supported_modes],
            "connected": inst.connected if inst else False,
        })
    return json.dumps(result, indent=2)


@mcp.tool()
def list_tools() -> str:
    """List all available instrument tools that can be called."""
    orch = _get_orchestrator()
    tools = orch.registry.list_tools()
    result = []
    for tool in tools:
        result.append({
            "name": tool.name,
            "description": tool.description,
            "instrument_type": tool.instrument_type,
            "parameters": tool.parameters,
        })
    return json.dumps(result, indent=2)


@mcp.tool()
def call_tool(tool_name: str, params: str = "{}") -> str:
    """Call a registered instrument tool by name.

    Args:
        tool_name: Tool name (e.g. "topspin.list_datasets", "platereader.process")
        params: JSON string of keyword arguments for the tool
    """
    orch = _get_orchestrator()
    kwargs = json.loads(params) if params else {}
    result = orch.call_tool(tool_name, **kwargs)
    return json.dumps(result, indent=2, default=str)


@mcp.tool()
def nmr_list_datasets() -> str:
    """List all available NMR datasets from TopSpin."""
    orch = _get_orchestrator()
    datasets = orch.call_tool("topspin.list_datasets")
    return json.dumps(datasets, indent=2, default=str)


@mcp.tool()
def nmr_process(data_path: str) -> str:
    """Process NMR data (Fourier transform, phase correction, baseline correction, peak picking).

    Args:
        data_path: Path to the NMR dataset directory
    """
    orch = _get_orchestrator()
    result = orch.call_tool("topspin.process", data_path=data_path)

    # Convert spectrum to serializable format
    output: dict[str, Any] = {
        "title": result.title,
        "solvent": result.solvent,
        "frequency_mhz": result.frequency_mhz,
        "num_peaks": len(result.peaks),
        "peaks": [
            {"ppm": round(p.ppm, 2), "intensity": round(p.intensity, 2)}
            for p in result.peaks[:50]  # cap at 50 peaks
        ],
    }
    return json.dumps(output, indent=2)


@mcp.tool()
def nmr_identify(data_path: str, molecular_formula: str = "") -> str:
    """Process NMR data and identify the compound using AI.

    Args:
        data_path: Path to the NMR dataset directory
        molecular_formula: Optional molecular formula (e.g. "C13H20O")
    """
    orch = _get_orchestrator()
    spectrum = orch.call_tool("topspin.process", data_path=data_path)

    from device_use.instruments.nmr.brain import NMRBrain
    brain = NMRBrain()
    analysis = brain.interpret_spectrum(
        spectrum,
        molecular_formula=molecular_formula,
    )
    return analysis


@mcp.tool()
def plate_reader_list_assays() -> str:
    """List available plate reader assays/datasets."""
    orch = _get_orchestrator()
    datasets = orch.call_tool("platereader.list_datasets")
    return json.dumps(datasets, indent=2, default=str)


@mcp.tool()
def plate_reader_process(assay_name: str = "") -> str:
    """Run a plate reader assay and return results.

    Args:
        assay_name: Name of the assay to run (e.g. "elisa_il6", "cell_viability")
    """
    orch = _get_orchestrator()
    reading = orch.call_tool("platereader.process", data_path=assay_name)

    output: dict[str, Any] = {
        "protocol": reading.protocol,
        "mode": reading.mode.value if hasattr(reading.mode, "value") else str(reading.mode),
        "wavelength_nm": reading.wavelength_nm,
        "format": reading.plate.format.value if hasattr(reading.plate.format, "value") else str(reading.plate.format),
        "num_wells": len(reading.plate.wells),
    }

    # Summarize well values
    values = [w.value for w in reading.plate.wells]
    import statistics
    if values:
        output["summary"] = {
            "mean": round(statistics.mean(values), 4),
            "std": round(statistics.stdev(values), 4) if len(values) > 1 else 0,
            "min": round(min(values), 4),
            "max": round(max(values), 4),
        }

    # Group by row
    rows: dict[str, list[float]] = {}
    for w in reading.plate.wells:
        rows.setdefault(w.row, []).append(w.value)
    output["rows"] = {
        row: round(statistics.mean(vals), 4) for row, vals in rows.items()
    }

    return json.dumps(output, indent=2)


@mcp.tool()
def run_pipeline(steps_json: str) -> str:
    """Run a multi-step pipeline on registered instruments.

    Args:
        steps_json: JSON array of pipeline steps, each with:
            - name: Step name
            - tool_name: Registered tool to call (e.g. "topspin.process")
            - params: Dict of parameters for the tool
            - retries: Number of retry attempts (default 0)
            - timeout_s: Timeout in seconds (default 0 = no limit)

    Example:
        [
            {"name": "load", "tool_name": "topspin.list_datasets"},
            {"name": "process", "tool_name": "topspin.process",
             "params": {"data_path": "/path/to/data"}}
        ]
    """
    from device_use.orchestrator import Pipeline, PipelineStep

    orch = _get_orchestrator()
    steps = json.loads(steps_json)

    pipeline = Pipeline("mcp_pipeline")
    for step_def in steps:
        pipeline.add_step(PipelineStep(
            name=step_def["name"],
            tool_name=step_def.get("tool_name", ""),
            params=step_def.get("params", {}),
            retries=step_def.get("retries", 0),
            timeout_s=step_def.get("timeout_s", 0),
        ))

    result = orch.run(pipeline)
    output = {
        "success": result.success,
        "pipeline": result.name,
        "duration_ms": round(result.duration_ms, 1),
        "steps": [
            {
                "name": name,
                "status": sr.status.value,
                "duration_ms": round(sr.duration_ms, 1),
                "error": sr.error or None,
            }
            for name, sr in result.steps
        ],
        "outputs": {k: str(v)[:500] for k, v in result.outputs.items()},
    }
    return json.dumps(output, indent=2, default=str)


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------

@mcp.resource("device-use://status")
def get_status() -> str:
    """Current status of the device-use middleware."""
    orch = _get_orchestrator()
    instruments = orch.registry.list_instruments()
    tools = orch.registry.list_tools()
    return json.dumps({
        "instruments": len(instruments),
        "tools": len(tools),
        "instrument_details": [
            {"name": i.name, "type": i.instrument_type, "vendor": i.vendor}
            for i in instruments
        ],
    }, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    mcp.run()


if __name__ == "__main__":
    main()
