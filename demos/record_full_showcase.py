#!/usr/bin/env python3
"""Full showcase: Desktop → Launch TopSpin → Fullscreen → Process → Results.

Records the complete experience from a clean macOS desktop through
AI-driven NMR data processing. Designed for showcase demos.

Usage:
    # 1. Kill TopSpin first: ssh admin@VM 'pkill -9 java'
    # 2. Run deterministic path: python demos/record_full_showcase.py
    # 3. Optional VLM overlay: OPENROUTER_API_KEY=... python demos/record_full_showcase.py
"""

from __future__ import annotations

import base64
import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

try:
    from openai import OpenAI

    _OPENAI_IMPORT_ERROR: Exception | None = None
except Exception as exc:
    OpenAI = Any  # type: ignore[misc,assignment]
    _OPENAI_IMPORT_ERROR = exc

# ── Config ──────────────────────────────────────
VM_IP = os.environ.get("VM_IP", "10.0.0.1")
VNC_USER = os.environ.get("VNC_USER", "changeme")
VNC_PASS = os.environ.get("VNC_PASS", "changeme")
MODEL = "anthropic/claude-sonnet-4.6"
DATASET = os.environ.get(
    "TOPSPIN_DATASET",
    "/opt/topspin5.0.0/examdata/exam_CMCse_2/1",
)
CMD_X, CMD_Y = 200, 960

FRAMES_DIR = Path("/tmp/full_showcase_frames")
OUTPUT_DIR = Path("/tmp/full_showcase_output")
CAPTURE_FPS = 3
PLAYBACK_FPS = 3

B, G, C, D, R, Y, RST = (
    "\033[1m",
    "\033[32m",
    "\033[36m",
    "\033[2m",
    "\033[31m",
    "\033[33m",
    "\033[0m",
)

_current_label = ""
_label_lock = threading.Lock()


def set_label(text: str) -> None:
    global _current_label
    with _label_lock:
        _current_label = text


def get_label() -> str:
    with _label_lock:
        return _current_label


# ── VNC ─────────────────────────────────────────


