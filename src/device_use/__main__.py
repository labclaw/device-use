"""Entry point for `python -m device_use`."""

import sys


def main():
    print("""
device-use — ROS for Lab Instruments

  Like browser-use, but for scientific instruments.
  AI agents operate lab devices through any control mode.

Quick Start:
  python demos/topspin_identify.py --dataset exam_CMCse_1 --formula C13H20O
  python demos/topspin_ai_scientist.py
  python demos/topspin_pipeline.py
  ./demos/run_web.sh

Architecture:
  Cloud Brain (Claude AI)
        |
   Orchestrator (pipeline + registry + events)
        |
   Instruments (TopSpin NMR → API / GUI / Offline)
        |
   Tools (PubChem, ToolUniverse)

Docs: demos/README.md
""")


if __name__ == "__main__":
    main()
