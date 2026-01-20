"""
Gemini VLM client implementation.

This module provides a production-ready VLM client using Google's Gemini 2.5 Flash
model for generating action suggestions during playtesting.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import base64

try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    genai = None

from ..core.observation import Observation
from ..core.action import Action, WaitAction, ClickAction, KeypressAction, action_from_dict
from .client import VLMClient

logger = logging.getLogger(__name__)


class GeminiVLMClient(VLMClient):
    """
    VLM client using Google Gemini 2.5 Flash for action suggestions.

    This client:
    - Sends screenshots and game context to Gemini
    - Maintains conversation state across steps
    - Parses JSON action responses
    - Validates suggested actions
    - Handles API errors gracefully

    State Management:
    - client.state stores persistent information across steps
    - Can include: previous actions, observations, game progress, etc.
    - State is passed to Gemini for better decision-making
    """

    def __init__(
        self,
        api_key: str,
        game_context: Optional[Dict[str, Any]] = None,
        output_dir: Optional[Path] = None,
        model_name: str = "gemini-2.0-flash-exp",
        temperature: float = 0.7,
        max_output_tokens: int = 256
    ):
        """
        Initialize Gemini VLM client.

        Args:
            api_key: Google API key for Gemini
            game_context: Game context (goal, controls, known bugs, etc.)
            output_dir: Output directory for resolving screenshot paths
            model_name: Gemini model to use
            temperature: Sampling temperature (0.0-1.0)
            max_output_tokens: Maximum tokens in response

        Raises:
            ImportError: If google-generativeai is not installed
            ValueError: If API key is invalid
        """
        if not GEMINI_AVAILABLE:
            raise ImportError(
                "google-generativeai package not installed. "
                "Install with: pip install google-generativeai"
            )

        super().__init__(game_context)

        # Store output directory for resolving screenshot paths
        self.output_dir = output_dir

        # Configure Gemini
        genai.configure(api_key=api_key)
        self.model_name = model_name
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens

        # Initialize model
        self.model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={
                "temperature": temperature,
                "max_output_tokens": max_output_tokens,
            }
        )

        # State management for conversation context
        self.state: Dict[str, Any] = {
            "step_count": 0,
            "recent_actions": [],  # Last N actions taken
            "max_recent_actions": 5,  # Keep last 5 actions in context
            "observations_summary": [],  # Key observations
        }

        logger.info(
            f"GeminiVLMClient initialized with model {model_name} "
            f"(temp={temperature}, game={self.game_context.get('name', 'N/A')})"
        )

    def _build_system_prompt(self) -> str:
        """
        Build the system prompt with game context and instructions.

        Returns:
            System prompt string
        """
        prompt = "You are an AI agent playtesting a web-based game. "

        # Add game context
        if self.game_context.get('name'):
            prompt += f"The game is: **{self.game_context['name']}**. "

        if self.game_context.get('goal'):
            prompt += f"\n\n**Objective:** {self.game_context['goal']}"

        if self.game_context.get('controls'):
            controls = self.game_context['controls']
            if isinstance(controls, dict):
                prompt += "\n\n**Controls:**"
                for action_type, description in controls.items():
                    prompt += f"\n- {action_type}: {description}"
            else:
                prompt += f"\n\n**Controls:** {controls}"

        if self.game_context.get('known_bugs'):
            prompt += "\n\n**Known Issues to Watch For:**"
            for bug in self.game_context['known_bugs']:
                prompt += f"\n- {bug}"

        if self.game_context.get('test_focus_areas'):
            prompt += "\n\n**Test Focus Areas:**"
            for area in self.game_context['test_focus_areas']:
                prompt += f"\n- {area}"

        # Add action format instructions
        prompt += """

**Your Task:**
Analyze the screenshot and suggest the next action to take.

**Available Actions:**
1. **wait**: Pause for a duration
   - Format: {"type": "wait", "duration_ms": <milliseconds>}
   - Example: {"type": "wait", "duration_ms": 1000}
   - Use this when: game is loading, animations playing, or observing changes

