"""
Browser environment abstraction using Playwright.

This module provides a clean interface between the controller and the browser,
ensuring separation of concerns and making it easy to:
- Mock the browser for testing
- Switch browser implementations
- Add instrumentation and logging
"""

import logging
import platform
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, ConsoleMessage

from ..core.observation import Observation, ConsoleEvent, DOMMetadata
from ..core.action import Action, WaitAction, ClickAction, KeypressAction, MouseMoveAction

logger = logging.getLogger(__name__)


class BrowserEnv:
    """
    Browser environment for executing actions and capturing observations.

    This is the primary interface between the controller and the browser.
    It abstracts away Playwright-specific details and provides a clean
    action → observation loop.

    Design notes:
    - The controller never directly accesses browser APIs
    - All state capture goes through the observation model
    - Actions are executed atomically
    - Console events are buffered between observations
    """

    def __init__(
        self,
        headless: bool = False,
        viewport_width: int = 1280,
        viewport_height: int = 720,
        timeout_ms: int = 30000
    ):
        """
        Initialize browser environment.

        Args:
            headless: Run browser in headless mode
            viewport_width: Browser viewport width
            viewport_height: Browser viewport height
            timeout_ms: Default timeout for operations
        """
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.timeout_ms = timeout_ms

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        # Buffer for console events since last observation
        self._console_buffer: List[ConsoleEvent] = []

        self._current_step = 0

        logger.info(
            f"BrowserEnv initialized (headless={headless}, "
            f"viewport={viewport_width}x{viewport_height})"
        )

    def start(self, url: str) -> None:
        """
        Start the browser and navigate to the initial URL.

        Args:
            url: URL to navigate to
        """
        logger.info(f"Starting browser and navigating to: {url}")

        self._playwright = sync_playwright().start()

        # Configure browser args for WebGL/WebGL2 support
        # Platform-specific configuration for best compatibility
        system = platform.system()

        browser_args = [
            '--enable-webgl',
            '--enable-webgl2',
            '--disable-blink-features=AutomationControlled',
            '--ignore-gpu-blocklist',
        ]

        # On Linux/Docker: use ANGLE + SwiftShader for software rendering
        # On macOS/Windows: use native GPU support (better compatibility)
        if system == 'Linux' or self.headless:
            logger.info("Using ANGLE + SwiftShader for WebGL2 (Linux/headless mode)")
            browser_args.extend([
                '--use-gl=angle',  # ANGLE for better WebGL2 support
                '--use-angle=swiftshader',  # SwiftShader backend for ANGLE
                '--enable-features=WebGL2ComputeContext',
                '--disable-gpu-vsync',  # Prevent vsync issues
            ])

            if self.headless:
                browser_args.extend([
                    '--disable-gpu',  # Disable GPU in headless (use software)
                    '--disable-dev-shm-usage',  # Avoid shared memory issues
                    '--no-sandbox',  # Required for some headless environments
                ])
        else:
            logger.info(f"Using native GPU support for WebGL2 ({system})")
            browser_args.extend([
                '--enable-features=WebGL2ComputeContext',
                '--disable-gpu-vsync',
            ])

        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=browser_args
        )

        self._context = self._browser.new_context(
            viewport={'width': self.viewport_width, 'height': self.viewport_height},
            accept_downloads=False,
            ignore_https_errors=True
        )

        self._page = self._context.new_page()

        # Set up console event listener
        self._page.on("console", self._on_console_message)

        # Navigate to URL
        self._page.goto(url, timeout=self.timeout_ms, wait_until="domcontentloaded")

        logger.info("Browser started successfully")

    def _on_console_message(self, msg: ConsoleMessage) -> None:
        """
        Handle console messages from the browser.

        Args:
            msg: Console message from Playwright
        """
        event = ConsoleEvent(
            timestamp=datetime.utcnow().isoformat() + "Z",
            level=msg.type,
            text=msg.text,
            location=msg.location.get("url") if msg.location else None
        )
        self._console_buffer.append(event)

    def observe(self, screenshot_path: Path) -> Observation:
        """
        Capture the current browser state as an observation.

        Args:
            screenshot_path: Absolute path to save screenshot

        Returns:
            Observation object
        """
        if not self._page:
            raise RuntimeError("Browser not started")

        logger.debug(f"Capturing observation for step {self._current_step}")

        # Take screenshot
        self._page.screenshot(path=str(screenshot_path), full_page=False)

        # Capture DOM metadata
        dom_metadata = self._capture_dom_metadata()

        # Create observation with buffered console events
        # Compute relative path from current directory to maintain "screenshots/" subdirectory
        try:
            relative_path = screenshot_path.relative_to(Path.cwd())
        except ValueError:
            # Fallback if screenshot_path is not relative to cwd
            relative_path = Path("screenshots") / screenshot_path.name

        observation = Observation(
            step=self._current_step,
            timestamp=Observation.create_timestamp(),
            screenshot_path=str(relative_path),  # Store relative path with subdirectory
            console_events=self._console_buffer.copy(),
            dom_metadata=dom_metadata
        )

        # Clear console buffer
        self._console_buffer.clear()

        logger.debug(f"Observation captured: {len(observation.console_events)} console events")

        return observation

    def _capture_dom_metadata(self) -> DOMMetadata:
        """
        Capture minimal DOM metadata.

        Returns:
            DOMMetadata object
        """
        if not self._page:
            raise RuntimeError("Browser not started")

        # Use Playwright's evaluate to get page info
        page_info = self._page.evaluate("""
            () => ({
                url: window.location.href,
                title: document.title,
                viewportWidth: window.innerWidth,
                viewportHeight: window.innerHeight,
                visibleTextLength: document.body ? document.body.innerText.length : 0
            })
        """)

        return DOMMetadata(
            url=page_info["url"],
            title=page_info["title"],
            viewport_width=page_info["viewportWidth"],
            viewport_height=page_info["viewportHeight"],
            visible_text_length=page_info["visibleTextLength"]
        )

    def act(self, action: Action) -> None:
        """
        Execute an action in the browser.

        Args:
            action: Action to execute

        Raises:
            RuntimeError: If browser not started
            ValueError: If action type is unknown
        """
        if not self._page:
            raise RuntimeError("Browser not started")

        logger.debug(f"Executing action: {action.action_type}")

        if isinstance(action, WaitAction):
            self._execute_wait(action)
        elif isinstance(action, ClickAction):
            self._execute_click(action)
        elif isinstance(action, KeypressAction):
            self._execute_keypress(action)
        elif isinstance(action, MouseMoveAction):
            self._execute_mouse_move(action)
        else:
            raise ValueError(f"Unknown action type: {type(action)}")

        self._current_step += 1

    def _execute_wait(self, action: WaitAction) -> None:
        """Execute a wait action."""
        self._page.wait_for_timeout(action.duration_ms)

    def _execute_click(self, action: ClickAction) -> None:
        """Execute a click action."""
        self._page.mouse.click(action.x, action.y, button=action.button)

    def _execute_keypress(self, action: KeypressAction) -> None:
        """Execute a keypress action."""
        # Build modifier string for Playwright
        modifiers_str = "+".join(action.modifiers) if action.modifiers else ""
        key_combo = f"{modifiers_str}+{action.key}" if modifiers_str else action.key

        self._page.keyboard.press(key_combo)

    def _execute_mouse_move(self, action: MouseMoveAction) -> None:
        """Execute a mouse move action."""
        self._page.mouse.move(action.x, action.y)

    def close(self) -> None:
        """Clean up browser resources."""
        logger.info("Closing browser")

        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

        logger.info("Browser closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
