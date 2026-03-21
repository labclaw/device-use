"""Targeted tests to close final device_use coverage gaps."""

from __future__ import annotations

import builtins
import importlib
import pathlib
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest


class TestPackageInitCoverage:
    def test_discover_plugins_registers_loaded_factory(self):
        from device_use import _discover_plugins
        from device_use.instruments.base import ControlMode

        class _EntryPoint:
            name = "fake"

            def load(self):
                return lambda mode: {"mode": mode.value}

        result = _discover_plugins(ControlMode.OFFLINE)
        with patch("importlib.metadata.entry_points", return_value=[_EntryPoint()]):
            result = _discover_plugins(ControlMode.OFFLINE)

        assert "fake" in result
        assert result["fake"]() == {"mode": "offline"}

    def test_discover_plugins_handles_entry_point_load_failure(self):
        from device_use import _discover_plugins
        from device_use.instruments.base import ControlMode

        class _BadEntryPoint:
            name = "broken"

            def load(self):
                raise RuntimeError("load failed")

        with patch("importlib.metadata.entry_points", return_value=[_BadEntryPoint()]):
            result = _discover_plugins(ControlMode.OFFLINE)
        assert result == {}

    def test_discover_plugins_handles_entry_point_discovery_failure_py311_path(self, monkeypatch):
        from device_use import _discover_plugins
        from device_use.instruments.base import ControlMode

        monkeypatch.setattr(sys, "version_info", (3, 11, 0))
        with patch("importlib.metadata.entry_points", side_effect=RuntimeError("boom")):
            result = _discover_plugins(ControlMode.OFFLINE)
        assert result == {}

    def test_create_orchestrator_handles_missing_builtin_adapters(self):
        import device_use

        original_import = builtins.__import__

        def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name in {
                "device_use.instruments.nmr.adapter",
                "device_use.instruments.plate_reader",
            }:
                raise ImportError("forced missing dependency")
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=_fake_import):
            orch = device_use.create_orchestrator(connect=False)

        assert orch.registry.list_instruments() == []


class TestAbstractProtocolCoverage:
    @pytest.mark.asyncio
    async def test_vision_backend_stub_methods_execute(self):
        from device_use.backends.base import VisionBackend

        assert VisionBackend.supports_grounding.fget(object()) is None
        assert await VisionBackend.observe(object(), b"png", "") is None
        assert await VisionBackend.plan(object(), b"png", "task", []) is None
        assert await VisionBackend.locate(object(), b"png", "button") is None

    def test_base_instrument_stub_methods_execute(self):
        from device_use.instruments.base import BaseInstrument

        assert BaseInstrument.info(object()) is None
        assert BaseInstrument.connect(object()) is None
        assert BaseInstrument.connected.fget(object()) is None
        assert BaseInstrument.mode.fget(object()) is None
        assert BaseInstrument.list_datasets(object()) is None
        assert BaseInstrument.acquire(object()) is None
        assert BaseInstrument.process(object(), "x") is None

    def test_base_tool_stub_methods_execute(self):
        from device_use.tools.base import BaseTool

        assert BaseTool.name.fget(object()) is None
        assert BaseTool.description.fget(object()) is None
        assert BaseTool.execute(object()) is None


