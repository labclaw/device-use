"""Screenshot capture and VLM understanding layer."""

from __future__ import annotations

import io
from typing import Any

import mss
from PIL import Image

from device_use.backends.base import VisionBackend
from device_use.core.window_manager import WindowManager


class ScreenObserver:
    """Capture screenshots and send to VLM for understanding.

    Captures only the instrument window (not full screen) to reduce noise
    and tokens. Scales screenshots to max 1280px width for VLM input
    (Anthropic pattern).
    """

    def __init__(
        self,
        window_manager: WindowManager,
        backend: VisionBackend | None = None,
    ) -> None:
        self._wm = window_manager
        self._backend = backend

    def capture_window(self, window_id: str) -> bytes:
        """Capture screenshot of specific window region. Returns PNG bytes.

        Uses mss for screen capture, crops to window region.
        """
        x, y, w, h = self._wm.get_window_rect(window_id)
        monitor = {"left": x, "top": y, "width": w, "height": h}
        with mss.mss() as sct:
            shot = sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def capture_and_scale(self, window_id: str, max_width: int = 1280) -> bytes:
        """Capture and scale screenshot for VLM input."""
        raw = self.capture_window(window_id)
        return self.scale_image(raw, max_width)

    async def observe(self, window_id: str, context: str = "") -> dict[str, Any]:
        """Capture screenshot and get VLM understanding.

        Returns dict with screenshot bytes and VLM description.
        """
        screenshot = self.capture_and_scale(window_id)
        result: dict[str, Any] = {"screenshot": screenshot}

        if self._backend is not None:
            vlm_result = await self._backend.observe(screenshot, context)
            result["description"] = vlm_result.get("description", "")
            result["elements"] = vlm_result.get("elements", [])
        else:
            result["description"] = ""
            result["elements"] = []

        return result

    def capture_full_screen(self, max_width: int = 1280) -> bytes:
        """Capture the primary monitor (full screen) and scale for VLM input."""
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Primary monitor
            shot = sct.grab(monitor)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return self.scale_image(buf.getvalue(), max_width)

    @staticmethod
    def scale_image(image_bytes: bytes, max_width: int = 1280) -> bytes:
        """Scale PNG image bytes to exactly max_width, preserving aspect ratio.

        Always resizes to ensure VLM coordinate space matches the scaler's
        assumption (vlm_width == max_width).
        """
        img = Image.open(io.BytesIO(image_bytes))
        if img.width == max_width:
            return image_bytes
        ratio = max_width / img.width
        new_height = int(img.height * ratio)
        img = img.resize((max_width, new_height), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
