"""
device-use Remote Agent Server

Lightweight FastAPI server that runs on Windows lab PCs.
Captures screenshots via mss, executes actions via pyautogui.
Exposes REST API over Tailscale for the Linux orchestrator.

Usage:
    python agent_server.py                    # default port 8421
    python agent_server.py --port 8422        # custom port
    python agent_server.py --password secret  # require auth header

Performance:
    Screenshot: ~30ms (mss native capture)
    Action:     ~10ms (pyautogui Win32 API)
    HTTP round-trip over Tailscale: ~6ms (direct) / ~180ms (relay)
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import logging
import platform
import threading
import time
import traceback
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    import mss
    import mss.tools
except ImportError:
    mss = None

try:
    import pyautogui

    pyautogui.FAILSAFE = False  # we do our own bounds checking
    pyautogui.PAUSE = 0.05
except ImportError:
    pyautogui = None

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
import uvicorn


app = FastAPI(title="device-use Remote Agent", version="0.2.0")

# Global config set at startup
_password: Optional[str] = None
_screen_w: int = 0
_screen_h: int = 0


def _init_screen_size():
    global _screen_w, _screen_h
    if pyautogui and _screen_w == 0:
        _screen_w, _screen_h = pyautogui.size()


def _check_auth(authorization: Optional[str] = Header(None)):
    if _password and authorization != f"Bearer {_password}":
        raise HTTPException(status_code=401, detail="Unauthorized")


def _clamp_coords(x: int, y: int) -> tuple[int, int]:
    """Clamp coordinates to screen bounds."""
    _init_screen_size()
    x = max(0, min(x, _screen_w - 1))
    y = max(0, min(y, _screen_h - 1))
    return x, y


# --- Models ---


class ClickRequest(BaseModel):
    x: int
    y: int
    button: str = "left"
    clicks: int = 1


class TypeRequest(BaseModel):
    text: str
    interval: float = 0.02


class HotkeyRequest(BaseModel):
    keys: list[str]


class ScrollRequest(BaseModel):
    x: int
    y: int
    clicks: int  # positive = up, negative = down


class MoveRequest(BaseModel):
    x: int
    y: int


class DragRequest(BaseModel):
    start_x: int
    start_y: int
    end_x: int
    end_y: int
    button: str = "left"
    duration: float = 0.3


class TaskRequest(BaseModel):
    goal: str
    model: str = "gpt-5.4"
    max_steps: int = 15
    display_width: int = 1280
    display_height: int = 800


# =====================================================================
# CU Loop Engine v2 — runs VLM calls locally on Windows
#
# Verified against official docs (2026-03-31):
#   OpenAI: https://developers.openai.com/docs/guides/tools-computer-use
#   Anthropic: https://platform.claude.com/docs/en/docs/agents-and-tools/computer-use
#
# Patterns from tested scripts:
#   GPT native CU: research/test_openephys_cu.py (3/3 success)
#   Claude native CU: research/test_sonnet46_native_cu.py (verified)
#   GPT FC fallback: research/test_gpt54_cu_loop.py (multi-tool fix)
# =====================================================================


def _capture_screenshot_b64(
    display_w: int = 1280, display_h: int = 800, fmt: str = "jpeg"
) -> tuple[str, int, int]:
    """Capture screen, resize, return (base64, native_w, native_h)."""
    _init_screen_size()
    with mss.mss() as sct:
        raw = sct.grab(sct.monitors[1])
    from PIL import Image

    img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
    native_w, native_h = img.size
    img = img.resize((display_w, display_h), Image.LANCZOS)

    buf = io.BytesIO()
    if fmt == "jpeg":
        img.save(buf, format="JPEG", quality=80)
    else:
        img.save(buf, format="PNG", optimize=False)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return b64, native_w, native_h


# --- Unified action executor ---
# Handles both OpenAI action format (type, x, y, keys, text)
# and Claude action format (action, coordinate, key, text)


_KEY_MAP = {
    "Return": "enter", "Escape": "escape", "Tab": "tab",
    "BackSpace": "backspace", "Delete": "delete", "space": "space",
    "super": "win", "Super_L": "win", "Home": "home", "End": "end",
    "Page_Up": "pageup", "Page_Down": "pagedown",
    "Up": "up", "Down": "down", "Left": "left", "Right": "right",
}


def _scale_xy(
    x: int, y: int,
    display_w: int, display_h: int,
    native_w: int, native_h: int,
) -> tuple[int, int]:
    """Scale coordinates from display space to native screen space."""
    return int(x * native_w / display_w), int(y * native_h / display_h)


def _execute_openai_action(
    action: dict[str, Any],
    display_w: int, display_h: int,
    native_w: int, native_h: int,
) -> str:
    """Execute an OpenAI computer_call action locally.

    Official action types (from docs):
    click, double_click, drag, move, scroll, keypress, type, wait, screenshot
    """
    action_type = action.get("type", "unknown")

    if action_type == "click":
        x, y = action.get("x", 0), action.get("y", 0)
        rx, ry = _scale_xy(x, y, display_w, display_h, native_w, native_h)
        btn = action.get("button", "left")
        pyautogui.click(rx, ry, button=btn)
        return f"click({rx},{ry},{btn})"

    elif action_type == "double_click":
        x, y = action.get("x", 0), action.get("y", 0)
        rx, ry = _scale_xy(x, y, display_w, display_h, native_w, native_h)
        pyautogui.click(rx, ry, clicks=2)
        return f"double_click({rx},{ry})"

    elif action_type == "type":
        text = action.get("text", "")
        pyautogui.typewrite(text, interval=0.02)
        return f"type({text!r})"

    elif action_type == "keypress":
        keys = action.get("keys", [])
        mapped = [_KEY_MAP.get(k, k.lower()) for k in keys]
        pyautogui.hotkey(*mapped)
        return f"keypress({mapped})"

    elif action_type == "scroll":
        x = action.get("x", native_w // 2)
        y = action.get("y", native_h // 2)
        rx, ry = _scale_xy(x, y, display_w, display_h, native_w, native_h)
        scroll_y = action.get("scroll_y", action.get("scrollY", 0))
        clicks = int(scroll_y / 120) if abs(scroll_y) >= 120 else (-1 if scroll_y < 0 else (1 if scroll_y > 0 else 0))
        pyautogui.scroll(clicks, x=rx, y=ry)
        return f"scroll({clicks}@{rx},{ry})"

    elif action_type == "move":
        x, y = action.get("x", 0), action.get("y", 0)
        rx, ry = _scale_xy(x, y, display_w, display_h, native_w, native_h)
        pyautogui.moveTo(rx, ry)
        return f"move({rx},{ry})"

    elif action_type == "drag":
        path = action.get("path", [])
        if len(path) >= 2:
            start = path[0]
            end = path[-1]
            sx = start.get("x", start[0]) if isinstance(start, dict) else start[0]
            sy = start.get("y", start[1]) if isinstance(start, dict) else start[1]
            ex = end.get("x", end[0]) if isinstance(end, dict) else end[0]
            ey = end.get("y", end[1]) if isinstance(end, dict) else end[1]
            rsx, rsy = _scale_xy(sx, sy, display_w, display_h, native_w, native_h)
            rex, rey = _scale_xy(ex, ey, display_w, display_h, native_w, native_h)
            pyautogui.moveTo(rsx, rsy)
            pyautogui.drag(rex - rsx, rey - rsy, duration=0.3)
            return f"drag({rsx},{rsy}->{rex},{rey})"
        return "drag(no_path)"

    elif action_type in ("screenshot", "wait"):
        if action_type == "wait":
            time.sleep(1)
        return action_type

    return f"unknown({action_type})"


def _execute_claude_action(
    action_input: dict[str, Any],
    display_w: int, display_h: int,
    native_w: int, native_h: int,
) -> str:
    """Execute a Claude computer use action locally.

    Official action types (from docs, computer_20251124):
    screenshot, left_click, right_click, middle_click, double_click,
    triple_click, type, key, mouse_move, scroll, left_click_drag,
    left_mouse_down, left_mouse_up, hold_key, wait, zoom
    """
    action = action_input.get("action", "unknown")

    if action in ("left_click", "right_click", "middle_click"):
        coord = action_input.get("coordinate", [0, 0])
        x, y = coord[0], coord[1]
        rx, ry = _scale_xy(x, y, display_w, display_h, native_w, native_h)
        btn = {"left_click": "left", "right_click": "right", "middle_click": "middle"}[action]
        pyautogui.click(rx, ry, button=btn)
        return f"{action}({rx},{ry})"

    elif action in ("double_click", "triple_click"):
        coord = action_input.get("coordinate", [0, 0])
        x, y = coord[0], coord[1]
        rx, ry = _scale_xy(x, y, display_w, display_h, native_w, native_h)
        clicks = 2 if action == "double_click" else 3
        pyautogui.click(rx, ry, clicks=clicks)
        return f"{action}({rx},{ry})"

    elif action == "type":
        text = action_input.get("text", "")
        pyautogui.typewrite(text, interval=0.02)
        return f"type({text!r})"

    elif action == "key":
        key_combo = action_input.get("key", "") or action_input.get("text", "")
        if "+" in key_combo:
            keys = [_KEY_MAP.get(k.strip(), k.strip().lower()) for k in key_combo.split("+")]
        else:
            keys = [_KEY_MAP.get(key_combo, key_combo.lower())]
        pyautogui.hotkey(*keys)
        return f"key({keys})"

    elif action == "mouse_move":
        coord = action_input.get("coordinate", [0, 0])
        x, y = coord[0], coord[1]
        rx, ry = _scale_xy(x, y, display_w, display_h, native_w, native_h)
        pyautogui.moveTo(rx, ry)
        return f"mouse_move({rx},{ry})"

    elif action == "scroll":
        coord = action_input.get("coordinate", [display_w // 2, display_h // 2])
        x, y = coord[0], coord[1]
        rx, ry = _scale_xy(x, y, display_w, display_h, native_w, native_h)
        direction = action_input.get("scroll_direction", "down")
        amount = action_input.get("scroll_amount", 3)
        clicks = -amount if direction == "down" else amount
        pyautogui.scroll(clicks, x=rx, y=ry)
        return f"scroll({direction},{amount}@{rx},{ry})"

    elif action == "left_click_drag":
        start_coord = action_input.get("start_coordinate", action_input.get("coordinate", [0, 0]))
        end_coord = action_input.get("end_coordinate", [0, 0])
        sx, sy = _scale_xy(start_coord[0], start_coord[1], display_w, display_h, native_w, native_h)
        ex, ey = _scale_xy(end_coord[0], end_coord[1], display_w, display_h, native_w, native_h)
        pyautogui.moveTo(sx, sy)
        pyautogui.drag(ex - sx, ey - sy, duration=0.3)
        return f"drag({sx},{sy}->{ex},{ey})"

    elif action == "screenshot":
        return "screenshot"

    elif action == "wait":
        duration = action_input.get("duration", 2)
        time.sleep(duration)
        return f"wait({duration}s)"

    return f"unknown({action})"


# --- GPT-5.4 Native Computer Use Loop ---
# Official API: tools=[{"type": "computer"}]
# Returns: computer_call items with actions list and call_id
# Continuation: computer_call_output with call_id + screenshot
# Ref: test_openephys_cu.py (verified 3/3 success)


def _run_gpt_native_cu_loop(
    goal: str,
    max_steps: int,
    display_w: int,
    display_h: int,
) -> dict[str, Any]:
    """Run GPT-5.4 native computer use loop (official API).

    Uses tools=[{"type": "computer"}] per OpenAI docs.
    Model returns computer_call with structured actions.
    """
    try:
        from openai import OpenAI
    except ImportError:
        return {"success": False, "error": "openai not installed on agent"}

    client = OpenAI()
    steps: list[dict[str, Any]] = []
    total_cost = 0.0
    prev_response_id: Optional[str] = None
    pending_call_id: Optional[str] = None
    pending_safety_checks: list = []
    success = False

    system = (
        f"You are controlling a Windows 11 lab PC. The screen is {display_w}x{display_h} pixels. "
        "This is a real computer in a neuroscience laboratory. "
        "Act precisely and decisively. After each action, verify the result from the screenshot. "
        "When the task is fully complete, stop requesting actions."
    )

    for i in range(max_steps):
        t0 = time.time()
        b64, native_w, native_h = _capture_screenshot_b64(display_w, display_h)

        if i == 0:
            # Initial call: user message with task + screenshot
            input_items: list[dict[str, Any]] = [{
                "role": "user",
                "content": [
                    {"type": "input_text", "text": goal},
                    {"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64}"},
                ],
            }]
        else:
            # Continuation: computer_call_output with screenshot
            output_item: dict[str, Any] = {
                "type": "computer_call_output",
                "call_id": pending_call_id,
                "output": {
                    "type": "computer_screenshot",
                    "image_url": f"data:image/jpeg;base64,{b64}",
                },
            }
            if pending_safety_checks:
                output_item["acknowledged_safety_checks"] = pending_safety_checks
                pending_safety_checks = []
            input_items = [output_item]

        request_kwargs: dict[str, Any] = {
            "model": "gpt-5.4",
            "tools": [{"type": "computer"}],
            "instructions": system,
            "input": input_items,
            "truncation": "auto",
        }
        if prev_response_id:
            request_kwargs["previous_response_id"] = prev_response_id

        response = client.responses.create(**request_kwargs)
        api_latency = time.time() - t0
        prev_response_id = response.id

        usage = response.usage
        in_tok = usage.input_tokens if usage else 0
        out_tok = usage.output_tokens if usage else 0
        cost = (in_tok * 2.50 + out_tok * 10.00) / 1_000_000
        total_cost += cost

        # Extract computer_call and message items from output
        computer_calls = []
        text_parts = []
        for item in response.output:
            item_type = getattr(item, "type", None)
            if item_type == "computer_call":
                computer_calls.append(item)
            elif item_type == "message":
                for part in (getattr(item, "content", None) or []):
                    if getattr(part, "type", None) == "output_text":
                        text_parts.append(getattr(part, "text", ""))

        if not computer_calls:
            # No computer_call — model is done
            steps.append({
                "step": i + 1, "action": "done",
                "text": " ".join(text_parts)[:200],
                "latency_s": round(api_latency, 2), "cost": round(cost, 5),
            })
            success = True
            break

        # Process computer_call items
        for cc in computer_calls:
            call_id = getattr(cc, "call_id", "")
            pending_call_id = call_id
            raw_checks = getattr(cc, "pending_safety_checks", []) or []
            if raw_checks:
                pending_safety_checks = [
                    c.model_dump() if hasattr(c, "model_dump") else c
                    for c in raw_checks
                ]
                logger.warning("Safety checks pending: %s", pending_safety_checks)

            # Extract actions (GPT-5.4 uses "actions" list or single "action")
            raw_actions = getattr(cc, "actions", None) or []
            if not raw_actions:
                single = getattr(cc, "action", None)
                if single:
                    raw_actions = [single]

            for raw_action in raw_actions:
                action_dict = (
                    raw_action.model_dump()
                    if hasattr(raw_action, "model_dump")
                    else raw_action
                )
                action_type = action_dict.get("type", "unknown")

                if action_type not in ("screenshot", "wait"):
                    result = _execute_openai_action(
                        action_dict, display_w, display_h, native_w, native_h,
                    )
                    time.sleep(0.5)
                else:
                    result = action_type
                    if action_type == "wait":
                        time.sleep(1)

                steps.append({
                    "step": i + 1, "action": action_type,
                    "params": {k: v for k, v in action_dict.items() if k != "type" and v is not None},
                    "result": result,
                    "latency_s": round(api_latency, 2), "cost": round(cost, 5),
                })

        time.sleep(0.3)

    return {
        "success": success,
        "model": "gpt-5.4-native-cu",
        "steps": steps,
        "total_steps": len(steps),
        "total_cost_usd": round(total_cost, 5),
    }


# --- Claude Sonnet Native CU Loop ---
# Official API: computer_20251124 tool type, computer-use-2025-11-24 beta
# Actions: left_click, type, key, scroll, screenshot, mouse_move, etc.
# Coordinate: [x, y] in display space (display_width_px x display_height_px)
# Ref: test_sonnet46_native_cu.py (verified PASS)


def _run_claude_cu_loop(
    goal: str,
    max_steps: int,
    display_w: int,
    display_h: int,
) -> dict[str, Any]:
    """Run Claude Sonnet CU loop (official computer_20251124 API).

    Uses beta messages API with computer_20251124 tool type.
    Model returns tool_use blocks with action + coordinate fields.
    """
    try:
        import anthropic
    except ImportError:
        return {"success": False, "error": "anthropic not installed on agent"}

    client = anthropic.Anthropic()
    steps: list[dict[str, Any]] = []
    success = False

    # Official: computer_20251124 for Sonnet 4.6, Opus 4.6, Opus 4.5
    tool_type = "computer_20251124"
    beta = "computer-use-2025-11-24"
    model = "claude-sonnet-4-6"

    system = (
        "You are controlling a real Windows 11 lab PC via mouse and keyboard. "
        "This is a neuroscience laboratory computer. "
        "Act decisively — click the target immediately. "
        "Do NOT wait, do NOT ask for more information. "
        "The screenshot you see is the CURRENT live screen. "
        "After each action, take a screenshot to verify the result."
    )

    # Official tool definition per Anthropic docs
    tools: list[dict[str, Any]] = [{
        "type": tool_type,
        "name": "computer",
        "display_width_px": display_w,
        "display_height_px": display_h,
    }]

    # Initial screenshot + task message
    b64, native_w, native_h = _capture_screenshot_b64(display_w, display_h)
    messages: list[dict[str, Any]] = [{
        "role": "user",
        "content": [
            {"type": "text", "text": goal},
            {
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
            },
        ],
    }]

    for i in range(max_steps):
        t0 = time.time()
        try:
            response = client.beta.messages.create(
                model=model,
                max_tokens=4096,
                system=system,
                tools=tools,
                messages=messages,
                betas=[beta],
            )
        except Exception as e:
            steps.append({"step": i + 1, "action": "error", "error": str(e)})
            break
        api_latency = time.time() - t0

        # Extract text and tool_use blocks
        text_parts = []
        tool_uses = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        if not tool_uses:
            # No tool use — model is done
            combined = " ".join(text_parts).lower()
            steps.append({
                "step": i + 1, "action": "done",
                "text": " ".join(text_parts)[:200],
                "latency_s": round(api_latency, 2),
            })
            success = any(w in combined for w in ["done", "complete", "success", "open", "visible"])
            if not success and response.stop_reason == "end_turn":
                success = True
            break

        # Add assistant response to conversation
        messages.append({"role": "assistant", "content": response.content})

        # Process each tool_use and collect tool_results
        tool_results: list[dict[str, Any]] = []
        for tu in tool_uses:
            action_input = tu.input
            action = action_input.get("action", "unknown")

            # Execute the action (skip screenshot — just re-capture below)
            if action != "screenshot":
                result = _execute_claude_action(
                    action_input, display_w, display_h, native_w, native_h,
                )
                time.sleep(0.5)
            else:
                result = "screenshot"

            # Capture new screenshot for tool_result (per Anthropic docs)
            b64, native_w, native_h = _capture_screenshot_b64(display_w, display_h)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": [{
                    "type": "image",
                    "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                }],
            })

            steps.append({
                "step": i + 1, "action": action,
                "result": result,
                "params": {k: v for k, v in action_input.items() if k != "action"},
                "latency_s": round(api_latency, 2),
            })

        messages.append({"role": "user", "content": tool_results})

    return {
        "success": success,
        "model": "claude-sonnet-4-6",
        "steps": steps,
        "total_steps": len(steps),
    }


# --- Fallback Pipeline ---
# Tries models in order: GPT-5.4 native CU → Claude Sonnet → error


def _run_fallback_pipeline(
    goal: str,
    max_steps: int,
    display_w: int,
    display_h: int,
) -> dict[str, Any]:
    """Try GPT-5.4 native CU first, fall back to Claude Sonnet on failure."""
    chain = [
        ("gpt-5.4-native-cu", _run_gpt_native_cu_loop),
        ("claude-sonnet-4-6", _run_claude_cu_loop),
    ]

    for model_name, runner in chain:
        logger.info("Fallback pipeline: trying %s", model_name)
        try:
            result = runner(goal, max_steps, display_w, display_h)
            if result.get("success"):
                result["fallback_model"] = model_name
                return result
            logger.warning("Model %s returned success=False, trying next", model_name)
        except Exception as e:
            logger.warning("Model %s failed: %s, trying next", model_name, e)

    return {"success": False, "error": "All models in fallback chain failed"}


# Model name → runner mapping
_CU_RUNNERS: dict[str, Any] = {
    "gpt-5.4": _run_gpt_native_cu_loop,
    "gpt-5.4-native": _run_gpt_native_cu_loop,
    "claude-sonnet-4-6": _run_claude_cu_loop,
    "sonnet": _run_claude_cu_loop,
    "auto": _run_fallback_pipeline,
}


# --- Session diagnostics ---


def _get_session_info() -> dict[str, Any]:
    """Get Windows session information for debugging Session 0 isolation.

    Returns process session ID, active console session ID, and whether
    this process can reach the interactive desktop.
    """
    info: dict[str, Any] = {
        "process_session_id": None,
        "console_session_id": None,
        "in_interactive_session": False,
        "platform": platform.system(),
    }

    if platform.system() != "Windows":
        info["note"] = "Session isolation is Windows-only"
        info["in_interactive_session"] = True
        return info

    try:
        import ctypes
        # WTSGetActiveConsoleSessionId — returns the session attached to
        # the physical console (keyboard/mouse/display)
        kernel32 = ctypes.windll.kernel32
        console_session = kernel32.WTSGetActiveConsoleSessionId()
        info["console_session_id"] = int(console_session)

        # Get our own process session ID
        import os as _os
        pid = _os.getpid()
        process_session = ctypes.c_ulong()
        kernel32.ProcessIdToSessionId(pid, ctypes.byref(process_session))
        info["process_session_id"] = int(process_session.value)

        # We are in the interactive session if our session matches console
        info["in_interactive_session"] = (
            info["process_session_id"] == info["console_session_id"]
        )

        if not info["in_interactive_session"]:
            info["warning"] = (
                f"Process is in Session {info['process_session_id']} but "
                f"console is Session {info['console_session_id']}. "
                "pyautogui clicks will NOT reach the desktop. "
                "Use fix_session.sh or restart_agent_interactive.ps1 to fix."
            )
    except Exception as e:
        info["error"] = f"Cannot query session info: {e}"

    return info


class LaunchRequest(BaseModel):
    """Launch an application in the agent's session (not via SSH)."""
    executable: str
    args: list[str] = []
    wait: bool = False
    timeout: int = 10