2. **click**: Click at specific coordinates
   - Format: {"type": "click", "x": <int>, "y": <int>}
   - Example: {"type": "click", "x": 640, "y": 360}
   - Coordinates are in pixels from top-left (0,0)
   - Use this when: interacting with buttons, UI elements, game objects

3. **keypress**: Press a keyboard key
   - Format: {"type": "keypress", "key": "<key_name>"}
   - Example: {"type": "keypress", "key": "Space"}
   - Common keys: "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Space", "Enter", "Escape", "w", "a", "s", "d"
   - Use this when: controlling character movement or triggering keyboard actions

**Response Format:**
You MUST respond with ONLY a valid JSON object representing one action. Do not include any other text or explanation.

Example responses:
{"type": "click", "x": 640, "y": 360}
{"type": "keypress", "key": "Space"}
{"type": "wait", "duration_ms": 2000}

**Decision-Making Guidelines:**
- Consider the game objective and current state
- Try to make progress toward the goal
- Watch for the known issues mentioned above
- Use wait actions sparingly (only when necessary)
- If stuck, try different interactions
- Balance exploration and exploitation
"""
        return prompt

    def _build_step_context(self, observation: Observation) -> str:
        """
        Build contextual information for the current step.

        Args:
            observation: Current observation

        Returns:
            Context string
        """
        context = f"**Step {observation.step}**\n\n"

        # Add recent action history
        if self.state["recent_actions"]:
            context += "**Recent Actions:**\n"
            for i, action in enumerate(self.state["recent_actions"][-3:], 1):
                context += f"{i}. {action}\n"
            context += "\n"

        # Add console events if any
        if observation.console_events:
            context += f"**Console Events ({len(observation.console_events)}):**\n"
            for event in observation.console_events[:5]:  # Show first 5
                context += f"- [{event.level}] {event.text[:100]}\n"
            context += "\n"

        # Add DOM metadata
        if observation.dom_metadata:
            context += (
                f"**Page Info:**\n"
                f"- URL: {observation.dom_metadata.url}\n"
                f"- Title: {observation.dom_metadata.title}\n"
                f"- Viewport: {observation.dom_metadata.viewport_width}x{observation.dom_metadata.viewport_height}\n\n"
            )

        context += "Based on the screenshot above, what action should be taken next?"

        return context

    def _load_image(self, screenshot_path: str) -> Any:
        """
        Load and encode image for Gemini.

        Args:
            screenshot_path: Path to screenshot

        Returns:
            PIL Image object for Gemini

        Raises:
            FileNotFoundError: If screenshot doesn't exist
        """
        from PIL import Image

        path = Path(screenshot_path)
        if not path.exists():
            raise FileNotFoundError(f"Screenshot not found: {screenshot_path}")

        return Image.open(path)

    def suggest_action(self, observation: Observation) -> Optional[Action]:
        """
        Suggest an action based on the current observation.

        Args:
            observation: Current browser state with screenshot

        Returns:
            Suggested action, or None if unable to generate suggestion
        """
        try:
            logger.debug(f"Querying Gemini for step {observation.step}")

            # Build prompt components
            system_prompt = self._build_system_prompt()
            step_context = self._build_step_context(observation)

            # Load screenshot
            # Resolve relative paths using output_dir
            screenshot_path = Path(observation.screenshot_path)
            if not screenshot_path.is_absolute() and self.output_dir:
                screenshot_full_path = self.output_dir / screenshot_path
            else:
                screenshot_full_path = screenshot_path

            image = self._load_image(str(screenshot_full_path))

            # Build full prompt
            full_prompt = f"{system_prompt}\n\n{step_context}"

            # Query Gemini with image
            response = self.model.generate_content([full_prompt, image])

            # Extract text response
            if not response.text:
                logger.warning("Gemini returned empty response")
                return None

            response_text = response.text.strip()
            logger.debug(f"Gemini response: {response_text}")

            # Parse JSON response
            action = self._parse_action_response(response_text)

            if action:
                # Update state with this action
                action_summary = f"Step {observation.step}: {action.action_type}"
                self.state["recent_actions"].append(action_summary)

                # Keep only recent actions
                if len(self.state["recent_actions"]) > self.state["max_recent_actions"]:
                    self.state["recent_actions"].pop(0)

                self.state["step_count"] += 1

                logger.info(
                    f"Gemini suggested {action.action_type} action at step {observation.step}"
                )

            return action

        except FileNotFoundError as e:
            logger.error(f"Screenshot not found: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {e}")
            logger.debug(f"Raw response: {response_text if 'response_text' in locals() else 'N/A'}")
            return None
        except Exception as e:
            logger.error(f"Error querying Gemini: {e}", exc_info=True)
            return None

    def _parse_action_response(self, response_text: str) -> Optional[Action]:
        """
        Parse Gemini's response into an Action object.

        Attempts to extract JSON from various response formats.

        Args:
            response_text: Raw response from Gemini

        Returns:
            Action object or None if parsing fails
        """
        # Try to extract JSON from response
        # Gemini might wrap JSON in markdown code blocks
        json_str = response_text.strip()

        # Remove markdown code blocks if present
        if json_str.startswith("```"):
            lines = json_str.split("\n")
            # Remove first and last lines if they're code block markers
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            json_str = "\n".join(lines).strip()

        # Try to find JSON object in the text
        start_idx = json_str.find("{")
        end_idx = json_str.rfind("}") + 1

        if start_idx != -1 and end_idx > start_idx:
            json_str = json_str[start_idx:end_idx]

        try:
            action_dict = json.loads(json_str)
            action = action_from_dict(action_dict)

            # Validate action
            if not self._validate_action(action):
                logger.warning(f"Invalid action suggested: {action_dict}")
                return None

            return action

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.debug(f"Attempted to parse: {json_str}")
            return None

    def _validate_action(self, action: Action) -> bool:
        """
        Validate that an action is legal.

        Args:
            action: Action to validate

        Returns:
            True if action is valid, False otherwise
        """
        if isinstance(action, WaitAction):
            # Wait duration should be reasonable (10ms to 10s)
            return 10 <= action.duration_ms <= 10000

        elif isinstance(action, ClickAction):
            # Click coordinates should be positive
            return action.x >= 0 and action.y >= 0

        elif isinstance(action, KeypressAction):
            # Key should be non-empty
            return bool(action.key)

        return False

    def get_semantic_analysis(self, observation: Observation) -> Optional[dict]:
        """
        Get semantic analysis of the current game state.

        This could be used for bug detection, progress assessment, etc.

        Args:
            observation: Current observation

        Returns:
            Analysis dictionary with insights
        """
        try:
            # Build analysis prompt
            prompt = f"""Analyze this game screenshot and provide insights.

Game: {self.game_context.get('name', 'Unknown')}
Goal: {self.game_context.get('goal', 'N/A')}
Step: {observation.step}

Analyze:
1. What is happening in the game?
2. Is progress being made toward the goal?
3. Are there any visual issues or bugs?
4. What should the player focus on next?

Respond with JSON:
{{
    "game_state": "brief description",
    "progress_assessment": "description of progress",
    "issues_detected": ["list of issues or bugs"],
    "recommendations": ["list of recommendations"]
}}
"""

            image = self._load_image(observation.screenshot_path)
            response = self.model.generate_content([prompt, image])

            if response.text:
                # Try to parse JSON response
                analysis = json.loads(response.text.strip())
                return analysis

        except Exception as e:
            logger.error(f"Error getting semantic analysis: {e}")

        return None

    def reset_state(self):
        """Reset the client's internal state."""
        self.state = {
            "step_count": 0,
            "recent_actions": [],
            "max_recent_actions": 5,
            "observations_summary": [],
        }
        logger.info("GeminiVLMClient state reset")
