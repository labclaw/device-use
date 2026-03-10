#!/bin/bash
# Launch Device-Use Web GUI
#
# Usage:
#   ./demos/run_web.sh              # start on port 8420
#   ./demos/run_web.sh --port 3000  # custom port

set -e

cd "$(dirname "$0")/.."

PORT="${2:-8420}"

echo ""
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║  Device-Use Web GUI                              ║"
echo "  ║  ROS for Lab Instruments                         ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo ""
echo "  → http://localhost:$PORT"
echo ""

# Activate venv if exists
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

PYTHONPATH=src exec uvicorn device_use.web.app:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --reload \
    --log-level info