# --- Endpoints ---


@app.get("/health")
def health():
    session = _get_session_info()
    return {
        "status": "ok",
        "hostname": platform.node(),
        "platform": platform.system(),
        "python": platform.python_version(),
        "mss": mss is not None,
        "pyautogui": pyautogui is not None,
        "session": session,
    }


@app.get("/session")
def session_info(authorization: Optional[str] = Header(None)):
    """Diagnose Windows session isolation.

    Returns whether this process is in the interactive desktop session.
    If not, pyautogui/pywinauto actions will not reach the user's desktop.

    Fix: Use fix_session.sh or restart_agent_interactive.ps1 to restart
    the agent in the correct session via Windows Task Scheduler with /IT.
    """
    _check_auth(authorization)
    return _get_session_info()


@app.post("/launch")
def launch_app(req: LaunchRequest, authorization: Optional[str] = Header(None)):
    """Launch an application in the agent's session.

    Since the agent runs in the interactive session (after fix_session),
    subprocess.Popen here inherits that session. This avoids the SSH
    session isolation problem where apps launched via SSH end up in
    Session 0 and are invisible on the desktop.

    Use this instead of SSH to launch GUI applications.
    """
    _check_auth(authorization)

    import subprocess as sp

    cmd = [req.executable] + req.args
    logger.info("Launching: %s", cmd)

    try:
        proc = sp.Popen(
            cmd,
            stdout=sp.PIPE if req.wait else sp.DEVNULL,
            stderr=sp.PIPE if req.wait else sp.DEVNULL,
            creationflags=0x00000010 if platform.system() == "Windows" else 0,
            # 0x10 = CREATE_NEW_CONSOLE — gives the app its own console window
        )

        if req.wait:
            stdout, stderr = proc.communicate(timeout=req.timeout)
            return {
                "ok": True,
                "pid": proc.pid,
                "returncode": proc.returncode,
                "stdout": stdout.decode("utf-8", errors="replace")[:2000],
                "stderr": stderr.decode("utf-8", errors="replace")[:2000],
            }
        else:
            return {
                "ok": True,
                "pid": proc.pid,
                "note": "Process launched in background (agent's session)",
            }
    except FileNotFoundError:
        raise HTTPException(404, f"Executable not found: {req.executable}")
    except Exception as e:
        raise HTTPException(500, f"Launch failed: {e}")


