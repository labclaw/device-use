"""SkillContext — assembles layered system prompts for device agents.

Reads from device-skills repository to build a complete system prompt with:
    Layer 1: Device identity (SOUL.md) + GUI profile (profile.yaml)
    Layer 2: Scientific domain knowledge (science.md)
    Layer 3: Dynamic RAG retrieval (task-specific docs)
    Layer 4: User context (from labclaw, optional)
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Token budgets (approximate chars, ~4 chars/token)
_L1_BUDGET = 8000  # ~2000 tokens for device identity
_L2_BUDGET = 3000  # ~750 tokens for science domain
_L3_BUDGET = 6000  # ~1500 tokens for RAG docs
_L4_BUDGET = 2000  # ~500 tokens for user context


def _truncate(text: str, max_chars: int) -> str:
    """Truncate text to max_chars at a paragraph boundary if possible."""
    if len(text) <= max_chars:
        return text
    # Try to break at paragraph
    cut = text[:max_chars].rfind("\n\n")
    if cut > max_chars // 2:
        return text[:cut] + "\n\n[... truncated]"
    return text[:max_chars] + "\n\n[... truncated]"


def _distill_profile(profile: dict) -> str:
    """Extract key operational info from profile.yaml into readable text."""
    parts: list[str] = []

    software = profile.get("software", "")
    if software:
        parts.append(f"Software: {software}")

    commands = profile.get("commands", {})
    if commands:
        cmd_lines = [f"  - {name}: `{cmd}`" for name, cmd in commands.items()]
        parts.append("Available commands:\n" + "\n".join(cmd_lines))

    command_bar = profile.get("command_bar", {})
    if command_bar:
        loc = command_bar.get("location", "")
        key = command_bar.get("submit_key", "")
        if loc or key:
            parts.append(f"Command bar: {loc}, submit with {key}")

    delays = profile.get("delays", {})
    if delays:
        delay_lines = [f"  - {name}: {val}s" for name, val in delays.items()]
        parts.append("Processing delays:\n" + "\n".join(delay_lines))

    safety = profile.get("safety", {})
    forbidden = safety.get("forbidden_commands", [])
    if forbidden:
        parts.append(f"FORBIDDEN commands (never use): {', '.join(forbidden)}")

    return "\n".join(parts)


class SkillContext:
    """Assembles layered system prompts for device agents.

    Usage::

        ctx = SkillContext("bruker-topspin")
        prompt = ctx.build_prompt("Process the 1H NMR spectrum")
        # prompt contains SOUL.md + profile + science + relevant docs
    """

    def __init__(
        self,
        device_name: str,
        skills_dir: Path | None = None,
    ) -> None:
        if skills_dir is None:
            # Default: monorepo layout — device-skills is sibling of device-use
            skills_dir = Path(__file__).resolve().parents[4] / "device-skills"

        self.device_name = device_name
        self.skills_dir = skills_dir
        self.device_dir = skills_dir / "devices" / device_name

        if not self.device_dir.exists():
            raise FileNotFoundError(f"Device '{device_name}' not found at {self.device_dir}")

        # Layer 1: SOUL.md (required) + profile.yaml (optional)
        soul_path = self.device_dir / "SOUL.md"
        if not soul_path.exists():
            raise FileNotFoundError(f"SOUL.md not found at {soul_path}")
        self.soul = soul_path.read_text(encoding="utf-8")

        profile_path = self.device_dir / "profile.yaml"
        if profile_path.exists():
            self.profile: dict | None = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
        else:
            self.profile = None
            logger.debug("No profile.yaml for %s", device_name)

        # Layer 2: science.md (optional)
        science_path = self.device_dir / "science.md"
        if science_path.exists():
            self.science = science_path.read_text(encoding="utf-8")
        else:
            self.science = None
            logger.debug("No science.md for %s", device_name)

    def build_prompt(
        self,
        task: str = "",
        user_context: str = "",
    ) -> str:
        """Assemble a complete system prompt from all available layers.

        Args:
            task: Natural language task description (used for RAG retrieval).
            user_context: Optional user-specific context (Layer 4).

        Returns:
            Complete system prompt string.
        """
        sections: list[str] = []

        # --- Layer 1: Device Identity ---
        l1 = f"# Device: {self.device_name}\n\n{self.soul}"
        if self.profile:
            l1 += f"\n\n## Operational Profile\n\n{_distill_profile(self.profile)}"
        sections.append(_truncate(l1, _L1_BUDGET))

        # --- Layer 2: Scientific Domain ---
        if self.science:
            sections.append(
                _truncate(
                    f"# Scientific Domain Knowledge\n\n{self.science}",
                    _L2_BUDGET,
                )
            )

        # --- Layer 3: Dynamic RAG ---
        if task:
            try:
                from device_use.knowledge.retriever import retrieve_docs

                docs = retrieve_docs(
                    self.device_name,
                    task,
                    skills_dir=self.skills_dir,
                )
                if docs:
                    sections.append(_truncate(docs, _L3_BUDGET))
            except Exception:
                logger.debug(
                    "RAG retrieval failed for %s",
                    self.device_name,
                    exc_info=True,
                )

        # --- Layer 4: User Context ---
        if user_context:
            sections.append(
                _truncate(
                    f"# User Context\n\n{user_context}",
                    _L4_BUDGET,
                )
            )

        return "\n\n---\n\n".join(sections)
