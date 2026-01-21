"""
VLM-advised controller implementation.

This controller demonstrates the proper architecture for VLM integration:
- The VLM is an ADVISOR, not a driver
- The controller maintains deterministic fallback behavior
- The controller decides whether/when to query the VLM
- The VLM's suggestions can be ignored or overridden
"""

import logging
from typing import Optional, List, Dict, Any

from .base import Controller
from .heuristic import RandomController
from ..core.observation import Observation
from ..core.action import Action

logger = logging.getLogger(__name__)


class VLMAdvisedController(Controller):
    """
    Heuristic controller that can incorporate VLM advice.

    This controller demonstrates the proper architecture for VLM integration:
    - The VLM is an ADVISOR, not a driver
    - The controller maintains deterministic fallback behavior
    - The controller decides whether/when to query the VLM
    - The VLM's suggestions can be ignored or overridden

    For the MVP, this uses simple heuristics with hooks for VLM integration.

    Design notes:
    - VLM queries are rate-limited (not every step)
    - Controller can override VLM suggestions
    - Deterministic fallback ensures reproducibility
    """

    def __init__(
        self,
        seed: Optional[int] = None,
        vlm_client=None,  # VLMClient interface (stub for MVP)
        query_interval: int = 1,  # Query VLM every N steps (deprecated, kept for compatibility)
        viewport_width: int = 1280,
        viewport_height: int = 720
    ):
        """
        Initialize VLM-advised controller.

        Args:
            seed: Random seed for deterministic fallback
            vlm_client: VLM client instance (optional)
            query_interval: Deprecated - controller now queries VLM only when action queue is empty
            viewport_width: Browser viewport width
            viewport_height: Browser viewport height
        """
        super().__init__(seed)
        self.vlm_client = vlm_client
        self.query_interval = query_interval  # Kept for compatibility but not used
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height

        # Fallback controller for when VLM is not used
        self.fallback = RandomController(
            seed=seed,
            viewport_width=viewport_width,
            viewport_height=viewport_height
        )

        # Action sequence cache
        self._action_queue: List[Action] = []
        self._current_goal: Optional[str] = None
        self._actions_executed_for_goal: List[Action] = []
        self._last_observation: Optional[Observation] = None

        logger.info(
            f"VLMAdvisedController initialized "
            f"(vlm={'enabled' if vlm_client else 'disabled'})"
        )

    def select_action(self, observation: Observation) -> Action:
        """
        Select action, possibly incorporating VLM advice.

        This method:
        1. Returns next action from cached queue if available
        2. Queries VLM for new action sequence when queue is empty
        3. Falls back to heuristic if VLM fails

        Args:
            observation: Current browser state

        Returns:
            Selected action
        """
        # Store observation for later analysis
        self._last_observation = observation

        # If we have queued actions, return the next one
        if self._action_queue:
            action = self._action_queue.pop(0)
            self._actions_executed_for_goal.append(action)
            logger.debug(
                f"Using queued action: {action.action_type} "
                f"({len(self._action_queue)} remaining in queue)"
            )
            return action

        # Action queue is empty - need to query VLM for next sequence
        if self.vlm_client is not None:
            action = self._get_next_action_sequence(observation)
            if action:
                return action

        # Fallback to heuristic
        action = self.fallback.select_action(observation)
        logger.debug(f"Using fallback: {action.action_type}")
        return action

    def _get_next_action_sequence(self, observation: Observation) -> Optional[Action]:
        """
        Query VLM for next action sequence.

        This method:
        1. Analyzes whether the previous goal was achieved (if any)
        2. Requests a new action sequence from the VLM
        3. Caches the sequence and returns the first action

        Args:
            observation: Current browser state

        Returns:
            First action from new sequence, or None if VLM unavailable/fails
        """
        if not self.vlm_client:
            return None

        try:
            # If we had a previous goal, analyze whether it was achieved
            previous_goal = self._current_goal
            actions_taken = self._actions_executed_for_goal.copy()

            if previous_goal and hasattr(self.vlm_client, 'get_semantic_analysis'):
                logger.info(f"Analyzing goal achievement: '{previous_goal}'")
                analysis = self.vlm_client.get_semantic_analysis(
                    observation,
                    previous_goal=previous_goal,
                    actions_taken=actions_taken
                )

                if analysis:
                    goal_achieved = analysis.get('goal_achieved', False)
                    next_goal = analysis.get('next_goal', 'Continue exploration')
                    logger.info(
                        f"Goal '{previous_goal}' achieved: {goal_achieved}. "
                        f"Next goal: '{next_goal}'"
                    )

                    # Check for issues
                    issues = analysis.get('issues_detected', [])
                    if issues:
                        logger.warning(f"Issues detected: {issues}")

            # Query VLM for next action sequence
            logger.info("Querying VLM for next action sequence")

            # Check if VLM client has the new suggest_action_sequence method
            if hasattr(self.vlm_client, 'suggest_action_sequence'):
                sequence = self.vlm_client.suggest_action_sequence(observation)
            else:
                # Fallback to old suggest_action method
                logger.warning("VLM client does not support action sequences, falling back to single action")
                single_action = self.vlm_client.suggest_action(observation)
                if single_action:
                    sequence = {
                        "goal": "Single action",
                        "actions": [single_action]
                    }
                else:
                    sequence = None

            if sequence and sequence.get('actions'):
                # Cache the action sequence
                self._current_goal = sequence['goal']
                self._action_queue = sequence['actions'].copy()
                self._actions_executed_for_goal = []

                # Return first action and mark it as executed
                first_action = self._action_queue.pop(0)
                self._actions_executed_for_goal.append(first_action)

                logger.info(
                    f"New action sequence for goal '{self._current_goal}': "
                    f"{len(sequence['actions'])} actions total"
                )
                logger.debug(f"Returning first action: {first_action.action_type}")

                return first_action

            logger.warning("VLM returned empty action sequence")
            return None

        except Exception as e:
            logger.warning(f"VLM query failed: {e}", exc_info=True)
            return None
