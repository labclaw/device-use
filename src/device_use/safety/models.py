"""Safety data models for device-use."""

from __future__ import annotations

from pydantic import BaseModel

from device_use.core.models import SafetyLevel


class SafetyConfig(BaseModel):
    """Configuration for safety enforcement."""

    level: SafetyLevel = SafetyLevel.NORMAL
    hardware_connected: bool = False
    # When hardware_connected=False, only L1 (whitelist) is enforced
    # When hardware_connected=True, all 5 layers are active


class SafetyVerdict(BaseModel):
    """Result of safety checking an action."""

    allowed: bool
    layer: str = ""  # which layer blocked it, e.g. "L1_whitelist"
    reason: str = ""
    requires_confirmation: bool = False