class TestTopSpinAdapterCoverage:
    def test_connect_dispatches_api_and_gui_modes(self, tmp_path):
        from device_use.instruments.base import ControlMode
        from device_use.instruments.nmr.adapter import TopSpinAdapter

        api = TopSpinAdapter(topspin_dir=str(tmp_path), mode=ControlMode.API)
        with patch.object(api, "_connect_api", return_value=True) as mock_api:
            assert api.connect() is True
        mock_api.assert_called_once()

        gui = TopSpinAdapter(topspin_dir=str(tmp_path), mode=ControlMode.GUI)
        with patch.object(gui, "_connect_gui", return_value=True) as mock_gui:
            assert gui.connect() is True
        mock_gui.assert_called_once()

    def test_connect_api_success_path(self, tmp_path):
        from device_use.instruments.base import ControlMode
        from device_use.instruments.nmr.adapter import TopSpinAdapter

        fake_bruker = types.ModuleType("bruker")
        fake_bruker.__path__ = []
        fake_api_pkg = types.ModuleType("bruker.api")
        fake_api_pkg.__path__ = []
        fake_topspin = types.ModuleType("bruker.api.topspin")

        class _FakeTopspin:
            def __init__(self):
                self._provider = MagicMock()

            def getDataProvider(self):  # noqa: N802
                return self._provider

            def getVersion(self):  # noqa: N802
                return "5.0.0"

        fake_topspin.Topspin = _FakeTopspin

        with patch.dict(
            sys.modules,
            {
                "bruker": fake_bruker,
                "bruker.api": fake_api_pkg,
                "bruker.api.topspin": fake_topspin,
            },
        ):
            adapter = TopSpinAdapter(topspin_dir=str(tmp_path), mode=ControlMode.API)
            assert adapter._connect_api() is True
            assert adapter.connected is True

    def test_connect_gui_returns_false_when_no_gui_modes_available(self, tmp_path):
        from device_use.instruments.base import ControlMode
        from device_use.instruments.nmr.adapter import TopSpinAdapter

        class _FakeGUI:
            available = False
            command_mode_available = False

            def detect_topspin_window(self):  # pragma: no cover - should not be called
                raise AssertionError("detect_topspin_window should not run")

        with patch("device_use.instruments.nmr.gui_automation.TopSpinGUIAutomation", _FakeGUI):
            adapter = TopSpinAdapter(topspin_dir=str(tmp_path), mode=ControlMode.GUI)
            assert adapter._connect_gui() is False

    def test_list_examdata_skips_experiments_without_fid(self, tmp_path):
        from device_use.instruments.nmr.adapter import TopSpinAdapter

        examdata = tmp_path / "topspin" / "examdata" / "sample_a"
        (examdata / "1").mkdir(parents=True)
        exp2 = examdata / "2"
        exp2.mkdir(parents=True)
        (exp2 / "fid").write_text("fid")

        adapter = TopSpinAdapter(topspin_dir=str(tmp_path / "topspin"))
        datasets = adapter.list_examdata()
        assert len(datasets) == 1
        assert datasets[0]["expno"] == 2

    def test_process_dataset_routes_api_gui_and_fallback(self, tmp_path):
        from device_use.instruments.base import ControlMode
        from device_use.instruments.nmr.adapter import TopSpinAdapter

        adapter = TopSpinAdapter(topspin_dir=str(tmp_path), mode=ControlMode.API)
        adapter._connected = True
        with patch.object(adapter, "_process_via_api", return_value="api-result") as mock_api:
            assert adapter.process_dataset("a") == "api-result"
        mock_api.assert_called_once_with("a")

        adapter._mode = ControlMode.GUI
        adapter._connected = True
        with patch.object(adapter, "_process_via_gui", return_value="gui-result") as mock_gui:
            assert adapter.process_dataset("b") == "gui-result"
        mock_gui.assert_called_once_with("b")

        adapter._mode = ControlMode.API
        adapter._connected = False
        with patch.object(
            adapter, "_process_via_nmrglue", return_value="offline-result"
        ) as mock_off:
            assert adapter.process_dataset("c") == "offline-result"
        mock_off.assert_called_once_with("c")


