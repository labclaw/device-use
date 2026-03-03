"""AgentResult — final output of a DeviceAgent.execute() run."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from device_use.core.models import ActionResult


class AgentResult(BaseModel):
    """Result of a complete agent execution run."""

    success: bool
    task: str = ""
    data: dict[str, Any] = Field(default_factory=dict)
    actions: list[ActionResult] = Field(default_factory=list)
    steps: int = 0
    duration_ms: float = 0
    error: str = ""
    final_screenshot: bytes | None = None

    @property
    def action_count(self) -> int:
        return len(self.actions)

    @property
    def success_rate(self) -> float:
        if not self.actions:
            return 0.0
        return sum(1 for a in self.actions if a.success) / len(self.actions)
