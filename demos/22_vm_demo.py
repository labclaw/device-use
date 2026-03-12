#!/usr/bin/env python3
"""AI operates TopSpin in Tart VM via CUA REST API.

Uses cua-computer-server running in the VM for screenshots and input.
Sonnet 4.6 (via OpenRouter) verifies each step via screenshot analysis.
Each frame is pushed to labwork-web as MJPEG stream for live viewing.

CUA Server API (SSE responses, prefix "data: "):
  POST http://<VM_IP>:8000/cmd
    {"command": "screenshot"}                         -> {"image_data": "<b64>"}
    {"command": "left_click", "params": {"x":N,"y":N}} -> {"success": true}
    {"command": "type_text", "params": {"text":"..."}}  -> {"success": true}
    {"command": "press_key", "params": {"key":"..."}}   -> {"success": true}
    {"command": "hotkey", "params": {"keys":["cmd","a"]}} -> {"success": true}
    {"command": "run_command", "params": {"command":"..."}} -> {"stdout":...}

Usage:
    # 1. Start VM:   tart run topspin-sequoia &
    # 2. Start CUA:  ssh admin@<IP> 'cua-computer-server &'
    # 3. Start web:  cd labwork-web && uvicorn app:app --port 8430
    # 4. Run demo:   python demos/22_vm_demo.py
    # 5. Watch:      open http://localhost:8430 -> Live VM tab
"""
from __future__ import annotations

import base64
import io
import json
import os
import re
import sys
import time

import httpx
from openai import OpenAI

# ── Config ──────────────────────────────────────
VM_IP = os.environ.get("VM_IP", "192.168.64.13")
CUA_URL = f"http://{VM_IP}:8000/cmd"
MODEL = "anthropic/claude-sonnet-4.6"
LABWORK_URL = os.environ.get("LABWORK_URL", "http://localhost:8430")
DATASET = os.environ.get(
    "TOPSPIN_DATASET",
    "/opt/topspin5.0.0/examdata/exam_CMCse_1/1",
)

# TopSpin command line position (logical coords for 1024x768 display)
CMD_X, CMD_Y = 100, 689

B = "\033[1m"
G = "\033[32m"
C = "\033[36m"
D = "\033[2m"
R = "\033[31m"
Y = "\033[33m"
RST = "\033[0m"


# ── CUA REST helpers ────────────────────────────

def cua_cmd(command: str, params: dict | None = None) -> dict:
    """Send a command to the CUA server, return parsed response."""
    body: dict = {"command": command}
    if params:
        body["params"] = params
    resp = httpx.post(CUA_URL, json=body, timeout=30)
    text = resp.text.strip()
    # SSE format: strip "data: " prefix
    if text.startswith("data: "):
        text = text[6:]
    return json.loads(text)


def cua_screenshot() -> tuple[str, bytes]:
    """Take screenshot via CUA, return (base64_str, png_bytes)."""
    result = cua_cmd("screenshot")
    if not result.get("success"):
        raise RuntimeError(f"Screenshot failed: {result.get('error')}")
    b64 = result["image_data"]
    return b64, base64.b64decode(b64)


def cua_click(x: int, y: int) -> None:
    """Click at logical coordinates."""
    cua_cmd("left_click", {"x": x, "y": y})


def cua_type(text: str) -> None:
    """Type text."""
    cua_cmd("type_text", {"text": text})


def cua_key(key: str) -> None:
    """Press a single key."""
    cua_cmd("press_key", {"key": key})


def cua_hotkey(keys: list[str]) -> None:
    """Press a key combination."""
    cua_cmd("hotkey", {"keys": keys})


def cua_run(command: str) -> dict:
    """Run a shell command in the VM."""
    return cua_cmd("run_command", {"command": command})