def _draw_cursor(img):
    """Draw a crosshair at the current mouse position so VLM can see it."""
    if not pyautogui:
        return img
    from PIL import ImageDraw

    mx, my = pyautogui.position()
    # Scale coords if image was resized
    scale_x = img.width / _screen_w if _screen_w else 1
    scale_y = img.height / _screen_h if _screen_h else 1
    cx = int(mx * scale_x)
    cy = int(my * scale_y)

    draw = ImageDraw.Draw(img)
    r = 12  # crosshair radius
    # White outline + red cross for visibility on any background
    for color, width in [("white", 3), ("red", 1)]:
        draw.line([(cx - r, cy), (cx + r, cy)], fill=color, width=width)
        draw.line([(cx, cy - r), (cx, cy + r)], fill=color, width=width)
    return img


@app.get("/screenshot")
def screenshot(
    format: str = "png",
    quality: int = 80,
    max_width: int = 0,
    cursor: bool = True,
    authorization: Optional[str] = Header(None),
):
    """Capture full screen. Returns PNG/JPEG bytes."""
    _check_auth(authorization)

    if not mss:
        raise HTTPException(500, "mss not installed")

    _init_screen_size()
    t0 = time.perf_counter()
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # primary monitor
        raw = sct.grab(monitor)

    from PIL import Image

    img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    if max_width and img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)

    if cursor:
        img = _draw_cursor(img)

    buf = io.BytesIO()
    if format == "jpeg":
        img.save(buf, format="JPEG", quality=quality)
        media_type = "image/jpeg"
    else:
        img.save(buf, format="PNG", optimize=False)
        media_type = "image/png"

    elapsed_ms = (time.perf_counter() - t0) * 1000
    return Response(
        content=buf.getvalue(),
        media_type=media_type,
        headers={
            "X-Capture-Ms": f"{elapsed_ms:.1f}",
            "X-Resolution": f"{raw.size.width}x{raw.size.height}",
        },
    )


