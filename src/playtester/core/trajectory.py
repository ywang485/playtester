"""
Trajectory logging system for the playtester.

Trajectories are append-only JSONL files that record the complete sequence
of observations and actions during a playtest session. This format enables:
- Streaming writes during long sessions
- Easy parsing and analysis
- Reproducibility and debugging
- Version control friendly diffs
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from .observation import Observation
from .action import Action

logger = logging.getLogger(__name__)


class TrajectoryLogger:
    """
    Append-only logger for playtest trajectories.

    File format: JSONL (JSON Lines) with versioned schema
    Each line is a JSON object with a "type" field indicating the entry type.

    Entry types:
    - "metadata": Session metadata (first line only)
    - "observation": Observation at step N
    - "action": Action taken after step N
    - "event": Other notable events (errors, controller switches, etc.)
    """

    SCHEMA_VERSION = "1.0.0"

    def __init__(self, output_dir: Path, session_id: Optional[str] = None):
        """
        Initialize trajectory logger.

        Args:
            output_dir: Directory to store trajectory file and artifacts
            session_id: Optional session identifier (generated if not provided)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.session_id = session_id or self._generate_session_id()
        self.trajectory_path = self.output_dir / "trajectory.jsonl"
        self.screenshots_dir = self.output_dir / "screenshots"
        self.screenshots_dir.mkdir(exist_ok=True)

        self._initialized = False
        logger.info(f"TrajectoryLogger initialized: {self.trajectory_path}")

    @staticmethod
    def _generate_session_id() -> str:
        """Generate a unique session identifier."""
        return datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    def initialize(self, metadata: Dict[str, Any]) -> None:
        """
        Write initial metadata entry to trajectory file.

        This should be called once at the start of a session.

        Args:
            metadata: Session metadata (URL, config, etc.)
        """
        if self._initialized:
            logger.warning("TrajectoryLogger already initialized")
            return

        entry = {
            "type": "metadata",
            "schema_version": self.SCHEMA_VERSION,
            "session_id": self.session_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "metadata": metadata
        }

        self._append_entry(entry)
        self._initialized = True
        logger.info(f"Trajectory initialized for session: {self.session_id}")

    def log_observation(self, observation: Observation) -> None:
        """
        Log an observation to the trajectory.

        Args:
            observation: Observation to log
        """
        if not self._initialized:
            logger.warning("Logging observation before initialization")

        entry = {
            "type": "observation",
            "data": observation.to_dict()
        }

        self._append_entry(entry)
        logger.debug(f"Logged observation for step {observation.step}")

    def log_action(self, action: Action, step: int) -> None:
        """
        Log an action to the trajectory.

        Args:
            action: Action to log
            step: Step number when action was taken
        """
        if not self._initialized:
            logger.warning("Logging action before initialization")

        entry = {
            "type": "action",
            "step": step,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": action.to_dict()
        }

        self._append_entry(entry)
        logger.debug(f"Logged {action.action_type} action for step {step}")

    def log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        Log a notable event to the trajectory.

        Use this for non-action/observation events like errors, state changes,
        controller switches, or other notable occurrences.

        Args:
            event_type: Type of event (e.g., 'error', 'controller_change')
            data: Event data
        """
        entry = {
            "type": "event",
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "data": data
        }

        self._append_entry(entry)
        logger.info(f"Logged event: {event_type}")

    def _append_entry(self, entry: Dict[str, Any]) -> None:
        """
        Append a JSON entry to the trajectory file.

        Args:
            entry: Dictionary to serialize and append
        """
        with open(self.trajectory_path, "a") as f:
            f.write(json.dumps(entry, separators=(',', ':')) + "\n")

    def get_screenshot_path(self, step: int, relative: bool = True) -> Path:
        """
        Generate a screenshot path for a given step.

        Args:
            step: Step number
            relative: If True, return path relative to output_dir

        Returns:
            Path to screenshot file
        """
        filename = f"step_{step:04d}.png"
        full_path = self.screenshots_dir / filename

        if relative:
            return Path("screenshots") / filename
        else:
            return full_path

    def finalize(self, metadata: Optional[Dict[str, Any]] = None) -> None:
        """
        Write final metadata entry to trajectory file.

        Args:
            metadata: Optional final metadata (total steps, outcome, etc.)
        """
        entry = {
            "type": "finalize",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "metadata": metadata or {}
        }

        self._append_entry(entry)
        logger.info(f"Trajectory finalized: {self.trajectory_path}")

    def generate_issue_summary(self) -> Dict[str, Any]:
        """
        Generate a summary of all issues detected during the session.

        Returns:
            Dictionary with issue counts and details
        """
        summary = {
            "crashes": 0,
            "webgl_context_lost": 0,
            "soft_locks": 0,
            "focus_issues": 0,
            "ui_deadends": 0,
            "performance_issues": 0,
            "network_failures": 0,
            "total_issues": 0,
            "steps_with_issues": []
        }

        try:
            with open(self.trajectory_path, "r") as f:
                for line in f:
                    entry = json.loads(line)
                    if entry.get("type") == "observation":
                        data = entry.get("data", {})
                        issues = data.get("issues")
                        if issues:
                            step = data.get("step")

                            if issues.get("page_error") or issues.get("webgl_context_lost"):
                                summary["crashes"] += 1
                                summary["steps_with_issues"].append(step)

                            if issues.get("webgl_context_lost"):
                                summary["webgl_context_lost"] += 1

                            if issues.get("state_unchanged_for_steps", 0) > 10:
                                summary["soft_locks"] += 1
                                summary["steps_with_issues"].append(step)

                            if issues.get("focus_lost"):
                                summary["focus_issues"] += 1

                            if issues.get("modal_detected") or issues.get("overlay_blocking"):
                                summary["ui_deadends"] += 1

                            if issues.get("long_task_detected") or (issues.get("frame_time_ms") or 0) > 100:
                                summary["performance_issues"] += 1

                            if issues.get("http_errors") or issues.get("asset_load_failures"):
                                summary["network_failures"] += 1

            summary["total_issues"] = (
                summary["crashes"] +
                summary["soft_locks"] +
                summary["ui_deadends"] +
                summary["performance_issues"] +
                summary["network_failures"]
            )
        except Exception as e:
            logger.error(f"Failed to generate issue summary: {e}")

        return summary