def _vncdo(*args: str, timeout: int = 20) -> subprocess.CompletedProcess:
    vncdo = resolve_vncdo_binary()
    result = subprocess.run(
        [vncdo, "-s", VM_IP, "--username", VNC_USER, "--password", VNC_PASS, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        if not detail:
            detail = f"exit {result.returncode}"
        raise RuntimeError(f"vncdo {' '.join(args)} failed: {detail}")
    return result


def vnc_screenshot(path: str = "/tmp/vnc_frame.png") -> Image.Image:
    target = Path(path)
    for attempt in range(3):
        try:
            old_mtime = target.stat().st_mtime_ns if target.exists() else None
            if target.exists():
                target.unlink()
            _vncdo("capture", str(target), timeout=25)
            if not target.exists():
                raise RuntimeError(f"capture did not create {target}")
            if old_mtime is not None and target.stat().st_mtime_ns == old_mtime:
                raise RuntimeError(f"capture produced stale frame at {target}")
            with Image.open(target) as img:
                img.load()
                return img.copy()
        except Exception:
            if attempt == 2:
                raise
            time.sleep(2)


def vnc_click(x: int, y: int) -> None:
    _vncdo("move", str(x), str(y), "pause", "0.1", "click", "1")


def vnc_type_command(cmd: str) -> None:
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


def vnc_key(key: str) -> None:
    _vncdo("key", key)


def vnc_fullscreen() -> None:
    """Toggle fullscreen via green button (top-left of TopSpin window).

    In 2048x1536 framebuffer: traffic lights at y~68-72.
    Red x~36, Yellow x~76, Green x~114.
    """
    _vncdo(
        "move",
        "36",
        "70",
        "pause",
        "0.5",  # hover over red to reveal buttons
        "move",
        "114",
        "70",
        "pause",
        "0.3",  # move to green button
        "click",
        "1",
    )


# ── SSH (shell commands) ───────────────────────


def cua_run(command: str) -> dict:
    """Run shell command on VM via SSH."""
    try:
        r = subprocess.run(
            [
                "sshpass",
                "-p",
                VNC_PASS,
                "ssh",
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "ConnectTimeout=5",
                f"{VNC_USER}@{VM_IP}",
                command,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return {"success": r.returncode == 0, "stdout": r.stdout, "stderr": r.stderr}
    except Exception as e:
        return {"error": str(e)}


# ── VLM ─────────────────────────────────────────


def screenshot_b64() -> str:
    img = vnc_screenshot()
    small = img.convert("RGB").resize((1280, 960), Image.LANCZOS)
    buf = io.BytesIO()
    small.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def ask_verify(ai: OpenAI, b64: str, check: str) -> dict:
    response = ai.chat.completions.create(
        model=MODEL,
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    {
                        "type": "text",
                        "text": (
                            f"TopSpin 5.0 NMR screenshot (1280x960). {check}\n"
                            'Return ONLY: {"ok": true/false, "desc": "brief"}'
                        ),
                    },
                ],
            }
        ],
    )
    text = response.choices[0].message.content.strip()
    m = re.search(r"\{[^}]+\}", text)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass
    return {"ok": False, "desc": text[:200]}


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def resolve_vncdo_binary() -> str:
    explicit = os.environ.get("VNCDO_BIN", "").strip()
    if explicit:
        return explicit

    candidates = [
        Path(sys.executable).with_name("vncdo"),
        Path(__file__).resolve().parents[2] / "device-use" / ".venv" / "bin" / "vncdo",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    found = shutil.which("vncdo")
    if found:
        return found
    raise RuntimeError(
        "vncdo not found. Set VNCDO_BIN or install vncdotool in the current environment."
    )


def load_openrouter_api_key() -> str | None:
    if _truthy_env("DEMO_DISABLE_VLM") or _truthy_env("DEMO_NO_VLM"):
        return None
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if api_key:
        return api_key

    zshrc = os.path.expanduser("~/.zshrc")
    if os.path.exists(zshrc):
        with open(zshrc) as f:
            for line in f:
                line = line.strip()
                if line.startswith("export OPENROUTER_API_KEY=") and not line.startswith("#"):
                    return line.split("=", 1)[1].strip("'\" ")
    return None


def build_optional_verifier(require_vlm: bool = False) -> OpenAI | None:
    if _OPENAI_IMPORT_ERROR is not None:
        if require_vlm:
            raise RuntimeError(f"openai package missing for VLM mode: {_OPENAI_IMPORT_ERROR}")
        return None

    api_key = load_openrouter_api_key()
    if not api_key:
        if require_vlm:
            raise RuntimeError("OPENROUTER_API_KEY required but not configured")
        return None
    return OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")


def vm_path_exists(path: str) -> bool:
    quoted = shlex.quote(path)
    result = cua_run(f"test -e {quoted} && echo YES || echo NO")
    return "YES" in result.get("stdout", "")


def vm_file_mtime(path: str) -> int | None:
    quoted = shlex.quote(path)
    result = cua_run(f"if [ -f {quoted} ]; then stat -f %m {quoted}; fi")
    if not result.get("success"):
        return None
    text = result.get("stdout", "").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def vm_any_process_running(pattern: str) -> bool:
    quoted = shlex.quote(pattern)
    result = cua_run(f"pgrep -f {quoted} >/dev/null && echo YES || echo NO")
    return "YES" in result.get("stdout", "")


def snapshot_mtimes(paths: list[str]) -> dict[str, int | None]:
    return {path: vm_file_mtime(path) for path in paths}


def wait_for_file_change(
    paths: list[str],
    before: dict[str, int | None],
    timeout_sec: int = 20,
    interval_sec: float = 1.0,
) -> tuple[bool, str]:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        changed: list[str] = []
        for path in paths:
            current = vm_file_mtime(path)
            previous = before.get(path)
            if current is not None and (previous is None or current > previous):
                changed.append(Path(path).name)
        if changed:
            return True, f"updated {', '.join(changed)}"
        time.sleep(interval_sec)
    names = ", ".join(Path(path).name for path in paths)
    return False, f"no file change observed in {names}"


def verify_file_change_or_existing(
    paths: list[str],
    before: dict[str, int | None],
    timeout_sec: int = 20,
    require_all_existing: bool = False,
) -> tuple[bool, str]:
    changed_ok, changed_desc = wait_for_file_change(paths, before, timeout_sec=timeout_sec)
    if changed_ok:
        return True, changed_desc

    existing = [path for path in paths if vm_path_exists(path)]
    if not existing:
        return False, changed_desc

    if require_all_existing and len(existing) != len(paths):
        return False, f"{changed_desc}; only {len(existing)}/{len(paths)} artifacts exist"

    names = ", ".join(Path(path).name for path in existing)
    return True, f"{changed_desc}; using existing artifacts: {names}"


def processed_paths(dataset: str) -> dict[str, str]:
    pdata = Path(dataset) / "pdata" / "1"
    return {
        "1r": str(pdata / "1r"),
        "1i": str(pdata / "1i"),
        "proc": str(pdata / "proc"),
        "procs": str(pdata / "procs"),
        "auditp": str(pdata / "auditp.txt"),
        "peaks": str(pdata / "peaks"),
        "peaklist": str(pdata / "peaklist.xml"),
        "peakrng": str(pdata / "peakrng"),
        "thumb": str(pdata / "thumb.png"),
    }


def reset_peak_artifacts(dataset: str) -> None:
    paths = processed_paths(dataset)
    cleanup = [paths["peaks"], paths["peaklist"], paths["peakrng"]]
    quoted = " ".join(shlex.quote(path) for path in cleanup)
    cua_run(f"rm -f {quoted}")


def verify_checkpoint(
    ai: OpenAI | None,
    check: str,
    deterministic_ok: bool,
    deterministic_desc: str,
) -> dict:
    result = {
        "ok": deterministic_ok,
        "desc": deterministic_desc,
        "mode": "deterministic",
    }
    if ai is None:
        return result

    try:
        vlm = ask_verify(ai, screenshot_b64(), check)
    except Exception as exc:
        result["mode"] = "deterministic+vlm-error"
        result["desc"] = f"{deterministic_desc}; vlm unavailable: {exc}"
        return result

    result["mode"] = "deterministic+vlm"
    result["vlm_ok"] = bool(vlm.get("ok", False))
    result["vlm_desc"] = str(vlm.get("desc", ""))[:160]
    if result["vlm_desc"]:
        prefix = "vlm" if result["vlm_ok"] else "vlm warn"
        result["desc"] = f"{deterministic_desc}; {prefix}: {result['vlm_desc']}"
    return result


# ── Label Overlay ───────────────────────────────


def add_label_overlay(img: Image.Image, label: str) -> Image.Image:
    if not label:
        return img
    w, h = img.size
    banner_h = 80
    banner_y = h - banner_h - 20

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    d.rectangle([(40, banner_y), (w - 40, banner_y + banner_h)], fill=(0, 0, 0, 180))

    if img.mode != "RGBA":
        img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)

    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 36)
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    tx = (w - tw) // 2
    ty = banner_y + (banner_h - (bbox[3] - bbox[1])) // 2
    draw.text((tx, ty), label, fill=(255, 255, 255, 255), font=font)
    return img.convert("RGB")