def cua_type_command(cmd: str) -> None:
    """Click TopSpin command line, select all, type command, press Return."""
    cua_click(CMD_X, CMD_Y)
    time.sleep(0.3)
    cua_hotkey(["command", "a"])
    time.sleep(0.1)
    cua_type(cmd)
    time.sleep(0.2)
    cua_key("return")


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
    """Take screenshot, push JPEG to stream, return (base64, png_bytes)."""
    b64, png_bytes = cua_screenshot()

    # Convert to JPEG for stream
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        push_frame(buf.getvalue())
    except ImportError:
        pass  # PIL not available — skip streaming

    return b64, png_bytes


# ── VLM ─────────────────────────────────────────

def ask_sonnet(client: OpenAI, screenshot_b64: str, question: str) -> str:
    """Send screenshot + question to Sonnet 4.6, get text response."""
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=512,
        messages=[{
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
                        "This is a 2048x1536 pixel screenshot of macOS with "
                        "Bruker TopSpin 5.0.\n"
                        f"{question}\n\n"
                        "Coordinates are in LOGICAL space (1024x768). "
                        "Return ONLY JSON, no markdown fences."
                    ),
                },
            ],
        }],
    )
    return response.choices[0].message.content.strip()


def ask_verify(
    client: OpenAI, screenshot_b64: str, check: str,
) -> dict:
    """Ask Sonnet to verify a condition. Returns {"ok": bool, "description": str}."""
    text = ask_sonnet(
        client, screenshot_b64,
        f'{check}\nReturn: {{"ok": true/false, "description": "what you see"}}',
    )
    m = re.search(r"\{[^}]+\}", text)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {"ok": False, "description": text[:200]}


def ask_coords(
    client: OpenAI, screenshot_b64: str, target: str,
) -> tuple[int, int] | None:
    """Ask Sonnet for coordinates of a UI element."""
    text = ask_sonnet(
        client, screenshot_b64,
        f'Find the "{target}" button/element. '
        f'Return: {{"x": N, "y": N}}',
    )
    mx = re.search(r'"x"\s*:\s*(\d+)', text)
    my = re.search(r'"y"\s*:\s*(\d+)', text)
    if mx and my:
        return int(mx.group(1)), int(my.group(1))
    return None


# ── Pipeline Steps ──────────────────────────────

def step_open_topspin(ai: OpenAI) -> bool:
    """Ensure TopSpin is open and visible."""
    push_log(">>> Open TopSpin", status="operating")

    b64, _ = screenshot_and_push()
    result = ask_verify(
        ai, b64,
        "Is Bruker TopSpin 5.0 open and visible? "
        "Look for the TopSpin window with toolbar, spectrum area, "
        "and command line.",
    )
    if result.get("ok"):
        push_log(f"  OK TopSpin already open: {result.get('description', '')}")
        return True

    # Activate via SSH osascript
    push_log("  TopSpin not visible, activating...")
    cua_run(
        "osascript -e 'tell application \"TopSpin 5.0.0\" to activate'"
    )
    time.sleep(5)

    b64, _ = screenshot_and_push()
    result = ask_verify(ai, b64, "Is TopSpin now visible?")
    if result.get("ok"):
        push_log("  OK TopSpin activated")
        return True

    # Try opening directly
    push_log("  Launching TopSpin app...")
    cua_run("open -a '/Applications/TopSpin 5.0.0.app'")
    time.sleep(15)

    # Dismiss any license/error dialogs
    for _ in range(3):
        b64, _ = screenshot_and_push()
        dlg = ask_verify(
            ai, b64,
            "Is there a dialog/popup with Close/OK/Cancel/Accept buttons? "
            "Set ok=true if yes.",
        )
        if not dlg.get("ok"):
            break
        desc = dlg.get("description", "")
        push_log(f"  Dismissing dialog: {desc[:60]}")
        if "license" in desc.lower() or "accept" in desc.lower():
            coords = ask_coords(ai, b64, "'I Accept' or 'Accept' button")
            if coords:
                cua_click(coords[0], coords[1])
                time.sleep(3)
                continue
        cua_key("return")
        time.sleep(2)

    b64, _ = screenshot_and_push()
    result = ask_verify(ai, b64, "Is TopSpin now visible?")
    ok = result.get("ok", False)
    push_log(f"  {'OK' if ok else 'FAIL'} TopSpin: {result.get('description', '')}")
    return ok


