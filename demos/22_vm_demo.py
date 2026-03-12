#!/usr/bin/env python3
"""AI operates TopSpin in Lume VM — streams to labwork-web.

Connects to a Lume macOS VM running TopSpin, uses Sonnet 4.6 (via OpenRouter)
to analyze screenshots and decide actions. Each frame is pushed to labwork-web
as MJPEG stream for live viewing.

Usage:
    # 1. Start VM:   lume run topspin-vm --vnc-port 5900
    # 2. Start web:  cd labwork-web && uvicorn app:app --port 8430
    # 3. Run demo:   python demos/22_vm_demo.py
    # 4. Watch:      open http://localhost:8430 → Live VM tab
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import sys
import time

import httpx
from openai import OpenAI

# ── Config ──────────────────────────────────────
VM_NAME = os.environ.get("VM_NAME", "topspin-vm")
DATASET = "/opt/topspin5.0.0/examdata/exam_CMCse_1/1"
MODEL = "anthropic/claude-sonnet-4"
LABWORK_URL = os.environ.get("LABWORK_URL", "http://localhost:8430")

B = "\033[1m"
G = "\033[32m"
C = "\033[36m"
D = "\033[2m"
R = "\033[31m"
RST = "\033[0m"


# ── Helpers ─────────────────────────────────────

async def push_frame(jpeg_bytes: bytes):
    """Push a JPEG frame to labwork-web MJPEG stream."""
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{LABWORK_URL}/vm/frame",
                content=jpeg_bytes,
                headers={"Content-Type": "image/jpeg"},
                timeout=2,
            )
        except Exception:
            pass


async def push_log(text: str, status: str | None = None):
    """Push a log line to labwork-web."""
    data: dict = {"text": text}
    if status:
        data["status"] = status
    async with httpx.AsyncClient() as client:
        try:
            await client.post(f"{LABWORK_URL}/vm/log", json=data, timeout=2)
        except Exception:
            pass
    print(f"  {D}{text}{RST}")


async def screenshot_and_push(computer) -> bytes:
    """Take screenshot, push to stream, return PNG bytes."""
    img = await computer.interface.screenshot()
    # JPEG for stream
    buf_jpg = io.BytesIO()
    img.save(buf_jpg, format="JPEG", quality=75)
    await push_frame(buf_jpg.getvalue())
    # PNG for VLM (better quality)
    buf_png = io.BytesIO()
    img.save(buf_png, format="PNG")
    return buf_png.getvalue()


def ask_sonnet(client: OpenAI, screenshot_b64: str, instruction: str) -> list[dict]:
    """Send screenshot + instruction to Sonnet 4.6, get back actions."""
    response = client.chat.completions.create(
        model=MODEL,
        max_tokens=1024,
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
                            "You are controlling Bruker TopSpin 5.0 NMR software on macOS.\n"
                            f"Current task: {instruction}\n\n"
                            "Reply with a JSON array of actions. Each action:\n"
                            '- {"type":"click","x":<int>,"y":<int>}\n'
                            '- {"type":"type","text":"<string>"}\n'
                            '- {"type":"key","key":"Return"}\n'
                            '- {"type":"wait","seconds":<int>}\n'
                            '- {"type":"done","status":"<what you see>"}\n\n'
                            "If the task is already complete, return "
                            '[{"type":"done","status":"..."}].\n'
                            "Return ONLY the JSON array, no markdown fences."
                        ),
                    },
                ],
            }
        ],
    )
    text = response.choices[0].message.content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return json.loads(text)


async def execute_action(computer, action: dict):
    """Execute one CUA action on the VM."""
    t = action.get("type", "")
    if t == "click":
        await computer.interface.left_click(action["x"], action["y"])
    elif t == "type":
        await computer.interface.type_text(action["text"])
    elif t == "key":
        await computer.interface.key(action["key"])
    elif t == "wait":
        await asyncio.sleep(action.get("seconds", 2))


async def run_step(
    computer,
    client: OpenAI,
    instruction: str,
    step_name: str,
    max_rounds: int = 8,
) -> bool:
    """Run one step with VLM screenshot-action loop."""
    await push_log(f"▶ {step_name}", status="operating")
    t0 = time.monotonic()

    for rnd in range(max_rounds):
        png = await screenshot_and_push(computer)
        b64 = base64.b64encode(png).decode()

        try:
            actions = ask_sonnet(client, b64, instruction)
        except Exception as e:
            await push_log(f"  VLM error: {e}")
            return False

        await push_log(f"  Round {rnd + 1}: {len(actions)} action(s)")

        for action in actions:
            if action.get("type") == "done":
                dt = time.monotonic() - t0
                status = action.get("status", "done")
                await push_log(f"  ✓ {step_name} ({dt:.1f}s): {status}")
                await screenshot_and_push(computer)
                return True

            await execute_action(computer, action)
            await asyncio.sleep(0.5)
            await screenshot_and_push(computer)

    await push_log(f"  ⚠ {step_name}: max rounds reached")
    return False


# ── Main ────────────────────────────────────────

async def main() -> int:
    print(
        f"\n{B}═══════════════════════════════════════════════{RST}\n"
        f"{B}  AI NMR Experiment — Lume VM + Sonnet 4.6{RST}\n"
        f"{D}  Watch at {LABWORK_URL} → Live VM tab{RST}\n"
        f"{B}═══════════════════════════════════════════════{RST}\n"
    )

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print(f"  {R}✗ OPENROUTER_API_KEY not set{RST}")
        return 1

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    # Connect to VM
    await push_log("Connecting to VM...", status="connecting")
    try:
        from computer import Computer

        computer = Computer(os_type="macos", name=VM_NAME)
        await computer.run()
    except Exception as e:
        await push_log(f"✗ VM connection failed: {e}", status="idle")
        return 1
    await push_log("✓ Connected to VM")

    await screenshot_and_push(computer)

    # Pipeline
    steps = [
        (
            "Open TopSpin",
            "Open the TopSpin application. It may already be open — check the Dock.",
        ),
        (
            "Load Dataset",
            f"Click on the command line at the bottom of TopSpin, "
            f"type 're {DATASET}' and press Return.",
        ),
        (
            "Fourier Transform",
            "Click the command line, type 'efp' and press Return. "
            "Wait for it to finish.",
        ),
        (
            "Phase Correction",
            "Click the command line, type 'apk' and press Return. "
            "Wait for it to finish.",
        ),
        (
            "Peak Picking",
            "Click the command line, type 'pp' and press Return. "
            "If a dialog appears, press Return to accept defaults.",
        ),
        (
            "Verify Result",
            "Look at the spectrum. Is it a clean 1H NMR spectrum with peaks? "
            "Report what you see.",
        ),
    ]

    t_total = time.monotonic()
    results: list[tuple[str, bool]] = []

    for name, instruction in steps:
        ok = await run_step(computer, client, instruction, name)
        results.append((name, ok))
        if not ok and name in ("Open TopSpin", "Load Dataset"):
            await push_log(
                f"✗ Critical failure at '{name}' — aborting", status="done"
            )
            break
        await asyncio.sleep(1)

    dt = time.monotonic() - t_total
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    icon = "✓" if passed == total else "⚠"
    summary = f"{icon} {passed}/{total} steps in {dt:.0f}s"
    await push_log(summary, status="done")

    print(f"\n{B}{summary}{RST}\n")
    await computer.stop()
    return 0 if passed == total else 1


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print(f"\n  {R}Interrupted{RST}")
        sys.exit(130)
