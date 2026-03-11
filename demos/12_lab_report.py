#!/usr/bin/env python3
"""Lab Report Generator — AI writes a complete experimental report.

This demo shows the full autonomous loop:
  1. Process data from BOTH instruments (NMR + Plate Reader)
  2. AI analyzes each dataset
  3. Generate publication-quality plots
  4. Cross-reference compounds on PubChem
  5. AI writes a structured lab report combining all findings

This is the vision: from raw data to paper-ready report, zero manual work.

Usage:
    python demos/lab_report_demo.py
    python demos/lab_report_demo.py --output report.md
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from device_use.instruments import ControlMode
from device_use.instruments.nmr.adapter import TopSpinAdapter
from device_use.instruments.plate_reader import PlateReaderAdapter
from device_use.orchestrator import Orchestrator, Pipeline, PipelineStep


def main():
    parser = argparse.ArgumentParser(description="AI Lab Report Generator")
    parser.add_argument("--output", "-o", default="output/lab_report.md")
    args = parser.parse_args()

    from lib.terminal import banner
    banner("AI Lab Report Generator",
           "Raw data → Process → Analyze → Cross-reference → Report")

    t0 = time.time()

    # ── Set up orchestrator with both instruments ────────────────
    orch = Orchestrator()
    nmr = TopSpinAdapter(mode=ControlMode.OFFLINE)
    reader = PlateReaderAdapter(mode=ControlMode.OFFLINE)
    orch.register(nmr)
    orch.register(reader)
    orch.connect_all()

    instruments = orch.registry.list_instruments()
    print(f"  Instruments: {', '.join(i.name for i in instruments)}")

    # ── Process NMR data ────────────────────────────────────────
    print("\n  Processing NMR data...")
    datasets = nmr.list_datasets()
    # Pick Alpha Ionone
    target = None
    for ds in datasets:
        if "CMCse_1" in ds.get("sample", ""):
            target = ds
            break
    if not target:
        target = datasets[0]

    spectrum = nmr.process(target["path"])
    print(f"    {spectrum.title or target['sample']}: {len(spectrum.peaks)} peaks, {spectrum.frequency_mhz:.0f} MHz")

    # Generate NMR plot
    from device_use.instruments.nmr.visualizer import plot_spectrum
    nmr_plot_path = Path("output/report_nmr_spectrum.png")
    nmr_plot_path.parent.mkdir(parents=True, exist_ok=True)
    plot_spectrum(spectrum, output_path=str(nmr_plot_path))
    print(f"    Plot: {nmr_plot_path}")

    # ── Process Plate Reader data ───────────────────────────────
    print("\n  Processing Plate Reader data...")
    elisa = reader.process("ELISA_IL6_plate1")
    viability = reader.process("CellViability_DrugScreen")
    print(f"    ELISA: {len(elisa.plate.wells)} wells, {elisa.wavelength_nm} nm")
    print(f"    Viability: {len(viability.plate.wells)} wells, {viability.wavelength_nm} nm")

    # Generate plate plots
    from device_use.instruments.plate_reader.visualizer import plot_plate_heatmap
    elisa_plot = "output/report_elisa.png"
    viab_plot = "output/report_viability.png"
    plot_plate_heatmap(elisa, output_path=elisa_plot)
    plot_plate_heatmap(viability, output_path=viab_plot)
    print(f"    Plots: {elisa_plot}, {viab_plot}")

    # ── AI Analysis ─────────────────────────────────────────────
    print("\n  Running AI analysis...")
    from device_use.instruments.nmr.brain import NMRBrain
    brain = NMRBrain()
    nmr_analysis = brain.interpret_spectrum(spectrum, stream=False)
    print(f"    NMR interpretation: {len(nmr_analysis)} chars")

    # ── PubChem cross-reference ─────────────────────────────────
    print("\n  Cross-referencing on PubChem...")
    compound_name = (spectrum.title or target["sample"]).split(" in ")[0].strip()
    pubchem_data = None
    try:
        from device_use.tools.pubchem import PubChemTool
        tool = PubChemTool()
        pubchem_data = tool.lookup_by_name(compound_name)
        print(f"    Found: CID {pubchem_data.get('CID', '?')}, {pubchem_data.get('MolecularFormula', '?')}")
    except Exception as e:
        print(f"    PubChem lookup skipped: {e}")

    # ── AI analysis of plate reader data ─────────────────────────
    print("\n  Running plate reader AI analysis...")
    from device_use.instruments.plate_reader.brain import PlateReaderBrain
    plate_brain = PlateReaderBrain()
    elisa_analysis = plate_brain.interpret_reading(elisa, stream=False)
    viability_analysis = plate_brain.interpret_reading(viability, stream=False)
    print(f"    ELISA interpretation: {len(elisa_analysis)} chars")
    print(f"    Viability interpretation: {len(viability_analysis)} chars")

    # ── Plate reader statistics ─────────────────────────────────
    import statistics

    # ELISA stats
    std_wells = [w for w in elisa.plate.wells if w.col <= 2]
    blank_wells = [w for w in elisa.plate.wells if w.col >= 11]
    std_mean = statistics.mean([w.value for w in std_wells])
    blank_mean = statistics.mean([w.value for w in blank_wells])

    # Viability Z-factor
    pos_wells = [w for w in viability.plate.wells if w.col <= 2]
    neg_wells = [w for w in viability.plate.wells if w.col >= 11]
    pos_mean = statistics.mean([w.value for w in pos_wells])
    neg_mean = statistics.mean([w.value for w in neg_wells])
    pos_std = statistics.stdev([w.value for w in pos_wells])
    neg_std = statistics.stdev([w.value for w in neg_wells])
    separation = abs(pos_mean - neg_mean)
    z_factor = 1 - 3 * (pos_std + neg_std) / separation if separation > 0 else float("-inf")

    # ── Generate Report ─────────────────────────────────────────
    print("\n  Generating report...")

    top_peaks = sorted(spectrum.peaks, key=lambda p: p.intensity, reverse=True)[:10]
    peak_table = "\n".join(
        f"| {p.ppm:.2f} | {p.intensity / max(pp.intensity for pp in spectrum.peaks) * 100:.1f}% | {p.multiplicity or '-'} |"
        for p in top_peaks
    )

    pubchem_section = ""
    if pubchem_data:
        pubchem_section = f"""