@app.get("/screenshot/base64")
def screenshot_base64(
    format: str = "png",
    quality: int = 80,
    max_width: int = 1280,
    cursor: bool = True,
    authorization: Optional[str] = Header(None),
):
    """Capture screen, return base64 string (for VLM input)."""
    _check_auth(authorization)

    if not mss:
        raise HTTPException(500, "mss not installed")

    _init_screen_size()
    t0 = time.perf_counter()
    with mss.mss() as sct:
        raw = sct.grab(sct.monitors[1])

    from PIL import Image

    img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    if max_width and img.width > max_width:
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)

    if cursor:
        img = _draw_cursor(img)

    buf = io.BytesIO()
    if format == "jpeg":
        img.save(buf, format="JPEG", quality=quality)
    else:
        img.save(buf, format="PNG", optimize=False)

    b64 = base64.b64encode(buf.getvalue()).decode()
    elapsed_ms = (time.perf_counter() - t0) * 1000

    return {
        "image": b64,
        "format": format,
        "width": img.width,
        "height": img.height,
        "capture_ms": round(elapsed_ms, 1),
    }


@app.post("/click")
def click(req: ClickRequest, authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    if not pyautogui:
        raise HTTPException(500, "pyautogui not installed")
    if req.button not in ("left", "right", "middle"):
        raise HTTPException(422, f"Invalid button: {req.button}")
    x, y = _clamp_coords(req.x, req.y)
    pyautogui.click(x, y, button=req.button, clicks=req.clicks)
    return {"ok": True, "action": "click", "x": x, "y": y}


@app.post("/type")
def type_text(req: TypeRequest, authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    if not pyautogui:
        raise HTTPException(500, "pyautogui not installed")
    pyautogui.typewrite(req.text, interval=req.interval)
    return {"ok": True, "action": "type", "length": len(req.text)}


@app.post("/hotkey")
def hotkey(req: HotkeyRequest, authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    if not pyautogui:
        raise HTTPException(500, "pyautogui not installed")
    pyautogui.hotkey(*req.keys)
    return {"ok": True, "action": "hotkey", "keys": req.keys}


@app.post("/scroll")
def scroll(req: ScrollRequest, authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    if not pyautogui:
        raise HTTPException(500, "pyautogui not installed")
    x, y = _clamp_coords(req.x, req.y)
    pyautogui.scroll(req.clicks, x=x, y=y)
    return {"ok": True, "action": "scroll", "clicks": req.clicks}


@app.post("/move")
def move(req: MoveRequest, authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    if not pyautogui:
        raise HTTPException(500, "pyautogui not installed")
    x, y = _clamp_coords(req.x, req.y)
    pyautogui.moveTo(x, y)
    return {"ok": True, "action": "move", "x": x, "y": y}


@app.post("/drag")
def drag(req: DragRequest, authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    if not pyautogui:
        raise HTTPException(500, "pyautogui not installed")
    if req.button not in ("left", "right", "middle"):
        raise HTTPException(422, f"Invalid button: {req.button}")
    sx, sy = _clamp_coords(req.start_x, req.start_y)
    ex, ey = _clamp_coords(req.end_x, req.end_y)
    pyautogui.moveTo(sx, sy)
    pyautogui.drag(ex - sx, ey - sy, duration=req.duration, button=req.button)
    return {"ok": True, "action": "drag"}


@app.post("/key")
def key_press(
    key: str, authorization: Optional[str] = Header(None)
):
    _check_auth(authorization)
    if not pyautogui:
        raise HTTPException(500, "pyautogui not installed")
    pyautogui.press(key)
    return {"ok": True, "action": "key", "key": key}


@app.post("/task")
def run_task(req: TaskRequest, authorization: Optional[str] = Header(None)):
    """Execute a full CU task autonomously.

    The VLM loop runs locally on Windows — no screenshot transfer over network.
    Linux orchestrator just sends the high-level goal and gets results back.
    """
    _check_auth(authorization)
    if not mss or not pyautogui:
        raise HTTPException(500, "mss/pyautogui not installed")

    runner = _CU_RUNNERS.get(req.model)
    if runner is None:
        raise HTTPException(
            422,
            f"Unknown model: {req.model}. Available: {list(_CU_RUNNERS.keys())}",
        )

    t0 = time.time()
    try:
        result = runner(
            goal=req.goal,
            max_steps=req.max_steps,
            display_w=req.display_width,
            display_h=req.display_height,
        )
    except Exception as e:
        logger.exception("Task execution failed")
        result = {
            "success": False,
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
        }

    result["total_time_s"] = round(time.time() - t0, 2)
    result["goal"] = req.goal
    return result


@app.get("/info")
def info(authorization: Optional[str] = Header(None)):
    """Screen and system info."""
    _check_auth(authorization)
    screen_size = pyautogui.size() if pyautogui else (0, 0)
    return {
        "hostname": platform.node(),
        "platform": platform.system(),
        "python": platform.python_version(),
        "screen_width": screen_size[0],
        "screen_height": screen_size[1],
    }


# --- Local screen recording (runs in interactive session) ---

_recorder_thread: Optional[threading.Thread] = None
_recorder_running = False
_recorder_frame_count = 0
_recorder_start_time = 0.0
_recorder_output_dir = ""


class RecordRequest(BaseModel):
    fps: int = 30
    output_dir: str = "C:\\temp\\oe_recording\\frames"
    duration: int = 0  # 0 = manual stop


def _record_loop(output_dir: str, fps: int, duration: int):
    global _recorder_running, _recorder_frame_count
    import os
    os.makedirs(output_dir, exist_ok=True)
    interval = 1.0 / fps
    sct = mss.mss()
    monitor = sct.monitors[1]
    start = time.time()

    while _recorder_running:
        if duration > 0 and (time.time() - start) > duration:
            break
        t0 = time.time()
        try:
            img = sct.grab(monitor)
            from PIL import Image as PILImage, ImageDraw
            pil_img = PILImage.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
            # Draw cursor crosshair at current mouse position
            if pyautogui:
                mx, my = pyautogui.position()
                draw = ImageDraw.Draw(pil_img)
                r = 15
                draw.ellipse([mx - r, my - r, mx + r, my + r],
                             outline=(255, 200, 0), width=3)
                draw.line([mx - r - 5, my, mx + r + 5, my],
                          fill=(255, 200, 0), width=2)
                draw.line([mx, my - r - 5, mx, my + r + 5],
                          fill=(255, 200, 0), width=2)
            path = os.path.join(output_dir, f"f_{_recorder_frame_count:06d}.jpg")
            pil_img.save(path, "JPEG", quality=85)
            _recorder_frame_count += 1
        except Exception:
            pass
        elapsed = time.time() - t0
        sl = max(0, interval - elapsed)
        if sl > 0:
            time.sleep(sl)

    _recorder_running = False


@app.post("/record/start")
def record_start(req: RecordRequest, authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    global _recorder_thread, _recorder_running, _recorder_frame_count
    global _recorder_start_time, _recorder_output_dir

    if _recorder_running:
        return {"ok": False, "error": "already recording"}

    _recorder_running = True
    _recorder_frame_count = 0
    _recorder_start_time = time.time()
    _recorder_output_dir = req.output_dir

    _recorder_thread = threading.Thread(
        target=_record_loop,
        args=(req.output_dir, req.fps, req.duration),
        daemon=True,
    )
    _recorder_thread.start()
    return {"ok": True, "fps": req.fps, "output_dir": req.output_dir}


@app.post("/record/stop")
def record_stop(authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    global _recorder_running
    _recorder_running = False
    if _recorder_thread:
        _recorder_thread.join(timeout=10)
    elapsed = time.time() - _recorder_start_time
    actual_fps = _recorder_frame_count / elapsed if elapsed > 0 else 0
    return {
        "ok": True,
        "frames": _recorder_frame_count,
        "duration_s": round(elapsed, 1),
        "actual_fps": round(actual_fps, 1),
        "output_dir": _recorder_output_dir,
    }


@app.get("/record/status")
def record_status(authorization: Optional[str] = Header(None)):
    _check_auth(authorization)
    elapsed = time.time() - _recorder_start_time if _recorder_running else 0
    return {
        "recording": _recorder_running,
        "frames": _recorder_frame_count,
        "elapsed_s": round(elapsed, 1),
        "output_dir": _recorder_output_dir,
    }


def main():
    parser = argparse.ArgumentParser(description="device-use Remote Agent")
    parser.add_argument("--host", default="0.0.0.0", help="Bind address")
    parser.add_argument("--port", type=int, default=8421, help="Port (default: 8421)")
    parser.add_argument("--password", default=None, help="Bearer token for auth")
    args = parser.parse_args()

    global _password
    _password = args.password

    print(f"device-use Remote Agent v0.2.0")
    print(f"  Host: {args.host}:{args.port}")
    print(f"  Auth: {'enabled' if _password else 'disabled'}")
    print(f"  Platform: {platform.system()} {platform.node()}")

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
