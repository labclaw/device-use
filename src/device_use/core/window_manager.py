"""Cross-platform window management (Linux-first)."""

from __future__ import annotations

import platform
import re
import subprocess
from dataclasses import dataclass


@dataclass
class WindowInfo:
    """Information about an application window."""

    window_id: str
    title: str
    x: int
    y: int
    width: int
    height: int
    is_active: bool


class WindowManager:
    """Find, focus, and query instrument application windows.

    Linux: uses wmctrl and xdotool.
    Windows/macOS: stubs that raise NotImplementedError for now.
    """

    def __init__(self) -> None:
        self._platform = platform.system().lower()
        if self._platform == "linux":
            self._check_linux_deps()

    # -- public API --

    def find_window(self, title_pattern: str) -> WindowInfo | None:
        """Find window matching title regex pattern."""
        if self._platform != "linux":
            raise NotImplementedError(
                f"Window management not yet supported on {self._platform}"
            )
        pattern = re.compile(title_pattern, re.IGNORECASE)
        active_int = self._get_active_window_int()
        for win in self._list_windows_raw():
            if pattern.search(win["title"]):
                return WindowInfo(
                    window_id=win["id"],
                    title=win["title"],
                    x=win["x"],
                    y=win["y"],
                    width=win["w"],
                    height=win["h"],
                    is_active=(self._normalize_id(win["id"]) == active_int),
                )
        return None

    def focus_window(self, window_id: str) -> bool:
        """Bring window to foreground."""
        if self._platform != "linux":
            raise NotImplementedError(
                f"Window management not yet supported on {self._platform}"
            )
        try:
            subprocess.run(
                ["wmctrl", "-i", "-a", window_id],
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def get_window_rect(self, window_id: str) -> tuple[int, int, int, int]:
        """Get window position and size (x, y, width, height)."""
        if self._platform != "linux":
            raise NotImplementedError(
                f"Window management not yet supported on {self._platform}"
            )
        target_int = self._normalize_id(window_id)
        for win in self._list_windows_raw():
            if self._normalize_id(win["id"]) == target_int:
                return (win["x"], win["y"], win["w"], win["h"])
        raise ValueError(f"Window {window_id} not found")

    def is_window_active(self, window_id: str) -> bool:
        """Check if window is currently in foreground."""
        if self._platform != "linux":
            raise NotImplementedError(
                f"Window management not yet supported on {self._platform}"
            )
        active_int = self._get_active_window_int()
        return self._normalize_id(window_id) == active_int

    def list_windows(self) -> list[WindowInfo]:
        """List all visible windows."""
        if self._platform != "linux":
            raise NotImplementedError(
                f"Window management not yet supported on {self._platform}"
            )
        active_int = self._get_active_window_int()
        results: list[WindowInfo] = []
        for win in self._list_windows_raw():
            results.append(
                WindowInfo(
                    window_id=win["id"],
                    title=win["title"],
                    x=win["x"],
                    y=win["y"],
                    width=win["w"],
                    height=win["h"],
                    is_active=(self._normalize_id(win["id"]) == active_int),
                )
            )
        return results

    # -- Linux internals --

    @staticmethod
    def _normalize_id(window_id: str | int) -> int:
        """Convert any hex or decimal window id (str or int) to an int for comparison."""
        if isinstance(window_id, int):
            return window_id
        return int(window_id, 16) if window_id.startswith("0x") else int(window_id)

    def _check_linux_deps(self) -> None:
        """Verify wmctrl and xdotool are installed."""
        for cmd in ("wmctrl", "xdotool"):
            try:
                subprocess.run(
                    ["which", cmd],
                    check=True,
                    capture_output=True,
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                raise RuntimeError(
                    f"'{cmd}' is required but not installed. "
                    f"Install with: sudo apt install {cmd}"
                )

    def _get_active_window_int(self) -> int:
        """Get the currently active window id as int."""
        try:
            result = subprocess.run(
                ["xdotool", "getactivewindow"],
                check=True,
                capture_output=True,
                text=True,
            )
            return int(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError):
            return -1

    def _list_windows_raw(self) -> list[dict]:
        """Parse wmctrl -l -G output into dicts.

        Output format per line:
            id  desktop  x  y  w  h  hostname  title...
        Example:
            0x04000007  0 0    51  1920 1029 myhost Terminal
        """
        result = subprocess.run(
            ["wmctrl", "-l", "-G"],
            check=True,
            capture_output=True,
            text=True,
        )
        windows: list[dict] = []
        for line in result.stdout.strip().splitlines():
            parts = line.split(None, 7)
            if len(parts) < 8:
                continue
            wid, _desktop, x, y, w, h, _host = parts[:7]
            title = parts[7]
            windows.append({
                "id": wid,
                "x": int(x),
                "y": int(y),
                "w": int(w),
                "h": int(h),
                "title": title,
            })
        return windows
