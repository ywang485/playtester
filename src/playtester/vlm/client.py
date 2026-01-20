"""
VLM client interface and stub implementation.

This module defines the interface for VLM integration. The VLM's role is
strictly ADVISORY - it does not have direct access to the browser and
cannot execute actions directly.

For the MVP, we provide only a stub implementation. Future versions will
integrate real VLM APIs (GPT-4V, Claude, Gemini, etc.).
"""

from abc import ABC, abstractmethod
from typing import Optional
import logging

from ..core.observation import Observation
from ..core.action import Action, WaitAction

logger = logging.getLogger(__name__)


class VLMClient(ABC):
    """
    Abstract base class for VLM clients.

    VLM clients take observations (including screenshots) and provide
    action suggestions. The controller decides whether to follow these
    suggestions.

    Design principles:
    - VLM has NO direct browser access
    - VLM has NO authority to execute actions
    - VLM suggestions can be ignored or overridden
    - VLM queries may fail (network, rate limits, etc.)
    - VLM responses must be validated by the controller

    Future implementations should handle:
    - Image encoding and upload
    - Prompt engineering
    - Rate limiting
    - Caching/memoization
    - Error handling and retries
    - Cost tracking
    """

    @abstractmethod
    def suggest_action(self, observation: Observation) -> Optional[Action]:
        """
        Suggest an action based on the current observation.

        Args:
            observation: Current browser state (includes screenshot)

        Returns:
            Suggested action, or None if unable to provide suggestion

        Note:
            This method may be slow (API calls) and may fail.
            Controllers should have fallback behavior.
        """
        pass

    @abstractmethod
    def get_semantic_analysis(self, observation: Observation) -> Optional[dict]:
        """
        Provide semantic analysis of the current state.

        This is a hook for future functionality like:
        - Bug detection (visual artifacts, UI dead-ends)
        - Progress assessment (game state interpretation)
        - Goal achievement (level completion, score milestones)

        Args:
            observation: Current browser state

        Returns:
            Dictionary with analysis results, or None if unavailable
        """
        pass


class StubVLMClient(VLMClient):
    """
    Stub VLM client for MVP and testing.

    This implementation always returns safe default actions and empty
    analysis. It serves as:
    - A placeholder for real VLM integration
    - A testing/debugging tool
    - Documentation of the VLM interface

    Replace this with a real implementation when ready to integrate VLMs.
    """

    def __init__(self):
        """Initialize stub VLM client."""
        logger.warning(
            "Using StubVLMClient - no real VLM integration. "
            "All suggestions will be placeholder values."
        )

    def suggest_action(self, observation: Observation) -> Optional[Action]:
        """
        Return a stub action suggestion.

        For MVP, this always suggests a wait action. A real implementation
        would analyze the screenshot and game state to suggest meaningful actions.

        Args:
            observation: Current browser state

        Returns:
            Stub wait action
        """
        logger.debug(f"StubVLMClient: returning stub action for step {observation.step}")

        # In a real implementation, this would:
        # 1. Encode the screenshot from observation.screenshot_path
        # 2. Send to VLM API with appropriate prompt
        # 3. Parse the VLM's response into an Action
        # 4. Validate the action is legal
        # 5. Return the action or None if invalid

        # For now, return a safe default
        return WaitAction(duration_ms=1000)

    def get_semantic_analysis(self, observation: Observation) -> Optional[dict]:
        """
        Return stub semantic analysis.

        Args:
            observation: Current browser state

        Returns:
            Empty analysis dict
        """
        logger.debug(f"StubVLMClient: returning stub analysis for step {observation.step}")

        # In a real implementation, this would:
        # 1. Analyze the screenshot for visual issues
        # 2. Check for common game bugs (frozen UI, crash indicators)
        # 3. Assess game progress
        # 4. Return structured analysis

        return {
            "stub": True,
            "message": "Real VLM analysis not implemented yet"
        }


# Example of how a real VLM client might look (NOT IMPLEMENTED):
#
# class GPT4VisionClient(VLMClient):
#     """Client for OpenAI GPT-4 Vision API."""
#
#     def __init__(self, api_key: str, prompt_template: str):
#         self.api_key = api_key
#         self.prompt_template = prompt_template
#         self.client = openai.Client(api_key=api_key)
#
#     def suggest_action(self, observation: Observation) -> Optional[Action]:
#         # Encode screenshot
#         with open(observation.screenshot_path, 'rb') as f:
#             image_data = base64.b64encode(f.read()).decode()
#
#         # Query GPT-4V
#         response = self.client.chat.completions.create(
#             model="gpt-4-vision-preview",
#             messages=[{
#                 "role": "user",
#                 "content": [
#                     {"type": "text", "text": self.prompt_template},
#                     {"type": "image_url", "image_url": f"data:image/png;base64,{image_data}"}
#                 ]
#             }]
#         )
#
#         # Parse response into Action
#         action_dict = json.loads(response.choices[0].message.content)
#         return action_from_dict(action_dict)
