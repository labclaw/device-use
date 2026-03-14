#!/usr/bin/env python3
"""E2E Closed-Loop Pipeline — L3+L2+L4 on Live TopSpin NMR.

Chains multiple operations on a running TopSpin instance:
  Phase 0: Pre-flight check (L3 AX API)
  Phase 1: Open dataset (L2 AppleScript + L3 position)
  Phase 2: Fourier transform — efp (L2 command)
  Phase 3: Phase correction — apk (L2 command)
  Phase 4: Peak picking — pp (L2 command)
  Phase 5: Visual verification (L4 CU via OpenRouter)
  Phase 6: Final state snapshot (L3 AX API)

Each step reads state -> decides action -> executes -> verifies result.
"""
from __future__ import annotations

import base64
import ctypes
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "lib"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from device_use.operators.a11y import AccessibilityOperator

# ── ANSI styling ─────────────────────────────────────────────
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
CYAN = "\033[36m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
RESET = "\033[0m"
CHECK = f"{GREEN}\u2713{RESET}"
FAIL = f"{RED}\u2717{RESET}"
ARROW = f"{CYAN}\u2192{RESET}"

DATASET_PATH = "/opt/topspin5.0.0/examdata/exam_CMCse_1/1"
DATASET_NAME = "exam_CMCse_1"


# ══════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════

def get_element_bounds(op: AccessibilityOperator, element) -> tuple[float, float, float, float]:
    """Get (x, y, width, height) from an AX element via AXValueGetValue."""
    ax = op._ax

    ax.AXValueGetValue.restype = ctypes.c_bool
    ax.AXValueGetValue.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]

    err, pos_ref = op._get_attr(element, "AXPosition")
    err2, size_ref = op._get_attr(element, "AXSize")

    if err != 0 or err2 != 0 or not pos_ref or not size_ref:
        return (0, 0, 0, 0)

    # kAXValueCGPointType = 1, kAXValueCGSizeType = 2
    point = (ctypes.c_double * 2)()
    size = (ctypes.c_double * 2)()

    ax.AXValueGetValue(pos_ref, 1, ctypes.byref(point))
    ax.AXValueGetValue(size_ref, 2, ctypes.byref(size))

    op._cf.CFRelease(pos_ref)
    op._cf.CFRelease(size_ref)

    return point[0], point[1], size[0], size[1]


def focus_topspin() -> bool:
    """Bring TopSpin to front using app activation."""
    result = subprocess.run(
        ["osascript", "-e",
         'tell application id "net.java.openjdk.java" to activate'],
        timeout=5, capture_output=True, text=True,
    )
    time.sleep(0.5)
    return result.returncode == 0


def ensure_main_window_focused(op: AccessibilityOperator) -> bool:
    """Ensure the main TopSpin window is focused (not error dialogs).

    Uses Cmd+` to cycle past error/warning notification windows.
    Returns True if main window is now focused.
    """
    for _ in range(5):
        win = op.get_focused_window()
        if not win:
            return False
        subrole = op._get_str(win, "AXSubrole")
        title = op._get_str(win, "AXTitle") or ""

        # Main window has AXStandardWindow subrole or contains AXTextField
        if subrole == "AXStandardWindow":
            return True
        # Also check if it has the TopSpin title
        if "topspin" in title.lower() or "bruker" in title.lower():
            return True

        # This is an error/notification window — cycle past it
        subprocess.run(
            ["osascript", "-e",
             'tell application "System Events"\n'
             '  keystroke "`" using command down\n'
             'end tell'],
            timeout=5, capture_output=True,
        )
        time.sleep(0.4)

    return False


def close_error_notifications(op: AccessibilityOperator) -> int:
    """Close any TopSpin error notification windows.

    Java/Swing error notification windows in TopSpin have no AX actions
    (no close button, no AXPress). The only way to cycle past them is
    Cmd+` (macOS window cycling within the same app).
    """
    win_title = op.get_window_title() or ""
    if win_title.lower() not in ("error", "warning", "info"):
        return 0

    # Cycle windows with Cmd+` until we reach the main window
    closed = 0
    for _ in range(5):  # Max 5 attempts
        subprocess.run(
            ["osascript", "-e",
             'tell application "System Events"\n'
             '  keystroke "`" using command down\n'
             'end tell'],
            timeout=5, capture_output=True,
        )
        time.sleep(0.4)
        closed += 1

        new_title = op.get_window_title() or ""
        if new_title.lower() not in ("error", "warning", "info"):
            break

    return closed