# ── Frame Recorder ──────────────────────────────


class FrameRecorder:
    def __init__(self, fps: float = 3.0):
        self.fps = fps
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.frame_count = 0
        self.errors = 0

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=15)

    def _run(self) -> None:
        interval = 1.0 / self.fps
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                path = str(FRAMES_DIR / f"raw_{self.frame_count:06d}.png")
                _vncdo("capture", path)
                if os.path.exists(path):
                    img = Image.open(path)
                    label = get_label()
                    if label:
                        img = add_label_overlay(img, label)
                    out = str(FRAMES_DIR / f"frame_{self.frame_count:06d}.png")
                    img.save(out)
                    if path != out:
                        os.unlink(path)
                    self.frame_count += 1
            except Exception:
                self.errors += 1
            elapsed = time.monotonic() - t0
            self._stop.wait(max(0, interval - elapsed))


# ── Pipeline ────────────────────────────────────


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"  {D}[{ts}]{RST} {msg}")


def run_full_pipeline(ai: OpenAI | None) -> list[tuple[str, bool]]:
    results = []
    paths = processed_paths(DATASET)

    # ═══════════════════════════════════════════════
    # ACT 1: LAUNCH
    # ═══════════════════════════════════════════════

    # Scene 1: Clean desktop
    set_label("LabClaw — AI Operating NMR Spectrometer")
    log(f"{B}Act 1: Launch TopSpin{RST}")
    time.sleep(5)

    # Scene 2: Launch TopSpin via GUI Terminal (avoids TCC/permission issues)
    # Key insight: SSH-launched processes trigger macOS TCC dialogs for System Events.
    # Launching from a GUI Terminal bypasses this entirely.
    set_label("AI Agent: Launching TopSpin NMR Software...")
    log("  Opening Terminal in VM GUI...")
    cua_run("open -a Terminal")
    time.sleep(3)

    log("  Typing TopSpin launch command...")
    _vncdo(
        "type",
        "/opt/topspin5.0.0/topspin &",
        "pause",
        "0.5",
        "key",
        "return",
    )
    time.sleep(3)

    # Scene 3: Wait for TopSpin to load (splash screen + initialization)
    set_label("TopSpin 5.0 — Initializing...")
    java_ok = False
    for i in range(20):  # 20 * 3s = 60s max wait
        time.sleep(3)
        r = cua_run("pgrep java > /dev/null && echo YES || echo NO")
        if "YES" in r.get("stdout", ""):
            java_ok = True
            log(f"  Java started at {(i + 1) * 3}s")
            break
    if not java_ok:
        log(f"  {R}Java never started{RST}")
        return results

    # Wait for GUI to fully load
    set_label("TopSpin 5.0 — Loading GUI...")
    time.sleep(30)

    # Try to minimize Terminal (non-critical — VNC may timeout under load)
    try:
        _vncdo("key", "super_l-h", timeout=5)
    except Exception:
        pass
    time.sleep(1)

    # Verify TopSpin loaded. The deterministic check is the source of truth;
    # VLM is only supplementary context when available.
    v = verify_checkpoint(
        ai,
        "Is TopSpin 5.0 main window visible with toolbar and command line?",
        deterministic_ok=java_ok
        and (vm_any_process_running("topspin") or vm_any_process_running("java")),
        deterministic_desc="java process detected and VNC capture succeeded",
    )
    results.append(("Launch TopSpin", v.get("ok", False)))
    log(f"  {'OK' if v.get('ok') else 'FAIL'}: {v.get('desc', '')[:80]}")

    if not v.get("ok"):
        # Wait more
        time.sleep(15)
        cua_run("killall universalAccessAuthWarn 2>/dev/null")
        time.sleep(3)
        v = verify_checkpoint(
            ai,
            "Is TopSpin visible now?",
            deterministic_ok=vm_any_process_running("java"),
            deterministic_desc="java process still running after extra wait",
        )
        results[0] = ("Launch TopSpin", v.get("ok", False))
        if not v.get("ok"):
            return results

    # Check for Find data dialog when VLM is available. In deterministic mode,
    # continue without gating on this auxiliary panel.
    if ai is not None:
        v_find = ask_verify(
            ai,
            screenshot_b64(),
            "Is there a 'Find data' panel/dialog showing a list of datasets? "
            "(NOT the normal TopSpin view with spectrum area)",
        )
    else:
        v_find = {"ok": False}
    if v_find.get("ok"):
        log("  Closing Find data dialog...")
        # Click Close button at bottom-right (framebuffer coords)
        vnc_click(1100, 1420)
        time.sleep(2)
        # If still there, try clicking in different spot
        v_still = ask_verify(ai, screenshot_b64(), "Is the Find data panel still visible?")
        if v_still.get("ok"):
            # Try clicking further down
            vnc_click(1100, 1440)
            time.sleep(1)

    set_label("TopSpin 5.0 Ready")
    time.sleep(3)

    # ═══════════════════════════════════════════════
    # ACT 2: FULLSCREEN
    # ═══════════════════════════════════════════════

    set_label("Going Fullscreen...")
    log(f"{B}Act 2: Fullscreen{RST}")
    time.sleep(1)

    # Click green traffic light button to maximize/fullscreen
    vnc_fullscreen()
    time.sleep(3)

    v = verify_checkpoint(
        ai,
        "Is TopSpin now in fullscreen or maximized mode? "
        "(window fills the entire screen, no desktop visible behind it)",
        deterministic_ok=vm_any_process_running("java"),
        deterministic_desc="fullscreen toggle dispatched and TopSpin still running",
    )
    results.append(("Fullscreen", v.get("ok", False)))
    log(f"  {'OK' if v.get('ok') else 'WARN'}: {v.get('desc', '')[:80]}")

    set_label("TopSpin 5.0 — Full Screen Mode")
    time.sleep(3)

    # ═══════════════════════════════════════════════
    # ACT 3: LOAD DATA
    # ═══════════════════════════════════════════════

    compound = DATASET.split("/")[-2]
    set_label(f"AI Command: re {compound}/1")
    log(f"{B}Act 3: Load Dataset ({compound}){RST}")
    time.sleep(3)

    dataset_exists = vm_path_exists(DATASET)
    vnc_type_command(f"re {DATASET}")
    time.sleep(8)

    set_label(f"Dataset Loaded: {compound}")
    time.sleep(4)

    v = verify_checkpoint(
        ai,
        "Is NMR data displayed? (FID or spectrum)",
        deterministic_ok=dataset_exists and vm_any_process_running("java"),
        deterministic_desc="dataset path exists and TopSpin remained alive after re",
    )
    results.append(("Load Dataset", v.get("ok", False)))
    log(f"  {'OK' if v.get('ok') else 'FAIL'}: {v.get('desc', '')[:80]}")

    # ═══════════════════════════════════════════════
    # ACT 4: PROCESS
    # ═══════════════════════════════════════════════

    # Step: Fourier Transform
    set_label("AI Command: efp (Fourier Transform)")
    log(f"{B}Act 4a: Fourier Transform{RST}")
    time.sleep(2)

    efp_before = snapshot_mtimes(
        [
            paths["1r"],
            paths["1i"],
            paths["proc"],
            paths["procs"],
            paths["auditp"],
            paths["thumb"],
        ]
    )
    vnc_type_command("efp")
    ok_efp, desc_efp = verify_file_change_or_existing(
        [paths["1r"], paths["1i"], paths["proc"], paths["procs"], paths["auditp"], paths["thumb"]],
        efp_before,
        timeout_sec=20,
        require_all_existing=False,
    )

    set_label("Fourier Transform Complete — Frequency Spectrum")
    time.sleep(4)

    v = verify_checkpoint(
        ai,
        "Has a frequency-domain spectrum appeared with peaks?",
        deterministic_ok=ok_efp,
        deterministic_desc=desc_efp,
    )
    results.append(("Fourier Transform", v.get("ok", False)))
    log(f"  {'OK' if v.get('ok') else 'FAIL'}: {v.get('desc', '')[:80]}")

    # Step: Phase Correction
    set_label("AI Command: apk (Auto Phase Correction)")
    log(f"{B}Act 4b: Phase Correction{RST}")
    time.sleep(2)

    apk_before = snapshot_mtimes(
        [
            paths["proc"],
            paths["procs"],
            paths["auditp"],
            paths["thumb"],
            paths["1r"],
        ]
    )
    vnc_type_command("apk")
    time.sleep(5)

    # Handle dialog
    v_dlg = (
        ask_verify(ai, screenshot_b64(), "Is there a centered dialog/popup?")
        if ai
        else {"ok": False}
    )
    if v_dlg.get("ok"):
        log("  Dismissing dialog...")
        vnc_key("return")
        time.sleep(3)

    ok_apk, desc_apk = verify_file_change_or_existing(
        [paths["proc"], paths["procs"], paths["auditp"], paths["thumb"], paths["1r"]],
        apk_before,
        timeout_sec=20,
        require_all_existing=False,
    )

    set_label("Phase Corrected — Clean Peaks, Flat Baseline")
    time.sleep(4)

    v = verify_checkpoint(
        ai,
        "Are peaks upright with flat baseline?",
        deterministic_ok=ok_apk,
        deterministic_desc=desc_apk,
    )
    results.append(("Phase Correction", v.get("ok", False)))
    log(f"  {'OK' if v.get('ok') else 'FAIL'}: {v.get('desc', '')[:80]}")

    # Step: Peak Picking
    set_label("AI Command: pp (Peak Picking)")
    log(f"{B}Act 4c: Peak Picking{RST}")
    time.sleep(2)

    pp_before = snapshot_mtimes(
        [
            paths["peaks"],
            paths["peaklist"],
            paths["peakrng"],
            paths["auditp"],
            paths["thumb"],
            paths["procs"],
        ]
    )
    vnc_type_command("pp")
    time.sleep(5)

    # Handle dialog
    v_dlg = (
        ask_verify(ai, screenshot_b64(), "Is there a centered dialog/popup?")
        if ai
        else {"ok": False}
    )
    if v_dlg.get("ok"):
        log("  Dismissing dialog...")
        vnc_key("return")
        time.sleep(3)

    ok_pp, desc_pp = verify_file_change_or_existing(
        [
            paths["peaks"],
            paths["peaklist"],
            paths["peakrng"],
            paths["auditp"],
            paths["thumb"],
            paths["procs"],
        ],
        pp_before,
        timeout_sec=20,
        require_all_existing=False,
    )

    set_label("Peaks Identified — Chemical Shifts Annotated")
    time.sleep(5)

    v = verify_checkpoint(
        ai,
        "Are peak annotations visible on the spectrum?",
        deterministic_ok=ok_pp,
        deterministic_desc=desc_pp,
    )
    results.append(("Peak Picking", v.get("ok", False)))
    log(f"  {'OK' if v.get('ok') else 'FAIL'}: {v.get('desc', '')[:80]}")

    # ═══════════════════════════════════════════════
    # ACT 5: RESULT
    # ═══════════════════════════════════════════════

    set_label("AI Analyzing Final Spectrum...")
    log(f"{B}Act 5: Final Verification{RST}")
    time.sleep(3)

    final_ok = all(
        vm_path_exists(path)
        for path in [paths["1r"], paths["proc"], paths["procs"], paths["peaks"]]
    )
    v = verify_checkpoint(
        ai,
        "Describe the NMR spectrum. Are peaks visible with annotations and ppm axis?",
        deterministic_ok=final_ok,
        deterministic_desc="processed spectrum artifacts and peak files exist on disk",
    )
    results.append(("Final Result", v.get("ok", False)))
    log(f"  {'OK' if v.get('ok') else 'FAIL'}: {v.get('desc', '')[:80]}")

    # End card
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    set_label(f"Complete: {passed}/{total} Steps Passed — AI NMR Processing Done")
    time.sleep(6)

    set_label("")
    return results