## PubChem Cross-Reference

| Property | Value |
|----------|-------|
| CID | {pubchem_data.get('CID', 'N/A')} |
| IUPAC Name | {pubchem_data.get('IUPACName', 'N/A')} |
| Molecular Formula | {pubchem_data.get('MolecularFormula', 'N/A')} |
| Molecular Weight | {pubchem_data.get('MolecularWeight', 'N/A')} |
| SMILES | `{pubchem_data.get('CanonicalSMILES', pubchem_data.get('SMILES', 'N/A'))}` |
| InChIKey | {pubchem_data.get('InChIKey', 'N/A')} |
"""

    dt = time.time() - t0

    report = f"""# Automated Lab Report

*Generated by device-use AI Lab Report Generator*
*Date: {time.strftime('%Y-%m-%d %H:%M')}*
*Total processing time: {dt:.1f}s*

---

## Instruments Used

| Instrument | Vendor | Type | Mode |
|------------|--------|------|------|
| TopSpin | Bruker | NMR Spectrometer | Offline |
| PlateReader | BioTek | Plate Reader | Offline |

---

## 1. NMR Spectroscopy

**Sample:** {spectrum.title or target['sample']}
**Frequency:** {spectrum.frequency_mhz:.1f} MHz
**Nucleus:** {spectrum.nucleus}
**Solvent:** {spectrum.solvent}
**Peaks detected:** {len(spectrum.peaks)}

### Peak List (Top 10 by Intensity)

| δ (ppm) | Rel. Intensity | Multiplicity |
|---------|----------------|--------------|
{peak_table}

### AI Interpretation

{nmr_analysis}

![NMR Spectrum](report_nmr_spectrum.png)
{pubchem_section}
---

## 2. Plate Reader Assays

### 2.1 ELISA (IL-6)

**Protocol:** {elisa.protocol}
**Wavelength:** {elisa.wavelength_nm} nm
**Plate format:** {elisa.plate.format.value}-well

| Metric | Value |
|--------|-------|
| Standard mean (cols 1-2) | OD = {std_mean:.4f} |
| Blank mean (cols 11-12) | OD = {blank_mean:.4f} |
| Signal/Noise ratio | {std_mean / max(blank_mean, 0.001):.1f}x |

![ELISA Heatmap](report_elisa.png)

### AI Interpretation (ELISA)

{elisa_analysis}

### 2.2 Cell Viability (Calcein AM)

**Protocol:** {viability.protocol}
**Excitation/Emission:** {viability.metadata['excitation_nm']}/{viability.metadata['emission_nm']} nm

| Metric | Value |
|--------|-------|
| Positive control mean | {pos_mean:.0f} RFU |
| Negative control mean | {neg_mean:.0f} RFU |
| Z-factor | {z_factor:.3f} |
| Assay quality | {'Excellent' if z_factor > 0.5 else 'Acceptable' if z_factor > 0 else 'Poor'} |

![Viability Heatmap](report_viability.png)

### AI Interpretation (Cell Viability)

{viability_analysis}

---

## Methods

### NMR Processing Pipeline
1. Load raw FID from Bruker format
2. Remove digital filter (group delay correction)
3. Zero-fill to 65,536 points
4. Apodization (exponential multiplication, LB=0.3 Hz)
5. Fast Fourier Transform
6. Automatic phase correction (ACME algorithm)
7. Baseline correction (polynomial)
8. Peak picking (threshold-based)

### Plate Reader
- ELISA: Endpoint absorbance at {elisa.wavelength_nm} nm, shake before read
- Viability: Fluorescence (Ex {viability.metadata['excitation_nm']} / Em {viability.metadata['emission_nm']} nm), gain {viability.metadata.get('gain', 'auto')}

---

## Appendix: Architecture

```
Cloud Brain (Claude AI)
        |
   Orchestrator (pipeline + registry + events)
        |                       |
   TopSpin NMR            Plate Reader
    |     |    |           |     |    |
  API   GUI  Offline    API   GUI  Offline
```

*Generated with [device-use](https://github.com/labclaw/device-use) — ROS for Lab Instruments*
"""

    # Write report
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report)

    from lib.terminal import finale
    finale([
        f"Report saved: {output_path}",
        f"Total time: {dt:.1f}s",
        "Sections: NMR analysis + ELISA + Cell Viability + Methods",
        "From raw instrument data to paper-ready report",
        "Zero manual work. This is the AI-native lab.",
    ], title="Lab Report Complete")


if __name__ == "__main__":
    main()
