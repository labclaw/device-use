"""Individual safety layer checkers (L1 through L5)."""

from __future__ import annotations

import logging
from pathlib import Path

from device_use.core.models import ActionRequest, DeviceProfile
from device_use.safety.models import SafetyConfig, SafetyVerdict

logger = logging.getLogger(__name__)


class ActionWhitelistChecker:
    """L1: Only actions in profile.allowed_actions are permitted. ALWAYS active."""

    def check(
        self,
        action: ActionRequest,
        profile: DeviceProfile,
        config: SafetyConfig,
    ) -> SafetyVerdict:
        if action.action_type not in profile.allowed_actions:
            return SafetyVerdict(
                allowed=False,
                layer="L1_whitelist",
                reason=f"Action type '{action.action_type.value}' not in allowed actions",
            )
        return SafetyVerdict(allowed=True)


class ParameterBoundsChecker:
    """L2: Parameter values + forbidden regions checked. Hardware only."""

    def check(
        self,
        action: ActionRequest,
        profile: DeviceProfile,
        config: SafetyConfig,
    ) -> SafetyVerdict:
        if not config.hardware_connected:
            return SafetyVerdict(allowed=True)

        # Check forbidden_regions against action coordinates
        if profile.safety.forbidden_regions:
            coords_to_check = []
            if action.coordinates:
                coords_to_check.append(action.coordinates)
            # Also check drag end coordinates
            end_x = action.parameters.get("end_x")
            end_y = action.parameters.get("end_y")
            if end_x is not None and end_y is not None:
                coords_to_check.append((end_x, end_y))

            for ax, ay in coords_to_check:
                for rx, ry, rw, rh in profile.safety.forbidden_regions:
                    if rx <= ax < rx + rw and ry <= ay < ry + rh:
                        return SafetyVerdict(
                            allowed=False,
                            layer="L2_parameter_bounds",
                            reason=(
                                f"Coordinates ({ax}, {ay}) fall within "
                                f"forbidden region ({rx}, {ry}, {rw}, {rh})"
                            ),
                        )

        bounds = profile.safety.bounds
        for key, value in action.parameters.items():
            min_key = f"{key}_min"
            if min_key in bounds:
                try:
                    if float(value) < float(bounds[min_key]):
                        return SafetyVerdict(
                            allowed=False,
                            layer="L2_parameter_bounds",
                            reason=(
                                f"Parameter '{key}' value {value} below minimum {bounds[min_key]}"
                            ),
                        )
                except (TypeError, ValueError):
                    logger.warning(
                        "Cannot check bounds for parameter '%s': value %r is not numeric",
                        key,
                        value,
                    )

            max_key = f"{key}_max"
            if max_key in bounds:
                try:
                    if float(value) > float(bounds[max_key]):
                        return SafetyVerdict(
                            allowed=False,
                            layer="L2_parameter_bounds",
                            reason=(
                                f"Parameter '{key}' value {value} exceeds maximum {bounds[max_key]}"
                            ),
                        )
                except (TypeError, ValueError):
                    logger.warning(
                        "Cannot check bounds for parameter '%s': value %r is not numeric",
                        key,
                        value,
                    )

        return SafetyVerdict(allowed=True)


class StateVerificationChecker:
    """L3: Post-action screenshot comparison placeholder. Hardware only."""

    def check(
        self,
        action: ActionRequest,
        profile: DeviceProfile,
        config: SafetyConfig,
    ) -> SafetyVerdict:
        if not config.hardware_connected:
            return SafetyVerdict(allowed=True)

        # Placeholder — always passes until vision verification is implemented
        return SafetyVerdict(allowed=True)


class HumanConfirmationGate:
    """L4: CLI prompt for human approval on requires_confirmation actions. Hardware only."""

    def __init__(self, auto_approve: bool = False) -> None:
        self.auto_approve = auto_approve

    def check(
        self,
        action: ActionRequest,
        profile: DeviceProfile,
        config: SafetyConfig,
    ) -> SafetyVerdict:
        if not config.hardware_connected:
            return SafetyVerdict(allowed=True)

        # Check if this action's target or description matches requires_confirmation
        requires = profile.safety.requires_confirmation
        needs_confirm = False
        for trigger in requires:
            if trigger in action.target or trigger in action.description:
                needs_confirm = True
                break

        if not needs_confirm:
            return SafetyVerdict(allowed=True)

        if self.auto_approve:
            return SafetyVerdict(allowed=True, requires_confirmation=True)

        # Interactive CLI prompt
        print(
            f"\n[SAFETY L4] Action requires confirmation: "
            f"{action.action_type.value} → {action.target}"
        )
        print(f"  Description: {action.description}")
        response = input("  Approve? [y/N]: ").strip().lower()
        if response in ("y", "yes"):
            return SafetyVerdict(allowed=True, requires_confirmation=True)

        return SafetyVerdict(
            allowed=False,
            layer="L4_human_confirmation",
            reason="Human operator denied the action",
            requires_confirmation=True,
        )


class EmergencyStopMonitor:
    """L5: File-based kill switch — checks if emergency_stop_file exists. Hardware only."""

    def check(
        self,
        action: ActionRequest,
        profile: DeviceProfile,
        config: SafetyConfig,
    ) -> SafetyVerdict:
        if not config.hardware_connected:
            return SafetyVerdict(allowed=True)

        stop_file = Path(profile.safety.emergency_stop_file)
        if stop_file.exists():
            return SafetyVerdict(
                allowed=False,
                layer="L5_emergency_stop",
                reason=f"Emergency stop file exists: {stop_file}",
            )
        return SafetyVerdict(allowed=True)