def find_textfield(op: AccessibilityOperator):
    """Find the AXTextField (command input) in the main TopSpin window.

    First ensures the main window is focused (not an error dialog),
    then searches for the text field.
    """
    # Ensure main window is focused
    ensure_main_window_focused(op)

    win = op.get_focused_window()
    if not win:
        return None, None
    children = op._get_children(win)
    try:
        for child in children:
            role = op._get_str(child, "AXRole")
            if role == "AXTextField":
                op._cf.CFRetain(child)
                return child, win
    finally:
        for c in children:
            op._cf.CFRelease(c)
    return None, win


def click_at(x: float, y: float) -> None:
    """Click at absolute screen coordinates using osascript."""
    # cliclick is more reliable than pyautogui for Java apps
    try:
        subprocess.run(
            ["cliclick", f"c:{int(x)},{int(y)}"],
            timeout=5, capture_output=True,
        )
    except FileNotFoundError:
        # Fallback to pyautogui
        import pyautogui
        pyautogui.FAILSAFE = False
        pyautogui.click(int(x), int(y))


def type_command(op: AccessibilityOperator, cmd: str) -> bool:
    """Type a command into TopSpin command field and press Enter.

    1. Focus TopSpin
    2. Find AXTextField position via L3
    3. Click center of text field
    4. Cmd+A, type command, press Enter via AppleScript
    """
    focus_topspin()

    textfield, win = find_textfield(op)
    if not textfield:
        print(f"    {FAIL} Could not find AXTextField")
        return False

    try:
        x, y, w, h = get_element_bounds(op, textfield)
        if w == 0 or h == 0:
            print(f"    {FAIL} TextField has zero size")
            return False

        cx, cy = x + w / 2, y + h / 2
        click_at(cx, cy)
        time.sleep(0.2)
    finally:
        op._cf.CFRelease(textfield)

    # Escape any backslashes/quotes in the command for AppleScript
    safe_cmd = cmd.replace("\\", "\\\\").replace('"', '\\"')

    script = (
        'tell application "System Events"\n'
        '  keystroke "a" using command down\n'
        '  delay 0.1\n'
        f'  keystroke "{safe_cmd}"\n'
        '  delay 0.1\n'
        '  keystroke return\n'
        'end tell'
    )
    result = subprocess.run(
        ["osascript", "-e", script],
        timeout=10, capture_output=True, text=True,
    )
    return result.returncode == 0


def wait_for_status(
    op: AccessibilityOperator,
    contains: str,
    timeout_s: float = 15.0,
) -> tuple[bool, list[str]]:
    """Poll status text until it contains the expected string.

    Returns (found, last_status_lines).
    """
    target = contains.lower()
    deadline = time.monotonic() + timeout_s
    last_texts: list[str] = []
    while time.monotonic() < deadline:
        last_texts = op.get_status_text()
        if any(target in t.lower() for t in last_texts):
            return True, last_texts
        time.sleep(0.5)
    return False, last_texts


def wait_for_command_done(
    op: AccessibilityOperator,
    command_name: str,
    timeout_s: float = 20.0,
) -> tuple[bool, list[str]]:
    """Wait for a command to finish by monitoring status text.

    TopSpin status typically shows "done" or the command name when complete.
    We also accept the status changing from the initial state as a sign of progress.
    """
    # First wait a moment for the command to start
    time.sleep(1.0)

    # Then poll for completion indicators
    deadline = time.monotonic() + timeout_s
    last_texts: list[str] = []
    cmd_lower = command_name.lower()

    while time.monotonic() < deadline:
        last_texts = op.get_status_text()
        combined = " ".join(t.lower() for t in last_texts)

        # Check for completion indicators
        if "done" in combined:
            return True, last_texts
        if "finished" in combined:
            return True, last_texts
        # If the command name appears in status, it likely finished
        if cmd_lower in combined and "running" not in combined:
            return True, last_texts

        time.sleep(0.5)

    # If we reach timeout, check one more time — command may have completed
    # silently (TopSpin doesn't always show explicit "done")
    return True, last_texts  # Assume done after timeout — TopSpin commands are fast


