#!/usr/bin/env python3
"""AI operates TopSpin via VNC on Tart VM — no VM-side permissions needed.

Uses vncdotool for VNC screenshots and input from the host side.
Sonnet 4.6 (via OpenRouter) verifies each step via screenshot analysis.
Each frame is pushed to labwork-web as MJPEG stream for live viewing.

Tart VM: topspin-sequoia (ARD auth via env vars VNC_USER/VNC_PASS, VNC port 5900).
Framebuffer: 2048x1536 (retina for 1024x768 VM display).
Sonnet perceives images at ~1280x960 and applies 1.6x scaling.

Usage:
    # 1. Start VM:   tart run topspin-sequoia --no-graphics --vnc-experimental
    # 2. Start web:  cd labwork-web && uvicorn app:app --port 8430
    # 3. Run demo:   python demos/25_vnc_cu_demo.py
    # 4. Watch:      open http://localhost:8430 → Live VM tab
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import subprocess
import sys
import threading
import time

import httpx
from openai import OpenAI
from PIL import Image
from vncdotool import api as vncapi

# ── Config ──────────────────────────────────────
MODEL = "anthropic/claude-sonnet-4.6"
LABWORK_URL = os.environ.get("LABWORK_URL", "http://localhost:8430")
DATASET = os.environ.get(
    "TOPSPIN_DATASET",
    "/opt/topspin5.0.0/examdata/exam_CMCse_1/1",
)

VM_NAME = os.environ.get("VM_NAME", "topspin-sequoia")
VM_USER = os.environ.get("VNC_USER", "changeme")
VM_PASS = os.environ.get("VNC_PASS", "changeme")
VNC_PORT = 5900

# TopSpin command line position (framebuffer coords, 2048x1536)
CMD_X, CMD_Y = 200, 960

B = "\033[1m"
G = "\033[32m"
C = "\033[36m"
D = "\033[2m"
R = "\033[31m"
Y = "\033[33m"
RST = "\033[0m"


# ── VNC helpers ──────────────────────────────────


def get_vnc_info() -> tuple[str, str]:
    """Get VNC address from tart ip."""
    result = subprocess.run(
        ["tart", "ip", VM_NAME],
        capture_output=True,
        text=True,
        timeout=10,
    )
    ip = result.stdout.strip()
    if not ip:
        raise RuntimeError(f"{VM_NAME} not running or IP not found")
    vnc_addr = f"{ip}::{VNC_PORT}"
    return vnc_addr, ip


def safe_disconnect(client, timeout: float = 2) -> None:
    """Disconnect VNC client with timeout (ARD auth hangs on disconnect)."""
    t = threading.Thread(target=client.disconnect)
    t.daemon = True
    t.start()
    t.join(timeout)


def vnc_connect(vnc_addr: str):
    """Create a VNC connection with ARD auth."""
    return vncapi.connect(vnc_addr, username=VM_USER, password=VM_PASS)


def vnc_screenshot(vnc_addr: str, path: str = "/tmp/vnc_frame.png") -> Image.Image:
    """Take a screenshot via VNC, return PIL Image."""
    c = vnc_connect(vnc_addr)
    c.captureScreen(path)
    safe_disconnect(c)
    return Image.open(path)


def vnc_click(vnc_addr: str, x: int, y: int):
    """Click at framebuffer coordinates via VNC."""
    c = vnc_connect(vnc_addr)
    c.mouseMove(int(x), int(y))
    time.sleep(0.1)
    c.mousePress(1)
    safe_disconnect(c)


def vnc_type_text(vnc_addr: str, text: str):
    """Type text via VNC with proper shift handling for uppercase and underscore."""
    c = vnc_connect(vnc_addr)
    for ch in text:
        if ch.isupper():
            c.keyDown("shift")
            c.keyPress(ch.lower())
            c.keyUp("shift")
        elif ch == "_":
            c.keyDown("shift")
            c.keyPress("-")
            c.keyUp("shift")
        else:
            c.keyPress(ch)
        time.sleep(0.02)
    safe_disconnect(c)


def vnc_key(vnc_addr: str, key: str):
    """Press a named key via VNC. Valid: return, tab, esc, bsp, space, etc."""
    c = vnc_connect(vnc_addr)
    c.keyPress(key)
    safe_disconnect(c)


def vnc_release_modifiers(vnc_addr: str):
    """Release any stuck modifier keys."""
    c = vnc_connect(vnc_addr)
    for mod in ("shift", "lshift", "rshift", "ctrl", "lctrl", "alt", "lalt", "lmeta"):
        c.keyUp(mod)
    time.sleep(0.1)
    safe_disconnect(c)


def vnc_type_command(vnc_addr: str, cmd: str):
    """Triple-click TopSpin command line, type command, press Return."""
    # Triple-click to select all in command line
    c = vnc_connect(vnc_addr)
    c.mouseMove(CMD_X, CMD_Y)
    time.sleep(0.1)
    c.mousePress(1)
    time.sleep(0.05)
    c.mousePress(1)
    time.sleep(0.05)
    c.mousePress(1)
    time.sleep(0.3)
    safe_disconnect(c)

    # Type the command
    vnc_type_text(vnc_addr, cmd)
    time.sleep(0.2)

    # Press Return to execute
    vnc_key(vnc_addr, "return")


# ── Stream helpers ───────────────────────────────


def push_frame(jpeg_bytes: bytes):
    """Push a JPEG frame to labwork-web MJPEG stream."""
    try:
        httpx.post(
            f"{LABWORK_URL}/vm/frame",
            content=jpeg_bytes,
            headers={"Content-Type": "image/jpeg"},
            timeout=2,
        )
    except Exception:
        pass


def push_log(text: str, status: str | None = None):
    """Push a log line to labwork-web."""
    data: dict = {"text": text}
    if status:
        data["status"] = status
    try:
        httpx.post(f"{LABWORK_URL}/vm/log", json=data, timeout=2)
    except Exception:
        pass
    print(f"  {D}{text}{RST}")


def screenshot_and_push(vnc_addr: str) -> tuple[Image.Image, bytes]:
    """Take screenshot, push JPEG to stream, return (image, png_bytes)."""
    img = vnc_screenshot(vnc_addr)

    # JPEG for stream
    buf_jpg = io.BytesIO()
    img.save(buf_jpg, format="JPEG", quality=75)
    push_frame(buf_jpg.getvalue())

    # PNG bytes for VLM
    buf_png = io.BytesIO()
    img.save(buf_png, format="PNG")
    return img, buf_png.getvalue()


# ── VLM ─────────────────────────────────────────


def ask_sonnet(client: OpenAI, screenshot_b64: str, question: str) -> str:
    """Send screenshot + question to Sonnet 4.6, get text response."""
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=512,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"},
                    },
                    {
                        "type": "text",
                        "text": (
                            "This is a 2048x1536 pixel screenshot of macOS with Bruker TopSpin 5.0.\n"
                            f"{question}\n\n"
                            "Remember: scale perceived coordinates by 1.6 for 2048x1536 space.\n"
                            "Return ONLY JSON, no markdown fences."
                        ),
                    },
                ],
            }
        ],
    )
    return response.choices[0].message.content.strip()


def ask_sonnet_coords(client: OpenAI, screenshot_b64: str, target: str) -> tuple[int, int] | None:
    """Ask Sonnet for coordinates of a UI element."""
    text = ask_sonnet(
        client, screenshot_b64, f'Find the "{target}" button/element. Return: {{"x": N, "y": N}}'
    )
    mx = re.search(r'"x"\s*:\s*(\d+)', text)
    my = re.search(r'"y"\s*:\s*(\d+)', text)
    if mx and my:
        return int(mx.group(1)), int(my.group(1))
    return None


def ask_sonnet_verify(client: OpenAI, screenshot_b64: str, check: str) -> dict:
    """Ask Sonnet to verify a condition. Returns {"ok": bool, "description": str}."""
    text = ask_sonnet(
        client,
        screenshot_b64,
        f'{check}\nReturn: {{"ok": true/false, "description": "what you see"}}',
    )
    # Parse JSON from response
    m = re.search(r"\{[^}]+\}", text)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {"ok": False, "description": text[:200]}


# ── Pipeline Steps ──────────────────────────────


def step_open_topspin(vnc_addr: str, ai: OpenAI) -> bool:
    """Ensure TopSpin is open and visible."""
    push_log("▶ Open TopSpin", status="operating")

    img, png = screenshot_and_push(vnc_addr)
    b64 = base64.b64encode(png).decode()

    result = ask_sonnet_verify(
        ai,
        b64,
        "Is Bruker TopSpin 5.0 open and visible? Look for the TopSpin toolbar and title bar.",
    )
    if result.get("ok"):
        push_log(f"  ✓ TopSpin already open: {result.get('description', '')}")
        return True

    # Try clicking TopSpin in dock
    push_log("  TopSpin not visible, looking in Dock...")
    coords = ask_sonnet_coords(ai, b64, "TopSpin icon in the Dock at the bottom")
    if coords:
        vnc_click(vnc_addr, coords[0], coords[1])
        time.sleep(5)
        img, png = screenshot_and_push(vnc_addr)
        b64 = base64.b64encode(png).decode()
        result = ask_sonnet_verify(ai, b64, "Is TopSpin now visible?")
        if result.get("ok"):
            push_log("  ✓ TopSpin opened from Dock")
            return True

    # Fallback: activate via SSH (handles cases where dock click didn't work)
    push_log("  Activating TopSpin via SSH...")
    subprocess.run(
        [
            "sshpass",
            "-p",
            VM_PASS,
            "ssh",
            "-o",
            "StrictHostKeyChecking=no",
            f"{VM_USER}@{_VM_IP}",
            "open -a '/opt/topspin5.0.0/TopSpin 5.0.0.app'",
        ],
        capture_output=True,
        timeout=10,
    )
    time.sleep(10)

    # Check for license dialog and accept it
    img, png = screenshot_and_push(vnc_addr)
    b64 = base64.b64encode(png).decode()
    license_check = ask_sonnet_verify(
        ai,
        b64,
        "Is there a license agreement dialog visible? Look for 'I Accept' or 'License' text. "
        "Set ok=true if you see a license dialog.",
    )
    if license_check.get("ok"):
        push_log("  License dialog — accepting...")
        coords = ask_sonnet_coords(ai, b64, "'I Accept' button")
        if coords:
            vnc_click(vnc_addr, coords[0], coords[1])
            time.sleep(5)

    # Final check after SSH activation
    for _wait in range(3):
        time.sleep(5)
        img, png = screenshot_and_push(vnc_addr)
        b64 = base64.b64encode(png).decode()
        result = ask_sonnet_verify(ai, b64, "Is Bruker TopSpin 5.0 open and visible?")
        if result.get("ok"):
            push_log("  ✓ TopSpin opened via SSH")
            return True

    push_log("  ✗ Could not open TopSpin")
    return False


def step_load_dataset(vnc_addr: str, ai: OpenAI) -> bool:
    """Load NMR dataset using 're' command."""
    push_log("▶ Load Dataset", status="operating")

    vnc_type_command(vnc_addr, f"re {DATASET}")
    time.sleep(5)

    img, png = screenshot_and_push(vnc_addr)
    b64 = base64.b64encode(png).decode()

    result = ask_sonnet_verify(
        ai,
        b64,
        "Has NMR data been loaded? Look for: a spectrum plot (FID or frequency domain) "
        "in the main panel, OR a molecular structure in the structure panel, OR dataset "
        "info in the title area. 'No structure available' alone does NOT mean failure.",
    )
    if result.get("ok"):
        push_log(f"  ✓ Dataset loaded: {result.get('description', '')}")
        return True

    push_log(f"  ⚠ Load unclear: {result.get('description', '')}")
    # Try again — might need to wait longer
    time.sleep(5)
    img, png = screenshot_and_push(vnc_addr)
    b64 = base64.b64encode(png).decode()
    result = ask_sonnet_verify(ai, b64, "Is there ANY spectrum or data displayed in TopSpin now?")
    ok = result.get("ok", False)
    push_log(f"  {'✓' if ok else '✗'} Retry: {result.get('description', '')}")
    return ok


def step_run_command(
    vnc_addr: str,
    ai: OpenAI,
    cmd: str,
    step_name: str,
    verify_prompt: str,
    handle_dialog: bool = False,
) -> bool:
    """Run a TopSpin command and verify the result."""
    push_log(f"▶ {step_name}", status="operating")

    vnc_type_command(vnc_addr, cmd)
    time.sleep(3)

    img, png = screenshot_and_push(vnc_addr)
    b64 = base64.b64encode(png).decode()

    if handle_dialog:
        # Dismiss dialogs in a loop (nested errors may require multiple rounds)
        for _dlg in range(3):
            dialog_check = ask_sonnet_verify(
                ai,
                b64,
                "Is there a dialog/popup window visible in the CENTER of the screen? "
                "NOT a macOS notification in the corner. Set ok=true ONLY for centered "
                "dialogs with Close/OK/Cancel buttons.",
            )
            if not dialog_check.get("ok"):
                break
            push_log(f"  Dialog detected: {dialog_check.get('description', '')}")
            # Press Return to accept/close (more reliable than clicking OK)
            vnc_key(vnc_addr, "return")
            time.sleep(3)
            img, png = screenshot_and_push(vnc_addr)
            b64 = base64.b64encode(png).decode()
            push_log("  Accepted dialog with Return")

    result = ask_sonnet_verify(ai, b64, verify_prompt)
    ok = result.get("ok", False)
    push_log(f"  {'✓' if ok else '⚠'} {step_name}: {result.get('description', '')}")
    return ok


def step_verify_result(vnc_addr: str, ai: OpenAI) -> bool:
    """Final verification — ask Sonnet to describe what it sees."""
    push_log("▶ Verify Result", status="operating")

    img, png = screenshot_and_push(vnc_addr)
    b64 = base64.b64encode(png).decode()

    result = ask_sonnet_verify(
        ai,
        b64,
        "Describe the NMR spectrum visible in TopSpin. Report ok=true if you can see: "
        "(1) NMR peaks visible in the spectrum display area, "
        "(2) a chemical shift axis (ppm scale) at the bottom, "
        "(3) any peak annotations or red markers in the spectrum area. "
        "Ignore any error dialogs — focus only on the spectrum itself. "
        "A dense pattern of red markers across the top IS valid peak picking output.",
    )
    ok = result.get("ok", False)
    push_log(f"  {'✓' if ok else '⚠'} Final: {result.get('description', '')}")
    return ok


# ── Main ────────────────────────────────────────

# Module-level VM IP (set during main)
_VM_IP: str = ""


def main() -> int:
    global _VM_IP

    print(
        f"\n{B}═══════════════════════════════════════════════{RST}\n"
        f"{B}  AI NMR Experiment — Tart VNC + Sonnet 4.6{RST}\n"
        f"{D}  VM: {VM_NAME} (ARD auth){RST}\n"
        f"{D}  Watch at {LABWORK_URL} → Live VM tab{RST}\n"
        f"{B}═══════════════════════════════════════════════{RST}\n"
    )

    # API key
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        # Try reading from labwork-web .env
        env_path = os.path.join(os.path.dirname(__file__), "..", "..", "labwork-web", ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("OPENROUTER_API_KEY="):
                        api_key = line.strip().split("=", 1)[1]
                        break
    if not api_key:
        print(f"  {R}✗ OPENROUTER_API_KEY not set{RST}")
        return 1

    ai = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    # Get VNC info from tart
    print("  Getting VNC info from tart...")
    try:
        vnc_addr, _VM_IP = get_vnc_info()
        print(f"  {G}✓ VNC: {vnc_addr} (ARD auth: {VM_USER}){RST}")
    except Exception as e:
        print(f"  {R}✗ {e}{RST}")
        return 1

    # Test VNC connection
    push_log("Testing VNC connection...", status="connecting")
    try:
        img, png = screenshot_and_push(vnc_addr)
        push_log(f"✓ VNC connected ({img.size[0]}x{img.size[1]}, {len(png) // 1024}KB)")
    except Exception as e:
        push_log(f"✗ VNC connection failed: {e}", status="idle")
        return 1

    # Release stuck modifiers / fix caps lock
    vnc_release_modifiers(vnc_addr)
    time.sleep(0.5)

    # Test typing and detect caps lock state
    push_log("Testing keyboard input...")
    c = vnc_connect(vnc_addr)
    c.mouseMove(CMD_X, CMD_Y)
    time.sleep(0.1)
    c.mousePress(1)
    time.sleep(0.3)
    for ch in "abc":
        c.keyPress(ch)
        time.sleep(0.03)
    safe_disconnect(c)
    time.sleep(0.5)
    img, png = screenshot_and_push(vnc_addr)

    # Check if caps lock is on by analyzing the command line text
    crop = img.crop((0, 930, 700, 990))
    crop.save("/tmp/vnc_kbd_test.png")
    b64_test = base64.b64encode(png).decode()
    caps_check = ask_sonnet_verify(
        ai,
        b64_test,
        "Look at the command line text field at the very bottom of the window. "
        "Does it contain 'abc' (lowercase) or 'ABC' (uppercase)? "
        "Set ok=true if lowercase 'abc', ok=false if uppercase 'ABC'.",
    )
    if not caps_check.get("ok"):
        push_log("  Caps lock detected — toggling off")
        vnc_key(vnc_addr, "caplk")
        time.sleep(0.3)
    push_log("✓ Keyboard input OK")

    # Clear the test text
    c = vnc_connect(vnc_addr)
    c.mouseMove(CMD_X, CMD_Y)
    time.sleep(0.1)
    c.mousePress(1)
    time.sleep(0.05)
    c.mousePress(1)
    time.sleep(0.05)
    c.mousePress(1)
    time.sleep(0.2)
    c.keyPress("bsp")
    time.sleep(0.2)
    safe_disconnect(c)

    # Close any visible error/license dialogs before starting pipeline
    for _dismiss in range(5):
        time.sleep(0.5)
        img, png = screenshot_and_push(vnc_addr)
        b64 = base64.b64encode(png).decode()
        dialog_check = ask_sonnet_verify(
            ai,
            b64,
            "Is there an error dialog, warning popup, license dialog, or modal window visible? "
            "NOT a regular application window and NOT a macOS notification banner in the corner. "
            "Set ok=true ONLY if you see a centered popup/dialog with Close/OK/Cancel/Accept buttons.",
        )
        if not dialog_check.get("ok"):
            break
        desc = dialog_check.get("description", "")
        push_log(f"  Dismissing dialog (round {_dismiss + 1}): {desc[:80]}")
        # License dialogs need "I Accept" clicked; error dialogs use Return
        if "license" in desc.lower() or "accept" in desc.lower():
            coords = ask_sonnet_coords(ai, b64, "'I Accept' or 'Accept' button")
            if coords:
                vnc_click(vnc_addr, coords[0], coords[1])
                time.sleep(3)
                screenshot_and_push(vnc_addr)
                continue
        vnc_key(vnc_addr, "return")
        time.sleep(1)
        screenshot_and_push(vnc_addr)

    # ── Pipeline ──
    t_total = time.monotonic()
    results: list[tuple[str, bool]] = []

    # Step 1: Open TopSpin
    ok = step_open_topspin(vnc_addr, ai)
    results.append(("Open TopSpin", ok))
    if not ok:
        push_log("✗ Critical: TopSpin not available — aborting", status="done")
        return 1

    # Step 2: Load Dataset
    ok = step_load_dataset(vnc_addr, ai)
    results.append(("Load Dataset", ok))
    if not ok:
        push_log("✗ Critical: Dataset load failed — aborting", status="done")
        return 1
    time.sleep(2)

    # Step 3: Fourier Transform (efp)
    ok = step_run_command(
        vnc_addr,
        ai,
        cmd="efp",
        step_name="Fourier Transform",
        verify_prompt="Has the spectrum changed after Fourier transform? Look for frequency-domain peaks.",
    )
    results.append(("Fourier Transform", ok))
    time.sleep(2)

    # Step 4: Phase Correction (apk) — may show error dialog on some data
    ok = step_run_command(
        vnc_addr,
        ai,
        cmd="apk",
        step_name="Phase Correction",
        verify_prompt="Has automatic phase correction been applied? Peaks should be upright and baseline flat.",
        handle_dialog=True,
    )
    results.append(("Phase Correction", ok))
    time.sleep(2)

    # Step 5: Peak Picking (pp) — may show dialog
    ok = step_run_command(
        vnc_addr,
        ai,
        cmd="pp",
        step_name="Peak Picking",
        verify_prompt="Are peak annotations/labels visible on the spectrum? Look for red markers or numbers above peaks.",
        handle_dialog=True,
    )
    results.append(("Peak Picking", ok))
    time.sleep(2)

    # Step 6: Verify final result
    ok = step_verify_result(vnc_addr, ai)
    results.append(("Verify Result", ok))

    # Summary
    dt = time.monotonic() - t_total
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    icon = "✓" if passed == total else "⚠"
    summary = f"{icon} {passed}/{total} steps in {dt:.0f}s"
    push_log(summary, status="done")

    # Save final screenshot
    final_path = "/tmp/vnc_demo_final.png"
    vnc_screenshot(vnc_addr, final_path)
    push_log(f"Final screenshot: {final_path}")

    print(f"\n{B}{'─' * 47}{RST}")
    for name, ok in results:
        print(f"  {G + '✓' if ok else Y + '⚠'} {name}{RST}")
    print(f"{B}{'─' * 47}{RST}")
    print(f"{B}{summary}{RST}\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n  {R}Interrupted{RST}")
        sys.exit(130)
