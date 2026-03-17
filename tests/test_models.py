"""Tests for core data models and profile loading."""

import pytest
from pydantic import ValidationError

from device_use.core.models import (
    ActionRequest,
    ActionResult,
    ActionType,
    AgentState,
    DeviceProfile,
    SafetyConstraints,
    SafetyLevel,
    ScreenDefinition,
    UIElement,
    WorkflowDefinition,
    WorkflowStep,
)
from device_use.profiles.loader import (
    BUILTIN_PROFILES_DIR,
    list_profiles,
    load_profile,
    validate_profile,
)

# --- Model construction ---


class TestDeviceProfile:
    def test_minimal_profile(self):
        profile = DeviceProfile(name="test", software="TestApp")
        assert profile.name == "test"
        assert profile.software == "TestApp"
        assert profile.hardware_connected is False
        assert profile.safety_level == SafetyLevel.NORMAL
        assert len(profile.allowed_actions) == len(ActionType)

    def test_hardware_profile(self):
        profile = DeviceProfile(
            name="microscope",
            software="ZEN",
            hardware_connected=True,
            safety_level=SafetyLevel.STRICT,
        )
        assert profile.hardware_connected is True
        assert profile.safety_level == SafetyLevel.STRICT

    def test_profile_with_workflows(self):
        step = WorkflowStep(
            action=ActionType.CLICK,
            target="button",
            description="Click the button",
        )
        workflow = WorkflowDefinition(
            name="test_workflow",
            steps=[step],
        )
        profile = DeviceProfile(
            name="test",
            software="App",
            workflows=[workflow],
        )
        assert len(profile.workflows) == 1
        assert profile.workflows[0].steps[0].action == ActionType.CLICK

    def test_profile_with_ui_elements(self):
        elem = UIElement(
            name="start_btn",
            description="Start button",
            region=(100, 200, 50, 30),
            element_type="button",
        )
        profile = DeviceProfile(
            name="test",
            software="App",
            ui_elements=[elem],
        )
        assert profile.ui_elements[0].region == (100, 200, 50, 30)

    def test_profile_roundtrip_json(self):
        profile = DeviceProfile(
            name="test",
            software="App",
            hardware_connected=True,
            safety=SafetyConstraints(
                max_actions_per_minute=10,
                bounds={"temp_max": 45},
            ),
        )
        json_str = profile.model_dump_json()
        restored = DeviceProfile.model_validate_json(json_str)
        assert restored.name == profile.name
        assert restored.hardware_connected is True
        assert restored.safety.bounds["temp_max"] == 45


class TestActionModels:
    def test_action_request(self):
        req = ActionRequest(
            action_type=ActionType.CLICK,
            coordinates=(100, 200),
            description="Click start",
        )
        assert req.coordinates == (100, 200)

    def test_action_result_success(self):
        req = ActionRequest(action_type=ActionType.CLICK)
        result = ActionResult(success=True, action=req, duration_ms=150.0)
        assert result.success is True
        assert result.duration_ms == 150.0

    def test_action_result_failure(self):
        req = ActionRequest(action_type=ActionType.TYPE, parameters={"text": "hello"})
        result = ActionResult(success=False, action=req, error="Window not found")
        assert result.success is False
        assert "Window" in result.error


class TestAgentState:
    def test_default_state(self):
        state = AgentState()
        assert state.step == 0
        assert state.status == "idle"
        assert state.history == []

    def test_state_with_history(self):
        state = AgentState(
            step=3,
            task="Open image.tif",
            status="running",
            history=[{"step": 0, "action": "click"}],
        )
        assert state.step == 3
        assert len(state.history) == 1


class TestEnums:
    def test_action_types(self):
        assert ActionType.CLICK.value == "click"
        assert ActionType("hotkey") == ActionType.HOTKEY

    def test_safety_levels(self):
        assert SafetyLevel.STRICT.value == "strict"
        assert SafetyLevel("permissive") == SafetyLevel.PERMISSIVE

    def test_invalid_action_type(self):
        with pytest.raises(ValueError):
            ActionType("invalid_action")


class TestScreenDefinition:
    def test_valid_screen(self):
        s = ScreenDefinition(width=1920, height=1080)
        assert s.width == 1920

    def test_zero_width_raises(self):
        with pytest.raises(ValidationError, match="must be > 0"):
            ScreenDefinition(width=0, height=1080)

    def test_zero_height_raises(self):
        with pytest.raises(ValidationError, match="must be > 0"):
            ScreenDefinition(width=1920, height=0)

    def test_negative_width_raises(self):
        with pytest.raises(ValidationError, match="must be > 0"):
            ScreenDefinition(width=-100, height=1080)


class TestValidation:
    def test_invalid_profile_missing_required(self):
        with pytest.raises(ValidationError):
            DeviceProfile()  # type: ignore — missing name, software

    def test_invalid_safety_level(self):
        with pytest.raises(ValidationError):
            DeviceProfile(name="x", software="y", safety_level="ultra_strict")


# --- Profile loading ---


class TestProfileLoader:
    def test_builtin_profiles_dir_exists(self):
        assert BUILTIN_PROFILES_DIR.exists()

    def test_load_fiji_profile(self):
        profile = load_profile("imagej-fiji")
        assert profile.name == "imagej-fiji"
        assert profile.software == "FIJI"
        assert profile.hardware_connected is False

    def test_load_gen5_profile(self):
        profile = load_profile("biotek-gen5")
        assert profile.name == "biotek-gen5"
        assert profile.hardware_connected is True
        assert profile.safety_level == SafetyLevel.STRICT

    def test_load_by_substring(self):
        profile = load_profile("fiji")
        assert profile.name == "imagej-fiji"

    def test_load_by_path(self):
        path = BUILTIN_PROFILES_DIR / "image-analysis" / "imagej-fiji.yaml"
        profile = load_profile(str(path))
        assert profile.name == "imagej-fiji"

    def test_load_nonexistent_raises(self):
        with pytest.raises(FileNotFoundError):
            load_profile("nonexistent-device-xyz")

    def test_list_profiles(self):
        profiles = list_profiles()
        assert len(profiles) >= 2
        names = [p["name"] for p in profiles]
        assert "imagej-fiji" in names
        assert "biotek-gen5" in names

    def test_validate_profile_valid(self):
        data = {"name": "test", "software": "App"}
        profile = validate_profile(data)
        assert profile.name == "test"

    def test_validate_profile_invalid(self):
        with pytest.raises(ValidationError):
            validate_profile({"description": "missing required fields"})

    def test_hardware_connected_flag_parsing(self):
        profiles = list_profiles()
        hw_flags = {p["name"]: p["hardware_connected"] for p in profiles}
        assert hw_flags["imagej-fiji"] is False
        assert hw_flags["biotek-gen5"] is True

    def test_gen5_safety_bounds(self):
        profile = load_profile("biotek-gen5")
        assert profile.safety.bounds["temperature_max"] == 45
        assert profile.safety.max_actions_per_minute == 10

    def test_fiji_workflows(self):
        profile = load_profile("imagej-fiji")
        workflow_names = [w.name for w in profile.workflows]
        assert "open_image" in workflow_names
        assert "measure_selection" in workflow_names
