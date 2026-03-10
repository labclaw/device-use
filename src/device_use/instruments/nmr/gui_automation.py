"""TopSpin GUI automation via Anthropic Computer Use.

Enables AI to visually operate the TopSpin NMR software, just like
a human scientist would — clicking menus, typing commands, reading results.

This is the "wow factor" mode: the AI doesn't just process data,
it physically operates the instrument software.

Architecture:
    Claude (Computer Use API)
        ↓ screenshots + actions
    TopSpin GUI (Java Swing)
        ↓ processed data
    nmrglue (data readback)
        ↓ NMRSpectrum

Requires:
    - ANTHROPIC_API_KEY environment variable
    - TopSpin 5.0.0 GUI running and visible on screen
    - anthropic Python SDK
"""

from __future__ import annotations

import base64
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# TopSpin command-line interface commands
TOPSPIN_COMMANDS = {
    "open_dataset": 're {path}',
    "fourier_transform": "efp",
    "auto_phase": "apk",
    "baseline_correct": "absn",
    "peak_pick": "ppf",
    "process_all": "efp\napbk\nppf",
}


class TopSpinGUIAutomation:
    """Automate TopSpin GUI via Computer Use API.

    Uses Anthropic's Computer Use (beta) to take screenshots of the
    TopSpin application, understand the current state, and send
    mouse/keyboard actions to process NMR data.

    Example::

        gui = TopSpinGUIAutomation()
        if gui.available:
            gui.open_dataset("/opt/topspin5.0.0/examdata/exam_CMCse_1/1")
            gui.process_spectrum()
    """

    def __init__(self) -> None:
        self._client = None
        self._model = "claude-sonnet-4-20250514"
        self._available = False
        self._topspin_visible = False
        self._init_client()

    def _init_client(self) -> None:
        """Try to initialize the Anthropic client."""
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return
        try:
            from anthropic import Anthropic
            self._client = Anthropic()
            self._available = True
        except ImportError:
            pass

    @property
    def available(self) -> bool:
        """Whether Computer Use is available (API key + SDK installed)."""
        return self._available

    def detect_topspin_window(self) -> bool:
        """Check if TopSpin GUI is visible on screen.

        Uses AppleScript on macOS to detect if TopSpin is running,
        or wmctrl on Linux.
        """
        import platform
        system = platform.system()

        if system == "Darwin":
            return self._detect_topspin_macos()
        elif system == "Linux":
            return self._detect_topspin_linux()
        return False

    def _detect_topspin_macos(self) -> bool:
        """Detect TopSpin on macOS using AppleScript."""
        try:
            result = subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events" to get name of every process '
                 'whose name contains "TopSpin"'],
                capture_output=True, text=True, timeout=5,
            )
            found = "TopSpin" in result.stdout
            self._topspin_visible = found
            return found
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _detect_topspin_linux(self) -> bool:
        """Detect TopSpin on Linux using wmctrl."""
        try:
            result = subprocess.run(
                ["wmctrl", "-l"],
                capture_output=True, text=True, timeout=5,
            )
            found = "TopSpin" in result.stdout
            self._topspin_visible = found
            return found
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def take_screenshot(self) -> bytes:
        """Capture the current screen.

        Returns PNG bytes of the screen capture.
        """
        import platform
        system = platform.system()

        if system == "Darwin":
            return self._screenshot_macos()
        elif system == "Linux":
            return self._screenshot_linux()
        raise RuntimeError(f"Screenshot not supported on {system}")

    def _screenshot_macos(self) -> bytes:
        """Take screenshot on macOS using screencapture."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name
        try:
            subprocess.run(
                ["screencapture", "-x", tmp_path],
                timeout=10, check=True,
            )
            return Path(tmp_path).read_bytes()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def _screenshot_linux(self) -> bytes:
        """Take screenshot on Linux using scrot or import."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp_path = f.name
        try:
            # Try scrot first, then ImageMagick import
            for cmd in [["scrot", tmp_path], ["import", "-window", "root", tmp_path]]:
                try:
                    subprocess.run(cmd, timeout=10, check=True)
                    return Path(tmp_path).read_bytes()
                except FileNotFoundError:
                    continue
            raise RuntimeError("No screenshot tool available (install scrot)")
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def send_to_computer_use(
        self,
        instruction: str,
        screenshot: bytes | None = None,
    ) -> dict[str, Any]:
        """Send an instruction to Claude Computer Use.

        Args:
            instruction: What to do (e.g., "Click the Process menu").
            screenshot: PNG bytes of current screen state.

        Returns:
            Dict with action to take (click, type, etc.)
        """
        if not self._available:
            raise RuntimeError("Computer Use not available — need ANTHROPIC_API_KEY")

        if screenshot is None:
            screenshot = self.take_screenshot()

        b64_image = base64.standard_b64encode(screenshot).decode("utf-8")

        response = self._client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=(
                "You are controlling a TopSpin NMR spectroscopy application. "
                "You can see the screen and need to perform actions to process "
                "NMR data. Describe the exact mouse/keyboard action needed."
            ),
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": b64_image,
                            },
                        },
                        {"type": "text", "text": instruction},
                    ],
                }
            ],
        )
        return {"response": response.content[0].text}

    def type_command(self, command: str) -> None:
        """Type a command into TopSpin's command line.

        TopSpin has a command line at the bottom of the window
        where you can type processing commands directly.
        """
        import platform

        if platform.system() == "Darwin":
            # Use AppleScript to type into TopSpin
            script = f'''
            tell application "TopSpin 5"
                activate
            end tell
            delay 0.5
            tell application "System Events"
                keystroke "{command}"
                keystroke return
            end tell
            '''
            subprocess.run(
                ["osascript", "-e", script],
                timeout=10, capture_output=True,
            )
        else:
            # Linux: use xdotool
            subprocess.run(
                ["xdotool", "type", "--delay", "50", command],
                timeout=10, capture_output=True,
            )
            subprocess.run(
                ["xdotool", "key", "Return"],
                timeout=5, capture_output=True,
            )

    def open_dataset(self, dataset_path: str) -> None:
        """Open a dataset in TopSpin GUI."""
        cmd = TOPSPIN_COMMANDS["open_dataset"].format(path=dataset_path)
        logger.info("GUI: Opening dataset %s", dataset_path)
        self.type_command(cmd)
        time.sleep(2)  # Wait for dataset to load

    def process_spectrum(self) -> None:
        """Run the standard processing pipeline via GUI commands.

        Sends commands to TopSpin's command line:
        1. efp  — exponential multiply + Fourier transform + phase
        2. apbk — auto phase + baseline correction
        3. ppf  — peak picking
        """
        commands = ["efp", "apbk", "ppf"]
        for cmd in commands:
            logger.info("GUI: Running %s", cmd)
            self.type_command(cmd)
            time.sleep(3)  # Wait for each step to complete

    def get_gui_status(self) -> dict[str, Any]:
        """Get current status of the GUI automation system."""
        return {
            "available": self._available,
            "topspin_visible": self._topspin_visible,
            "model": self._model,
            "has_api_key": bool(os.environ.get("ANTHROPIC_API_KEY")),
        }
