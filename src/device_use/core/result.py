"""AgentResult — final output of a DeviceAgent.execute() run."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

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

    @model_validator(mode="after")
    def _check_consistency(self) -> AgentResult:
        if not self.success and not self.error:
            self.error = "Unknown failure"
        return self

    @property
    def action_count(self) -> int:
        return len(self.actions)

    @property
    def success_rate(self) -> float:
        if not self.actions:
            return 1.0 if self.success else 0.0
        return sum(1 for a in self.actions if a.success) / len(self.actions)