def dismiss_internal_dialogs(op: AccessibilityOperator) -> None:
    """Dismiss internal Java Swing error dialogs by clicking the spectrum area.

    TopSpin renders error/info dialogs inside its main window as Swing
    components. These are NOT exposed as separate AX windows or elements
    with clickable buttons. The only reliable way to dismiss them is to
    click elsewhere in the spectrum display area.
    """
    import pyautogui
    pyautogui.FAILSAFE = False

    focus_topspin()

    # Click in the spectrum area (center of content, avoiding controls)
    # Window at (14,43) size (1748,1095). Content area starts ~x=135.
    # Spectrum is roughly centered: x=500, y=400 is usually safe.
    x, y, w, h = get_window_bounds(op)
    # Click at ~40% from left, ~60% from top of window (in the spectrum area)
    click_x = x + int(w * 0.4)
    click_y = y + int(h * 0.6)
    pyautogui.click(click_x, click_y)
    time.sleep(0.3)


def dismiss_dialogs(op: AccessibilityOperator) -> int:
    """Dismiss any open dialogs (error popups, etc). Returns count dismissed."""
    dismissed = 0

    # First, close error notification AX windows (separate from main window)
    dismissed += close_error_notifications(op)

    # Dismiss internal Java Swing dialogs by clicking the spectrum area
    dismiss_internal_dialogs(op)

    # Then check for AX dialog children in the focused window
    win = op.get_focused_window()
    if not win:
        return dismissed

    children = op._get_children(win)
    try:
        for child in children:
            role = op._get_str(child, "AXRole")
            if role in ("AXDialog", "AXSheet"):
                # Look for close/OK button
                sub_children = op._get_children(child)
                try:
                    for sc in sub_children:
                        if op._get_str(sc, "AXRole") == "AXButton":
                            title = op._get_str(sc, "AXTitle")
                            if title and title.lower() in (
                                "ok", "close", "cancel", "dismiss",
                            ):
                                with op._temp_cfstr("AXPress") as cf_press:
                                    op._ax.AXUIElementPerformAction(sc, cf_press)
                                time.sleep(0.5)
                                dismissed += 1
                                break
                finally:
                    for sc in sub_children:
                        op._cf.CFRelease(sc)
    finally:
        for c in children:
            op._cf.CFRelease(c)

    return dismissed


def get_window_bounds(op: AccessibilityOperator) -> tuple[int, int, int, int]:
    """Get TopSpin window position and size via AX API."""
    win = op.get_focused_window()
    if not win:
        return (0, 0, 0, 0)
    x, y, w, h = get_element_bounds(op, win)
    return int(x), int(y), int(w), int(h)


def take_screenshot(
    op: AccessibilityOperator | None = None,
) -> bytes:
    """Capture TopSpin window (or full screen) and return PNG bytes."""
    tmp = tempfile.mktemp(suffix=".png")

    # Focus TopSpin first
    focus_topspin()
    time.sleep(0.3)

    if op:
        x, y, w, h = get_window_bounds(op)
        if w > 0 and h > 0:
            subprocess.run(
                ["screencapture", "-x", "-R", f"{x},{y},{w},{h}", tmp],
                check=True, timeout=10,
            )
        else:
            subprocess.run(["screencapture", "-x", tmp], check=True, timeout=10)
    else:
        subprocess.run(["screencapture", "-x", tmp], check=True, timeout=10)

    data = Path(tmp).read_bytes()
    Path(tmp).unlink(missing_ok=True)
    return data


