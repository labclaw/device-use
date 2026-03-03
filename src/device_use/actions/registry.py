"""Action type → executor mapping registry."""

from __future__ import annotations

from typing import Callable

from device_use.actions.models import BaseAction
from device_use.core.models import ActionType

# Type aliases for readability
_Handler = Callable[[BaseAction], None]
_Decorator = Callable[[_Handler], _Handler]

# Registry: ActionType → handler function
_ACTION_HANDLERS: dict[ActionType, _Handler] = {}


def register_handler(action_type: ActionType) -> _Decorator:
    """Decorator to register an action handler."""

    def decorator(fn: _Handler) -> _Handler:
        _ACTION_HANDLERS[action_type] = fn
        return fn

    return decorator


def get_handler(action_type: ActionType) -> Callable[[BaseAction], None]:
    """Get the handler for an action type."""
    handler = _ACTION_HANDLERS.get(action_type)
    if handler is None:
        raise ValueError(f"No handler registered for action type: {action_type}")
    return handler


def list_registered() -> list[ActionType]:
    """List all registered action types."""
    return list(_ACTION_HANDLERS.keys())