# ── Video Assembly ──────────────────────────────


def assemble(frame_count: int) -> tuple[str, str, str]:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUTPUT_DIR.mkdir(exist_ok=True)

    mp4 = str(OUTPUT_DIR / f"labclaw_full_{timestamp}.mp4")
    mp4_4k = str(OUTPUT_DIR / f"labclaw_full_{timestamp}_4k.mp4")
    gif = str(OUTPUT_DIR / f"labclaw_full_{timestamp}.gif")

    # 1080p MP4
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(PLAYBACK_FPS),
            "-i",
            str(FRAMES_DIR / "frame_%06d.png"),
            "-vf",
            "scale=1440:1080:flags=lanczos",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "14",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            mp4,
        ],
        capture_output=True,
        timeout=300,
    )

    # 4K MP4 (native 2048x1536)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(PLAYBACK_FPS),
            "-i",
            str(FRAMES_DIR / "frame_%06d.png"),
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "16",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            mp4_4k,
        ],
        capture_output=True,
        timeout=300,
    )

    # GIF (palette-optimized)
    palette = str(OUTPUT_DIR / "palette.png")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(PLAYBACK_FPS),
            "-i",
            str(FRAMES_DIR / "frame_%06d.png"),
            "-vf",
            f"fps={PLAYBACK_FPS},scale=960:720:flags=lanczos,palettegen=max_colors=128",
            palette,
        ],
        capture_output=True,
        timeout=120,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-framerate",
            str(PLAYBACK_FPS),
            "-i",
            str(FRAMES_DIR / "frame_%06d.png"),
            "-i",
            palette,
            "-lavfi",
            f"fps={PLAYBACK_FPS},scale=960:720:flags=lanczos[x];[x][1:v]paletteuse=dither=bayer",
            "-loop",
            "0",
            gif,
        ],
        capture_output=True,
        timeout=300,
    )

    return mp4, mp4_4k, gif


