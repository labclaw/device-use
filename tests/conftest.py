"""Shared test configuration — ensures src/ is on sys.path."""

from __future__ import annotations

import os
import struct
import sys
import zlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

_EXAMDATA_DIR = Path("/opt/topspin5.0.0/examdata")
requires_examdata = pytest.mark.skipif(
    not _EXAMDATA_DIR.exists(),
    reason="TopSpin examdata not installed (need /opt/topspin5.0.0/examdata)",
)


@pytest.fixture(autouse=True)
def _mock_gui_deps_if_headless():
    """Provide mock pyautogui/pyperclip when no display server is available.

    This allows tests that import device_use.actions.executor to run in
    headless CI environments without a real X11/Wayland display.
    """
    import device_use.actions.executor as _exec

    if os.environ.get("DISPLAY"):
        yield
        return

    orig_pyautogui = _exec._pyautogui
    orig_pyperclip = _exec._pyperclip
    orig_failsafe = _exec._FailSafeException

    if orig_pyautogui is None:
        _exec._pyautogui = MagicMock()
        _exec._pyperclip = MagicMock()

        class _FakeFailSafeError(Exception):
            pass

        _exec._FailSafeException = _FakeFailSafeError

    yield

    _exec._pyautogui = orig_pyautogui
    _exec._pyperclip = orig_pyperclip
    _exec._FailSafeException = orig_failsafe


def _create_minimal_png() -> bytes:
    """Create a 1x1 red pixel PNG for mock screenshots."""
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
    raw = b"\x00\xff\x00\x00"
    compressed = zlib.compress(raw)
    idat_crc = zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF
    idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + struct.pack(">I", idat_crc)
    iend_crc = zlib.crc32(b"IEND") & 0xFFFFFFFF
    iend = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
    return sig + ihdr + idat + iend


@pytest.fixture
def minimal_png() -> bytes:
    """A minimal valid 1x1 PNG image for testing."""
    return _create_minimal_png()


@pytest.fixture
def mock_capture():
    """Async callable returning a minimal PNG, for agent._capture_screenshot."""

    async def _capture() -> bytes:
        return _create_minimal_png()

    return _capture