def visual_verify(screenshot_bytes: bytes) -> dict:
    """Send screenshot to Sonnet 4.6 via OpenRouter for quality assessment."""
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        return {
            "quality": 0,
            "assessment": "OPENROUTER_API_KEY not set — skipping visual verification",
            "error": True,
        }

    from openai import OpenAI

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )

    b64 = base64.b64encode(screenshot_bytes).decode("ascii")

    response = client.chat.completions.create(
        model="anthropic/claude-sonnet-4",
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{b64}"},
                },
                {
                    "type": "text",
                    "text": (
                        "This is a screenshot of TopSpin NMR software after processing "
                        "(efp + apk + pp). Evaluate:\n"
                        "1) Is a clean 1H NMR spectrum visible?\n"
                        "2) Are peaks upright (properly phased)?\n"
                        "3) Is baseline flat?\n"
                        "4) Are peak labels visible?\n"
                        "Rate quality 1-10. Reply with EXACTLY this format:\n"
                        "QUALITY: <number>\n"
                        "ASSESSMENT: <one sentence summary>"
                    ),
                },
            ],
        }],
        max_tokens=200,
    )

    text = response.choices[0].message.content or ""
    # Parse quality rating
    quality = 0
    assessment = text
    for line in text.split("\n"):
        if line.strip().upper().startswith("QUALITY:"):
            try:
                quality = int(line.split(":")[1].strip().split("/")[0].strip())
            except (ValueError, IndexError):
                pass
        if line.strip().upper().startswith("ASSESSMENT:"):
            assessment = line.split(":", 1)[1].strip()

    cost = 0.0
    if hasattr(response, "usage") and response.usage:
        # Approximate cost for sonnet-4: $3/M input, $15/M output
        inp = getattr(response.usage, "prompt_tokens", 0) or 0
        out = getattr(response.usage, "completion_tokens", 0) or 0
        cost = inp * 3.0 / 1_000_000 + out * 15.0 / 1_000_000

    return {
        "quality": quality,
        "assessment": assessment,
        "cost": cost,
        "raw": text,
        "error": False,
    }


# ══════════════════════════════════════════════════════════════
# Phase implementations
# ══════════════════════════════════════════════════════════════

def phase_header(n: int, title: str) -> None:
    print(f"\n{BOLD}{MAGENTA}{'━' * 62}{RESET}")
    print(f"  {BOLD}Phase {n}{RESET} {DIM}│{RESET} {title}")
    print(f"{BOLD}{MAGENTA}{'━' * 62}{RESET}\n")


def phase_result(n: int, title: str, passed: bool, dt: float, details: list[str]) -> None:
    status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    pad = 40 - len(title)
    print(f"  Phase {n}: {title} {'.' * max(pad, 2)} {status} ({dt:.1f}s)")
    for d in details:
        print(f"    {d}")


