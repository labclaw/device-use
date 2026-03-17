"""Tests for SkillContext 4-layer system."""

from __future__ import annotations

import textwrap
from unittest.mock import patch

import pytest

from device_use.skills.context import SkillContext, _distill_profile, _truncate

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def skills_dir(tmp_path):
    """Create a minimal device-skills directory structure."""
    device_dir = tmp_path / "devices" / "test-device"
    device_dir.mkdir(parents=True)

    # SOUL.md (required)
    (device_dir / "SOUL.md").write_text(
        "# Test Device\nYou are a test instrument operator.",
        encoding="utf-8",
    )

    # profile.yaml (optional)
    (device_dir / "profile.yaml").write_text(
        textwrap.dedent("""\
        software: TestApp 2.0
        commands:
          process: proc
          transform: ft
        command_bar:
          location: bottom
          submit_key: Enter
        delays:
          processing: 2
          save: 1
        safety:
          forbidden_commands:
            - format_disk
            - rm_rf
        """),
        encoding="utf-8",
    )

    # science.md (optional)
    (device_dir / "science.md").write_text(
        "# Science\nTest science domain knowledge.",
        encoding="utf-8",
    )

    return tmp_path


@pytest.fixture
def minimal_skills_dir(tmp_path):
    """Create a skills dir with only required files (SOUL.md, no profile/science)."""
    device_dir = tmp_path / "devices" / "minimal-device"
    device_dir.mkdir(parents=True)
    (device_dir / "SOUL.md").write_text(
        "# Minimal\nBasic device.",
        encoding="utf-8",
    )
    return tmp_path


# ---------------------------------------------------------------------------
# _truncate helper
# ---------------------------------------------------------------------------


class TestTruncate:
    def test_short_text_unchanged(self):
        text = "Hello world"
        assert _truncate(text, 100) == text

    def test_exact_length_unchanged(self):
        text = "x" * 50
        assert _truncate(text, 50) == text

    def test_truncate_at_paragraph(self):
        text = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        result = _truncate(text, 40)
        assert result.endswith("[... truncated]")
        assert "First paragraph." in result

    def test_truncate_no_good_paragraph_break(self):
        text = "A" * 200
        result = _truncate(text, 50)
        assert len(result) == 50 + len("\n\n[... truncated]")
        assert result.endswith("[... truncated]")

    def test_truncate_empty_string(self):
        assert _truncate("", 100) == ""


# ---------------------------------------------------------------------------
# _distill_profile helper
# ---------------------------------------------------------------------------


class TestDistillProfile:
    def test_empty_profile(self):
        assert _distill_profile({}) == ""

    def test_software_only(self):
        result = _distill_profile({"software": "TopSpin 5.0"})
        assert result == "Software: TopSpin 5.0"

    def test_commands(self):
        profile = {"commands": {"process": "proc", "transform": "ft"}}
        result = _distill_profile(profile)
        assert "Available commands:" in result
        assert "process: `proc`" in result
        assert "transform: `ft`" in result

    def test_command_bar(self):
        profile = {"command_bar": {"location": "bottom", "submit_key": "Enter"}}
        result = _distill_profile(profile)
        assert "Command bar: bottom, submit with Enter" in result

    def test_delays(self):
        profile = {"delays": {"processing": 2, "save": 1}}
        result = _distill_profile(profile)
        assert "Processing delays:" in result
        assert "processing: 2s" in result

    def test_safety_forbidden(self):
        profile = {"safety": {"forbidden_commands": ["rm", "format"]}}
        result = _distill_profile(profile)
        assert "FORBIDDEN" in result
        assert "rm" in result
        assert "format" in result

    def test_full_profile(self):
        profile = {
            "software": "TestApp",
            "commands": {"run": "go"},
            "command_bar": {"location": "top", "submit_key": "Return"},
            "delays": {"startup": 5},
            "safety": {"forbidden_commands": ["danger"]},
        }
        result = _distill_profile(profile)
        assert "Software: TestApp" in result
        assert "Available commands:" in result
        assert "Command bar:" in result
        assert "Processing delays:" in result
        assert "FORBIDDEN" in result


# ---------------------------------------------------------------------------
# SkillContext initialization
# ---------------------------------------------------------------------------


