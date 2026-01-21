"""
Base controller interface.

Controllers implement the decision-making logic for the agent.
They observe the browser state and select actions to take.
"""

from abc import ABC, abstractmethod
from typing import Optional

from ..core.observation import Observation
from ..core.action import Action


class Controller(ABC):
    """
    Abstract base class for all controllers.

    Controllers are stateful and deterministic (given a seed).
    They should not directly access the browser - all interaction
    goes through the observation → action interface.

    Design principles:
    - Controllers are PURE: same observation sequence → same action sequence
    - Controllers do NOT have side effects (no direct browser access)
    - Controllers can maintain internal state (step count, history, etc.)
    - Controllers must be serializable (for checkpointing/replay)
    """

    def __init__(self, seed: Optional[int] = None):
        """
        Initialize controller.

        Args:
            seed: Random seed for deterministic behavior
        """
        self.seed = seed
        self.step_count = 0

    @abstractmethod
    def select_action(self, observation: Observation) -> Action:
        """
        Select an action based on the current observation.

        This is the core decision-making method that all controllers must implement.

        Args:
            observation: Current browser state

        Returns:
            Action to execute
        """
        pass

    def reset(self) -> None:
        """
        Reset controller state.

        Called at the start of a new episode. Override if controller
        maintains state that should be cleared between episodes.
        """
        self.step_count = 0

    def on_action_executed(self, action: Action) -> None:
        """
        Hook called after an action is executed.

        Override this to update internal state based on actions taken.

        Args:
            action: Action that was just executed
        """
        self.step_count += 1