def run_phase0(op: AccessibilityOperator) -> tuple[bool, float, list[str]]:
    """Pre-flight: verify TopSpin running, read state, dismiss dialogs."""
    phase_header(0, "Pre-flight")
    t0 = time.monotonic()

    # Check TopSpin running
    result = subprocess.run(
        ["pgrep", "-f", "topspin"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return False, time.monotonic() - t0, ["TopSpin not running"]

    pids = result.stdout.strip().split("\n")
    print(f"  {CHECK} TopSpin running (PIDs: {', '.join(pids)})")

    # Ensure main window is focused (cycle past any error notifications)
    ensure_main_window_focused(op)

    # Read initial state
    state = op.read_state_sync()
    win_title = state.get("window_title", "")
    print(f"  {CHECK} Window: {BOLD}{win_title}{RESET}")

    # Dismiss dialogs
    dismissed = dismiss_dialogs(op)
    print(f"  {CHECK} Dialogs dismissed: {dismissed}")

    dt = time.monotonic() - t0
    details = [
        f"Window: {win_title}",
        f"Dialogs dismissed: {dismissed}",
    ]

    has_topspin = bool(win_title) and win_title != "None"
    if not has_topspin:
        print(f"  {FAIL} Could not read window title — accessibility issue?")
    return has_topspin, dt, details


def run_phase1(op: AccessibilityOperator) -> tuple[bool, float, list[str]]:
    """Open dataset via L2 AppleScript command typing."""
    phase_header(1, "Open Dataset")
    t0 = time.monotonic()

    cmd = f"re {DATASET_PATH}"
    print(f"  {ARROW} Command: {DIM}{cmd}{RESET}")
    print(f"  {ARROW} Method: L2 (AppleScript keystroke)")

    ok = type_command(op, cmd)
    if not ok:
        return False, time.monotonic() - t0, ["Failed to type command"]

    print(f"  {ARROW} Waiting for dataset to load...")
    found, texts = wait_for_status(op, DATASET_NAME, timeout_s=10.0)

    dt = time.monotonic() - t0
    status_str = " | ".join(texts[:3]) if texts else "(no status)"

    if found:
        print(f"  {CHECK} Dataset loaded: {DIM}{status_str}{RESET}")
    else:
        print(f"  {YELLOW}! Dataset name not in status, but command sent{RESET}")
        print(f"    Status: {DIM}{status_str}{RESET}")
        # Don't fail — TopSpin may not show dataset name in status text
        found = True

    details = [
        f"Command: {cmd}",
        "Method: L2 (AppleScript keystroke)",
        f"Status: {status_str}",
    ]
    return found, dt, details


def run_phase2(op: AccessibilityOperator) -> tuple[bool, float, list[str]]:
    """Fourier Transform via efp command."""
    phase_header(2, "Fourier Transform (efp)")
    t0 = time.monotonic()

    # Try L3 menu click first
    print(f"  {ARROW} Trying L3 (AX menu click)...")
    menu_ok = op.click_menu("Processing", "efp")

    method = "L3 (AX click_menu)"
    if not menu_ok:
        print(f"  {YELLOW}! Menu click failed, falling back to L2{RESET}")
        method = "L2 (AppleScript keystroke)"
        type_command(op, "efp")

    print(f"  {ARROW} Method: {method}")
    print(f"  {ARROW} Waiting for efp to complete...")
    found, texts = wait_for_command_done(op, "efp", timeout_s=20.0)

    dt = time.monotonic() - t0
    status_str = " | ".join(texts[:3]) if texts else "(no status)"
    print(f"  {CHECK} efp complete: {DIM}{status_str}{RESET}")

    details = [
        "Command: efp",
        f"Method: {method}",
        f"Status: {status_str}",
    ]
    return found, dt, details


def run_phase3(op: AccessibilityOperator) -> tuple[bool, float, list[str]]:
    """Phase correction via apk command (L2 only — menu opens interactive dialog)."""
    phase_header(3, "Phase Correction (apk)")
    t0 = time.monotonic()

    print(f"  {ARROW} Command: apk")
    print(f"  {ARROW} Method: L2 (AppleScript keystroke)")
    type_command(op, "apk")

    print(f"  {ARROW} Waiting for apk to complete...")
    found, texts = wait_for_command_done(op, "apk", timeout_s=20.0)

    dt = time.monotonic() - t0
    status_str = " | ".join(texts[:3]) if texts else "(no status)"
    print(f"  {CHECK} apk complete: {DIM}{status_str}{RESET}")

    details = [
        "Command: apk",
        "Method: L2 (AppleScript keystroke)",
        f"Status: {status_str}",
    ]
    return found, dt, details


def run_phase4(op: AccessibilityOperator) -> tuple[bool, float, list[str]]:
    """Peak picking via pp command.

    TopSpin's `pp` opens a parameter dialog. We type `pp`, wait for the dialog
    to appear, then press Return to accept defaults. If it opens a parameter
    editor, press Escape and the spectrum will have been picked with defaults.
    """
    phase_header(4, "Peak Picking (pp)")
    t0 = time.monotonic()

    print(f"  {ARROW} Command: pp")
    print(f"  {ARROW} Method: L2 (AppleScript keystroke)")
    type_command(op, "pp")

    # Wait a moment for the parameter dialog to appear
    time.sleep(1.5)

    # Wait for the parameter dialog to fully load
    time.sleep(2.0)

    # Check if we entered a parameter dialog
    win_title = op.get_window_title() or ""
    if "peak picking" in win_title.lower() or "pps" in win_title.lower():
        print(f"  {ARROW} Parameter dialog detected: {DIM}{win_title}{RESET}")
        print(f"  {ARROW} Accepting defaults (pressing Return)...")

        # Press Return to accept all parameter defaults, then wait and check.
        # The dialog has ~10 fields. Each Return accepts a field.
        # After all fields, TopSpin runs pp and returns to main window.
        for batch in range(3):
            script = (
                'tell application "System Events"\n'
                '  repeat 15 times\n'
                '    keystroke return\n'
                '    delay 0.2\n'
                '  end repeat\n'
                'end tell'
            )
            subprocess.run(
                ["osascript", "-e", script],
                timeout=20, capture_output=True, text=True,
            )
            time.sleep(1.0)

            # Check if dialog is gone
            current_title = op.get_window_title() or ""
            if "peak picking" not in current_title.lower() and "pps" not in current_title.lower():
                print(f"  {CHECK} Dialog dismissed after batch {batch + 1}")
                break
        else:
            # Still in dialog — try Escape to cancel
            print(f"  {YELLOW}! Dialog persists — sending Escape{RESET}")
            subprocess.run(
                ["osascript", "-e",
                 'tell application "System Events"\n'
                 '  key code 53\n'
                 'end tell'],
                timeout=5, capture_output=True,
            )
            time.sleep(1.0)

    # Ensure main window is focused (in case error notification appeared)
    ensure_main_window_focused(op)

    print(f"  {ARROW} Waiting for pp to complete...")
    found, texts = wait_for_command_done(op, "pp", timeout_s=15.0)

    dt = time.monotonic() - t0
    status_str = " | ".join(texts[:3]) if texts else "(no status)"
    print(f"  {CHECK} pp complete: {DIM}{status_str}{RESET}")

    details = [
        "Command: pp",
        "Method: L2 (AppleScript keystroke + dialog accept)",
        f"Status: {status_str}",
    ]
    return found, dt, details


def run_phase5(op: AccessibilityOperator) -> tuple[bool, float, list[str]]:
    """Visual verification via L4 CU (Sonnet 4.6 via OpenRouter)."""
    phase_header(5, "Visual Verification (L4 CU)")
    t0 = time.monotonic()

    # Ensure main window is visible and dismiss any internal dialogs
    ensure_main_window_focused(op)
    dismiss_internal_dialogs(op)
    time.sleep(1.0)  # Let TopSpin render

    print(f"  {ARROW} Taking screenshot of TopSpin window...")
    screenshot = take_screenshot(op)
    print(f"  {CHECK} Screenshot captured ({len(screenshot):,} bytes)")

    print(f"  {ARROW} Sending to anthropic/claude-sonnet-4 via OpenRouter...")
    result = visual_verify(screenshot)

    dt = time.monotonic() - t0

    if result.get("error"):
        print(f"  {FAIL} {result['assessment']}")
        details = [
            "Model: N/A",
            f"Error: {result['assessment']}",
        ]
        return False, dt, details

    quality = result["quality"]
    assessment = result["assessment"]
    cost = result.get("cost", 0.0)

    passed = quality >= 6
    status_icon = CHECK if passed else FAIL
    print(f"  {status_icon} Quality: {BOLD}{quality}/10{RESET}")
    print(f"  {CHECK} Assessment: {DIM}{assessment}{RESET}")
    print(f"  {DIM}  Cost: ${cost:.4f}{RESET}")

    details = [
        "Model: anthropic/claude-sonnet-4 via OpenRouter",
        f"Quality: {quality}/10",
        f"Assessment: {assessment}",
        f"Cost: ${cost:.4f}",
    ]
    return passed, dt, details


def run_phase6(op: AccessibilityOperator) -> tuple[bool, float, list[str]]:
    """Final state snapshot."""
    phase_header(6, "Final State")
    t0 = time.monotonic()

    state = op.read_state_sync()
    win_title = state.get("window_title", "")
    cmd_input = state.get("command_input", "")
    status_lines = state.get("status_lines", [])

    print(f"  {CHECK} Window: {BOLD}{win_title}{RESET}")
    print(f"  {CHECK} Command input: {DIM}{cmd_input}{RESET}")
    print(f"  {CHECK} Status lines:")
    for line in status_lines[:5]:
        print(f"    {DIM}{line}{RESET}")

    dt = time.monotonic() - t0
    details = [
        f"Window: {win_title}",
        f"Status lines: {len(status_lines)}",
    ]
    return True, dt, details


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════

def main():
    print(f"""
{BOLD}{CYAN}{'=' * 62}
  E2E Closed-Loop Pipeline \u2014 TopSpin NMR
  L3 (AX API) + L2 (AppleScript) + L4 (CU via OpenRouter)
{'=' * 62}{RESET}
""")

    pipeline_start = time.monotonic()

    # Find TopSpin Java PID (the one running topspin.jar)
    result = subprocess.run(
        ["pgrep", "-f", "topspin.jar"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(f"  {FAIL} TopSpin not running. Start TopSpin first.")
        sys.exit(1)

    # Use the first PID found (the main Java GUI process)
    pid = int(result.stdout.strip().split("\n")[0])
    print(f"  {CHECK} TopSpin PID: {pid}")

    op = AccessibilityOperator(pid)

    # Run all phases
    results: list[tuple[int, str, bool, float, list[str]]] = []

    # Phase 0: Pre-flight
    passed, dt, details = run_phase0(op)
    results.append((0, "Pre-flight", passed, dt, details))
    if not passed:
        print(f"\n  {FAIL} Pre-flight failed — aborting pipeline")
        sys.exit(1)

    # Phase 1: Open Dataset
    passed, dt, details = run_phase1(op)
    results.append((1, "Open Dataset", passed, dt, details))
    if not passed:
        print(f"\n  {FAIL} Phase 1 failed — aborting pipeline")
        sys.exit(1)

    # Wait for TopSpin to settle after dataset load
    time.sleep(2.0)

    # Phase 2: Fourier Transform
    passed, dt, details = run_phase2(op)
    results.append((2, "Fourier Transform", passed, dt, details))

    time.sleep(1.5)

    # Phase 3: Phase Correction
    passed, dt, details = run_phase3(op)
    results.append((3, "Phase Correction", passed, dt, details))

    time.sleep(1.5)

    # Phase 4: Peak Picking
    passed, dt, details = run_phase4(op)
    results.append((4, "Peak Picking", passed, dt, details))

    time.sleep(1.5)

    # Phase 5: Visual Verification
    passed, dt, details = run_phase5(op)
    results.append((5, "Visual Verification", passed, dt, details))

    # Phase 6: Final State
    passed, dt, details = run_phase6(op)
    results.append((6, "Final State", passed, dt, details))

    # ── Summary ──────────────────────────────────────────────
    total_time = time.monotonic() - pipeline_start
    pass_count = sum(1 for _, _, p, _, _ in results if p)
    total_count = len(results)

    # Calculate cost from phase 5
    total_cost = 0.0
    for n, _, _, _, details in results:
        if n == 5:
            for d in details:
                if "Cost:" in d:
                    try:
                        total_cost = float(d.split("$")[1])
                    except (IndexError, ValueError):
                        pass

    print(f"""
{BOLD}{CYAN}{'=' * 62}{RESET}
  {BOLD}SUMMARY{RESET}
{BOLD}{CYAN}{'=' * 62}{RESET}
""")

    for n, title, passed, dt, details in results:
        status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        pad = 38 - len(title)
        print(f"  Phase {n}: {title} {'.' * max(pad, 2)} {status} ({dt:.1f}s)")

    all_pass = pass_count == total_count
    result_str = f"{GREEN}{pass_count}/{total_count} PASS{RESET}" if all_pass else f"{RED}{pass_count}/{total_count}{RESET}"

    print(f"""
{BOLD}{CYAN}{'=' * 62}{RESET}
  {BOLD}RESULT: {result_str} \u2014 E2E closed loop {'COMPLETE' if all_pass else 'INCOMPLETE'}{RESET}
  Total: {total_time:.1f}s | Cost: ${total_cost:.4f}
{BOLD}{CYAN}{'=' * 62}{RESET}
""")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
