"""Tests for remaining coverage gaps across multiple modules."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from device_use.core.models import DeviceProfile

# ===========================================================================
# core/prompts — workflows branch (lines 38-40)
# ===========================================================================


class TestPromptsWorkflows:
    def test_system_prompt_with_workflows(self):
        from device_use.core.models import WorkflowDefinition
        from device_use.core.prompts import PromptBuilder

        profile = DeviceProfile(
            name="test",
            software="App",
            workflows=[
                WorkflowDefinition(name="open_file", description="Open a file from disk"),
                WorkflowDefinition(name="save_file", description="Save current document"),
            ],
        )
        builder = PromptBuilder(profile)
        prompt = builder.system_prompt()
        assert "open_file" in prompt
        assert "save_file" in prompt
        assert "Available workflows" in prompt


# ===========================================================================
# core/observer — capture_full_screen and observe branches
# ===========================================================================


class TestObserverCoverage:
    def test_capture_full_screen(self):
        from device_use.core.observer import ScreenObserver

        mock_wm = MagicMock()
        observer = ScreenObserver(mock_wm)
        # Mock the whole capture_full_screen to test the scale_image path
        with (
            patch("mss.mss") as mock_mss,
            patch("PIL.Image.frombytes") as mock_frombytes,
            patch.object(ScreenObserver, "scale_image", return_value=b"scaled_png"),
        ):
            mock_sct = MagicMock()
            mock_sct.__enter__ = MagicMock(return_value=mock_sct)
            mock_sct.__exit__ = MagicMock(return_value=False)
            mock_sct.monitors = [{}, {"left": 0, "top": 0, "width": 1920, "height": 1080}]
            mock_shot = MagicMock()
            mock_shot.size = (1920, 1080)
            mock_shot.bgra = b"\x00" * (1920 * 1080 * 4)
            mock_sct.grab.return_value = mock_shot
            mock_mss.return_value = mock_sct

            mock_img = MagicMock()
            mock_img.save = MagicMock(side_effect=lambda b, **kw: b.write(b"PNG"))
            mock_frombytes.return_value = mock_img

            result = observer.capture_full_screen()
            assert result == b"scaled_png"

    def test_observe_with_backend(self):
        from device_use.core.observer import ScreenObserver

        mock_wm = MagicMock()
        mock_backend = MagicMock()
        mock_backend.observe = AsyncMock(
            return_value={"description": "screen state", "elements": [{"name": "btn"}]}
        )
        observer = ScreenObserver(mock_wm, backend=mock_backend)

        with (
            patch.object(observer, "capture_and_scale", return_value=b"PNG"),
        ):
            result = asyncio.run(observer.observe("win123", context="test"))
        assert result["description"] == "screen state"
        assert len(result["elements"]) == 1

    def test_observe_without_backend(self):
        from device_use.core.observer import ScreenObserver

        mock_wm = MagicMock()
        observer = ScreenObserver(mock_wm, backend=None)

        with patch.object(observer, "capture_and_scale", return_value=b"PNG"):
            result = asyncio.run(observer.observe("win123"))
        assert result["description"] == ""
        assert result["elements"] == []


# ===========================================================================
# core/window_manager — _normalize_id, _check_linux_deps
# ===========================================================================


class TestWindowManagerCoverage:
    def test_normalize_id_int(self):
        from device_use.core.window_manager import WindowManager

        assert WindowManager._normalize_id(42) == 42

    def test_normalize_id_hex(self):
        from device_use.core.window_manager import WindowManager

        assert WindowManager._normalize_id("0x2a") == 42

    def test_normalize_id_decimal_str(self):
        from device_use.core.window_manager import WindowManager

        assert WindowManager._normalize_id("42") == 42

    def test_check_linux_deps_missing(self):
        from device_use.core.window_manager import WindowManager

        wm = MagicMock(spec=WindowManager)
        wm._check_linux_deps = WindowManager._check_linux_deps.__get__(wm)
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="not installed"):
                wm._check_linux_deps()

    def test_get_active_window_int_error(self):
        from device_use.core.window_manager import WindowManager

        wm = MagicMock(spec=WindowManager)
        wm._get_active_window_int = WindowManager._get_active_window_int.__get__(wm)
        import subprocess

        with patch("subprocess.run", side_effect=subprocess.CalledProcessError(1, "xdotool")):
            result = wm._get_active_window_int()
        assert result == -1


# ===========================================================================
# core/agent — uncovered branches
# ===========================================================================


class TestAgentCoverage:
    @pytest.mark.asyncio
    async def test_capture_with_observer_full_screen(self):
        from device_use.core.agent import DeviceAgent

        profile = DeviceProfile(name="test", software="App")
        backend = MagicMock()
        backend.supports_grounding = True
        observer = MagicMock()
        observer.capture_full_screen.return_value = b"PNG"

        agent = DeviceAgent(profile, backend, observer=observer)
        # No window_id in metadata -> full screen
        result = await agent._capture_screenshot()
        observer.capture_full_screen.assert_called_once()

    @pytest.mark.asyncio
    async def test_capture_with_observer_window(self):
        from device_use.core.agent import DeviceAgent

        profile = DeviceProfile(name="test", software="App", metadata={"window_id": "0x12345"})
        backend = MagicMock()
        backend.supports_grounding = True
        observer = MagicMock()
        observer.capture_and_scale.return_value = b"PNG"

        agent = DeviceAgent(profile, backend, observer=observer)
        result = await agent._capture_screenshot()
        observer.capture_and_scale.assert_called_once_with(window_id="0x12345")

    @pytest.mark.asyncio
    async def test_plan_no_screenshot(self):
        from device_use.core.agent import DeviceAgent

        profile = DeviceProfile(name="test", software="App")
        backend = MagicMock()
        backend.supports_grounding = True

        agent = DeviceAgent(profile, backend)
        result = await agent._plan(b"", "task", 0)
        assert result["error"] == "No screenshot — cannot plan"

    @pytest.mark.asyncio
    async def test_observe_no_screenshot(self):
        from device_use.core.agent import DeviceAgent

        profile = DeviceProfile(name="test", software="App")
        backend = MagicMock()
        backend.supports_grounding = True

        agent = DeviceAgent(profile, backend)
        result = await agent._observe(b"", "task", 0)
        assert result == "No screenshot available"

    @pytest.mark.asyncio
    async def test_consecutive_parse_failures_abort(self):
        from device_use.core.agent import DeviceAgent

        profile = DeviceProfile(name="test", software="App")
        backend = MagicMock()
        backend.supports_grounding = True
        backend.observe = AsyncMock(return_value={"description": "screen"})
        backend.plan = AsyncMock(
            return_value={
                "done": False,
                "action": {"action_type": "fly_to_moon"},
            }
        )

        agent = DeviceAgent(profile, backend, max_steps=10)
        agent._capture_screenshot = AsyncMock(return_value=b"\x89PNG")
        agent._executor._settle_delay = 0

        result = await agent.execute("bad task")
        assert result.success is False
        assert "parse failures" in result.error

    def test_profile_property(self):
        from device_use.core.agent import DeviceAgent

        profile = DeviceProfile(name="test", software="App")
        backend = MagicMock()
        backend.supports_grounding = True
        agent = DeviceAgent(profile, backend)
        assert agent.profile.name == "test"


# ===========================================================================
# safety/guard — rate limit line 63
# ===========================================================================


class TestSafetyGuardRateLimit:
    def test_rate_limit_blocks(self):
        from device_use.core.models import ActionRequest, ActionType
        from device_use.safety.guard import SafetyGuard

        profile = DeviceProfile(name="test", software="App")
        # Override safety to have max 2 actions/minute
        profile.safety.max_actions_per_minute = 2
        guard = SafetyGuard(profile, auto_approve=False)

        action = ActionRequest(action_type=ActionType.CLICK)
        # Record 2 actions
        guard.record_action(action)
        guard.record_action(action)

        # Third should be blocked
        verdict = guard.check(action)
        assert verdict.allowed is False
        assert "Rate limit" in verdict.reason


# ===========================================================================
# profiles/loader — uncovered lines
# ===========================================================================


class TestProfileLoaderCoverage:
    def test_load_from_yaml_path(self, tmp_path):
        from device_use.profiles.loader import load_profile

        profile_data = {
            "name": "test-instrument",
            "software": "TestApp",
        }
        import yaml

        path = tmp_path / "test.yaml"
        with open(path, "w") as f:
            yaml.dump(profile_data, f)

        profile = load_profile(str(path))
        assert profile.name == "test-instrument"

    def test_load_invalid_yaml(self, tmp_path):
        from device_use.profiles.loader import _load_from_file

        path = tmp_path / "bad.yaml"
        path.write_text("just a string")
        with pytest.raises(ValueError, match="must be a mapping"):
            _load_from_file(path)

    def test_list_profiles_nonexistent_dir(self, tmp_path):
        from device_use.profiles.loader import list_profiles

        result = list_profiles(tmp_path / "nonexistent")
        assert result == []

    def test_list_profiles_broken_yaml(self, tmp_path):
        from device_use.profiles.loader import list_profiles

        (tmp_path / "broken.yaml").write_text("{invalid yaml: [}")
        result = list_profiles(tmp_path)
        assert result == []

    def test_validate_profile(self):
        from device_use.profiles.loader import validate_profile

        profile = validate_profile({"name": "test", "software": "App"})
        assert profile.name == "test"

    def test_load_substring_match(self):
        from device_use.profiles.loader import load_profile

        profile = load_profile("fiji")
        assert "fiji" in profile.name.lower()


# ===========================================================================
# integrations/labclaw — connect failure (lines 79-81)
# ===========================================================================


class TestLabClawCoverage:
    @pytest.mark.asyncio
    async def test_connect_failure(self):
        from device_use.integrations.labclaw import GUIDriver

        profile = MagicMock()
        backend = MagicMock()

        driver = GUIDriver(profile, backend)
        with patch("device_use.integrations.labclaw.DeviceAgent", side_effect=ValueError("bad")):
            result = await driver.connect()
        assert result is False
        assert driver.is_connected is False


# ===========================================================================
# integrations/mcp_server — uncovered tools
# ===========================================================================


class TestMCPServerCoverage:
    def test_nmr_process(self):
        from device_use.integrations import mcp_server

        mock_orch = MagicMock()
        mock_spectrum = MagicMock()
        mock_spectrum.title = "Test"
        mock_spectrum.solvent = "CDCl3"
        mock_spectrum.frequency_mhz = 400.0
        mock_spectrum.peaks = [MagicMock(ppm=7.2, intensity=100.0)]
        mock_orch.call_tool.return_value = mock_spectrum

        with patch.object(mcp_server, "_get_orchestrator", return_value=mock_orch):
            result = mcp_server.nmr_process("/data/test/1")
        import json

        data = json.loads(result)
        assert data["title"] == "Test"
        assert len(data["peaks"]) == 1

    def test_nmr_identify(self):
        from device_use.integrations import mcp_server

        mock_orch = MagicMock()
        mock_spectrum = MagicMock()
        mock_spectrum.title = "alpha ionone"
        mock_spectrum.sample_name = ""
        mock_orch.call_tool.return_value = mock_spectrum

        with (
            patch.object(mcp_server, "_get_orchestrator", return_value=mock_orch),
            patch("device_use.instruments.nmr.brain.NMRBrain") as MockBrain,
        ):
            MockBrain.return_value.interpret_spectrum.return_value = "Analysis result"
            result = mcp_server.nmr_identify("/data/test/1", "C13H20O")
        assert result == "Analysis result"

    def test_plate_reader_list_assays(self):
        from device_use.integrations import mcp_server

        mock_orch = MagicMock()
        mock_orch.call_tool.return_value = [{"name": "elisa", "type": "absorbance"}]

        with patch.object(mcp_server, "_get_orchestrator", return_value=mock_orch):
            result = mcp_server.plate_reader_list_assays()
        import json

        data = json.loads(result)
        assert len(data) == 1


# ===========================================================================
# instruments/plate_reader/adapter — uncovered lines
# ===========================================================================


class TestPlateReaderAdapterCoverage:
    def test_connect_api_returns_false(self):
        from device_use.instruments.plate_reader.adapter import PlateReaderAdapter

        adapter = PlateReaderAdapter(mode="api")
        result = adapter.connect()
        assert result is False

    def test_connect_gui_returns_false(self):
        from device_use.instruments.plate_reader.adapter import PlateReaderAdapter

        adapter = PlateReaderAdapter(mode="gui")
        result = adapter.connect()
        assert result is False

    def test_acquire_offline_raises(self):
        from device_use.instruments.plate_reader.adapter import PlateReaderAdapter

        adapter = PlateReaderAdapter()
        adapter._connected = True
        with pytest.raises(RuntimeError, match="OFFLINE"):
            adapter.acquire()

    def test_acquire_nonoffline_raises(self):
        from device_use.instruments.plate_reader.adapter import PlateReaderAdapter

        adapter = PlateReaderAdapter(mode="api")
        adapter._connected = True
        with pytest.raises(NotImplementedError):
            adapter.acquire()

    def test_list_datasets_nonoffline_raises(self):
        from device_use.instruments.plate_reader.adapter import PlateReaderAdapter

        adapter = PlateReaderAdapter(mode="api")
        adapter._mode_val = "api"
        adapter._connected = True
        # Force the mode to api
        from device_use.instruments.base import ControlMode

        adapter._mode = ControlMode.API
        with pytest.raises(NotImplementedError):
            adapter.list_datasets()

    def test_process_nonoffline_raises(self):
        from device_use.instruments.base import ControlMode
        from device_use.instruments.plate_reader.adapter import PlateReaderAdapter

        adapter = PlateReaderAdapter(mode="api")
        adapter._connected = True
        adapter._mode = ControlMode.API
        with pytest.raises(NotImplementedError):
            adapter.process("data")

    def test_ensure_connected_auto_connects(self):
        from device_use.instruments.plate_reader.adapter import PlateReaderAdapter

        adapter = PlateReaderAdapter()
        adapter._ensure_connected()
        assert adapter.connected is True

    def test_ensure_connected_fails(self):
        from device_use.instruments.base import ControlMode
        from device_use.instruments.plate_reader.adapter import PlateReaderAdapter

        adapter = PlateReaderAdapter(mode=ControlMode.API)
        with pytest.raises(RuntimeError, match="Failed to connect"):
            adapter._ensure_connected()

    def test_reading_to_csv(self):
        from device_use.instruments.plate_reader.adapter import PlateReaderAdapter

        adapter = PlateReaderAdapter()
        adapter.connect()
        reading = adapter.process("elisa_standard_curve")
        csv_str = adapter.reading_to_csv(reading)
        assert "Protocol" in csv_str
        assert len(csv_str) > 100


# ===========================================================================
# instruments/plate_reader/brain — uncovered lines
# ===========================================================================


class TestPlateReaderBrainCoverage:
    def test_cached_or_error_unknown_protocol(self):
        from device_use.instruments.plate_reader.brain import PlateReaderBrain

        with patch.dict("os.environ", {}, clear=True):
            brain = PlateReaderBrain()
        reading = MagicMock()
        reading.protocol = "Unknown Protocol XYZ"
        with pytest.raises(RuntimeError, match="No ANTHROPIC_API_KEY"):
            brain._cached_or_error(reading, stream=False)

    def test_interpret_reading_cached(self):
        from device_use.instruments.plate_reader.brain import PlateReaderBrain

        with patch.dict("os.environ", {}, clear=True):
            brain = PlateReaderBrain()
        reading = MagicMock()
        reading.protocol = "ELISA Standard Curve"
        result = brain.interpret_reading(reading)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_interpret_reading_cached_stream(self):
        from device_use.instruments.plate_reader.brain import PlateReaderBrain

        with patch.dict("os.environ", {}, clear=True):
            brain = PlateReaderBrain()
        reading = MagicMock()
        reading.protocol = "ELISA Standard Curve"
        gen = brain.interpret_reading(reading, stream=True)
        text = "".join(gen)
        assert len(text) > 0


# ===========================================================================
# instruments/plate_reader/visualizer — output_path branch
# ===========================================================================


class TestPlateReaderVisualizerCoverage:
    def test_plot_heatmap_to_file(self, tmp_path):
        from device_use.instruments.plate_reader.adapter import PlateReaderAdapter
        from device_use.instruments.plate_reader.visualizer import plot_plate_heatmap

        adapter = PlateReaderAdapter()
        adapter.connect()
        reading = adapter.process("elisa_standard_curve")
        out_file = str(tmp_path / "heatmap.png")
        result = plot_plate_heatmap(reading, output_path=out_file)
        assert Path(out_file).exists()


# ===========================================================================
# tools/tooluniverse — uncovered lines
# ===========================================================================


class TestToolUniverseCoverage:
    def test_tool_props(self):
        from device_use.tools.tooluniverse import ToolUniverseTool

        tool = ToolUniverseTool()
        assert tool.name == "tooluniverse"
        assert "600+" in tool.description
        assert tool.connected is False

    def test_connect_not_available(self):
        from device_use.tools.tooluniverse import ToolUniverseError, ToolUniverseTool

        tool = ToolUniverseTool()
        with patch("device_use.tools.tooluniverse._TU_AVAILABLE", False):
            with pytest.raises(ToolUniverseError):
                tool.connect()

    def test_execute_find(self):
        from device_use.tools.tooluniverse import ToolUniverseTool

        tool = ToolUniverseTool()
        tool._connected = True
        tool._tu = MagicMock()
        tool._tu.run.return_value = [{"name": "tool1"}]
        result = tool.execute(action="find", query="NMR", limit=5)
        assert len(result) == 1

    def test_execute_call(self):
        from device_use.tools.tooluniverse import ToolUniverseTool

        tool = ToolUniverseTool()
        tool._connected = True
        tool._tu = MagicMock()
        tool._tu.run.return_value = {"result": "ok"}
        result = tool.execute(action="call", tool_name="test_tool", arg1="val1")
        assert result == {"result": "ok"}

    def test_execute_call_no_name(self):
        from device_use.tools.tooluniverse import ToolUniverseTool

        tool = ToolUniverseTool()
        tool._connected = True
        tool._tu = MagicMock()
        with pytest.raises(ValueError, match="tool_name required"):
            tool.execute(action="call")

    def test_execute_spec(self):
        from device_use.tools.tooluniverse import ToolUniverseTool

        tool = ToolUniverseTool()
        tool._connected = True
        tool._tu = MagicMock()
        tool._tu.tool_specification.return_value = {"spec": "data"}
        result = tool.execute(action="spec", tool_name="test_tool")
        assert result == {"spec": "data"}

    def test_execute_unknown_action(self):
        from device_use.tools.tooluniverse import ToolUniverseTool

        tool = ToolUniverseTool()
        tool._connected = True
        tool._tu = MagicMock()
        with pytest.raises(ValueError, match="Unknown action"):
            tool.execute(action="invalid")

    def test_ensure_connected_auto(self):
        from device_use.tools.tooluniverse import ToolUniverseError, ToolUniverseTool

        tool = ToolUniverseTool()
        with patch("device_use.tools.tooluniverse._TU_AVAILABLE", False):
            with pytest.raises(ToolUniverseError):
                tool._ensure_connected()

    def test_find_chemistry_tools(self):
        from device_use.tools.tooluniverse import ToolUniverseTool

        tool = ToolUniverseTool()
        tool._connected = True
        tool._tu = MagicMock()
        tool._tu.run.return_value = []
        result = tool.find_chemistry_tools()
        assert result == []

    def test_find_spectroscopy_tools(self):
        from device_use.tools.tooluniverse import ToolUniverseTool

        tool = ToolUniverseTool()
        tool._connected = True
        tool._tu = MagicMock()
        tool._tu.run.return_value = []
        result = tool.find_spectroscopy_tools()
        assert result == []

    def test_find_drug_discovery_tools(self):
        from device_use.tools.tooluniverse import ToolUniverseTool

        tool = ToolUniverseTool()
        tool._connected = True
        tool._tu = MagicMock()
        tool._tu.run.return_value = []
        result = tool.find_drug_discovery_tools()
        assert result == []

    def test_get_available_tools(self):
        from device_use.tools.tooluniverse import get_available_tools

        tools = get_available_tools()
        assert len(tools) >= 1
        assert tools[0].name == "pubchem"


# ===========================================================================
# tools/pubchem — uncovered execute paths
# ===========================================================================


class TestPubChemCoverage:
    def test_execute_by_cid(self):
        from device_use.tools.pubchem import PubChemTool

        tool = PubChemTool()
        with patch.object(tool, "get_compound_summary", return_value="summary") as mock:
            result = tool.execute(cid=2244)
        mock.assert_called_once_with(2244)

    def test_execute_by_formula(self):
        from device_use.tools.pubchem import PubChemTool

        tool = PubChemTool()
        with patch.object(tool, "lookup_by_formula", return_value={"CID": 123}) as mock:
            result = tool.execute(formula="C9H8O4")
        mock.assert_called_once_with("C9H8O4")

    def test_execute_no_args(self):
        from device_use.tools.pubchem import PubChemTool

        tool = PubChemTool()
        with pytest.raises(ValueError, match="requires one of"):
            tool.execute()

    def test_fetch_json_http_error(self):
        import urllib.error

        from device_use.tools.pubchem import PubChemError, _fetch_json

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.HTTPError("url", 404, "Not Found", {}, None),
        ):
            with pytest.raises(PubChemError, match="HTTP 404"):
                _fetch_json("https://example.com/api")

    def test_fetch_json_url_error(self):
        import urllib.error

        from device_use.tools.pubchem import PubChemError, _fetch_json

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            with pytest.raises(PubChemError, match="connection error"):
                _fetch_json("https://example.com/api")

    def test_fetch_json_invalid_json(self):
        from device_use.tools.pubchem import PubChemError, _fetch_json

        mock_response = MagicMock()
        mock_response.read.return_value = b"not json"
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_response):
            with pytest.raises(PubChemError, match="non-JSON"):
                _fetch_json("https://example.com/api")

    def test_extract_compound_empty(self):
        from device_use.tools.pubchem import PubChemError, _extract_compound

        with pytest.raises(PubChemError, match="No compound"):
            _extract_compound({})

    def test_extract_cid_from_identifier_list(self):
        from device_use.tools.pubchem import _extract_cid

        data = {"IdentifierList": {"CID": [12345]}}
        assert _extract_cid(data) == 12345

    def test_extract_cid_failure(self):
        from device_use.tools.pubchem import PubChemError, _extract_cid

        with pytest.raises(PubChemError, match="Could not extract"):
            _extract_cid({})


# ===========================================================================
# orchestrator — uncovered lines (emit error, etc.)
# ===========================================================================


class TestOrchestratorCoverage:
    def test_emit_catches_listener_errors(self):
        from device_use.orchestrator import Event, EventType, ToolRegistry

        registry = ToolRegistry()

        def bad_listener(event):
            raise RuntimeError("listener bug")

        registry.add_listener(bad_listener)
        # This should not raise
        registry._emit(Event(event_type=EventType.STEP_START, data={}))


# ===========================================================================
# skills/context — uncovered lines
# ===========================================================================


class TestSkillsContextCoverage:
    def test_missing_device_dir(self, tmp_path):
        from device_use.skills.context import SkillContext

        with pytest.raises(FileNotFoundError, match="not found"):
            SkillContext("nonexistent-device", skills_dir=tmp_path)

    def test_missing_soul_md(self, tmp_path):
        from device_use.skills.context import SkillContext

        device_dir = tmp_path / "devices" / "my-device"
        device_dir.mkdir(parents=True)
        with pytest.raises(FileNotFoundError, match="SOUL.md"):
            SkillContext("my-device", skills_dir=tmp_path)

    def test_build_prompt_minimal(self, tmp_path):
        from device_use.skills.context import SkillContext

        device_dir = tmp_path / "devices" / "my-device"
        device_dir.mkdir(parents=True)
        (device_dir / "SOUL.md").write_text("# My Device\nYou control this device.")

        ctx = SkillContext("my-device", skills_dir=tmp_path)
        prompt = ctx.build_prompt("Process data")
        assert "My Device" in prompt
        assert "my-device" in prompt


# ===========================================================================
# actions/models — parse_action line 131
# ===========================================================================


class TestParseActionCoverage:
    def test_parse_action_unknown_type(self):
        from device_use.actions.models import parse_action

        with pytest.raises(ValueError, match="is not a valid"):
            parse_action({"action_type": "teleport"})


# ===========================================================================
# web/app — uncovered endpoints
# ===========================================================================


class TestWebAppCoverage:
    def test_list_tools_endpoint(self):
        from fastapi.testclient import TestClient

        from device_use.web.app import app

        client = TestClient(app)
        resp = client.get("/api/tools")
        assert resp.status_code == 200
        data = resp.json()
        assert "tools" in data
        assert "count" in data

    def test_architecture_endpoint(self):
        from fastapi.testclient import TestClient

        from device_use.web.app import app

        client = TestClient(app)
        resp = client.get("/api/architecture")
        assert resp.status_code == 200
        data = resp.json()
        assert "layers" in data
