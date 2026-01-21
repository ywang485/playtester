"""
Gemini VLM client implementation.

This module provides a production-ready VLM client using Google's Gemini 2.5 Flash
model for generating action suggestions during playtesting.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
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
        max_output_tokens: int = 256,
        trajectory_logger: Optional[Any] = None
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
            trajectory_logger: Optional TrajectoryLogger for logging VLM outputs

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

        # Store trajectory logger for logging VLM outputs
        self.trajectory_logger = trajectory_logger

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
            "current_goal": None,  # Current goal being pursued
            "actions_for_current_goal": [],  # Actions executed for current goal
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
Analyze the screenshot and suggest a SEQUENCE of actions to accomplish a specific goal or sub-goal.

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
You MUST respond with ONLY a valid JSON object with two fields:
1. "goal": A brief description of what this action sequence aims to accomplish
2. "actions": An array of 2-5 actions to execute in sequence

Do not include any other text or explanation outside the JSON.

Example response:
{
  "goal": "Click the start button and begin the game",
  "actions": [
    {"type": "click", "x": 640, "y": 360},
    {"type": "wait", "duration_ms": 1000}
  ]
}

**Decision-Making Guidelines:**
- Plan a coherent sequence of actions toward a specific sub-goal
- Each sequence should accomplish something meaningful (e.g., "navigate to menu", "collect item", "defeat enemy")
- Include 2-5 actions per sequence (not too few, not too many)
- Include wait actions between interactions when needed for game response
- Consider the game objective and current state
- Watch for the known issues mentioned above
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

    def suggest_action_sequence(self, observation: Observation) -> Optional[Dict[str, Any]]:
        """
        Suggest a sequence of actions based on the current observation.

        Args:
            observation: Current browser state with screenshot

        Returns:
            Dictionary with 'goal' and 'actions' fields, or None if unable to generate suggestion
            Format: {"goal": str, "actions": List[Action]}
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

            # Log raw VLM output to trajectory
            if self.trajectory_logger:
                self.trajectory_logger.log_event("vlm_action_sequence_response", {
                    "step": observation.step,
                    "model": self.model_name,
                    "raw_response": response_text,
                    "temperature": self.temperature
                })

            # Parse JSON response
            action_sequence = self._parse_action_sequence_response(response_text)

            if action_sequence:
                # Update state with this action sequence
                goal = action_sequence["goal"]
                actions = action_sequence["actions"]
                action_summary = f"Step {observation.step}: {len(actions)} actions for goal '{goal}'"
                self.state["recent_actions"].append(action_summary)

                # Keep only recent actions
                if len(self.state["recent_actions"]) > self.state["max_recent_actions"]:
                    self.state["recent_actions"].pop(0)

                self.state["step_count"] += 1

                logger.info(
                    f"Gemini suggested {len(actions)} actions for goal: {goal}"
                )

                # Log parsed action sequence to trajectory
                if self.trajectory_logger:
                    self.trajectory_logger.log_event("vlm_action_sequence_parsed", {
                        "step": observation.step,
                        "goal": goal,
                        "actions": [action.to_dict() for action in actions],
                        "num_actions": len(actions)
                    })

            return action_sequence

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

    def suggest_action(self, observation: Observation) -> Optional[Action]:
        """
        Suggest a single action (legacy compatibility method).

        This method wraps suggest_action_sequence for backward compatibility.
        Returns the first action from the sequence.

        Args:
            observation: Current browser state with screenshot

        Returns:
            Suggested action, or None if unable to generate suggestion
        """
        sequence = self.suggest_action_sequence(observation)
        if sequence and sequence.get("actions"):
            return sequence["actions"][0]
        return None

    def _parse_action_sequence_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """
        Parse Gemini's response into an action sequence.

        Attempts to extract JSON from various response formats.

        Args:
            response_text: Raw response from Gemini

        Returns:
            Dictionary with 'goal' and 'actions' fields, or None if parsing fails
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
            response_dict = json.loads(json_str)

            # Validate response structure
            if "goal" not in response_dict or "actions" not in response_dict:
                logger.error(f"Response missing required fields 'goal' or 'actions': {response_dict}")
                return None

            if not isinstance(response_dict["actions"], list):
                logger.error(f"'actions' field must be a list: {response_dict}")
                return None

            # Parse actions
            actions = []
            for action_dict in response_dict["actions"]:
                try:
                    action = action_from_dict(action_dict)
                    # Validate action
                    if not self._validate_action(action):
                        logger.warning(f"Invalid action in sequence: {action_dict}")
                        continue
                    actions.append(action)
                except Exception as e:
                    logger.warning(f"Failed to parse action: {action_dict}, error: {e}")
                    continue

            if not actions:
                logger.error("No valid actions in sequence")
                return None

            return {
                "goal": response_dict["goal"],
                "actions": actions
            }

        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}")
            logger.debug(f"Attempted to parse: {json_str}")
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

    def get_semantic_analysis(
        self,
        observation: Observation,
        previous_goal: Optional[str] = None,
        actions_taken: Optional[List[Action]] = None
    ) -> Optional[dict]:
        """
        Get semantic analysis of the current game state.

        Analyzes whether previous actions achieved their goal and determines next steps.

        Args:
            observation: Current observation
            previous_goal: The goal from the previous action sequence (if any)
            actions_taken: The actions that were executed (if any)

        Returns:
            Analysis dictionary with:
            - game_state: Description of current state
            - goal_achieved: Whether the previous goal was accomplished (if applicable)
            - progress_assessment: Overall progress toward game objective
            - issues_detected: Any visual bugs or issues
            - next_goal: Recommended next goal to pursue
        """
        try:
            # Determine the overall objective
            if self.game_context.get('goal'):
                overall_objective = self.game_context['goal']
            else:
                # Infer reasonable default based on game type
                game_name = self.game_context.get('name', 'this game')
                overall_objective = f"Play {game_name} as an average human player would - explore, interact with UI elements, try to make progress, and test different game mechanics"

            # Build analysis prompt
            prompt = f"""Analyze this game screenshot and evaluate progress.

