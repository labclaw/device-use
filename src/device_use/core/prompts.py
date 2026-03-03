"""Prompt templates for the device-use agent.

System prompts incorporate device profile information (safety constraints,
known UI elements, workflows) so the VLM operates with domain knowledge.
"""

from __future__ import annotations

from device_use.core.models import DeviceProfile


class PromptBuilder:
    """Builds prompts for VLM interactions, incorporating profile context."""

    def __init__(self, profile: DeviceProfile):
        self._profile = profile

    def system_prompt(self) -> str:
        """Build the system prompt with device/software context."""
        p = self._profile
        safety_note = (
            "CRITICAL: This software controls physical hardware. "
            "Every action has real-world consequences. "
            "Verify each action carefully before execution."
            if p.hardware_connected
            else "This is analysis software with no physical hardware attached. "
            "Actions can be undone or retried."
        )

        elements_desc = ""
        if p.ui_elements:
            elements_desc = "\n\nKnown UI elements:\n"
            for elem in p.ui_elements:
                elements_desc += f"- {elem.name}: {elem.description}\n"

        workflows_desc = ""
        if p.workflows:
            workflows_desc = "\n\nAvailable workflows:\n"
            for wf in p.workflows:
                workflows_desc += f"- {wf.name}: {wf.description}\n"

        allowed = ", ".join(a.value for a in p.allowed_actions)

        return (
            f"You are an AI agent controlling {p.software}.\n"
            f"{safety_note}\n\n"
            f"Allowed actions: {allowed}\n"
            f"Safety level: {p.safety_level.value}\n"
            f"Max actions/minute: {p.safety.max_actions_per_minute}"
            f"{elements_desc}"
            f"{workflows_desc}"
        )

    def observation_prompt(self, task: str, step: int) -> str:
        """Prompt for observing the current screen state."""
        return (
            f"Task: {task}\n"
            f"Step: {step}\n\n"
            "Describe what you see on the screen. Identify:\n"
            "1. Current state of the application\n"
            "2. Relevant UI elements visible\n"
            "3. Any dialogs, menus, or popups open\n"
            "4. Progress toward the task goal"
        )

    def planning_prompt(self, task: str, observation: str, step: int) -> str:
        """Prompt for planning the next action."""
        return (
            f"Task: {task}\n"
            f"Step: {step}\n"
            f"Current observation: {observation}\n\n"
            "Plan the next action. Respond with a JSON object:\n"
            '{\n'
            '  "reasoning": "why this action is needed",\n'
            '  "action": {\n'
            '    "action_type": "click|type|hotkey|scroll|drag|wait",\n'
            '    "coordinates": [x, y],  // for click/scroll actions\n'
            '    "text": "...",           // for type action\n'
            '    "keys": ["ctrl", "s"],   // for hotkey action\n'
            '    "description": "what this action does"\n'
            '  },\n'
            '  "done": false,\n'
            '  "confidence": 0.9\n'
            '}\n\n'
            'Set "done": true when the task is complete.\n'
            'Set "done": false and include "error" if the task cannot be completed.'
        )

    def verification_prompt(self, task: str, action_desc: str) -> str:
        """Prompt for verifying action result."""
        return (
            f"Task: {task}\n"
            f"Last action: {action_desc}\n\n"
            "Verify the action result:\n"
            "1. Did the action execute correctly?\n"
            "2. Is the application in the expected state?\n"
            "3. Any error dialogs or unexpected changes?"
        )
