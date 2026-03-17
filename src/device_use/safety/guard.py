"""SafetyGuard — chains all 5 safety layers."""

from __future__ import annotations

import time
from collections import deque

from device_use.core.models import ActionRequest, DeviceProfile
from device_use.safety.layers import (
    ActionWhitelistChecker,
    EmergencyStopMonitor,
    HumanConfirmationGate,
    ParameterBoundsChecker,
    StateVerificationChecker,
)
from device_use.safety.models import SafetyConfig, SafetyVerdict


class SafetyGuard:
    """Chains all 5 safety layers. Wired into the executor, not the agent loop."""

    def __init__(
        self,
        profile: DeviceProfile,
        config: SafetyConfig | None = None,
        auto_approve: bool = False,
    ) -> None:
        # Determine config from profile if not provided
        if config is None:
            config = SafetyConfig(
                level=profile.safety_level,
                hardware_connected=profile.hardware_connected,
            )
        self.config = config
        self.profile = profile

        # Build layer chain — L5 emergency stop FIRST (kill switch must preempt all)
        self._layers: list = []
        if config.hardware_connected:
            self._layers.append(EmergencyStopMonitor())  # L5 — checked first
        self._layers.append(ActionWhitelistChecker())  # L1 always active
        if config.hardware_connected:
            self._layers.append(ParameterBoundsChecker())  # L2
            self._layers.append(StateVerificationChecker())  # L3
            self._layers.append(
                HumanConfirmationGate(  # L4
                    auto_approve=auto_approve,
                )
            )

        # 10K-entry action history deque for rate limiting
        self._history: deque[float] = deque(maxlen=10_000)

    def check(self, action: ActionRequest) -> SafetyVerdict:
        """Run safety layers (L5 kill switch first, then L1->L4).

        Short-circuit on first rejection.
        """
        # Check rate limit — prune expired entries from left (deque is time-ordered)
        now = time.monotonic()
        cutoff = now - 60.0
        while self._history and self._history[0] <= cutoff:
            self._history.popleft()
        recent_count = len(self._history)
        if recent_count >= self.profile.safety.max_actions_per_minute:
            return SafetyVerdict(
                allowed=False,
                layer="rate_limit",
                reason=(
                    f"Rate limit exceeded: {recent_count} actions in last 60s "
                    f"(max {self.profile.safety.max_actions_per_minute})"
                ),
            )

        # Run through each layer
        for layer in self._layers:
            verdict = layer.check(action, self.profile, self.config)
            if not verdict.allowed:
                return verdict

        return SafetyVerdict(allowed=True)

    def record_action(self, action: ActionRequest) -> None:
        """Add to history deque with timestamp."""
        self._history.append(time.monotonic())