Game: {self.game_context.get('name', 'Unknown')}
Overall Objective: {overall_objective}
Step: {observation.step}
"""

            # Add previous goal context if available
            if previous_goal and actions_taken:
                prompt += f"""
Previous Goal: {previous_goal}
Actions Taken: {len(actions_taken)} actions
"""
                actions_summary = []
                for i, action in enumerate(actions_taken, 1):
                    actions_summary.append(f"{i}. {action.action_type}")
                prompt += "Actions: " + ", ".join(actions_summary) + "\n"

            prompt += """
Analyze:
1. What is the current game state? (describe what you see)
"""

            if previous_goal:
                prompt += f"""2. Was the previous goal "{previous_goal}" successfully achieved? (yes/no and explain why)
3. Should we continue with the current approach or try something different?
4. What should be the next goal to pursue?
"""
            else:
                prompt += """2. What should be the first goal to pursue?
"""

            prompt += """
5. Are there any visual issues, bugs, or anomalies?
6. Is progress being made toward the overall objective?

Respond with ONLY valid JSON (no other text):
{
    "game_state": "brief description of what you see",
"""

            if previous_goal:
                prompt += """    "goal_achieved": true or false,
    "goal_achievement_explanation": "explain whether previous goal was achieved",
"""

            prompt += """    "progress_assessment": "assessment of overall progress",
    "issues_detected": ["list of issues or bugs, empty list if none"],
    "next_goal": "specific next goal to pursue (be concrete and actionable)",
    "reasoning": "brief explanation of why this next goal makes sense"
}
"""

            # Load screenshot
            screenshot_path = Path(observation.screenshot_path)
            if not screenshot_path.is_absolute() and self.output_dir:
                screenshot_full_path = self.output_dir / screenshot_path
            else:
                screenshot_full_path = screenshot_path

            image = self._load_image(str(screenshot_full_path))
            response = self.model.generate_content([prompt, image])

            if response.text:
                # Try to parse JSON response
                response_text = response.text.strip()

                # Log raw VLM output to trajectory
                if self.trajectory_logger:
                    self.trajectory_logger.log_event("vlm_semantic_analysis_response", {
                        "step": observation.step,
                        "model": self.model_name,
                        "raw_response": response_text,
                        "previous_goal": previous_goal,
                        "actions_taken_count": len(actions_taken) if actions_taken else 0
                    })

                # Remove markdown code blocks if present
                if response_text.startswith("```"):
                    lines = response_text.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].startswith("```"):
                        lines = lines[:-1]
                    response_text = "\n".join(lines).strip()

                # Try to find JSON object
                start_idx = response_text.find("{")
                end_idx = response_text.rfind("}") + 1
                if start_idx != -1 and end_idx > start_idx:
                    response_text = response_text[start_idx:end_idx]

                analysis = json.loads(response_text)
                logger.info(f"Semantic analysis: goal_achieved={analysis.get('goal_achieved', 'N/A')}, next_goal={analysis.get('next_goal', 'N/A')}")

                # Log parsed semantic analysis to trajectory
                if self.trajectory_logger:
                    self.trajectory_logger.log_event("vlm_semantic_analysis_parsed", {
                        "step": observation.step,
                        "analysis": analysis
                    })

                return analysis

        except Exception as e:
            logger.error(f"Error getting semantic analysis: {e}", exc_info=True)

        return None

    def reset_state(self):
        """Reset the client's internal state."""
        self.state = {
            "step_count": 0,
            "recent_actions": [],
            "max_recent_actions": 5,
            "observations_summary": [],
            "current_goal": None,
            "actions_for_current_goal": [],
        }
        logger.info("GeminiVLMClient state reset")
