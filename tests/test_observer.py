"""Tests for window management and screen observation."""

from __future__ import annotations

import io
import subprocess
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from device_use.core.observer import ScreenObserver
from device_use.core.window_manager import WindowInfo, WindowManager


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _force_linux_platform(monkeypatch):
    """WindowManager is Linux-only; mock platform so tests run on macOS/Windows."""
    monkeypatch.setattr("device_use.core.window_manager.platform.system", lambda: "Linux")

WMCTRL_OUTPUT = """\
0x04000007  0 0    51  1920 1029 myhost Terminal
0x04800003  0 100  200 800  600  myhost FIJI - ImageJ 2.14.0
0x05000001  0 50   100 1024 768  myhost Gen5 3.x - BioTek
"""

WMCTRL_OUTPUT_MINIMAL = """\
0x04000007  0 0    51  1920 1029 myhost Terminal
"""

WMCTRL_OUTPUT_SHORT_LINE = """\
0x04000007  0 0    51  1920
"""


def _make_png(width: int = 200, height: int = 100) -> bytes:
    """Create a small test PNG image."""
    img = Image.new("RGB", (width, height), color=(128, 64, 32))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _mock_subprocess_run(wmctrl_output: str, active_dec_id: int = 0x04000007):
    """Return a side_effect function for subprocess.run mock."""

    def side_effect(cmd, **kwargs):
        if cmd == ["which", "wmctrl"] or cmd == ["which", "xdotool"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")
        if cmd == ["wmctrl", "-l", "-G"]:
            return subprocess.CompletedProcess(
                cmd, 0, stdout=wmctrl_output, stderr=""
            )
        if cmd == ["xdotool", "getactivewindow"]:
            return subprocess.CompletedProcess(
                cmd, 0, stdout=f"{active_dec_id}\n", stderr=""
            )
        if len(cmd) >= 3 and cmd[0] == "wmctrl" and cmd[1] == "-i":
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    return side_effect


# ---------------------------------------------------------------------------
# WindowManager tests
# ---------------------------------------------------------------------------


class TestWindowManagerListWindows:
    @patch("device_use.core.window_manager.subprocess.run")
    def test_list_windows(self, mock_run):
        mock_run.side_effect = _mock_subprocess_run(WMCTRL_OUTPUT)
        wm = WindowManager()
        windows = wm.list_windows()
        assert len(windows) == 3
        titles = [w.title for w in windows]
        assert "Terminal" in titles
        assert "FIJI - ImageJ 2.14.0" in titles
        assert "Gen5 3.x - BioTek" in titles

    @patch("device_use.core.window_manager.subprocess.run")
    def test_list_windows_geometry(self, mock_run):
        mock_run.side_effect = _mock_subprocess_run(WMCTRL_OUTPUT)
        wm = WindowManager()
        windows = wm.list_windows()
        fiji = [w for w in windows if "FIJI" in w.title][0]
        assert fiji.x == 100
        assert fiji.y == 200
        assert fiji.width == 800
        assert fiji.height == 600

    @patch("device_use.core.window_manager.subprocess.run")
    def test_list_windows_active_flag(self, mock_run):
        mock_run.side_effect = _mock_subprocess_run(
            WMCTRL_OUTPUT, active_dec_id=0x04800003
        )
        wm = WindowManager()
        windows = wm.list_windows()
        active = [w for w in windows if w.is_active]
        assert len(active) == 1
        assert "FIJI" in active[0].title

    @patch("device_use.core.window_manager.subprocess.run")
    def test_list_windows_skips_short_lines(self, mock_run):
        mock_run.side_effect = _mock_subprocess_run(WMCTRL_OUTPUT_SHORT_LINE)
        wm = WindowManager()
        windows = wm.list_windows()
        assert len(windows) == 0


class TestWindowManagerFindWindow:
    @patch("device_use.core.window_manager.subprocess.run")
    def test_find_by_exact_title(self, mock_run):
        mock_run.side_effect = _mock_subprocess_run(WMCTRL_OUTPUT)
        wm = WindowManager()
        win = wm.find_window("FIJI")
        assert win is not None
        assert win.title == "FIJI - ImageJ 2.14.0"
        assert win.window_id == "0x04800003"

    @patch("device_use.core.window_manager.subprocess.run")
    def test_find_by_regex(self, mock_run):
        mock_run.side_effect = _mock_subprocess_run(WMCTRL_OUTPUT)
        wm = WindowManager()
        win = wm.find_window(r"Gen5\s+\d")
        assert win is not None
        assert "Gen5" in win.title

    @patch("device_use.core.window_manager.subprocess.run")
    def test_find_case_insensitive(self, mock_run):
        mock_run.side_effect = _mock_subprocess_run(WMCTRL_OUTPUT)
        wm = WindowManager()
        win = wm.find_window("fiji")
        assert win is not None

    @patch("device_use.core.window_manager.subprocess.run")
    def test_find_no_match(self, mock_run):
        mock_run.side_effect = _mock_subprocess_run(WMCTRL_OUTPUT)
        wm = WindowManager()
        win = wm.find_window("NonexistentApp")
        assert win is None


class TestWindowManagerFocus:
    @patch("device_use.core.window_manager.subprocess.run")
    def test_focus_window_success(self, mock_run):
        mock_run.side_effect = _mock_subprocess_run(WMCTRL_OUTPUT)
        wm = WindowManager()
        assert wm.focus_window("0x04800003") is True

    @patch("device_use.core.window_manager.subprocess.run")
    def test_focus_window_calls_wmctrl(self, mock_run):
        mock_run.side_effect = _mock_subprocess_run(WMCTRL_OUTPUT)
        wm = WindowManager()
        wm.focus_window("0x04800003")
        # Check that wmctrl -i -a was called
        focus_calls = [
            c
            for c in mock_run.call_args_list
            if len(c[0][0]) >= 3
            and c[0][0][0] == "wmctrl"
            and c[0][0][1] == "-i"
            and c[0][0][2] == "-a"
        ]
        assert len(focus_calls) == 1
        assert focus_calls[0][0][0][3] == "0x04800003"

    @patch("device_use.core.window_manager.subprocess.run")
    def test_focus_window_failure(self, mock_run):
        def side_effect(cmd, **kwargs):
            if cmd == ["which", "wmctrl"] or cmd == ["which", "xdotool"]:
                return subprocess.CompletedProcess(cmd, 0)
            if cmd[0] == "wmctrl" and "-a" in cmd:
                raise subprocess.CalledProcessError(1, cmd)
            return _mock_subprocess_run(WMCTRL_OUTPUT)(cmd, **kwargs)

        mock_run.side_effect = side_effect
        wm = WindowManager()
        assert wm.focus_window("0xBAD") is False


class TestWindowManagerGetRect:
    @patch("device_use.core.window_manager.subprocess.run")
    def test_get_rect(self, mock_run):
        mock_run.side_effect = _mock_subprocess_run(WMCTRL_OUTPUT)
        wm = WindowManager()
        rect = wm.get_window_rect("0x04800003")
        assert rect == (100, 200, 800, 600)

    @patch("device_use.core.window_manager.subprocess.run")
    def test_get_rect_not_found(self, mock_run):
        mock_run.side_effect = _mock_subprocess_run(WMCTRL_OUTPUT)
        wm = WindowManager()
        with pytest.raises(ValueError, match="not found"):
            wm.get_window_rect("0xDEADBEEF")


class TestWindowManagerIsActive:
    @patch("device_use.core.window_manager.subprocess.run")
    def test_is_active_true(self, mock_run):
        mock_run.side_effect = _mock_subprocess_run(
            WMCTRL_OUTPUT, active_dec_id=0x04800003
        )
        wm = WindowManager()
        assert wm.is_window_active("0x4800003") is True

    @patch("device_use.core.window_manager.subprocess.run")
    def test_is_active_false(self, mock_run):
        mock_run.side_effect = _mock_subprocess_run(
            WMCTRL_OUTPUT, active_dec_id=0x04000007
        )
        wm = WindowManager()
        assert wm.is_window_active("0x04800003") is False


class TestWindowManagerDeps:
    @patch("device_use.core.window_manager.subprocess.run")
    def test_missing_wmctrl_raises(self, mock_run):
        def side_effect(cmd, **kwargs):
            if cmd == ["which", "wmctrl"]:
                raise subprocess.CalledProcessError(1, cmd)
            return subprocess.CompletedProcess(cmd, 0)

        mock_run.side_effect = side_effect
        with pytest.raises(RuntimeError, match="wmctrl"):
            WindowManager()

    @patch("device_use.core.window_manager.subprocess.run")
    def test_missing_xdotool_raises(self, mock_run):
        def side_effect(cmd, **kwargs):
            if cmd == ["which", "xdotool"]:
                raise subprocess.CalledProcessError(1, cmd)
            return subprocess.CompletedProcess(cmd, 0)

        mock_run.side_effect = side_effect
        with pytest.raises(RuntimeError, match="xdotool"):
            WindowManager()

    @patch("device_use.core.window_manager.platform.system", return_value="Darwin")
    def test_non_linux_raises(self, mock_platform):
        wm = WindowManager()
        with pytest.raises(NotImplementedError):
            wm.list_windows()
        with pytest.raises(NotImplementedError):
            wm.find_window("test")
        with pytest.raises(NotImplementedError):
            wm.focus_window("0x1")
        with pytest.raises(NotImplementedError):
            wm.get_window_rect("0x1")
        with pytest.raises(NotImplementedError):
            wm.is_window_active("0x1")


# ---------------------------------------------------------------------------
# ScreenObserver tests
# ---------------------------------------------------------------------------


class TestScaleImage:
    def test_scale_down_large_image(self):
        png = _make_png(2560, 1440)
        scaled = ScreenObserver.scale_image(png, max_width=1280)
        img = Image.open(io.BytesIO(scaled))
        assert img.width == 1280
        assert img.height == 720

    def test_upscale_small_image(self):
        png = _make_png(640, 480)
        scaled = ScreenObserver.scale_image(png, max_width=1280)
        # Small images are scaled up to max_width for consistent VLM coord space
        img = Image.open(io.BytesIO(scaled))
        assert img.width == 1280
        assert img.height == 960

    def test_exact_max_width(self):
        png = _make_png(1280, 720)
        scaled = ScreenObserver.scale_image(png, max_width=1280)
        assert scaled == png

    def test_custom_max_width(self):
        png = _make_png(1000, 500)
        scaled = ScreenObserver.scale_image(png, max_width=800)
        img = Image.open(io.BytesIO(scaled))
        assert img.width == 800
        assert img.height == 400


class TestCaptureWindow:
    @patch("device_use.core.window_manager.subprocess.run")
    @patch("device_use.core.observer.mss.mss")
    def test_capture_window(self, mock_mss_cls, mock_run):
        mock_run.side_effect = _mock_subprocess_run(WMCTRL_OUTPUT)
        wm = WindowManager()

        # Mock mss capture
        fake_img = Image.new("RGBA", (800, 600), (128, 64, 32, 255))
        buf = io.BytesIO()
        fake_img.save(buf, format="PNG")
        mock_shot = MagicMock()
        mock_shot.size = (800, 600)
        # mss returns BGRA raw bytes
        mock_shot.bgra = fake_img.tobytes("raw", "BGRA")
        mock_sct = MagicMock()
        mock_sct.grab.return_value = mock_shot
        mock_sct.__enter__ = MagicMock(return_value=mock_sct)
        mock_sct.__exit__ = MagicMock(return_value=False)
        mock_mss_cls.return_value = mock_sct

        observer = ScreenObserver(wm)
        result = observer.capture_window("0x04800003")

        # Verify it's valid PNG
        img = Image.open(io.BytesIO(result))
        assert img.size == (800, 600)

        # Verify mss was called with correct monitor region
        mock_sct.grab.assert_called_once_with(
            {"left": 100, "top": 200, "width": 800, "height": 600}
        )

    @patch("device_use.core.window_manager.subprocess.run")
    @patch("device_use.core.observer.mss.mss")
    def test_capture_and_scale(self, mock_mss_cls, mock_run):
        mock_run.side_effect = _mock_subprocess_run(WMCTRL_OUTPUT)
        wm = WindowManager()

        # Create 1920x1080 "screenshot"
        fake_img = Image.new("RGBA", (1920, 1080), (64, 128, 32, 255))
        mock_shot = MagicMock()
        mock_shot.size = (1920, 1080)
        mock_shot.bgra = fake_img.tobytes("raw", "BGRA")
        mock_sct = MagicMock()
        mock_sct.grab.return_value = mock_shot
        mock_sct.__enter__ = MagicMock(return_value=mock_sct)
        mock_sct.__exit__ = MagicMock(return_value=False)
        mock_mss_cls.return_value = mock_sct

        # Override get_window_rect to return 1920x1080 window
        wm.get_window_rect = MagicMock(return_value=(0, 0, 1920, 1080))

        observer = ScreenObserver(wm)
        result = observer.capture_and_scale("0x04000007", max_width=1280)

        img = Image.open(io.BytesIO(result))
        assert img.width == 1280
        assert img.height == 720


class TestObserve:
    @patch("device_use.core.window_manager.subprocess.run")
    @patch("device_use.core.observer.mss.mss")
    async def test_observe_without_backend(self, mock_mss_cls, mock_run):
        mock_run.side_effect = _mock_subprocess_run(WMCTRL_OUTPUT)
        wm = WindowManager()

        fake_img = Image.new("RGBA", (800, 600), (128, 64, 32, 255))
        mock_shot = MagicMock()
        mock_shot.size = (800, 600)
        mock_shot.bgra = fake_img.tobytes("raw", "BGRA")
        mock_sct = MagicMock()
        mock_sct.grab.return_value = mock_shot
        mock_sct.__enter__ = MagicMock(return_value=mock_sct)
        mock_sct.__exit__ = MagicMock(return_value=False)
        mock_mss_cls.return_value = mock_sct

        observer = ScreenObserver(wm)
        result = await observer.observe("0x04800003")

        assert "screenshot" in result
        assert result["description"] == ""
        assert result["elements"] == []
        # Verify screenshot is valid PNG
        img = Image.open(io.BytesIO(result["screenshot"]))
        assert img.width <= 1280

    @patch("device_use.core.window_manager.subprocess.run")
    @patch("device_use.core.observer.mss.mss")
    async def test_observe_with_backend(self, mock_mss_cls, mock_run):
        mock_run.side_effect = _mock_subprocess_run(WMCTRL_OUTPUT)
        wm = WindowManager()

        fake_img = Image.new("RGBA", (800, 600), (128, 64, 32, 255))
        mock_shot = MagicMock()
        mock_shot.size = (800, 600)
        mock_shot.bgra = fake_img.tobytes("raw", "BGRA")
        mock_sct = MagicMock()
        mock_sct.grab.return_value = mock_shot
        mock_sct.__enter__ = MagicMock(return_value=mock_sct)
        mock_sct.__exit__ = MagicMock(return_value=False)
        mock_mss_cls.return_value = mock_sct

        # Mock VisionBackend
        mock_backend = AsyncMock()
        mock_backend.observe.return_value = {
            "description": "FIJI main window with toolbar visible",
            "elements": [
                {"name": "File menu", "type": "menu", "coords": (30, 10)},
            ],
        }

        observer = ScreenObserver(wm, backend=mock_backend)
        result = await observer.observe("0x04800003", context="analyzing image")

        assert result["description"] == "FIJI main window with toolbar visible"
        assert len(result["elements"]) == 1
        assert result["elements"][0]["name"] == "File menu"
        mock_backend.observe.assert_called_once()

    @patch("device_use.core.window_manager.subprocess.run")
    @patch("device_use.core.observer.mss.mss")
    async def test_observe_with_context(self, mock_mss_cls, mock_run):
        mock_run.side_effect = _mock_subprocess_run(WMCTRL_OUTPUT)
        wm = WindowManager()

        fake_img = Image.new("RGBA", (800, 600), (128, 64, 32, 255))
        mock_shot = MagicMock()
        mock_shot.size = (800, 600)
        mock_shot.bgra = fake_img.tobytes("raw", "BGRA")
        mock_sct = MagicMock()
        mock_sct.grab.return_value = mock_shot
        mock_sct.__enter__ = MagicMock(return_value=mock_sct)
        mock_sct.__exit__ = MagicMock(return_value=False)
        mock_mss_cls.return_value = mock_sct

        mock_backend = AsyncMock()
        mock_backend.observe.return_value = {
            "description": "dialog box",
            "elements": [],
        }

        observer = ScreenObserver(wm, backend=mock_backend)
        await observer.observe("0x04800003", context="waiting for dialog")

        # Verify context was passed to backend
        call_args = mock_backend.observe.call_args
        assert call_args[1].get("context", call_args[0][1]) == "waiting for dialog"