def step_load_dataset(ai: OpenAI) -> bool:
    """Load NMR dataset using 're' command."""
    push_log(">>> Load Dataset", status="operating")

    cua_type_command(f"re {DATASET}")
    time.sleep(5)

    b64, _ = screenshot_and_push()
    result = ask_verify(
        ai, b64,
        "Has NMR data been loaded? Look for: a spectrum plot "
        "(FID or frequency domain) in the main panel, OR dataset "
        "info in the title area.",
    )
    if result.get("ok"):
        push_log(f"  OK Dataset loaded: {result.get('description', '')}")
        return True

    # Retry with longer wait
    push_log("  Waiting longer for dataset...")
    time.sleep(5)
    b64, _ = screenshot_and_push()
    result = ask_verify(
        ai, b64, "Is there ANY spectrum or data displayed in TopSpin?",
    )
    ok = result.get("ok", False)
    push_log(f"  {'OK' if ok else 'WARN'} Retry: {result.get('description', '')}")
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

    cua_type_command(cmd)
    time.sleep(3)

    b64, _ = screenshot_and_push()

    if handle_dialog:
        for _dlg in range(3):
            dlg = ask_verify(
                ai, b64,
                "Is there a dialog/popup window visible in the CENTER? "
                "NOT a notification. Set ok=true ONLY for centered "
                "dialogs with Close/OK/Cancel buttons.",
            )
            if not dlg.get("ok"):
                break
            push_log(f"  Dialog: {dlg.get('description', '')[:60]}")
            cua_key("return")
            time.sleep(3)
            b64, _ = screenshot_and_push()
            push_log("  Accepted dialog with Return")

    result = ask_verify(ai, b64, verify_prompt)
    ok = result.get("ok", False)
    push_log(
        f"  {'OK' if ok else 'WARN'} {step_name}: "
        f"{result.get('description', '')}",
    )
    return ok


def step_verify_result(ai: OpenAI) -> bool:
    """Final verification of the NMR spectrum."""
    push_log(">>> Verify Result", status="operating")

    b64, _ = screenshot_and_push()
    result = ask_verify(
        ai, b64,
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
        f"{B}  AI NMR Experiment -- CUA + Sonnet 4.6{RST}\n"
        f"{D}  VM: {VM_IP}  |  CUA: {CUA_URL}{RST}\n"
        f"{D}  Watch at {LABWORK_URL} -> Live VM tab{RST}\n"
        f"{B}{'=' * 55}{RST}\n"
    )

    # API key
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        env_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "labwork-web", ".env",
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

    # Verify CUA server
    print("  Testing CUA connection...")
    try:
        result = cua_cmd("get_screen_size")
        size = result.get("size", {})
        print(
            f"  {G}OK CUA: {size.get('width')}x{size.get('height')}{RST}",
        )
    except Exception as e:
        print(f"  {R}FAIL CUA connection failed: {e}{RST}")
        return 1

    # Take initial screenshot
    push_log("Taking initial screenshot...", status="connecting")
    b64, png = screenshot_and_push()
    print(f"  {G}OK Screenshot: {len(png) // 1024}KB{RST}")

    # Save locally for inspection
    with open("/tmp/cua_vm_initial.png", "wb") as f:
        f.write(png)

    # ── Pipeline ──
    t_total = time.monotonic()
    results: list[tuple[str, bool]] = []

    # Step 1: Open TopSpin
    ok = step_open_topspin(ai)
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
            "Has the spectrum changed after Fourier transform? "
            "Look for frequency-domain peaks."
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
    _, final_png = screenshot_and_push()
    with open("/tmp/cua_vm_final.png", "wb") as f:
        f.write(final_png)

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
    print(f"{D}Screenshots: /tmp/cua_vm_initial.png, /tmp/cua_vm_final.png{RST}\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n  {R}Interrupted{RST}")
        sys.exit(130)
