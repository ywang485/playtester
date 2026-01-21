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

from ..core.observation import Observation, ConsoleEvent, DOMMetadata, IssueDetection
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
        timeout_ms: int = 30000,
        record_video: bool = True,
        video_dir: Optional[Path] = None
    ):
        """
        Initialize browser environment.

        Args:
            headless: Run browser in headless mode
            viewport_width: Browser viewport width
            viewport_height: Browser viewport height
            timeout_ms: Default timeout for operations
            record_video: Enable video recording of the session
            video_dir: Directory to save video files (defaults to output_dir/videos)
        """
        self.headless = headless
        self.viewport_width = viewport_width
        self.viewport_height = viewport_height
        self.timeout_ms = timeout_ms
        self.record_video = record_video
        self.video_dir = video_dir

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._page: Optional[Page] = None

        # Buffer for console events since last observation
        self._console_buffer: List[ConsoleEvent] = []

        # Issue tracking
        self._page_crashed: bool = False
        self._webgl_context_lost: bool = False
        self._http_errors: List[str] = []
        self._asset_load_failures: List[str] = []
        self._previous_dom_hash: Optional[str] = None
        self._state_unchanged_steps: int = 0

        # Console log accumulator for final report
        self._all_console_events: List[ConsoleEvent] = []

        self._current_step = 0
        self._video_path: Optional[Path] = None

        logger.info(
            f"BrowserEnv initialized (headless={headless}, "
            f"viewport={viewport_width}x{viewport_height}, "
            f"record_video={record_video})"
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

        # Configure video recording if enabled
        context_options = {
            'viewport': {'width': self.viewport_width, 'height': self.viewport_height},
            'accept_downloads': False,
            'ignore_https_errors': True
        }

        if self.record_video and self.video_dir:
            # Ensure video directory exists
            self.video_dir.mkdir(parents=True, exist_ok=True)
            context_options['record_video_dir'] = str(self.video_dir)
            context_options['record_video_size'] = {
                'width': self.viewport_width,
                'height': self.viewport_height
            }
            logger.info(f"Video recording enabled, saving to: {self.video_dir}")

        self._context = self._browser.new_context(**context_options)

        self._page = self._context.new_page()

        # Set up event listeners
        self._page.on("console", self._on_console_message)
        self._page.on("pageerror", self._on_page_error)
        self._page.on("crash", self._on_crash)

        # Set up network monitoring
        self._page.on("response", self._on_response)
        self._page.on("requestfailed", self._on_request_failed)

        # Inject WebGL context loss detection
        self._inject_webgl_monitor()

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
        self._all_console_events.append(event)

    def _on_page_error(self, error) -> None:
        """Handle uncaught page errors."""
        logger.error(f"Page error detected: {error}")
        self._page_crashed = True
        error_event = ConsoleEvent(
            timestamp=datetime.utcnow().isoformat() + "Z",
            level="error",
            text=f"Uncaught page error: {error}",
            location=None
        )
        self._console_buffer.append(error_event)
        self._all_console_events.append(error_event)

    def _on_crash(self) -> None:
        """Handle page crash."""
        logger.error("Page crashed!")
        self._page_crashed = True

    def _on_response(self, response) -> None:
        """Monitor HTTP responses for errors."""
        if response.status >= 400:
            error_msg = f"{response.status} {response.url}"
            self._http_errors.append(error_msg)
            if response.status >= 500:
                logger.warning(f"Server error: {error_msg}")
            elif response.status >= 400:
                logger.warning(f"Client error: {error_msg}")

    def _on_request_failed(self, request) -> None:
        """Handle failed network requests."""
        failure = request.failure
        if failure:
            error_msg = f"{request.url}: {failure}"
            self._asset_load_failures.append(error_msg)
            logger.warning(f"Asset load failure: {error_msg}")

    def _inject_webgl_monitor(self) -> None:
        """Inject JavaScript to monitor WebGL context loss."""
        if not self._page:
            return

        script = """
        (() => {
            window.__playtester_webgl_lost = false;

            // Monitor all canvas elements
            const monitorCanvas = (canvas) => {
                const ctx = canvas.getContext('webgl') || canvas.getContext('webgl2');
                if (ctx) {
                    canvas.addEventListener('webglcontextlost', (event) => {
                        console.error('WebGL context lost!');
                        window.__playtester_webgl_lost = true;
                    }, false);
                }
            };

            // Monitor existing canvases
            document.querySelectorAll('canvas').forEach(monitorCanvas);

            // Monitor future canvases
            const observer = new MutationObserver((mutations) => {
                mutations.forEach((mutation) => {
                    mutation.addedNodes.forEach((node) => {
                        if (node.tagName === 'CANVAS') {
                            monitorCanvas(node);
                        }
                    });
                });
            });

            observer.observe(document.body, { childList: true, subtree: true });
        })();
        """

        try:
            self._page.evaluate(script)
            logger.debug("WebGL context monitoring injected")
        except Exception as e:
            logger.warning(f"Failed to inject WebGL monitor: {e}")

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

        # Detect issues
        issues = self._detect_issues()

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
            dom_metadata=dom_metadata,
            issues=issues
        )

        # Clear console buffer (but keep in all_console_events)
        self._console_buffer.clear()

        # Clear per-step issue tracking
        self._http_errors.clear()
        self._asset_load_failures.clear()

        logger.debug(f"Observation captured: {len(observation.console_events)} console events")
        if issues and issues.has_issues():
            logger.warning(f"Issues detected at step {self._current_step}: {issues}")

        return observation

    def _detect_issues(self) -> IssueDetection:
        """
        Detect various issues in the current browser state.

        Returns:
            IssueDetection object with detected issues
        """
        if not self._page:
            return IssueDetection()

        # Check for WebGL context loss
        webgl_lost = False
        try:
            webgl_lost = self._page.evaluate("() => window.__playtester_webgl_lost || false")
        except Exception as e:
            logger.debug(f"Could not check WebGL status: {e}")

        # Detect soft-locks by checking DOM state changes
        current_dom_hash = self._compute_dom_hash()
        if current_dom_hash == self._previous_dom_hash:
            self._state_unchanged_steps += 1
        else:
            self._state_unchanged_steps = 0
        self._previous_dom_hash = current_dom_hash

        # Check if page has focus
        focus_lost = False
        try:
            focus_lost = not self._page.evaluate("() => document.hasFocus()")
        except Exception as e:
            logger.debug(f"Could not check focus: {e}")

        # Detect modals and overlays
        modal_detected = False
        overlay_blocking = False
        try:
            ui_state = self._page.evaluate("""
                () => {
                    // Check for modal dialogs
                    const modals = document.querySelectorAll('[role="dialog"], .modal, [class*="modal"]');
                    const hasModal = modals.length > 0;

                    // Check for blocking overlays
                    const overlays = document.querySelectorAll('.overlay, [class*="overlay"], [class*="backdrop"]');
                    const hasOverlay = Array.from(overlays).some(el => {
                        const style = window.getComputedStyle(el);
                        return style.display !== 'none' && style.visibility !== 'hidden';
                    });

                    return { hasModal, hasOverlay };
                }
            """)
            modal_detected = ui_state.get("hasModal", False)
            overlay_blocking = ui_state.get("hasOverlay", False)
        except Exception as e:
            logger.debug(f"Could not check UI state: {e}")

        # Measure frame time and detect long tasks
        frame_time_ms = None
        long_task_detected = False
        try:
            perf_data = self._page.evaluate("""
                () => {
                    if (!performance || !performance.getEntriesByType) {
                        return null;
                    }

                    // Get recent frame timing
                    const frameEntries = performance.getEntriesByType('frame');
                    const recentFrame = frameEntries.length > 0 ? frameEntries[frameEntries.length - 1] : null;

                    // Check for long tasks
                    const longTasks = performance.getEntriesByType('longtask');
                    const hasLongTask = longTasks.some(task => task.duration > 50);

                    return {
                        frameTime: recentFrame ? recentFrame.duration : null,
                        hasLongTask: hasLongTask
                    };
                }
            """)
            if perf_data:
                frame_time_ms = perf_data.get("frameTime")
                long_task_detected = perf_data.get("hasLongTask", False)
        except Exception as e:
            logger.debug(f"Could not get performance data: {e}")

        return IssueDetection(
            page_error=self._page_crashed,
            webgl_context_lost=webgl_lost,
            state_unchanged_for_steps=self._state_unchanged_steps,
            focus_lost=focus_lost,
            modal_detected=modal_detected,
            overlay_blocking=overlay_blocking,
            frame_time_ms=frame_time_ms,
            long_task_detected=long_task_detected,
            http_errors=self._http_errors.copy(),
            asset_load_failures=self._asset_load_failures.copy()
        )

    def _compute_dom_hash(self) -> str:
        """
        Compute a hash of the DOM state for soft-lock detection.

        Returns:
            Hash string representing current DOM state
        """
        if not self._page:
            return ""

        try:
            dom_state = self._page.evaluate("""
                () => {
                    // Capture key DOM properties that indicate state changes
                    return {
                        title: document.title,
                        url: window.location.href,
                        bodyHtml: document.body ? document.body.innerHTML.substring(0, 1000) : '',
                        activeElement: document.activeElement ? document.activeElement.tagName : '',
                        scrollY: window.scrollY,
                        canvasCount: document.querySelectorAll('canvas').length
                    };
                }
            """)
            # Simple hash using string representation
            import hashlib
            return hashlib.md5(str(dom_state).encode()).hexdigest()
        except Exception as e:
            logger.debug(f"Could not compute DOM hash: {e}")
            return ""

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

    def close(self, output_dir: Optional[Path] = None) -> Optional[Path]:
        """
        Clean up browser resources and finalize video recording.

        Args:
            output_dir: Optional output directory to save console log

        Returns:
            Path to the saved video file, or None if video recording was disabled
        """
        logger.info("Closing browser")

        video_path = None

        if self._page and self.record_video:
            # Get video path before closing context
            try:
                video_path = self._page.video.path()
                logger.info(f"Video will be saved to: {video_path}")
            except Exception as e:
                logger.warning(f"Could not get video path: {e}")

        # Save console log before closing
        if output_dir:
            self._save_console_log(output_dir)

        if self._context:
            self._context.close()
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

        if video_path:
            video_path = Path(video_path)
            if video_path.exists():
                logger.info(f"Video recording saved: {video_path}")
                self._video_path = video_path
            else:
                logger.warning(f"Video file not found at: {video_path}")
                video_path = None

        logger.info("Browser closed")
        return video_path

    def _save_console_log(self, output_dir: Path) -> None:
        """
        Save all console events to a console.log file.

        Args:
            output_dir: Directory to save console log
        """
        console_log_path = output_dir / "console.log"

        try:
            with open(console_log_path, "w") as f:
                f.write("# Browser Console Log\n")
                f.write(f"# Total events: {len(self._all_console_events)}\n")
                f.write("#" + "="*78 + "\n\n")

                for event in self._all_console_events:
                    location_str = f" [{event.location}]" if event.location else ""
                    f.write(f"[{event.timestamp}] [{event.level.upper()}]{location_str}\n")
                    f.write(f"{event.text}\n\n")

            logger.info(f"Console log saved: {console_log_path} ({len(self._all_console_events)} events)")
        except Exception as e:
            logger.error(f"Failed to save console log: {e}")

    def get_video_path(self) -> Optional[Path]:
        """
        Get the path to the recorded video.

        Returns:
            Path to video file, or None if recording was disabled or not yet saved
        """
        return self._video_path

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
