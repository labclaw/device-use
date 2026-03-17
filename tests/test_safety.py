"""Tests for the 5-layer safety model."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from device_use.core.models import (
    ActionRequest,
    ActionType,
    DeviceProfile,
    SafetyConstraints,
    SafetyLevel,
)
from device_use.safety.guard import SafetyGuard
from device_use.safety.layers import (
    ActionWhitelistChecker,
    EmergencyStopMonitor,
    HumanConfirmationGate,
    ParameterBoundsChecker,
    StateVerificationChecker,
)
from device_use.safety.models import SafetyConfig

# --- Fixtures ---


@pytest.fixture()
def software_profile() -> DeviceProfile:
    """Software-only profile (FIJI-like)."""
    return DeviceProfile(
        name="test-software",
        software="TestApp",
        hardware_connected=False,
        safety_level=SafetyLevel.NORMAL,
        allowed_actions=[ActionType.CLICK, ActionType.TYPE, ActionType.SCREENSHOT],
        safety=SafetyConstraints(
            max_actions_per_minute=60,
        ),
    )


@pytest.fixture()
def hardware_profile() -> DeviceProfile:
    """Hardware-connected profile (plate reader-like)."""
    return DeviceProfile(
        name="test-hardware",
        software="TestInstrument",
        hardware_connected=True,
        safety_level=SafetyLevel.STRICT,
        allowed_actions=[ActionType.CLICK, ActionType.TYPE, ActionType.WAIT],
        safety=SafetyConstraints(
            max_actions_per_minute=10,
            requires_confirmation=["start_read", "delete_data"],
            emergency_stop_file="/tmp/test_device_use_stop",
            bounds={
                "temperature_min": 4,
                "temperature_max": 45,
                "shake_speed_max": 1000,
            },
        ),
    )


@pytest.fixture()
def software_config() -> SafetyConfig:
    return SafetyConfig(level=SafetyLevel.NORMAL, hardware_connected=False)


@pytest.fixture()
def hardware_config() -> SafetyConfig:
    return SafetyConfig(level=SafetyLevel.STRICT, hardware_connected=True)


@pytest.fixture()
def click_action() -> ActionRequest:
    return ActionRequest(
        action_type=ActionType.CLICK,
        target="button",
        description="Click a button",
    )


@pytest.fixture()
def drag_action() -> ActionRequest:
    return ActionRequest(
        action_type=ActionType.DRAG,
        target="canvas",
        description="Drag on canvas",
    )


# --- L1 ActionWhitelistChecker ---


class TestL1ActionWhitelist:
    def test_allowed_action_passes(
        self, software_profile: DeviceProfile, software_config: SafetyConfig
    ):
        checker = ActionWhitelistChecker()
        action = ActionRequest(action_type=ActionType.CLICK)
        verdict = checker.check(action, software_profile, software_config)
        assert verdict.allowed is True

    def test_disallowed_action_blocked(
        self, software_profile: DeviceProfile, software_config: SafetyConfig
    ):
        checker = ActionWhitelistChecker()
        action = ActionRequest(action_type=ActionType.DRAG)
        verdict = checker.check(action, software_profile, software_config)
        assert verdict.allowed is False
        assert verdict.layer == "L1_whitelist"
        assert "drag" in verdict.reason.lower()

    def test_all_actions_allowed_when_default(self, software_config: SafetyConfig):
        """Default profile allows all action types."""
        profile = DeviceProfile(name="test", software="App")
        checker = ActionWhitelistChecker()
        for action_type in ActionType:
            action = ActionRequest(action_type=action_type)
            verdict = checker.check(action, profile, software_config)
            assert verdict.allowed is True


# --- L2 ParameterBoundsChecker ---


class TestL2ParameterBounds:
    def test_in_bounds_passes(self, hardware_profile: DeviceProfile, hardware_config: SafetyConfig):
        checker = ParameterBoundsChecker()
        action = ActionRequest(
            action_type=ActionType.CLICK,
            parameters={"temperature": 25},
        )
        verdict = checker.check(action, hardware_profile, hardware_config)
        assert verdict.allowed is True

    def test_above_max_blocked(
        self, hardware_profile: DeviceProfile, hardware_config: SafetyConfig
    ):
        checker = ParameterBoundsChecker()
        action = ActionRequest(
            action_type=ActionType.CLICK,
            parameters={"temperature": 50},
        )
        verdict = checker.check(action, hardware_profile, hardware_config)
        assert verdict.allowed is False
        assert verdict.layer == "L2_parameter_bounds"
        assert "exceeds maximum" in verdict.reason

    def test_below_min_blocked(
        self, hardware_profile: DeviceProfile, hardware_config: SafetyConfig
    ):
        checker = ParameterBoundsChecker()
        action = ActionRequest(
            action_type=ActionType.CLICK,
            parameters={"temperature": 2},
        )
        verdict = checker.check(action, hardware_profile, hardware_config)
        assert verdict.allowed is False
        assert verdict.layer == "L2_parameter_bounds"
        assert "below minimum" in verdict.reason

    def test_shake_speed_max_blocked(
        self, hardware_profile: DeviceProfile, hardware_config: SafetyConfig
    ):
        checker = ParameterBoundsChecker()
        action = ActionRequest(
            action_type=ActionType.CLICK,
            parameters={"shake_speed": 1500},
        )
        verdict = checker.check(action, hardware_profile, hardware_config)
        assert verdict.allowed is False
        assert "shake_speed" in verdict.reason

    def test_skipped_for_software_profiles(
        self, software_profile: DeviceProfile, software_config: SafetyConfig
    ):
        checker = ParameterBoundsChecker()
        # Even with out-of-bounds params, software profile bypasses L2
        action = ActionRequest(
            action_type=ActionType.CLICK,
            parameters={"temperature": 999},
        )
        verdict = checker.check(action, software_profile, software_config)
        assert verdict.allowed is True

    def test_non_numeric_param_ignored(
        self, hardware_profile: DeviceProfile, hardware_config: SafetyConfig
    ):
        checker = ParameterBoundsChecker()
        action = ActionRequest(
            action_type=ActionType.CLICK,
            parameters={"temperature": "not_a_number"},
        )
        verdict = checker.check(action, hardware_profile, hardware_config)
        assert verdict.allowed is True

    def test_forbidden_region_blocks(self, hardware_config: SafetyConfig):
        profile = DeviceProfile(
            name="test-hw",
            software="Inst",
            hardware_connected=True,
            safety=SafetyConstraints(
                forbidden_regions=[(100, 100, 50, 50)],
            ),
        )
        checker = ParameterBoundsChecker()
        # Inside forbidden region
        action = ActionRequest(
            action_type=ActionType.CLICK,
            coordinates=(120, 130),
        )
        verdict = checker.check(action, profile, hardware_config)
        assert verdict.allowed is False
        assert "forbidden region" in verdict.reason

    def test_forbidden_region_allows_outside(self, hardware_config: SafetyConfig):
        profile = DeviceProfile(
            name="test-hw",
            software="Inst",
            hardware_connected=True,
            safety=SafetyConstraints(
                forbidden_regions=[(100, 100, 50, 50)],
            ),
        )
        checker = ParameterBoundsChecker()
        # Outside forbidden region
        action = ActionRequest(
            action_type=ActionType.CLICK,
            coordinates=(200, 200),
        )
        verdict = checker.check(action, profile, hardware_config)
        assert verdict.allowed is True

    def test_forbidden_region_exclusive_boundary(self, hardware_config: SafetyConfig):
        """Point at (rx+rw, ry+rh) is outside the region (exclusive right/bottom)."""
        profile = DeviceProfile(
            name="test-hw",
            software="Inst",
            hardware_connected=True,
            safety=SafetyConstraints(
                forbidden_regions=[(100, 100, 50, 50)],
            ),
        )
        checker = ParameterBoundsChecker()
        # Exactly at right/bottom boundary — should be allowed (exclusive)
        action = ActionRequest(
            action_type=ActionType.CLICK,
            coordinates=(150, 150),
        )
        verdict = checker.check(action, profile, hardware_config)
        assert verdict.allowed is True

    def test_forbidden_region_blocks_drag_end(self, hardware_config: SafetyConfig):
        """Drag end coordinates inside forbidden region → blocked."""
        profile = DeviceProfile(
            name="test-hw",
            software="Inst",
            hardware_connected=True,
            safety=SafetyConstraints(
                forbidden_regions=[(500, 500, 100, 100)],
            ),
        )
        checker = ParameterBoundsChecker()
        # Start is outside, end is inside forbidden region
        action = ActionRequest(
            action_type=ActionType.DRAG,
            coordinates=(200, 200),
            parameters={"end_x": 550, "end_y": 550},
        )
        verdict = checker.check(action, profile, hardware_config)
        assert verdict.allowed is False
        assert "forbidden region" in verdict.reason

    def test_forbidden_region_skipped_software(self, software_config: SafetyConfig):
        profile = DeviceProfile(
            name="test-sw",
            software="App",
            hardware_connected=False,
            safety=SafetyConstraints(
                forbidden_regions=[(0, 0, 9999, 9999)],
            ),
        )
        checker = ParameterBoundsChecker()
        action = ActionRequest(
            action_type=ActionType.CLICK,
            coordinates=(50, 50),
        )
        verdict = checker.check(action, profile, software_config)
        assert verdict.allowed is True


# --- L3 StateVerificationChecker ---


class TestL3StateVerification:
    def test_placeholder_always_passes(
        self, hardware_profile: DeviceProfile, hardware_config: SafetyConfig
    ):
        checker = StateVerificationChecker()
        action = ActionRequest(action_type=ActionType.CLICK)
        verdict = checker.check(action, hardware_profile, hardware_config)
        assert verdict.allowed is True

    def test_skipped_for_software_profiles(
        self, software_profile: DeviceProfile, software_config: SafetyConfig
    ):
        checker = StateVerificationChecker()
        action = ActionRequest(action_type=ActionType.CLICK)
        verdict = checker.check(action, software_profile, software_config)
        assert verdict.allowed is True


# --- L4 HumanConfirmationGate ---


class TestL4HumanConfirmation:
    def test_auto_approve_passes(
        self, hardware_profile: DeviceProfile, hardware_config: SafetyConfig
    ):
        checker = HumanConfirmationGate(auto_approve=True)
        action = ActionRequest(
            action_type=ActionType.CLICK,
            target="start_read",
            description="Start plate reading",
        )
        verdict = checker.check(action, hardware_profile, hardware_config)
        assert verdict.allowed is True
        assert verdict.requires_confirmation is True

    def test_no_confirmation_needed_passes(
        self, hardware_profile: DeviceProfile, hardware_config: SafetyConfig
    ):
        checker = HumanConfirmationGate(auto_approve=False)
        action = ActionRequest(
            action_type=ActionType.CLICK,
            target="safe_button",
            description="A safe action",
        )
        verdict = checker.check(action, hardware_profile, hardware_config)
        assert verdict.allowed is True

    def test_denied_by_human(self, hardware_profile: DeviceProfile, hardware_config: SafetyConfig):
        checker = HumanConfirmationGate(auto_approve=False)
        action = ActionRequest(
            action_type=ActionType.CLICK,
            target="start_read",
            description="Start plate reading",
        )
        with patch("builtins.input", return_value="n"):
            verdict = checker.check(action, hardware_profile, hardware_config)
        assert verdict.allowed is False
        assert verdict.layer == "L4_human_confirmation"

    def test_approved_by_human(
        self, hardware_profile: DeviceProfile, hardware_config: SafetyConfig
    ):
        checker = HumanConfirmationGate(auto_approve=False)
        action = ActionRequest(
            action_type=ActionType.CLICK,
            target="start_read",
            description="Start plate reading",
        )
        with patch("builtins.input", return_value="y"):
            verdict = checker.check(action, hardware_profile, hardware_config)
        assert verdict.allowed is True
        assert verdict.requires_confirmation is True

    def test_skipped_for_software_profiles(
        self, software_profile: DeviceProfile, software_config: SafetyConfig
    ):
        checker = HumanConfirmationGate(auto_approve=False)
        action = ActionRequest(
            action_type=ActionType.CLICK,
            target="start_read",
            description="Start plate reading",
        )
        # Should not prompt for software profiles
        verdict = checker.check(action, software_profile, software_config)
        assert verdict.allowed is True


# --- L5 EmergencyStopMonitor ---


class TestL5EmergencyStop:
    def test_no_stop_file_passes(
        self, hardware_profile: DeviceProfile, hardware_config: SafetyConfig
    ):
        # Ensure stop file does not exist
        stop_path = Path(hardware_profile.safety.emergency_stop_file)
        if stop_path.exists():
            stop_path.unlink()

        checker = EmergencyStopMonitor()
        action = ActionRequest(action_type=ActionType.CLICK)
        verdict = checker.check(action, hardware_profile, hardware_config)
        assert verdict.allowed is True

    def test_stop_file_exists_blocked(
        self, hardware_profile: DeviceProfile, hardware_config: SafetyConfig
    ):
        stop_path = Path(hardware_profile.safety.emergency_stop_file)
        try:
            stop_path.touch()
            checker = EmergencyStopMonitor()
            action = ActionRequest(action_type=ActionType.CLICK)
            verdict = checker.check(action, hardware_profile, hardware_config)
            assert verdict.allowed is False
            assert verdict.layer == "L5_emergency_stop"
            assert "Emergency stop" in verdict.reason
        finally:
            if stop_path.exists():
                stop_path.unlink()

    def test_skipped_for_software_profiles(
        self, software_profile: DeviceProfile, software_config: SafetyConfig
    ):
        # Even if stop file exists, software profiles skip L5
        stop_path = Path(software_profile.safety.emergency_stop_file)
        try:
            stop_path.touch()
            checker = EmergencyStopMonitor()
            action = ActionRequest(action_type=ActionType.CLICK)
            verdict = checker.check(action, software_profile, software_config)
            assert verdict.allowed is True
        finally:
            if stop_path.exists():
                stop_path.unlink()


# --- SafetyGuard (chained layers) ---


class TestSafetyGuard:
    def test_software_profile_only_l1(self, software_profile: DeviceProfile):
        guard = SafetyGuard(software_profile)
        # L1 allowed
        verdict = guard.check(ActionRequest(action_type=ActionType.CLICK))
        assert verdict.allowed is True
        # L1 blocked
        verdict = guard.check(ActionRequest(action_type=ActionType.DRAG))
        assert verdict.allowed is False
        assert verdict.layer == "L1_whitelist"

    def test_hardware_profile_all_layers(self, hardware_profile: DeviceProfile):
        # Ensure no stop file
        stop_path = Path(hardware_profile.safety.emergency_stop_file)
        if stop_path.exists():
            stop_path.unlink()

        guard = SafetyGuard(hardware_profile, auto_approve=True)
        # Simple allowed action
        verdict = guard.check(ActionRequest(action_type=ActionType.CLICK))
        assert verdict.allowed is True

    def test_hardware_l1_blocks_before_l2(self, hardware_profile: DeviceProfile):
        guard = SafetyGuard(hardware_profile, auto_approve=True)
        # DRAG is not in hardware_profile.allowed_actions
        verdict = guard.check(
            ActionRequest(
                action_type=ActionType.DRAG,
                parameters={"temperature": 999},
            )
        )
        assert verdict.allowed is False
        assert verdict.layer == "L1_whitelist"

    def test_hardware_l2_blocks_out_of_bounds(self, hardware_profile: DeviceProfile):
        guard = SafetyGuard(hardware_profile, auto_approve=True)
        verdict = guard.check(
            ActionRequest(
                action_type=ActionType.CLICK,
                parameters={"temperature": 100},
            )
        )
        assert verdict.allowed is False
        assert verdict.layer == "L2_parameter_bounds"

    def test_hardware_l5_emergency_stop(self, hardware_profile: DeviceProfile):
        stop_path = Path(hardware_profile.safety.emergency_stop_file)
        try:
            stop_path.touch()
            guard = SafetyGuard(hardware_profile, auto_approve=True)
            verdict = guard.check(ActionRequest(action_type=ActionType.CLICK))
            assert verdict.allowed is False
            assert verdict.layer == "L5_emergency_stop"
        finally:
            if stop_path.exists():
                stop_path.unlink()

    def test_config_auto_derived_from_profile(self, hardware_profile: DeviceProfile):
        guard = SafetyGuard(hardware_profile)
        assert guard.config.hardware_connected is True
        assert guard.config.level == SafetyLevel.STRICT

    def test_explicit_config_overrides(self, hardware_profile: DeviceProfile):
        config = SafetyConfig(
            level=SafetyLevel.PERMISSIVE,
            hardware_connected=False,
        )
        guard = SafetyGuard(hardware_profile, config=config)
        assert guard.config.hardware_connected is False
        # Only L1 layer since hardware_connected=False in config
        assert len(guard._layers) == 1

    def test_record_action(self, software_profile: DeviceProfile):
        guard = SafetyGuard(software_profile)
        action = ActionRequest(action_type=ActionType.CLICK)
        guard.record_action(action)
        guard.record_action(action)
        assert len(guard._history) == 2


# --- Rate limiting ---


class TestRateLimiting:
    def test_rate_limit_exceeded_blocked(self, hardware_profile: DeviceProfile):
        """Exceed max_actions_per_minute → blocked."""
        guard = SafetyGuard(hardware_profile, auto_approve=True)
        action = ActionRequest(action_type=ActionType.CLICK)

        # Record max_actions_per_minute actions (10 for hardware_profile)
        for _ in range(hardware_profile.safety.max_actions_per_minute):
            verdict = guard.check(action)
            assert verdict.allowed is True
            guard.record_action(action)

        # Next action should be rate-limited
        verdict = guard.check(action)
        assert verdict.allowed is False
        assert verdict.layer == "rate_limit"
        assert "Rate limit exceeded" in verdict.reason

    def test_rate_limit_not_hit_under_threshold(self, software_profile: DeviceProfile):
        guard = SafetyGuard(software_profile)
        action = ActionRequest(action_type=ActionType.CLICK)

        # Record fewer than max (60 for software)
        for _ in range(5):
            verdict = guard.check(action)
            assert verdict.allowed is True
            guard.record_action(action)

        verdict = guard.check(action)
        assert verdict.allowed is True

    def test_rate_limit_history_bounded(self, software_profile: DeviceProfile):
        guard = SafetyGuard(software_profile)
        action = ActionRequest(action_type=ActionType.CLICK)

        # Record more than deque maxlen
        for _ in range(100):
            guard.record_action(action)

        # Deque should cap at 10000
        assert len(guard._history) == 100  # well under 10K, just verify it works