class TestSpectralLibraryCoverage:
    def test_from_examdata_covers_loop_and_exception_paths(self, tmp_path, monkeypatch):
        from device_use.instruments.nmr.library import SpectralLibrary
        from device_use.instruments.nmr.processor import NMRPeak, NMRSpectrum

        sample_ok = tmp_path / "sample_ok"
        sample_bad = tmp_path / "sample_bad"
        hidden_sample = tmp_path / ".hidden_sample"
        for sample in (sample_ok, sample_bad, hidden_sample):
            sample.mkdir()

        ok_exp = sample_ok / "1"
        ok_exp.mkdir()
        (ok_exp / "fid").write_text("fid")
        (sample_ok / "2").mkdir()
        (sample_ok / "notes.txt").write_text("not a directory")

        bad_exp = sample_bad / "2"
        bad_exp.mkdir()
        (bad_exp / "fid").write_text("fid")

        hidden_exp = hidden_sample / "1"
        hidden_exp.mkdir()
        (hidden_exp / "fid").write_text("fid")

        original_exists = pathlib.Path.exists
        original_iterdir = pathlib.Path.iterdir
        virtual_examdata = "/opt/topspin5.0.0/examdata"

        def _exists(path_obj):
            if str(path_obj) == virtual_examdata:
                return True
            return original_exists(path_obj)

        def _iterdir(path_obj):
            if str(path_obj) == virtual_examdata:
                return iter([hidden_sample, sample_ok, sample_bad])
            return original_iterdir(path_obj)

        monkeypatch.setattr(pathlib.Path, "exists", _exists)
        monkeypatch.setattr(pathlib.Path, "iterdir", _iterdir)

        class _FakeProcessor:
            def read_bruker(self, dataset_path):
                if dataset_path.endswith("/2"):
                    raise RuntimeError("bad dataset")
                return {"acqus": {}}, np.array([1.0 + 0.0j])

            def process_1d(self, dic, fid, dataset_path):
                return NMRSpectrum(
                    data=np.array([1.0]),
                    ppm_scale=np.array([1.0]),
                    peaks=[NMRPeak(ppm=1.0, intensity=100.0)],
                    nucleus="1H",
                    title="ok",
                    sample_name="sample_ok",
                )

        with patch("device_use.instruments.nmr.processor.NMRProcessor", _FakeProcessor):
            lib = SpectralLibrary.from_examdata()

        assert len(lib) == 1
        assert lib.list_entries() == ["ok"]


class TestAgentCoverage:
    @pytest.mark.asyncio
    async def test_execute_skips_invalid_batched_actions(self):
        from device_use.core.agent import DeviceAgent
        from device_use.core.models import DeviceProfile

        profile = DeviceProfile(name="test", software="App")
        backend = MagicMock()
        backend.supports_grounding = True
        backend.observe = AsyncMock(return_value={"description": "screen"})
        backend.plan = AsyncMock(
            side_effect=[
                {
                    "done": False,
                    "reasoning": "first action",
                    "action": {"action_type": "wait", "seconds": 0},
                    "_remaining_actions": [{"action": {"action_type": "invalid_action"}}],
                },
                {"done": True, "data": {"ok": True}},
            ]
        )

        agent = DeviceAgent(profile, backend, max_steps=3)
        agent._capture_screenshot = AsyncMock(return_value=b"\x89PNG")
        agent._executor._settle_delay = 0

        result = await agent.execute("task")
        assert result.success is True
        assert len(result.actions) == 1

    @pytest.mark.asyncio
    async def test_execute_reraises_failsafe_exception(self):
        from device_use.core.agent import DeviceAgent
        from device_use.core.models import DeviceProfile

        class _FakeFailSafeError(Exception):
            pass

        profile = DeviceProfile(name="test", software="App")
        backend = MagicMock()
        backend.supports_grounding = True

        agent = DeviceAgent(profile, backend, max_steps=1)
        agent._capture_screenshot = AsyncMock(side_effect=_FakeFailSafeError("panic"))

        with patch("device_use.actions.executor._FailSafeException", _FakeFailSafeError):
            with pytest.raises(_FakeFailSafeError, match="panic"):
                await agent.execute("task")

    @pytest.mark.asyncio
    async def test_capture_screenshot_without_observer_returns_empty_bytes(self):
        from device_use.core.agent import DeviceAgent
        from device_use.core.models import DeviceProfile

        profile = DeviceProfile(name="test", software="App")
        backend = MagicMock()
        backend.supports_grounding = True
        agent = DeviceAgent(profile, backend, observer=None)
        assert await agent._capture_screenshot() == b""


