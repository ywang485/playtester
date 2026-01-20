"""
Heuristic controller implementations.

These controllers use deterministic or pseudo-random strategies
rather than learning from experience.
"""

import random
import logging
from typing import Optional

from .base import Controller
from ..core.observation import Observation
from ..core.action import Action, WaitAction, ClickAction, KeypressAction

logger = logging.getLogger(__name__)


class RandomController(Controller):
    """
    Simple random exploration controller.

    Randomly selects actions from the action space with configurable
    probabilities. Useful for:
    - Baseline comparisons
    - Fuzzing/stress testing
    - Initial exploration

    This is a minimal but complete controller implementation.
    """

    def __init__(
        self,
        seed: Optional[int] = None,
        click_prob: float = 0.6,
        keypress_prob: float = 0.2,
        wait_prob: float = 0.2,
        viewport_width: int = 1280,
        viewport_height: int = 720
    ):
        """
        Initialize random controller.

        Args:
            seed: Random seed for reproducibility
            click_prob: Probability of selecting a click action
            keypress_prob: Probability of selecting a keypress action
            wait_prob: Probability of selecting a wait action
            viewport_width: Browser viewport width (for click coordinates)
            viewport_height: Browser viewport height (for click coordinates)
        """
        super().__init__(seed)
        self.click_prob = click_prob
        self.keypress_prob = keypress_prob
        self.wait_prob = wait_prob
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height

        # Normalize probabilities
        total = click_prob + keypress_prob + wait_prob
        self.click_prob /= total
        self.keypress_prob /= total
        self.wait_prob /= total

        # Initialize RNG
        self.rng = random.Random(seed)

        logger.info(f"RandomController initialized (seed={seed})")

    def select_action(self, observation: Observation) -> Action:
        """
        Select a random action.

        Args:
            observation: Current browser state (unused by random controller)

        Returns:
            Randomly selected action
        """
        # Choose action type
        roll = self.rng.random()

        if roll < self.click_prob:
            return self._random_click()
        elif roll < self.click_prob + self.keypress_prob:
            return self._random_keypress()
        else:
            return self._random_wait()

    def _random_click(self) -> ClickAction:
        """Generate a random click action."""
        x = self.rng.randint(0, self.viewport_width - 1)
        y = self.rng.randint(0, self.viewport_height - 1)
        return ClickAction(x=x, y=y)

    def _random_keypress(self) -> KeypressAction:
        """Generate a random keypress action."""
        # Common game keys
        keys = [
            'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
            'w', 'a', 's', 'd',
            'Space', 'Enter', 'Escape'
        ]
        key = self.rng.choice(keys)
        return KeypressAction(key=key)

    def _random_wait(self) -> WaitAction:
        """Generate a random wait action."""
        # Wait between 100ms and 2000ms
        duration = self.rng.randint(100, 2000)
        return WaitAction(duration_ms=duration)


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
        query_interval: int = 5,  # Query VLM every N steps
        viewport_width: int = 1280,
        viewport_height: int = 720
    ):
        """
        Initialize VLM-advised controller.

        Args:
            seed: Random seed for deterministic fallback
            vlm_client: VLM client instance (optional, stub for MVP)
            query_interval: How often to query the VLM (in steps)
            viewport_width: Browser viewport width
            viewport_height: Browser viewport height
        """
        super().__init__(seed)
        self.vlm_client = vlm_client
        self.query_interval = query_interval
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height

        # Fallback controller for when VLM is not used
        self.fallback = RandomController(
            seed=seed,
            viewport_width=viewport_width,
            viewport_height=viewport_height
        )

        # Cache for VLM advice
        self._last_vlm_action: Optional[Action] = None
        self._vlm_advice_valid_until: int = 0

        logger.info(
            f"VLMAdvisedController initialized "
            f"(query_interval={query_interval}, vlm={'enabled' if vlm_client else 'disabled'})"
        )

    def select_action(self, observation: Observation) -> Action:
        """
        Select action, possibly incorporating VLM advice.

        Args:
            observation: Current browser state

        Returns:
            Selected action
        """
        # Check if we should query the VLM
        should_query_vlm = (
            self.vlm_client is not None
            and self.step_count % self.query_interval == 0
        )

        if should_query_vlm:
            action = self._get_vlm_action(observation)
            if action:
                logger.debug(f"Using VLM advice: {action.action_type}")
                return action

        # Fallback to heuristic
        action = self.fallback.select_action(observation)
        logger.debug(f"Using fallback: {action.action_type}")
        return action

    def _get_vlm_action(self, observation: Observation) -> Optional[Action]:
        """
        Query VLM for action advice.

        Args:
            observation: Current browser state

        Returns:
            Suggested action or None if VLM unavailable/fails
        """
        if not self.vlm_client:
            return None

        try:
            # Query VLM (stub for MVP)
            suggestion = self.vlm_client.suggest_action(observation)
            return suggestion
        except Exception as e:
            logger.warning(f"VLM query failed: {e}")
            return None
