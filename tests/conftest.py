"""Shared test configuration — ensures src/ is on sys.path."""

from __future__ import annotations

import struct
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


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