class TestSkillContextInit:
    def test_init_full(self, skills_dir):
        ctx = SkillContext("test-device", skills_dir=skills_dir)
        assert ctx.device_name == "test-device"
        assert ctx.soul.startswith("# Test Device")
        assert ctx.profile is not None
        assert ctx.profile["software"] == "TestApp 2.0"
        assert ctx.science is not None

    def test_init_minimal(self, minimal_skills_dir):
        ctx = SkillContext("minimal-device", skills_dir=minimal_skills_dir)
        assert ctx.device_name == "minimal-device"
        assert ctx.soul == "# Minimal\nBasic device."
        assert ctx.profile is None
        assert ctx.science is None

    def test_init_device_not_found(self, tmp_path):
        (tmp_path / "devices").mkdir()
        with pytest.raises(FileNotFoundError, match="not found"):
            SkillContext("nonexistent", skills_dir=tmp_path)

    def test_init_no_soul(self, tmp_path):
        device_dir = tmp_path / "devices" / "no-soul"
        device_dir.mkdir(parents=True)
        with pytest.raises(FileNotFoundError, match="SOUL.md"):
            SkillContext("no-soul", skills_dir=tmp_path)

    def test_device_dir_path(self, skills_dir):
        ctx = SkillContext("test-device", skills_dir=skills_dir)
        assert ctx.device_dir == skills_dir / "devices" / "test-device"


# ---------------------------------------------------------------------------
# SkillContext.build_prompt
# ---------------------------------------------------------------------------


class TestSkillContextBuildPrompt:
    def test_build_prompt_full(self, skills_dir):
        ctx = SkillContext("test-device", skills_dir=skills_dir)
        prompt = ctx.build_prompt()
        # L1: device identity
        assert "# Device: test-device" in prompt
        assert "You are a test instrument operator" in prompt
        # L1: profile
        assert "Operational Profile" in prompt
        assert "Software: TestApp 2.0" in prompt
        # L2: science
        assert "Scientific Domain Knowledge" in prompt
        assert "Test science domain knowledge" in prompt

    def test_build_prompt_minimal(self, minimal_skills_dir):
        ctx = SkillContext("minimal-device", skills_dir=minimal_skills_dir)
        prompt = ctx.build_prompt()
        assert "# Device: minimal-device" in prompt
        assert "Basic device." in prompt
        # No profile or science sections
        assert "Operational Profile" not in prompt
        assert "Scientific Domain" not in prompt

    def test_build_prompt_with_user_context(self, skills_dir):
        ctx = SkillContext("test-device", skills_dir=skills_dir)
        prompt = ctx.build_prompt(user_context="User prefers metric units")
        assert "# User Context" in prompt
        assert "User prefers metric units" in prompt

    def test_build_prompt_no_user_context(self, skills_dir):
        ctx = SkillContext("test-device", skills_dir=skills_dir)
        prompt = ctx.build_prompt(user_context="")
        assert "User Context" not in prompt

    def test_build_prompt_sections_separated(self, skills_dir):
        ctx = SkillContext("test-device", skills_dir=skills_dir)
        prompt = ctx.build_prompt()
        assert "\n\n---\n\n" in prompt

    def test_build_prompt_rag_failure_graceful(self, skills_dir):
        """RAG retrieval failure should not crash build_prompt."""
        ctx = SkillContext("test-device", skills_dir=skills_dir)
        # The import of retrieve_docs happens inline; an ImportError is caught
        # by the bare except. Just call with a task — if retriever doesn't exist
        # it will fail gracefully.
        prompt = ctx.build_prompt(task="process spectrum")
        assert "# Device: test-device" in prompt

    def test_build_prompt_rag_returns_docs(self, skills_dir):
        """When RAG retrieval succeeds, docs are included in prompt."""
        ctx = SkillContext("test-device", skills_dir=skills_dir)
        with patch(
            "device_use.knowledge.retriever.retrieve_docs",
            return_value="## Relevant Docs\nHow to process NMR spectra.",
            create=True,
        ):
            prompt = ctx.build_prompt(task="process spectrum")
            assert "Relevant Docs" in prompt

    def test_build_prompt_rag_skipped_no_task(self, skills_dir):
        """RAG is not attempted when task is empty."""
        ctx = SkillContext("test-device", skills_dir=skills_dir)
        with patch(
            "device_use.knowledge.retriever.retrieve_docs",
            side_effect=AssertionError("should not be called"),
            create=True,
        ):
            # No task = no RAG attempt
            prompt = ctx.build_prompt(task="")
            assert "# Device: test-device" in prompt

    def test_build_prompt_safety_info_included(self, skills_dir):
        ctx = SkillContext("test-device", skills_dir=skills_dir)
        prompt = ctx.build_prompt()
        assert "FORBIDDEN" in prompt
        assert "format_disk" in prompt

    def test_build_prompt_truncation(self, tmp_path):
        """Long SOUL.md gets truncated to L1 budget."""
        device_dir = tmp_path / "devices" / "long-soul"
        device_dir.mkdir(parents=True)
        # Write a SOUL.md that exceeds L1 budget (8000 chars)
        long_text = "A" * 10000
        (device_dir / "SOUL.md").write_text(long_text, encoding="utf-8")

        ctx = SkillContext("long-soul", skills_dir=tmp_path)
        prompt = ctx.build_prompt()
        # Should be truncated
        assert "[... truncated]" in prompt
        assert len(prompt) < 10000
