"""Operator abstraction for instrument control.

Operators provide layered control strategies:
  L1: API    — Direct programmatic control (fastest, most reliable)
  L2: Script — AppleScript/JXA/macro automation
  L3: A11y   — macOS Accessibility API (read UI state, click elements)
  L4: CU     — Computer Use via VLM (screenshot → model → action, slowest)

Each instrument defines which layers are available. The system tries
the fastest available layer first, falling back as needed.
"""

from __future__ import annotations

from device_use.operators.a11y import AccessibilityOperator
from device_use.operators.base import BaseOperator, ControlLayer, OperatorResult

__all__ = ["BaseOperator", "ControlLayer", "AccessibilityOperator", "OperatorResult"]
