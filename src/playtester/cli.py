"""
CLI entry point for the playtester.

Provides a command-line interface for running playtest sessions.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Dict, Any

from .browser.env import BrowserEnv
from .controller import RandomController, VLMAdvisedController
from .controller.base import Controller
from .core.trajectory import TrajectoryLogger
from .vlm import StubVLMClient

# Try to import GeminiVLMClient (optional dependency)
try:
    from .vlm import GeminiVLMClient
    GEMINI_AVAILABLE = True
except ImportError:
    GeminiVLMClient = None
    GEMINI_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)


def run_playtest(
    url: str,
    steps: int,
    output_dir: Path,
    controller_type: str = "random",
    seed: Optional[int] = None,
    headless: bool = False,
    viewport_width: int = 1280,
    viewport_height: int = 720,
    game_context: Optional[Dict[str, Any]] = None,
    vlm_provider: str = "stub",
    vlm_api_key: Optional[str] = None
) -> None:
    """
    Run a single playtest session.

    This is the main orchestration function that ties together:
    - Browser environment
    - Controller
    - Trajectory logging

    Args:
        url: URL to test
        steps: Number of steps to run
        output_dir: Directory for output artifacts
        controller_type: Type of controller ('random' or 'vlm')
        seed: Random seed for reproducibility
        headless: Run browser in headless mode
        viewport_width: Browser viewport width
        viewport_height: Browser viewport height
        game_context: Optional game context (goal, controls, known bugs, etc.)
        vlm_provider: VLM provider ('stub' or 'gemini')
        vlm_api_key: API key for VLM provider
    """
    logger.info("="*80)
    logger.info(f"Starting playtest session")
    logger.info(f"URL: {url}")
    logger.info(f"Steps: {steps}")
    logger.info(f"Controller: {controller_type}")
    logger.info(f"Seed: {seed}")
    logger.info(f"Output: {output_dir}")
    if game_context:
        logger.info(f"Game context: {game_context.get('name', 'N/A')}")
        if game_context.get('goal'):
            logger.info(f"  Goal: {game_context['goal']}")
    logger.info("="*80)

    # Initialize trajectory logger
    metadata = {
        "url": url,
        "steps": steps,
        "controller_type": controller_type,
        "seed": seed,
        "viewport": {"width": viewport_width, "height": viewport_height}
    }
    if game_context:
        metadata["game_context"] = game_context

    trajectory_logger = TrajectoryLogger(output_dir)
    trajectory_logger.initialize(metadata)

    # Initialize controller
    controller = create_controller(
        controller_type=controller_type,
        seed=seed,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
        game_context=game_context,
        vlm_provider=vlm_provider,
        vlm_api_key=vlm_api_key,
        output_dir=output_dir
    )

    # Initialize browser environment
    env = BrowserEnv(
        headless=headless,
        viewport_width=viewport_width,
        viewport_height=viewport_height
    )

    try:
        # Start browser and navigate to URL
        env.start(url)
        logger.info("Browser started successfully")

        # Main playtest loop
        for step in range(steps):
            logger.info(f"Step {step}/{steps}")

            # Capture observation
            screenshot_path = trajectory_logger.get_screenshot_path(step, relative=False)
            observation = env.observe(screenshot_path)

            # Log observation
            trajectory_logger.log_observation(observation)

            # Log console events if any
            if observation.console_events:
                logger.info(f"  Console events: {len(observation.console_events)}")
                for event in observation.console_events:
                    logger.debug(f"    [{event.level}] {event.text[:100]}")

            # Select action
            action = controller.select_action(observation)
            logger.info(f"  Action: {action.action_type}")

            # Log action
            trajectory_logger.log_action(action, step)

            # Execute action
            env.act(action)

            # Notify controller
            controller.on_action_executed(action)

        logger.info("="*80)
        logger.info(f"Playtest session complete: {steps} steps")
        logger.info(f"Trajectory: {trajectory_logger.trajectory_path}")
        logger.info(f"Screenshots: {trajectory_logger.screenshots_dir}")
        logger.info("="*80)

    except Exception as e:
        logger.error(f"Error during playtest: {e}", exc_info=True)
        trajectory_logger.log_event("error", {"message": str(e), "type": type(e).__name__})
        raise

    finally:
        # Clean up
        env.close()
        trajectory_logger.finalize({"total_steps": controller.step_count})


def create_controller(
    controller_type: str,
    seed: Optional[int],
    viewport_width: int,
    viewport_height: int,
    game_context: Optional[Dict[str, Any]] = None,
    vlm_provider: str = "stub",
    vlm_api_key: Optional[str] = None,
    output_dir: Optional[Path] = None
) -> Controller:
    """
    Factory function to create controllers.

    Args:
        controller_type: Type of controller to create
        seed: Random seed
        viewport_width: Browser viewport width
        viewport_height: Browser viewport height
        game_context: Optional game context for VLM
        vlm_provider: VLM provider ('stub' or 'gemini')
        vlm_api_key: API key for VLM provider (if needed)
        output_dir: Output directory for screenshots (needed for VLM)

    Returns:
        Controller instance

    Raises:
        ValueError: If controller type is unknown or VLM configuration is invalid
    """
    if controller_type == "random":
        return RandomController(
            seed=seed,
            viewport_width=viewport_width,
            viewport_height=viewport_height
        )
    elif controller_type == "vlm":
        # Create VLM client based on provider
        vlm_client = create_vlm_client(
            provider=vlm_provider,
            game_context=game_context,
            api_key=vlm_api_key,
            output_dir=output_dir
        )

        return VLMAdvisedController(
            seed=seed,
            vlm_client=vlm_client,
            viewport_width=viewport_width,
            viewport_height=viewport_height
        )
    else:
        raise ValueError(f"Unknown controller type: {controller_type}")


def create_vlm_client(
    provider: str,
    game_context: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    output_dir: Optional[Path] = None
):
    """
    Factory function to create VLM clients.

    Args:
        provider: VLM provider ('stub' or 'gemini')
        game_context: Game context for VLM
        api_key: API key for VLM provider
        output_dir: Output directory (needed for absolute screenshot paths)

    Returns:
        VLM client instance

    Raises:
        ValueError: If provider is unknown or configuration is invalid
    """
    if provider == "stub":
        logger.info("Using StubVLMClient (no real VLM)")
        return StubVLMClient(game_context=game_context)

    elif provider == "gemini":
        if not GEMINI_AVAILABLE:
            raise ValueError(
                "Gemini provider requested but google-generativeai not installed. "
                "Install with: pip install google-generativeai pillow"
            )

        # Get API key from parameter or environment
        api_key = api_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "Gemini API key required. Provide via --gemini-api-key or "
                "set GOOGLE_API_KEY or GEMINI_API_KEY environment variable."
            )

        logger.info("Using GeminiVLMClient with Gemini 2.0 Flash")
        return GeminiVLMClient(
            api_key=api_key,
            game_context=game_context,
            output_dir=output_dir
        )

    else:
        raise ValueError(
            f"Unknown VLM provider: {provider}. "
            f"Available providers: stub, gemini"
        )


def load_config(config_path: Path) -> Dict[str, Any]:
    """
    Load configuration from a JSON file.

    Args:
        config_path: Path to JSON config file

    Returns:
        Configuration dictionary

    Raises:
        FileNotFoundError: If config file doesn't exist
        json.JSONDecodeError: If config file is invalid JSON
    """
    logger.info(f"Loading config from: {config_path}")
    with open(config_path, 'r') as f:
        config = json.load(f)
    return config


def build_game_context(
    name: Optional[str] = None,
    goal: Optional[str] = None,
    controls: Optional[str] = None,
    known_bugs: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Build game context dictionary from individual arguments.

    Args:
        name: Game name
        goal: Game goal description
        controls: Controls description
        known_bugs: Comma-separated list of known bugs

    Returns:
        Game context dictionary, or None if no context provided
    """
    context = {}

    if name:
        context["name"] = name
    if goal:
        context["goal"] = goal
    if controls:
        context["controls"] = controls
    if known_bugs:
        context["known_bugs"] = [bug.strip() for bug in known_bugs.split(",")]

    return context if context else None


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Playtester: Hybrid Heuristic + VLM Browser Playtesting Agent",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        "--url",
        type=str,
        required=True,
        help="URL of the WebGL game to test"
    )

    parser.add_argument(
        "--steps",
        type=int,
        default=50,
        help="Number of steps to run"
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./output"),
        help="Directory for output artifacts"
    )

    parser.add_argument(
        "--controller",
        type=str,
        choices=["random", "vlm"],
        default="random",
        help="Type of controller to use"
    )

    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility"
    )

    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode"
    )

    parser.add_argument(
        "--viewport-width",
        type=int,
        default=1280,
        help="Browser viewport width"
    )

    parser.add_argument(
        "--viewport-height",
        type=int,
        default=720,
        help="Browser viewport height"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    # Game context arguments
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to JSON config file with game context and settings"
    )

    parser.add_argument(
        "--game-name",
        type=str,
        help="Name of the game (for logging and VLM context)"
    )

    parser.add_argument(
        "--game-goal",
        type=str,
        help="Description of the game goal (for VLM context)"
    )

    parser.add_argument(
        "--game-controls",
        type=str,
        help="Description of game controls (for VLM context)"
    )

    parser.add_argument(
        "--known-bugs",
        type=str,
        help="Comma-separated list of known bug areas to monitor"
    )

    # VLM arguments
    parser.add_argument(
        "--vlm-provider",
        type=str,
        choices=["stub", "gemini"],
        default="stub",
        help="VLM provider to use (stub=no real VLM, gemini=Google Gemini)"
    )

    parser.add_argument(
        "--gemini-api-key",
        type=str,
        help="Google API key for Gemini (or set GOOGLE_API_KEY env var)"
    )

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load config file if provided
    config = {}
    if args.config:
        try:
            config = load_config(args.config)
        except Exception as e:
            logger.error(f"Failed to load config file: {e}")
            sys.exit(1)

    # CLI arguments override config file
    # Extract playtest settings
    url = args.url if args.url != parser.get_default('url') else config.get('url', args.url)
    steps = args.steps if args.steps != parser.get_default('steps') else config.get('steps', args.steps)
    output_dir = args.output_dir if args.output_dir != parser.get_default('output_dir') else Path(config.get('output_dir', args.output_dir))
    controller_type = args.controller if args.controller != parser.get_default('controller') else config.get('controller', args.controller)
    seed = args.seed if args.seed is not None else config.get('seed')
    headless = args.headless if args.headless else config.get('headless', False)
    viewport_width = args.viewport_width if args.viewport_width != parser.get_default('viewport_width') else config.get('viewport_width', args.viewport_width)
    viewport_height = args.viewport_height if args.viewport_height != parser.get_default('viewport_height') else config.get('viewport_height', args.viewport_height)

    # Build game context from CLI args
    cli_game_context = build_game_context(
        name=args.game_name,
        goal=args.game_goal,
        controls=args.game_controls,
        known_bugs=args.known_bugs
    )

    # Merge game context: CLI args override config file
    game_context = config.get('game_context', {})
    if cli_game_context:
        game_context.update(cli_game_context)

    game_context = game_context if game_context else None

    # Extract VLM settings
    vlm_provider = args.vlm_provider if hasattr(args, 'vlm_provider') and args.vlm_provider else config.get('vlm_provider', 'stub')
    vlm_api_key = args.gemini_api_key if hasattr(args, 'gemini_api_key') and args.gemini_api_key else config.get('gemini_api_key')

    # Run playtest
    try:
        run_playtest(
            url=url,
            steps=steps,
            output_dir=output_dir,
            controller_type=controller_type,
            seed=seed,
            headless=headless,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
            game_context=game_context,
            vlm_provider=vlm_provider,
            vlm_api_key=vlm_api_key
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
