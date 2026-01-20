"""
Observation models for the playtester.

Observations capture the state of the browser at a given point in time.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path


@dataclass
class ConsoleEvent:
    """A single console event from the browser."""

    timestamp: str  # ISO format
    level: str  # 'log', 'warn', 'error', 'info', 'debug'
    text: str
    location: Optional[str] = None  # URL:line:column if available

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'ConsoleEvent':
        return ConsoleEvent(**data)


@dataclass
class DOMMetadata:
    """
    Minimal DOM metadata for the current page.

    NOTE: This is intentionally minimal for the MVP.
    Future versions may include:
    - Interactive element positions
    - Accessibility tree
    - Canvas/WebGL context info
    - Network activity
    """

    url: str
    title: str
    viewport_width: int
    viewport_height: int
    visible_text_length: int = 0  # Placeholder for future text extraction

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'DOMMetadata':
        return DOMMetadata(**data)


@dataclass
class Observation:
    """
    Complete observation of the browser state at a point in time.

    This is the primary data structure passed to controllers and logged
    in trajectories. All observations must be fully serializable.
    """

    step: int
    timestamp: str  # ISO format
    screenshot_path: str  # Relative to trajectory output directory
    console_events: List[ConsoleEvent] = field(default_factory=list)
    dom_metadata: Optional[DOMMetadata] = None

    # Extension point for future observation types
    # (e.g., performance metrics, network logs, etc.)
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize observation to dictionary for logging."""
        return {
            "step": self.step,
            "timestamp": self.timestamp,
            "screenshot_path": self.screenshot_path,
            "console_events": [event.to_dict() for event in self.console_events],
            "dom_metadata": self.dom_metadata.to_dict() if self.dom_metadata else None,
            "extra": self.extra
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'Observation':
        """Deserialize observation from dictionary."""
        return Observation(
            step=data["step"],
            timestamp=data["timestamp"],
            screenshot_path=data["screenshot_path"],
            console_events=[
                ConsoleEvent.from_dict(event) for event in data.get("console_events", [])
            ],
            dom_metadata=(
                DOMMetadata.from_dict(data["dom_metadata"])
                if data.get("dom_metadata")
                else None
            ),
            extra=data.get("extra", {})
        )

    @staticmethod
    def create_timestamp() -> str:
        """Generate a standardized timestamp string."""
        return datetime.utcnow().isoformat() + "Z"
