"""
Action models for the playtester.

Actions represent atomic operations that can be performed in the browser.
All actions are serializable for trajectory logging and replay.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Dict, Any, Literal


@dataclass
class Action(ABC):
    """
    Base class for all actions.

    Actions must be:
    - Serializable (to/from dict)
    - Deterministic (same action = same result given same state)
    - Atomic (single operation)
    """

    @abstractmethod
    def to_dict(self) -> Dict[str, Any]:
        """Serialize action to dictionary for logging."""
        pass

    @staticmethod
    @abstractmethod
    def from_dict(data: Dict[str, Any]) -> 'Action':
        """Deserialize action from dictionary."""
        pass

    @property
    @abstractmethod
    def action_type(self) -> str:
        """Return the action type identifier."""
        pass


@dataclass
class WaitAction(Action):
    """Wait for a specified duration in milliseconds."""

    duration_ms: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.action_type,
            "duration_ms": self.duration_ms
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'WaitAction':
        return WaitAction(duration_ms=data["duration_ms"])

    @property
    def action_type(self) -> str:
        return "wait"


@dataclass
class ClickAction(Action):
    """Click at specified coordinates."""

    x: int
    y: int
    button: Literal["left", "right", "middle"] = "left"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.action_type,
            "x": self.x,
            "y": self.y,
            "button": self.button
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'ClickAction':
        return ClickAction(
            x=data["x"],
            y=data["y"],
            button=data.get("button", "left")
        )

    @property
    def action_type(self) -> str:
        return "click"


@dataclass
class KeypressAction(Action):
    """Press a keyboard key."""

    key: str  # Playwright key notation (e.g., 'Enter', 'ArrowUp', 'a')
    modifiers: list[Literal["Alt", "Control", "Meta", "Shift"]] = None

    def __post_init__(self):
        if self.modifiers is None:
            self.modifiers = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.action_type,
            "key": self.key,
            "modifiers": self.modifiers
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'KeypressAction':
        return KeypressAction(
            key=data["key"],
            modifiers=data.get("modifiers", [])
        )

    @property
    def action_type(self) -> str:
        return "keypress"


def action_from_dict(data: Dict[str, Any]) -> Action:
    """
    Factory function to deserialize actions from dictionaries.

    Args:
        data: Dictionary containing action type and parameters

    Returns:
        Action instance

    Raises:
        ValueError: If action type is unknown
    """
    action_type = data.get("type")

    if action_type == "wait":
        return WaitAction.from_dict(data)
    elif action_type == "click":
        return ClickAction.from_dict(data)
    elif action_type == "keypress":
        return KeypressAction.from_dict(data)
    else:
        raise ValueError(f"Unknown action type: {action_type}")
