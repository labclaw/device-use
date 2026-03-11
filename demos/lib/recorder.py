"""Demo session recorder — captures screenshots and assembles GIF."""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class DemoRecorder:
    """Capture screenshots during a demo session and save as GIF."""

    def __init__(self, output_dir: Path | None = None) -> None:
        self._output_dir = output_dir or Path("output/gui_session")
        self._output_dir.mkdir(parents=True, exist_ok=True)
        self.frames: list[dict[str, Any]] = []

    def capture(self, label: str = "") -> Path | None:
        import platform

        timestamp = time.strftime("%H%M%S")
        filename = f"{len(self.frames):03d}_{label}_{timestamp}.png"
        filepath = self._output_dir / filename

        try:
            if platform.system() == "Darwin":
                subprocess.run(
                    ["screencapture", "-x", str(filepath)],
                    timeout=10, check=True, capture_output=True,
                )
            else:
                subprocess.run(
                    ["scrot", str(filepath)],
                    timeout=10, check=True, capture_output=True,
                )

            self.frames.append({
                "path": filepath,
                "label": label,
                "timestamp": time.time(),
            })
            return filepath

        except (subprocess.SubprocessError, FileNotFoundError) as exc:
            logger.warning("Screenshot capture failed: %s", exc)
            return None

    def save_gif(self, output_path: Path, duration_ms: int = 1500) -> Path | None:
        if not self.frames:
            return None

        try:
            from PIL import Image
        except ImportError:
            logger.warning("Pillow not installed — cannot create GIF")
            return None

        images = []
        for frame in self.frames:
            path = frame["path"]
            if path.exists():
                img = Image.open(path)
                max_width = 1280
                if img.width > max_width:
                    ratio = max_width / img.width
                    img = img.resize(
                        (max_width, int(img.height * ratio)),
                        Image.LANCZOS,
                    )
                images.append(img)

        if not images:
            return None

        images[0].save(
            str(output_path),
            save_all=True,
            append_images=images[1:],
            duration=duration_ms,
            loop=0,
        )
        return output_path

    @property
    def frame_count(self) -> int:
        return len(self.frames)
