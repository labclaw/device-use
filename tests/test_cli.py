"""Tests for the CLI module — all commands and helpers."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from device_use import cli

# ---------------------------------------------------------------------------
# _list_profiles
# ---------------------------------------------------------------------------


class TestListProfiles:
    def test_list_profiles_output(self, capsys):
        cli._list_profiles()
        out = capsys.readouterr().out
        assert "Name" in out
        assert "Software" in out

    def test_list_profiles_empty(self, capsys):
        with patch("device_use.profiles.loader.list_profiles", return_value=[]):
            cli._list_profiles()
        out = capsys.readouterr().out
        assert "No profiles found" in out


# ---------------------------------------------------------------------------
# _create_backend
# ---------------------------------------------------------------------------


class TestCreateBackend:
    def test_claude_backend(self):
        args = MagicMock(backend="claude", model=None)
        with patch("device_use.backends.claude.AsyncAnthropic"):
            backend = cli._create_backend(args)
        assert backend._model == "claude-sonnet-4-20250514"

    def test_claude_backend_custom_model(self):
        args = MagicMock(backend="claude", model="claude-opus-4-20250514")
        with patch("device_use.backends.claude.AsyncAnthropic"):
            backend = cli._create_backend(args)
        assert backend._model == "claude-opus-4-20250514"

    def test_openai_backend(self):
        args = MagicMock(backend="openai", model=None)
        with patch("device_use.backends.openai_compat.AsyncOpenAI"):
            backend = cli._create_backend(args)
        assert backend._model == "gpt-4o"

    def test_openai_backend_custom_model(self):
        args = MagicMock(backend="openai", model="gpt-5.4")
        with patch("device_use.backends.openai_compat.AsyncOpenAI"):
            backend = cli._create_backend(args)
        assert backend._model == "gpt-5.4"


# ---------------------------------------------------------------------------
# _run
# ---------------------------------------------------------------------------


class TestRun:
    @pytest.mark.asyncio
    async def test_run_success(self, capsys):
        mock_result = MagicMock(
            success=True, steps=2, action_count=1, duration_ms=500.0, error=None
        )

        args = MagicMock(
            profile="imagej-fiji", backend="claude", model=None, task="Open file", max_steps=10
        )
        with (
            patch("device_use.profiles.loader.load_profile") as mock_load,
            patch("device_use.cli._create_backend") as mock_backend,
            patch("device_use.core.agent.DeviceAgent") as mock_agent_cls,
        ):
            mock_profile = MagicMock()
            mock_profile.name = "test"
            mock_profile.hardware_connected = False
            mock_load.return_value = mock_profile
            mock_agent_cls.return_value.execute = AsyncMock(return_value=mock_result)
            await cli._run(args)

        out = capsys.readouterr().out
        assert "SUCCESS" in out

    @pytest.mark.asyncio
    async def test_run_failure(self, capsys):
        mock_result = MagicMock(
            success=False, steps=1, action_count=0, duration_ms=100.0, error="Connection failed"
        )

        args = MagicMock(
            profile="imagej-fiji", backend="claude", model=None, task="task", max_steps=5
        )
        with (
            patch("device_use.profiles.loader.load_profile") as mock_load,
            patch("device_use.cli._create_backend") as mock_backend,
            patch("device_use.core.agent.DeviceAgent") as mock_agent_cls,
        ):
            mock_profile = MagicMock()
            mock_profile.name = "test"
            mock_profile.hardware_connected = False
            mock_load.return_value = mock_profile
            mock_agent_cls.return_value.execute = AsyncMock(return_value=mock_result)
            await cli._run(args)

        out = capsys.readouterr().out
        assert "FAILED" in out
        assert "Connection failed" in out


# ---------------------------------------------------------------------------
# _interactive
# ---------------------------------------------------------------------------


class TestInteractive:
    @pytest.mark.asyncio
    async def test_interactive_quit(self, capsys):
        args = MagicMock(profile="imagej-fiji", backend="claude", model=None)
        with (
            patch("device_use.profiles.loader.load_profile") as mock_load,
            patch("device_use.cli._create_backend") as mock_backend,
            patch("builtins.input", side_effect=["quit"]),
        ):
            mock_load.return_value = MagicMock(name="test")
            await cli._interactive(args)

        out = capsys.readouterr().out
        assert "interactive mode" in out

    @pytest.mark.asyncio
    async def test_interactive_eof(self):
        args = MagicMock(profile="imagej-fiji", backend="claude", model=None)
        with (
            patch("device_use.profiles.loader.load_profile") as mock_load,
            patch("device_use.cli._create_backend") as mock_backend,
            patch("builtins.input", side_effect=EOFError),
        ):
            mock_load.return_value = MagicMock(name="test")
            await cli._interactive(args)

    @pytest.mark.asyncio
    async def test_interactive_task_then_quit(self, capsys):
        mock_result = MagicMock(success=True, steps=1, duration_ms=50.0, error=None)

        args = MagicMock(profile="imagej-fiji", backend="claude", model=None)
        with (
            patch("device_use.profiles.loader.load_profile") as mock_load,
            patch("device_use.cli._create_backend") as mock_backend,
            patch("device_use.core.agent.DeviceAgent") as mock_agent_cls,
            patch("builtins.input", side_effect=["do something", "exit"]),
        ):
            mock_load.return_value = MagicMock(name="test")
            mock_agent_cls.return_value.execute = AsyncMock(return_value=mock_result)
            await cli._interactive(args)

        out = capsys.readouterr().out
        assert "OK" in out

    @pytest.mark.asyncio
    async def test_interactive_task_with_error(self, capsys):
        mock_result = MagicMock(success=False, steps=1, duration_ms=50.0, error="Some error")

        args = MagicMock(profile="imagej-fiji", backend="claude", model=None)
        with (
            patch("device_use.profiles.loader.load_profile") as mock_load,
            patch("device_use.cli._create_backend") as mock_backend,
            patch("device_use.core.agent.DeviceAgent") as mock_agent_cls,
            patch("builtins.input", side_effect=["do something", "q"]),
        ):
            mock_load.return_value = MagicMock(name="test")
            mock_agent_cls.return_value.execute = AsyncMock(return_value=mock_result)
            await cli._interactive(args)

        out = capsys.readouterr().out
        assert "FAIL" in out
        assert "Some error" in out

    @pytest.mark.asyncio
    async def test_interactive_empty_input(self):
        args = MagicMock(profile="imagej-fiji", backend="claude", model=None)
        with (
            patch("device_use.profiles.loader.load_profile") as mock_load,
            patch("device_use.cli._create_backend") as mock_backend,
            patch("builtins.input", side_effect=["", "quit"]),
        ):
            mock_load.return_value = MagicMock(name="test")
            await cli._interactive(args)


# ---------------------------------------------------------------------------
# _instruments
# ---------------------------------------------------------------------------


class TestInstruments:
    def test_instruments_output(self, capsys):
        cli._instruments()
        out = capsys.readouterr().out
        assert "Instruments" in out
        assert "Tools" in out


# ---------------------------------------------------------------------------
# _status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_status_output(self, capsys):
        cli._status()
        out = capsys.readouterr().out
        assert "Architecture Status" in out
        assert "Cloud Brain" in out
        assert "Instruments" in out
        assert "External Tools" in out


# ---------------------------------------------------------------------------
# _demo
# ---------------------------------------------------------------------------


class TestDemo:
    def test_demo_runs_subprocess(self):
        with patch("subprocess.run") as mock_run:
            cli._demo("nmr")
        mock_run.assert_called_once()
        assert "demos/" in mock_run.call_args.args[0][1]


# ---------------------------------------------------------------------------
# _scaffold
# ---------------------------------------------------------------------------


class TestScaffold:
    def test_scaffold_creates_directory(self, tmp_path, capsys):
        cli._scaffold("zeiss-zen", str(tmp_path))
        out = capsys.readouterr().out
        assert "device_use_zeiss_zen" in out
        assert (tmp_path / "device_use_zeiss_zen" / "pyproject.toml").exists()
        assert (
            tmp_path / "device_use_zeiss_zen" / "src" / "device_use_zeiss_zen" / "__init__.py"
        ).exists()

    def test_scaffold_existing_dir(self, tmp_path, capsys):
        (tmp_path / "device_use_zeiss_zen").mkdir()
        cli._scaffold("zeiss-zen", str(tmp_path))
        out = capsys.readouterr().out
        assert "already exists" in out


# ---------------------------------------------------------------------------
# _write
# ---------------------------------------------------------------------------


class TestWrite:
    def test_write_creates_file(self, tmp_path):
        path = str(tmp_path / "sub" / "file.txt")
        cli._write(path, "hello")
        assert Path(path).read_text() == "hello"


# ---------------------------------------------------------------------------
# _hero
# ---------------------------------------------------------------------------


class TestHero:
    def test_hero_output(self, capsys):
        cli._hero()
        out = capsys.readouterr().out
        # Check the hero banner elements
        assert "Middleware ready" in out


# ---------------------------------------------------------------------------
# main() dispatch
# ---------------------------------------------------------------------------


class TestMain:
    def test_no_command(self, capsys):
        with patch("sys.argv", ["device-use"]):
            cli.main()
        out = capsys.readouterr().out
        assert "Middleware ready" in out

    def test_list_profiles_command(self, capsys):
        with patch("sys.argv", ["device-use", "list-profiles"]):
            cli.main()
        out = capsys.readouterr().out
        assert "Name" in out

    def test_instruments_command(self, capsys):
        with patch("sys.argv", ["device-use", "instruments"]):
            cli.main()
        out = capsys.readouterr().out
        assert "Instruments" in out

    def test_status_command(self, capsys):
        with patch("sys.argv", ["device-use", "status"]):
            cli.main()
        out = capsys.readouterr().out
        assert "Architecture Status" in out

    def test_scaffold_command(self, tmp_path, capsys):
        with patch("sys.argv", ["device-use", "scaffold", "test-dev", "-o", str(tmp_path)]):
            cli.main()
        out = capsys.readouterr().out
        assert "device_use_test_dev" in out

    def test_demo_command(self):
        with (
            patch("sys.argv", ["device-use", "demo", "nmr"]),
            patch("subprocess.run") as mock_run,
        ):
            cli.main()
        mock_run.assert_called_once()

    def test_run_command(self):
        mock_result = MagicMock(success=True, steps=1, action_count=0, duration_ms=10.0, error=None)

        with (
            patch("sys.argv", ["device-use", "run", "task", "--profile", "imagej-fiji"]),
            patch("device_use.core.agent.DeviceAgent") as mock_agent_cls,
            patch("device_use.backends.claude.AsyncAnthropic"),
        ):
            mock_agent_cls.return_value.execute = AsyncMock(return_value=mock_result)
            cli.main()

    def test_interactive_command(self):
        with (
            patch("sys.argv", ["device-use", "interactive", "--profile", "imagej-fiji"]),
            patch("device_use.backends.claude.AsyncAnthropic"),
            patch("builtins.input", side_effect=["quit"]),
        ):
            cli.main()
