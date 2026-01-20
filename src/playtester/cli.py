"""
CLI entry point for the playtester.

Provides a command-line interface for running playtest sessions.
"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Optional

from .browser.env import BrowserEnv
from .controller import RandomController, VLMAdvisedController
from .controller.base import Controller
from .core.trajectory import TrajectoryLogger
from .vlm import StubVLMClient

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
    viewport_height: int = 720
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
    """
    logger.info("="*80)
    logger.info(f"Starting playtest session")
    logger.info(f"URL: {url}")
    logger.info(f"Steps: {steps}")
    logger.info(f"Controller: {controller_type}")
    logger.info(f"Seed: {seed}")
    logger.info(f"Output: {output_dir}")
    logger.info("="*80)

    # Initialize trajectory logger
    trajectory_logger = TrajectoryLogger(output_dir)
    trajectory_logger.initialize({
        "url": url,
        "steps": steps,
        "controller_type": controller_type,
        "seed": seed,
        "viewport": {"width": viewport_width, "height": viewport_height}
    })

    # Initialize controller
    controller = create_controller(
        controller_type=controller_type,
        seed=seed,
        viewport_width=viewport_width,
        viewport_height=viewport_height
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
    viewport_height: int
) -> Controller:
    """
    Factory function to create controllers.

    Args:
        controller_type: Type of controller to create
        seed: Random seed
        viewport_width: Browser viewport width
        viewport_height: Browser viewport height

    Returns:
        Controller instance

    Raises:
        ValueError: If controller type is unknown
    """
    if controller_type == "random":
        return RandomController(
            seed=seed,
            viewport_width=viewport_width,
            viewport_height=viewport_height
        )
    elif controller_type == "vlm":
        # For MVP, use stub VLM client
        vlm_client = StubVLMClient()
        return VLMAdvisedController(
            seed=seed,
            vlm_client=vlm_client,
            viewport_width=viewport_width,
            viewport_height=viewport_height
        )
    else:
        raise ValueError(f"Unknown controller type: {controller_type}")


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

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Run playtest
    try:
        run_playtest(
            url=args.url,
            steps=args.steps,
            output_dir=args.output_dir,
            controller_type=args.controller,
            seed=args.seed,
            headless=args.headless,
            viewport_width=args.viewport_width,
            viewport_height=args.viewport_height
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