class TestToolUniverseCoverage:
    def test_module_sets_available_when_tooluniverse_import_succeeds(self):
        import device_use.tools.tooluniverse as tu_mod

        fake_tooluniverse = types.ModuleType("tooluniverse")

        class _FakeToolUniverse:
            pass

        fake_tooluniverse.ToolUniverse = _FakeToolUniverse

        with patch.dict(sys.modules, {"tooluniverse": fake_tooluniverse}):
            module_name = "_tooluniverse_probe"
            spec = importlib.util.spec_from_file_location(module_name, tu_mod.__file__)
            probe_mod = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = probe_mod
            spec.loader.exec_module(probe_mod)
            assert probe_mod._TU_AVAILABLE is True
            sys.modules.pop(module_name, None)

    def test_ensure_connected_calls_connect_when_available(self):
        from device_use.tools.tooluniverse import ToolUniverseTool

        tool = ToolUniverseTool()
        with patch("device_use.tools.tooluniverse._TU_AVAILABLE", True):
            with patch.object(tool, "connect") as mock_connect:
                tool._ensure_connected()
        mock_connect.assert_called_once()

    def test_get_available_tools_includes_tooluniverse(self):
        from device_use.tools import tooluniverse as tu_mod

        with patch.object(tu_mod, "_TU_AVAILABLE", True):
            tools = tu_mod.get_available_tools()
        assert any(tool.name == "tooluniverse" for tool in tools)


