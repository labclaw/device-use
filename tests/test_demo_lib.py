"""Tests for shared demo library."""
import sys
from pathlib import Path

# Make demos/lib importable
sys.path.insert(0, str(Path(__file__).parent.parent / "demos"))

from lib.terminal import (
    BOLD, DIM, GREEN, CYAN, YELLOW, RED, MAGENTA, RESET,
    CHECK, ARROW, WARN,
    banner, step, ok, warn, err, info, progress, done, section, finale,
)


class TestTerminalConstants:
    def test_color_constants_are_ansi(self):
        assert BOLD.startswith("\033[")
        assert RESET == "\033[0m"

    def test_check_uses_green(self):
        assert GREEN in CHECK

    def test_arrow_uses_cyan(self):
        assert CYAN in ARROW

    def test_warn_uses_yellow(self):
        assert YELLOW in WARN


class TestTerminalHelpers:
    def test_banner_prints_title(self, capsys):
        banner("Test Title", "subtitle")
        out = capsys.readouterr().out
        assert "Test Title" in out
        assert "subtitle" in out

    def test_step_prints_number(self, capsys):
        step(3, "Do something")
        out = capsys.readouterr().out
        assert "Step 3" in out
        assert "Do something" in out

    def test_ok_prints_check(self, capsys):
        ok("success message")
        out = capsys.readouterr().out
        assert "success message" in out

    def test_warn_prints_warning(self, capsys):
        warn("warning message")
        out = capsys.readouterr().out
        assert "warning message" in out

    def test_err_prints_error(self, capsys):
        err("error message")
        out = capsys.readouterr().out
        assert "error message" in out

    def test_info_prints_dim(self, capsys):
        info("info message")
        out = capsys.readouterr().out
        assert "info message" in out

    def test_section_prints_bold(self, capsys):
        section("Section Title")
        out = capsys.readouterr().out
        assert "Section Title" in out

    def test_finale_prints_summary(self, capsys):
        finale(["Result 1", "Result 2"])
        out = capsys.readouterr().out
        assert "Result 1" in out
        assert "Complete" in out

    def test_phase_prints_number_and_title(self, capsys):
        from lib.terminal import phase
        phase(2, "Processing", "sub info")
        out = capsys.readouterr().out
        assert "Phase 2" in out
        assert "Processing" in out
        assert "sub info" in out


class TestDemoRunner:
    def test_runner_creates_argparser(self):
        from lib.runner import DemoRunner
        runner = DemoRunner("Test Demo")
        args = runner.parser.parse_args(["--mode", "offline", "--no-brain"])
        assert args.mode == "offline"
        assert args.no_brain is True

    def test_runner_default_mode_is_auto(self):
        from lib.runner import DemoRunner
        runner = DemoRunner("Test Demo")
        args = runner.parser.parse_args([])
        assert args.mode == "auto"

    def test_runner_connect_offline(self, tmp_path):
        from lib.runner import DemoRunner
        examdata = tmp_path / "examdata"
        examdata.mkdir()
        runner = DemoRunner("Test")
        args = runner.parser.parse_args(["--mode", "offline", "--topspin-dir", str(tmp_path)])
        adapter, mode = runner.connect(args)
        assert mode.value == "offline"
        assert adapter.connected

    def test_print_peak_table_empty(self, capsys):
        from lib.runner import print_peak_table
        from device_use.instruments.nmr.processor import NMRSpectrum
        spectrum = NMRSpectrum(
            data=[0.0], ppm_scale=[0.0], peaks=[],
            frequency_mhz=400.0, nucleus="1H", solvent="CDCl3",
        )
        print_peak_table(spectrum)
        out = capsys.readouterr().out
        assert "Peak List" in out


class TestDemoRecorder:
    def test_recorder_init(self, tmp_path):
        from lib.recorder import DemoRecorder
        recorder = DemoRecorder(output_dir=tmp_path)
        assert recorder.frame_count == 0
        assert recorder.frames == []

    def test_recorder_save_gif_no_frames(self, tmp_path):
        from lib.recorder import DemoRecorder
        recorder = DemoRecorder(output_dir=tmp_path)
        result = recorder.save_gif(tmp_path / "test.gif")
        assert result is None
