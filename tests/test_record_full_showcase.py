"""Regression tests for the deterministic full-showcase demo path."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def _load_demo_module():
    demo_path = Path(__file__).parent.parent / "demos" / "record_full_showcase.py"
    spec = importlib.util.spec_from_file_location("record_full_showcase_test", demo_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_optional_verifier_returns_none_without_key(monkeypatch):
    demo = _load_demo_module()
    monkeypatch.setattr(demo, "load_openrouter_api_key", lambda: None)
    assert demo.build_optional_verifier(require_vlm=False) is None


def test_load_openrouter_api_key_honors_disable_flag(monkeypatch):
    demo = _load_demo_module()
    monkeypatch.setenv("DEMO_DISABLE_VLM", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-live")
    assert demo.load_openrouter_api_key() is None


def test_build_optional_verifier_raises_when_required(monkeypatch):
    demo = _load_demo_module()
    monkeypatch.setattr(demo, "load_openrouter_api_key", lambda: None)
    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY required"):
        demo.build_optional_verifier(require_vlm=True)


def test_verify_checkpoint_uses_deterministic_result_without_ai():
    demo = _load_demo_module()
    result = demo.verify_checkpoint(None, "ignored", True, "deterministic ok")
    assert result == {
        "ok": True,
        "desc": "deterministic ok",
        "mode": "deterministic",
    }


def test_vncdo_raises_on_failed_command(monkeypatch):
    demo = _load_demo_module()

    class Result:
        returncode = 1
        stderr = "capture failed"
        stdout = ""

    monkeypatch.setattr(demo, "resolve_vncdo_binary", lambda: "/tmp/vncdo")
    monkeypatch.setattr(demo.subprocess, "run", lambda *args, **kwargs: Result())

    with pytest.raises(RuntimeError, match="capture failed"):
        demo._vncdo("capture", "/tmp/frame.png")


def test_resolve_vncdo_binary_prefers_env_override(monkeypatch):
    demo = _load_demo_module()
    monkeypatch.setenv("VNCDO_BIN", "/custom/vncdo")
    assert demo.resolve_vncdo_binary() == "/custom/vncdo"


def test_reset_peak_artifacts_removes_expected_files(monkeypatch):
    demo = _load_demo_module()
    calls = []
    monkeypatch.setattr(demo, "cua_run", lambda command: calls.append(command) or {"success": True})
    demo.reset_peak_artifacts("/tmp/dataset/1")
    assert len(calls) == 1
    assert "rm -f" in calls[0]
    assert "peaklist.xml" in calls[0]
    assert "peakrng" in calls[0]
    assert "peaks" in calls[0]


def test_vnc_screenshot_requires_capture_output(monkeypatch, tmp_path):
    demo = _load_demo_module()
    target = tmp_path / "frame.png"

    monkeypatch.setattr(demo, "_vncdo", lambda *args, **kwargs: object())
    monkeypatch.setattr(demo.time, "sleep", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="capture did not create"):
        demo.vnc_screenshot(str(target))
