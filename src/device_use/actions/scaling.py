"""Bidirectional coordinate scaling between VLM space and screen space.

VLMs operate at a fixed resolution (e.g., 1280x800). Actual screens vary.
Additionally, captures are window-relative while pyautogui needs absolute coords.

Scaling pipeline:
  VLM coords → screen-relative (within window) → absolute screen coords
  absolute screen coords → screen-relative → VLM coords
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CoordinateScaler:
    """Bidirectional scaler: VLM ↔ screen coordinates.

    Args:
        vlm_width: Width of image sent to VLM.
        vlm_height: Height of image sent to VLM.
        screen_width: Actual width of captured window region.
        screen_height: Actual height of captured window region.
        window_x: Window top-left X on screen (for absolute offset).
        window_y: Window top-left Y on screen (for absolute offset).
    """

    vlm_width: int
    vlm_height: int
    screen_width: int
    screen_height: int
    window_x: int = 0
    window_y: int = 0

    def __post_init__(self) -> None:
        if self.vlm_width <= 0 or self.vlm_height <= 0:
            raise ValueError(f"VLM dimensions must be > 0, got {self.vlm_width}x{self.vlm_height}")
        if self.screen_width <= 0 or self.screen_height <= 0:
            raise ValueError(
                f"Screen dimensions must be > 0, got {self.screen_width}x{self.screen_height}"
            )

    @property
    def scale_x(self) -> float:
        return self.screen_width / self.vlm_width if self.vlm_width else 1.0

    @property
    def scale_y(self) -> float:
        return self.screen_height / self.vlm_height if self.vlm_height else 1.0

    def vlm_to_screen(self, x: int, y: int) -> tuple[int, int]:
        """Convert VLM coordinates to absolute screen coordinates."""
        screen_x = round(x * self.scale_x) + self.window_x
        screen_y = round(y * self.scale_y) + self.window_y
        return screen_x, screen_y

    def screen_to_vlm(self, x: int, y: int) -> tuple[int, int]:
        """Convert absolute screen coordinates to VLM coordinates."""
        rel_x = x - self.window_x
        rel_y = y - self.window_y
        vlm_x = round(rel_x / self.scale_x) if self.scale_x else 0
        vlm_y = round(rel_y / self.scale_y) if self.scale_y else 0
        return vlm_x, vlm_y

    def clamp_screen(self, x: int, y: int) -> tuple[int, int]:
        """Clamp absolute screen coordinates to window bounds."""
        clamped_x = max(self.window_x, min(x, self.window_x + self.screen_width - 1))
        clamped_y = max(self.window_y, min(y, self.window_y + self.screen_height - 1))
        return clamped_x, clamped_y
