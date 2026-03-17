"""Action models — typed representations of GUI actions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from device_use.core.models import ActionType


class BaseAction(BaseModel):
    """Base for all GUI actions."""

    model_config = ConfigDict(extra="ignore")

    action_type: ActionType
    description: str = ""


class ClickAction(BaseAction):
    action_type: ActionType = ActionType.CLICK
    x: int
    y: int
    button: Literal["left", "right", "middle"] = "left"


class DoubleClickAction(BaseAction):
    action_type: ActionType = ActionType.DOUBLE_CLICK
    x: int
    y: int


class RightClickAction(BaseAction):
    action_type: ActionType = ActionType.RIGHT_CLICK
    x: int
    y: int


class TypeAction(BaseAction):
    action_type: ActionType = ActionType.TYPE
    text: str
    interval: float = 0.02  # seconds between keystrokes


class HotkeyAction(BaseAction):
    action_type: ActionType = ActionType.HOTKEY
    keys: list[str]  # e.g. ["ctrl", "s"]


class ScrollAction(BaseAction):
    action_type: ActionType = ActionType.SCROLL
    x: int
    y: int
    clicks: int  # positive = up, negative = down


class DragAction(BaseAction):
    action_type: ActionType = ActionType.DRAG
    start_x: int
    start_y: int
    end_x: int
    end_y: int
    duration: float = 0.5  # seconds


class WaitAction(BaseAction):
    action_type: ActionType = ActionType.WAIT
    seconds: float = 1.0


class ScreenshotAction(BaseAction):
    action_type: ActionType = ActionType.SCREENSHOT


class MoveAction(BaseAction):
    action_type: ActionType = ActionType.MOVE
    x: int
    y: int


# Union type for dispatch
Action = (
    ClickAction
    | DoubleClickAction
    | RightClickAction
    | TypeAction
    | HotkeyAction
    | ScrollAction
    | DragAction
    | WaitAction
    | ScreenshotAction
    | MoveAction
)


def parse_action(data: dict) -> Action:
    """Parse a dict into the appropriate Action subclass."""
    data = dict(data)  # defensive copy

    # Normalize "type" -> "action_type" (VLMs vary)
    action_type = ActionType(data.get("action_type", data.get("type", "")))
    data["action_type"] = action_type.value

    # Flatten nested "parameters" dict (OpenAI backend format)
    params = data.pop("parameters", None)
    if isinstance(params, dict):
        for k, v in params.items():
            data.setdefault(k, v)

    # Normalize "coordinates": [x, y] -> "x", "y" (VLM prompt format)
    coords = data.get("coordinates")
    if isinstance(coords, (list, tuple)) and len(coords) == 2:
        data.setdefault("x", int(coords[0]))
        data.setdefault("y", int(coords[1]))

    type_map: dict[ActionType, type[BaseAction]] = {
        ActionType.CLICK: ClickAction,
        ActionType.DOUBLE_CLICK: DoubleClickAction,
        ActionType.RIGHT_CLICK: RightClickAction,
        ActionType.TYPE: TypeAction,
        ActionType.HOTKEY: HotkeyAction,
        ActionType.SCROLL: ScrollAction,
        ActionType.DRAG: DragAction,
        ActionType.WAIT: WaitAction,
        ActionType.SCREENSHOT: ScreenshotAction,
        ActionType.MOVE: MoveAction,
    }
    cls = type_map.get(action_type)
    if cls is None:
        raise ValueError(f"Unknown action type: {action_type}")
    return cls(**data)
