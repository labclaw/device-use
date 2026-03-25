#!/usr/bin/env python3
"""AI operates TopSpin in Tart VM via VNC + Sonnet 4.6.

Uses vncdo CLI for screenshots, mouse clicks, and keyboard input (ARD auth).
CUA REST API is used only for shell commands (launching apps, killing processes).
CUA keyboard/mouse don't work for Java/Swing apps on macOS VMs.

Sonnet 4.6 (via OpenRouter) verifies each step via screenshot analysis.
Each frame is pushed to labwork-web as MJPEG stream for live viewing.

Framebuffer: 2048x1536 (retina @2x for 1024x768 VM display).
VNC mouse input is in framebuffer coords (2048x1536).

Usage:
    # 1. Start VM:    tart run topspin-sequoia --no-graphics --vnc-experimental &
    # 2. Start CUA:   (on VM) cua-computer-server &
    # 3. Start web:   cd labwork-web && uvicorn app:app --port 8430
    # 4. Run demo:    python demos/22_vm_demo.py
    # 5. Watch:       open http://localhost:8430 -> Live VM tab
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import subprocess
import sys
import time

import httpx
from openai import OpenAI
from PIL import Image

# ── Config ──────────────────────────────────────
VM_IP = os.environ.get("VM_IP", "10.0.0.1")
VNC_USER = os.environ.get("VNC_USER", "changeme")
VNC_PASS = os.environ.get("VNC_PASS", "changeme")
CUA_URL = f"http://{VM_IP}:8000/cmd"  # For run_command only
MODEL = "anthropic/claude-sonnet-4.6"
LABWORK_URL = os.environ.get("LABWORK_URL", "http://localhost:8430")
DATASET = os.environ.get(
    "TOPSPIN_DATASET",
    "/opt/topspin5.0.0/examdata/exam_CMCse_1/1",
)

# TopSpin command line position (framebuffer coords, 2048x1536)
CMD_X, CMD_Y = 200, 960

B = "\033[1m"
G = "\033[32m"
C = "\033[36m"
D = "\033[2m"
R = "\033[31m"
Y = "\033[33m"
RST = "\033[0m"


# ── VNC helpers (via vncdo CLI) ─────────────────


def _vncdo(*args: str, timeout: int = 15) -> subprocess.CompletedProcess:
    """Run vncdo command with ARD auth credentials."""
    cmd = [
        sys.executable.replace("python", "vncdo").replace(
            "bin/python",
            "bin/vncdo",
        ),
        "-s",
        VM_IP,
        "--username",
        VNC_USER,
        "--password",
        VNC_PASS,
        *args,
    ]
    # Fallback: find vncdo next to python
    if not os.path.exists(cmd[0]):
        venv_bin = os.path.dirname(sys.executable)
        cmd[0] = os.path.join(venv_bin, "vncdo")
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def vnc_screenshot(path: str = "/tmp/vnc_frame.png") -> Image.Image:
    """Take a VNC screenshot, return PIL Image."""
    _vncdo("capture", path)
    return Image.open(path)


def vnc_click(x: int, y: int) -> None:
    """Click at framebuffer coordinates (2048x1536)."""
    _vncdo("move", str(x), str(y), "pause", "0.1", "click", "1")


def vnc_type_text(text: str) -> None:
    """Type text character by character via VNC."""
    _vncdo("type", text)


def vnc_key(key: str) -> None:
    """Press a named key: return, tab, esc, bsp, space, etc."""
    _vncdo("key", key)


def vnc_type_command(cmd: str) -> None:
    """Triple-click TopSpin command line, type command, press Return.

    All input goes through VNC (mouse clicks, typing, Return key).
    CUA keyboard doesn't reach Java/Swing apps in macOS VMs.
    """
    # Triple-click to select all text in command line, then type + Return
    _vncdo(
        "move",
        str(CMD_X),
        str(CMD_Y),
        "pause",
        "0.2",
        "click",
        "1",
        "pause",
        "0.05",
        "click",
        "1",
        "pause",
        "0.05",
        "click",
        "1",
        "pause",
        "0.3",
        "type",
        cmd,
        "pause",
        "0.3",
        "key",
        "return",
    )


# ── CUA helpers (shell commands only) ─────────────
#
# CUA keyboard/mouse don't reach Java/Swing apps in macOS VMs.
# We only use CUA for run_command (launching apps, killing processes).


def _cua_cmd(command: str, params: dict | None = None) -> dict:
    """Send a command to CUA server, return parsed response."""
    body: dict = {"command": command}
    if params:
        body["params"] = params
    resp = httpx.post(CUA_URL, json=body, timeout=30)
    # CUA returns SSE format: "data: {...}"
    for line in resp.text.strip().splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    return json.loads(resp.text.strip())


def cua_run(command: str) -> dict:
    """Run a shell command in the VM via CUA REST API."""
    return _cua_cmd("run_command", {"command": command})


# ── Stream helpers ──────────────────────────────


def push_frame(jpeg_bytes: bytes) -> None:
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


def push_log(text: str, status: str | None = None) -> None:
    """Push a log line to labwork-web."""
    data: dict = {"text": text}
    if status:
        data["status"] = status
    try:
        httpx.post(f"{LABWORK_URL}/vm/log", json=data, timeout=2)
    except Exception:
        pass
    print(f"  {D}{text}{RST}")


def screenshot_and_push() -> tuple[str, bytes]:
    """Take VNC screenshot, resize, push JPEG, return (b64, png_bytes)."""
    img = vnc_screenshot()

    # Push JPEG for live stream
    buf_jpg = io.BytesIO()
    img.convert("RGB").save(buf_jpg, format="JPEG", quality=75)
    push_frame(buf_jpg.getvalue())

    # Resize to 1280x960 for VLM (under 5MB limit)
    img_small = img.convert("RGB").resize((1280, 960), Image.LANCZOS)
    buf_png = io.BytesIO()
    img_small.save(buf_png, format="PNG", optimize=True)
    png_bytes = buf_png.getvalue()
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return b64, png_bytes


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
                        "image_url": {
                            "url": f"data:image/png;base64,{screenshot_b64}",
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "This is a 1280x960 screenshot of macOS with "
                            "Bruker TopSpin 5.0 NMR software.\n"
                            f"{question}\n\n"
                            "Return ONLY JSON, no markdown fences."
                        ),
                    },
                ],
            }
        ],
    )
    return response.choices[0].message.content.strip()


def ask_verify(
    client: OpenAI,
    screenshot_b64: str,
    check: str,
) -> dict:
    """Ask Sonnet to verify a condition."""
    text = ask_sonnet(
        client,
        screenshot_b64,
        f'{check}\nReturn: {{"ok": true/false, "description": "what you see"}}',
    )
    m = re.search(r"\{[^}]+\}", text)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {"ok": False, "description": text[:200]}


# ── Pipeline Steps ──────────────────────────────


def step_ensure_topspin(ai: OpenAI) -> bool:
    """Ensure TopSpin is open and visible."""
    push_log(">>> Ensure TopSpin visible", status="operating")

    # Kill any stale notification dialogs
    cua_run("pkill -9 UserNotificationCenter 2>/dev/null")

    b64, _ = screenshot_and_push()
    result = ask_verify(
        ai,
        b64,
        "Is Bruker TopSpin 5.0 open with its main window visible? "
        "Look for the TopSpin toolbar, spectrum area, and command line.",
    )
    if result.get("ok"):
        push_log(f"  OK TopSpin visible: {result.get('description', '')}")
        return True

    # TopSpin not visible -- try launching it
    push_log("  TopSpin not visible, launching...")
    cua_run("pkill -9 java 2>/dev/null")
    time.sleep(3)
    cua_run('open "/Applications/TopSpin 5.0.0.app"')
    time.sleep(45)  # TopSpin takes ~30-40s to start in VM

    # Kill notification dialogs that appear during startup
    cua_run("pkill -9 UserNotificationCenter 2>/dev/null")
    time.sleep(3)

    b64, _ = screenshot_and_push()
    result = ask_verify(ai, b64, "Is TopSpin now visible?")
    ok = result.get("ok", False)
    push_log(f"  {'OK' if ok else 'FAIL'} {result.get('description', '')}")
    return ok


def step_load_dataset(ai: OpenAI) -> bool:
    """Load NMR dataset using 're' command."""
    push_log(">>> Load Dataset", status="operating")

    vnc_type_command(f"re {DATASET}")
    time.sleep(5)

    b64, _ = screenshot_and_push()
    result = ask_verify(
        ai,
        b64,
        "Has NMR data been loaded? Look for a spectrum plot "
        "(FID or frequency domain) in the main panel, OR dataset "
        "info in the title area.",
    )
    if result.get("ok"):
        push_log(f"  OK Dataset loaded: {result.get('description', '')}")
        return True

    # Retry with longer wait
    push_log("  Waiting longer...")
    time.sleep(5)
    b64, _ = screenshot_and_push()
    result = ask_verify(
        ai,
        b64,
        "Is there ANY spectrum or data displayed in TopSpin?",
    )
    ok = result.get("ok", False)
    push_log(f"  {'OK' if ok else 'WARN'} {result.get('description', '')}")
    return ok


def step_run_command(
    ai: OpenAI,
    cmd: str,
    step_name: str,
    verify_prompt: str,
    handle_dialog: bool = False,
) -> bool:
    """Run a TopSpin command and verify the result."""
    push_log(f">>> {step_name}", status="operating")

    vnc_type_command(cmd)
    time.sleep(3)

    b64, _ = screenshot_and_push()

    if handle_dialog:
        for _dlg in range(3):
            dlg = ask_verify(
                ai,
                b64,
                "Is there a dialog/popup window visible in the CENTER? "
                "NOT a notification. Set ok=true ONLY for centered "
                "dialogs with Close/OK/Cancel buttons.",
            )
            if not dlg.get("ok"):
                break
            push_log(f"  Dialog: {dlg.get('description', '')[:60]}")
            vnc_key("return")
            time.sleep(3)
            b64, _ = screenshot_and_push()

    result = ask_verify(ai, b64, verify_prompt)
    ok = result.get("ok", False)
    push_log(
        f"  {'OK' if ok else 'WARN'} {step_name}: {result.get('description', '')}",
    )
    return ok


def step_verify_result(ai: OpenAI) -> bool:
    """Final verification of the NMR spectrum."""
    push_log(">>> Verify Result", status="operating")

    b64, _ = screenshot_and_push()
    result = ask_verify(
        ai,
        b64,
        "Describe the NMR spectrum visible in TopSpin. Report ok=true "
        "if you can see: (1) NMR peaks in the spectrum display, "
        "(2) a chemical shift axis (ppm) at the bottom, "
        "(3) any peak annotations or markers. "
        "Ignore error dialogs -- focus on the spectrum itself.",
    )
    ok = result.get("ok", False)
    push_log(f"  {'OK' if ok else 'WARN'} Final: {result.get('description', '')}")
    return ok


# ── Main ────────────────────────────────────────


def main() -> int:
    print(
        f"\n{B}{'=' * 55}{RST}\n"
        f"{B}  AI NMR Experiment -- VNC + Sonnet 4.6{RST}\n"
        f"{D}  VM: {VM_IP}  |  VNC: {VM_IP}:5900{RST}\n"
        f"{D}  Watch at {LABWORK_URL} -> Live VM tab{RST}\n"
        f"{B}{'=' * 55}{RST}\n"
    )

    # API key
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        env_path = os.path.join(
            os.path.dirname(__file__),
            "..",
            "..",
            "labwork-web",
            ".env",
        )
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("OPENROUTER_API_KEY="):
                        api_key = line.strip().split("=", 1)[1]
                        break
    if not api_key:
        print(f"  {R}FAIL OPENROUTER_API_KEY not set{RST}")
        return 1

    ai = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    # Test VNC connection
    print("  Testing VNC connection...")
    try:
        img = vnc_screenshot()
        print(f"  {G}OK VNC: {img.size[0]}x{img.size[1]}{RST}")
    except Exception as e:
        print(f"  {R}FAIL VNC: {e}{RST}")
        return 1

    # Kill stale notification dialogs from previous sessions
    try:
        cua_run("pkill -9 UserNotificationCenter 2>/dev/null")
    except Exception:
        pass  # CUA server might not be running

    push_log("Starting pipeline...", status="connecting")

    # ── Pipeline ──
    t_total = time.monotonic()
    results: list[tuple[str, bool]] = []

    # Step 1: Ensure TopSpin visible
    ok = step_ensure_topspin(ai)
    results.append(("Open TopSpin", ok))
    if not ok:
        push_log("FAIL Critical: TopSpin not available", status="done")
        return 1

    # Step 2: Load Dataset
    ok = step_load_dataset(ai)
    results.append(("Load Dataset", ok))
    if not ok:
        push_log("FAIL Critical: Dataset load failed", status="done")
        return 1
    time.sleep(2)

    # Step 3: Fourier Transform (efp)
    ok = step_run_command(
        ai,
        cmd="efp",
        step_name="Fourier Transform",
        verify_prompt=(
            "Has the spectrum changed after Fourier transform? Look for frequency-domain peaks."
        ),
    )
    results.append(("Fourier Transform", ok))
    time.sleep(2)

    # Step 4: Phase Correction (apk)
    ok = step_run_command(
        ai,
        cmd="apk",
        step_name="Phase Correction",
        verify_prompt=(
            "Has automatic phase correction been applied? "
            "Peaks should be upright and baseline flat."
        ),
        handle_dialog=True,
    )
    results.append(("Phase Correction", ok))
    time.sleep(2)

    # Step 5: Peak Picking (pp)
    ok = step_run_command(
        ai,
        cmd="pp",
        step_name="Peak Picking",
        verify_prompt=(
            "Are peak annotations/labels visible on the spectrum? "
            "Look for red markers or numbers above peaks."
        ),
        handle_dialog=True,
    )
    results.append(("Peak Picking", ok))
    time.sleep(2)

    # Step 6: Verify final result
    ok = step_verify_result(ai)
    results.append(("Verify Result", ok))

    # Save final screenshot
    vnc_screenshot("/tmp/vm_demo_final.png")

    # Summary
    dt = time.monotonic() - t_total
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    icon = "OK" if passed == total else "WARN"
    summary = f"{icon} {passed}/{total} steps in {dt:.0f}s"
    push_log(summary, status="done")

    print(f"\n{B}{'=' * 55}{RST}")
    for name, ok in results:
        status = f"{G}OK{RST}" if ok else f"{Y}WARN{RST}"
        print(f"  {status} {name}")
    print(f"{B}{'=' * 55}{RST}")
    print(f"{B}{summary}{RST}")
    print(f"{D}Final screenshot: /tmp/vm_demo_final.png{RST}\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n  {R}Interrupted{RST}")
        sys.exit(130)
