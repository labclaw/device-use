#!/usr/bin/env python3
"""Quick CUA test — verify screenshot + Sonnet 4.6 action loop on VM.

Tests:
  1. Connect to VM via CUA SDK
  2. Take screenshot
  3. Send to Sonnet 4.6 via OpenRouter
  4. Execute returned action
  5. Take another screenshot to verify
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import sys
import time

from openai import OpenAI

VM_NAME = os.environ.get("VM_NAME", "topspin-vm")
MODEL = "anthropic/claude-sonnet-4.6"

B = "\033[1m"
G = "\033[32m"
R = "\033[31m"
D = "\033[2m"
RST = "\033[0m"


async def main():
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print(f"{R}✗ OPENROUTER_API_KEY not set{RST}")
        return 1

    client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    # Step 1: Connect to VM
    print(f"\n{B}=== CUA Basic Test ==={RST}\n")
    print(f"  {D}VM: {VM_NAME}{RST}")
    print(f"  {D}Model: {MODEL}{RST}\n")

    print(f"  1. Connecting to VM...")
    try:
        from computer import Computer
        computer = Computer(os_type="macos", name=VM_NAME)
        await computer.run()
        print(f"  {G}✓ Connected{RST}")
    except Exception as e:
        print(f"  {R}✗ Connection failed: {e}{RST}")
        return 1

    # Step 2: Take screenshot
    print(f"  2. Taking screenshot...")
    try:
        img = await computer.interface.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        b64 = base64.b64encode(png_bytes).decode()
        print(f"  {G}✓ Screenshot: {img.size[0]}x{img.size[1]}, {len(png_bytes)//1024}KB{RST}")

        # Save locally for inspection
        img.save("/tmp/cua_test_screenshot.png")
        print(f"  {D}  Saved to /tmp/cua_test_screenshot.png{RST}")
    except Exception as e:
        print(f"  {R}✗ Screenshot failed: {e}{RST}")
        await computer.stop()
        return 1

    # Step 3: Send to Sonnet 4.6
    print(f"  3. Sending to Sonnet 4.6...")
    t0 = time.monotonic()
    try:
        response = client.chat.completions.create(
            model=MODEL,
            max_tokens=512,
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
                            "You are looking at a macOS desktop. "
                            "Describe what you see in 1-2 sentences. "
                            "Then suggest ONE simple action (click, type, or key) "
                            "as a JSON object like {\"type\":\"click\",\"x\":500,\"y\":300} "
                            "or {\"type\":\"done\",\"status\":\"description\"}.\n"
                            "Return ONLY the JSON, no markdown."
                        ),
                    },
                ],
            }],
        )
        dt = time.monotonic() - t0
        text = response.choices[0].message.content.strip()
        print(f"  {G}✓ Response ({dt:.1f}s):{RST}")
        print(f"  {D}  {text[:200]}{RST}")
    except Exception as e:
        print(f"  {R}✗ VLM error: {e}{RST}")
        await computer.stop()
        return 1

    # Step 4: Parse and execute action
    print(f"  4. Executing action...")
    try:
        # Extract JSON from response
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        # Find JSON object in text
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            action = json.loads(text[start:end])
        else:
            action = {"type": "done", "status": "no action parsed"}

        t = action.get("type", "")
        if t == "click":
            x, y = action["x"], action["y"]
            await computer.interface.left_click(x, y)
            print(f"  {G}✓ Clicked ({x}, {y}){RST}")
        elif t == "type":
            await computer.interface.type_text(action["text"])
            print(f"  {G}✓ Typed: {action['text']}{RST}")
        elif t == "key":
            await computer.interface.key(action["key"])
            print(f"  {G}✓ Key: {action['key']}{RST}")
        elif t == "done":
            print(f"  {G}✓ Done: {action.get('status', '')}{RST}")
        else:
            print(f"  {D}  Unknown action type: {t}{RST}")
    except Exception as e:
        print(f"  {R}✗ Action error: {e}{RST}")

    # Step 5: Final screenshot
    print(f"  5. Final screenshot...")
    try:
        await asyncio.sleep(1)
        img2 = await computer.interface.screenshot()
        img2.save("/tmp/cua_test_screenshot_after.png")
        print(f"  {G}✓ Saved to /tmp/cua_test_screenshot_after.png{RST}")
    except Exception as e:
        print(f"  {R}✗ {e}{RST}")

    await computer.stop()
    print(f"\n{B}{G}✓ CUA test complete{RST}\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print(f"\n{R}Interrupted{RST}")
        sys.exit(130)