class TestRemainingSingleLineCoverage:
    def test_parse_action_unknown_type_map_branch(self, monkeypatch):
        import device_use.actions.models as action_models

        class _Member:
            def __init__(self, value: str):
                self.value = value

            def __hash__(self):
                return hash(self.value)

            def __eq__(self, other):
                return isinstance(other, _Member) and self.value == other.value

        class _FakeActionType:
            CLICK = _Member("click")
            DOUBLE_CLICK = _Member("double_click")
            RIGHT_CLICK = _Member("right_click")
            TYPE = _Member("type")
            HOTKEY = _Member("hotkey")
            SCROLL = _Member("scroll")
            DRAG = _Member("drag")
            WAIT = _Member("wait")
            SCREENSHOT = _Member("screenshot")
            MOVE = _Member("move")

            def __new__(cls, _raw):
                return _Member("unknown")

        monkeypatch.setattr(action_models, "ActionType", _FakeActionType)
        with pytest.raises(ValueError, match="Unknown action type"):
            action_models.parse_action({"action_type": "click"})

    @pytest.mark.asyncio
    async def test_openai_legacy_adds_system_prompt_messages(self):
        from device_use.backends.openai_compat import OpenAICompatBackend

        with patch("device_use.backends.openai_compat.AsyncOpenAI"):
            backend = OpenAICompatBackend(model="gpt-4o")

        backend.system_prompt = "system message"
        captured_messages = {}

        async def _observe_chat(messages):
            captured_messages["observe"] = messages
            return '{"description": "ok", "elements": []}'

        async def _plan_chat(messages):
            captured_messages["plan"] = messages
            return (
                '{"action": {"action_type": "wait", "seconds": 1}, '
                '"reasoning": "ok", "done": false, "confidence": 0.8}'
            )

        backend._chat_call = _observe_chat
        await backend._observe_legacy(b"\x89PNG")

        backend._chat_call = _plan_chat
        await backend._plan_legacy(b"\x89PNG", "task")

        assert captured_messages["observe"][0]["role"] == "system"
        assert captured_messages["plan"][0]["role"] == "system"

    def test_gui_automation_init_client_import_error_with_api_key(self, monkeypatch):
        from device_use.instruments.nmr.gui_automation import TopSpinGUIAutomation

        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        original_import = builtins.__import__

        def _fake_import(name, globals=None, locals=None, fromlist=(), level=0):
            if name == "anthropic":
                raise ImportError("forced import error")
            return original_import(name, globals, locals, fromlist, level)

        with patch("builtins.__import__", side_effect=_fake_import):
            gui = TopSpinGUIAutomation()
        assert gui.available is False

    def test_gui_automation_send_to_computer_use_uses_take_screenshot_when_none(self):
        from device_use.instruments.nmr.gui_automation import TopSpinGUIAutomation

        gui = TopSpinGUIAutomation()
        gui._available = True
        gui._client = MagicMock()
        gui.take_screenshot = MagicMock(return_value=b"\x89PNG")

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text='{"action_type":"wait"}')]
        gui._client.messages.create.return_value = mock_response

        result = gui.send_to_computer_use("do thing", screenshot=None)
        assert "response" in result
        gui.take_screenshot.assert_called_once()

    def test_plate_reader_adapter_connect_gui_branch(self):
        from device_use.instruments.base import ControlMode
        from device_use.instruments.plate_reader.adapter import PlateReaderAdapter

        adapter = PlateReaderAdapter(mode=ControlMode.GUI)
        assert adapter.connect() is False

    def test_plate_reader_brain_includes_context_in_user_message(self):
        from device_use.instruments.plate_reader.adapter import PlateReaderAdapter
        from device_use.instruments.plate_reader.brain import PlateReaderBrain

        adapter = PlateReaderAdapter()
        adapter.connect()
        reading = adapter.process("elisa_standard_curve")

        with (
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
            patch("anthropic.Anthropic"),
        ):
            brain = PlateReaderBrain()

        brain._call = MagicMock(return_value="ok")
        result = brain.interpret_reading(reading, context="extra context", stream=False)
        assert result == "ok"
        assert "Additional context: extra context" in brain._call.call_args.args[1]

    def test_template_connect_unknown_mode_returns_false(self):
        from device_use.instruments.template import InstrumentTemplate

        template = InstrumentTemplate(mode="offline")
        template._mode = object()
        assert template.connect() is False

    def test_mcp_server_main_calls_run(self):
        from device_use.integrations import mcp_server

        with patch.object(mcp_server.mcp, "run") as mock_run:
            mcp_server.main()
        mock_run.assert_called_once()

    def test_retrieve_docs_uses_default_skills_dir(self):
        from device_use.knowledge.retriever import retrieve_docs

        result = retrieve_docs("nonexistent-device", "task")
        assert result == ""

    def test_pipeline_result_last_output_returns_none_when_no_completed_steps(self):
        from device_use.orchestrator import PipelineResult, StepResult, StepStatus

        result = PipelineResult(name="x")
        result.steps.append(("s1", StepResult(status=StepStatus.FAILED, error="bad")))
        assert result.last_output is None

    def test_orchestrator_emit_catches_listener_errors(self):
        from device_use.orchestrator import Event, EventType, Orchestrator

        orch = Orchestrator()

        def _bad_listener(_event):
            raise RuntimeError("listener failed")

        orch.on_event(_bad_listener)
        orch._emit(Event(event_type=EventType.STEP_START, data={}))

    def test_orchestrator_connect_all_skips_missing_instrument_instance(self):
        from device_use.instruments.base import ControlMode, InstrumentInfo
        from device_use.orchestrator import Orchestrator

        orch = Orchestrator()
        info = InstrumentInfo(
            name="ghost",
            vendor="N/A",
            instrument_type="nmr",
            supported_modes=[ControlMode.OFFLINE],
        )
        orch.registry.list_instruments = MagicMock(return_value=[info])
        orch.registry.get_instrument = MagicMock(return_value=None)

        assert orch.connect_all() == {}

    def test_safety_guard_prunes_expired_history_entries(self, monkeypatch):
        from device_use.core.models import ActionRequest, ActionType, DeviceProfile
        from device_use.safety.guard import SafetyGuard

        profile = DeviceProfile(name="test", software="App")
        guard = SafetyGuard(profile, auto_approve=True)

        guard._history.append(10.0)
        guard._history.append(100.0)
        monkeypatch.setattr("device_use.safety.guard.time.monotonic", lambda: 100.0)

        verdict = guard.check(ActionRequest(action_type=ActionType.CLICK))
        assert verdict.allowed is True
        assert list(guard._history) == [100.0]

    def test_skill_context_default_skills_dir_path(self):
        from device_use.skills.context import SkillContext

        with pytest.raises(FileNotFoundError):
            SkillContext("definitely-missing-device-name")
