"""Token-aware history compaction for the agent loop.

Follows Agent-S3 pattern: keep all text context, drop old screenshots.
This prevents context window overflow while preserving reasoning chain.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class HistoryEntry:
    """A single step in agent history."""

    step: int
    action: dict[str, Any]
    observation: str = ""
    reasoning: str = ""
    screenshot: bytes | None = None
    success: bool = True


class AgentHistory:
    """Manages agent conversation history with image compaction.

    Keeps latest K screenshots to bound token usage (images are expensive).
    All text (reasoning, observations) is preserved for full context.
    """

    def __init__(self, max_images: int = 5):
        self._entries: list[HistoryEntry] = []
        self._max_images = max_images

    def add(self, entry: HistoryEntry) -> None:
        """Add a step entry to history."""
        self._entries.append(entry)

    def compact(self) -> None:
        """Drop old screenshots, keeping only the latest K images.

        Text content (observations, reasoning) is never dropped.
        """
        entries_with_images = [
            i for i, e in enumerate(self._entries) if e.screenshot is not None
        ]
        if len(entries_with_images) <= self._max_images:
            return

        # Drop images from oldest entries, keep latest max_images
        to_drop = entries_with_images[: -self._max_images]
        for idx in to_drop:
            self._entries[idx].screenshot = None

    @property
    def entries(self) -> list[HistoryEntry]:
        return list(self._entries)

    @property
    def latest(self) -> HistoryEntry | None:
        return self._entries[-1] if self._entries else None

    def to_messages(self) -> list[dict[str, Any]]:
        """Convert history to message format for VLM context.

        Returns list of dicts with 'role', 'content' suitable for
        building VLM conversation context.
        """
        messages = []
        for entry in self._entries:
            content_parts: list[dict[str, Any]] = []

            # Text context (always included)
            text = f"Step {entry.step}: {entry.observation}"
            if entry.reasoning:
                text += f"\nReasoning: {entry.reasoning}"
            text += f"\nAction: {entry.action}"
            text += f"\nResult: {'success' if entry.success else 'failed'}"
            content_parts.append({"type": "text", "text": text})

            # Screenshot (only if still present after compaction)
            if entry.screenshot is not None:
                content_parts.append({
                    "type": "image",
                    "data": entry.screenshot,
                })

            messages.append({"role": "user", "content": content_parts})

        return messages

    def __len__(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