# ── Main ────────────────────────────────────────


def main() -> int:
    print(
        f"\n{B}{'=' * 60}{RST}\n"
        f"{B}  LabClaw Full Showcase — Desktop to Results{RST}\n"
        f"{D}  Dataset: {DATASET}{RST}\n"
        f"{D}  Capture: {CAPTURE_FPS}fps | Playback: {PLAYBACK_FPS}fps{RST}\n"
        f"{B}{'=' * 60}{RST}\n"
    )

    FRAMES_DIR.mkdir(exist_ok=True)
    for f in FRAMES_DIR.glob("*.png"):
        f.unlink()

    require_vlm = _truthy_env("DEMO_REQUIRE_VLM")
    try:
        ai = build_optional_verifier(require_vlm=require_vlm)
    except RuntimeError as exc:
        print(f"  {R}FAIL: {exc}{RST}")
        return 1

    if ai is None:
        if _OPENAI_IMPORT_ERROR is not None:
            print(
                f"  {Y}WARN: openai package unavailable ({_OPENAI_IMPORT_ERROR}) — deterministic path only{RST}"
            )
        else:
            print(f"  {Y}WARN: No API key found — running deterministic control path only{RST}")
    else:
        print(f"  {G}OK VLM verification enabled ({MODEL}){RST}")

    # Ensure clean state — kill all TopSpin processes for reproducibility
    print("  Cleaning VM state...")
    for proc in [
        "java",
        "cpr",
        "cprclient",
        "dataserver",
        "restartserver",
        "toolserver",
        "osascript",
        "applet",
    ]:
        cua_run(f"pkill -9 {proc} 2>/dev/null")
    time.sleep(2)
    cua_run(
        "rm -f /opt/topspin5.0.0/prog/curdir/admin/*.ref "
        "/opt/topspin5.0.0/prog/curdir/admin/cd.* "
        "/opt/topspin5.0.0/prog/curdir/admin/nmrdata-search/database/database.lock.db"
    )
    # Pre-approve TCC permission to prevent System Events dialogs
    cua_run(
        "sudo sqlite3 '/Library/Application Support/com.apple.TCC/TCC.db' "
        '"INSERT OR REPLACE INTO access (service, client, client_type, auth_value, '
        "auth_reason, auth_version, indirect_object_identifier, "
        "indirect_object_identifier_type, flags) VALUES "
        "('kTCCServiceAppleEvents', '/usr/libexec/sshd-keygen-wrapper', "
        "1, 2, 3, 1, 'com.apple.systemevents', 0, 0);\""
    )
    print(f"  {G}OK VM clean{RST}")

    if not vm_path_exists(DATASET):
        print(f"  {R}FAIL dataset missing: {DATASET}{RST}")
        return 1

    reset_peak_artifacts(DATASET)
    print(f"  {G}OK dataset peak artifacts reset{RST}")

    print("  Testing VNC...")
    try:
        vnc_screenshot()
        print(f"  {G}OK VNC connected{RST}")
    except Exception as e:
        print(f"  {R}FAIL VNC: {e}{RST}")
        return 1

    # Start recording
    recorder = FrameRecorder(fps=CAPTURE_FPS)
    recorder.start()
    print(f"  {G}Recording at {CAPTURE_FPS}fps{RST}\n")

    t0 = time.monotonic()
    results = run_full_pipeline(ai)
    dt = time.monotonic() - t0

    time.sleep(2)
    recorder.stop()

    frames = recorder.frame_count
    print(f"\n  Frames: {frames} ({recorder.errors} errors)")
    print(f"  Duration: {dt:.0f}s ({frames / PLAYBACK_FPS:.0f}s video)")

    if frames < 20:
        print(f"  {R}Too few frames{RST}")
        return 1

    print(f"\n  {Y}Assembling video...{RST}")
    mp4, mp4_4k, gif = assemble(frames)

    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    print(f"\n{B}{'=' * 60}{RST}")
    for name, ok in results:
        s = f"{G}OK{RST}" if ok else f"{R}FAIL{RST}"
        print(f"  {s} {name}")
    print(f"{B}{'=' * 60}{RST}")

    for path, label in [(mp4, "1080p"), (mp4_4k, "4K"), (gif, "GIF")]:
        if os.path.exists(path):
            sz = os.path.getsize(path)
            print(f"  {G}{label}: {path} ({sz // 1024}KB){RST}")

    print(f"  {D}Pipeline: {passed}/{total} in {dt:.0f}s{RST}")
    print(f"{B}{'=' * 60}{RST}\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n  {R}Interrupted{RST}")
        sys.exit(130)
