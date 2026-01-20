# Playtester: Hybrid Heuristic + VLM Browser Playtesting Agent

A production-quality research codebase for automated browser-based playtesting of WebGL games. This system combines deterministic heuristic control with optional Vision-Language Model (VLM) advisory capabilities.

## Overview

Playtester is designed as an extensible foundation for automated game testing research. It provides a clean separation between environment, policy, perception, and logging layers while maintaining production-quality code standards.

### Key Principles

1. **VLM as Advisor, Not Driver**: The VLM provides suggestions but has no direct browser access or authority to execute actions
2. **Deterministic and Reproducible**: Given a seed, the agent produces identical behavior
3. **Observable and Inspectable**: All actions, observations, and decisions are logged in structured format
4. **Modular and Extensible**: Clear interfaces allow easy addition of new controllers, detectors, and analysis tools

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Controller                           │
│         (Deterministic heuristic + optional VLM advice)      │
└─────────────────────┬───────────────────┬───────────────────┘
                      │                   │
              select_action()     suggest_action()
                      │                   │
                      v                   v
┌─────────────────────────────┐  ┌─────────────────────────┐
│      BrowserEnv             │  │     VLMClient           │
│  (Playwright abstraction)   │  │   (Advisory only)       │
└─────────────────────────────┘  └─────────────────────────┘
           │        │
      act()│        │observe()
           v        v
    ┌─────────────────────┐
    │   Browser (Chromium) │
    └─────────────────────┘
           │
           v
    ┌─────────────────────┐
    │  TrajectoryLogger   │
    │   (JSONL + assets)  │
    └─────────────────────┘
```

### Core Components

#### 1. **Core Data Models** (`src/playtester/core/`)

- **`Observation`**: Captures browser state at a point in time
  - Screenshot path
  - Console events
  - DOM metadata (minimal for MVP)
  - Timestamp
  - Extensible via `extra` field

- **`Action`**: Represents atomic browser operations
  - `WaitAction`: Pause for specified duration
  - `ClickAction`: Click at coordinates
  - `KeypressAction`: Press keyboard key
  - All actions are serializable

- **`TrajectoryLogger`**: Append-only JSONL logging
  - Versioned schema (v1.0.0)
  - Records observations, actions, and events
  - Stores screenshots separately
  - Enables replay and analysis

#### 2. **Browser Environment** (`src/playtester/browser/`)

- **`BrowserEnv`**: Clean abstraction over Playwright
  - Headful/headless Chromium
  - WebGL support (SwiftShader software rendering)
  - Console event capture
  - Screenshot capture
  - Atomic action execution
  - No direct access from controllers

#### 3. **Controllers** (`src/playtester/controller/`)

- **`Controller`** (abstract base): Policy interface
  - `select_action(observation) -> action`
  - Stateful but deterministic
  - No direct browser access

- **`RandomController`**: Baseline exploration
  - Randomly selects actions
  - Configurable action probabilities
  - Useful for fuzzing and baselines

- **`VLMAdvisedController`**: Hybrid approach
  - Queries VLM at intervals
  - Falls back to heuristics
  - VLM is advisory, not authoritative

#### 4. **VLM Interface** (`src/playtester/vlm/`)

- **`VLMClient`** (abstract): Interface for VLM integration
  - `suggest_action()`: Get action suggestion
  - `get_semantic_analysis()`: Get semantic insights
  - Designed for async, fallible operations

- **`StubVLMClient`**: Placeholder implementation
  - Returns safe defaults
  - Documents expected behavior
  - Replace with real VLM integration

## Installation

### Local Installation

```bash
# Clone repository
git clone <repository-url>
cd playtester

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium

# Install package
pip install -e .
```

### Docker Installation

```bash
# Build image
docker build -t playtester .

# Run example (mount output directory)
docker run -v $(pwd)/output:/app/output playtester \
    playtester --url https://example.com/game --steps 50
```

## Usage

### Basic CLI Usage

```bash
# Run with random controller
playtester --url https://example.com/game --steps 50

# Run with VLM controller (stub)
playtester --url https://example.com/game --steps 50 --controller vlm

# Run headless with specific seed
playtester --url https://example.com/game --steps 100 \
    --headless --seed 42 --output-dir ./my-output

# Run with verbose logging
playtester --url https://example.com/game --steps 20 --verbose
```

### CLI Arguments

**Core Arguments:**
- `--url`: URL of WebGL game to test (required)
- `--steps`: Number of steps to run (default: 50)
- `--output-dir`: Directory for output artifacts (default: ./output)
- `--controller`: Controller type: `random` or `vlm` (default: random)
- `--seed`: Random seed for reproducibility (default: random)
- `--headless`: Run browser in headless mode (default: false)
- `--viewport-width`: Browser viewport width (default: 1280)
- `--viewport-height`: Browser viewport height (default: 720)
- `--verbose`: Enable verbose logging

**Game Context Arguments:**
- `--config`: Path to JSON config file with game context and settings
- `--game-name`: Name of the game (for logging and VLM context)
- `--game-goal`: Description of the game goal (for VLM context)
- `--game-controls`: Description of game controls (for VLM context)
- `--known-bugs`: Comma-separated list of known bug areas to monitor

### Using Config Files

For complex setups or reusable configurations, use JSON config files:

```bash
# Run with config file
playtester --config examples/monopoly_config.json

# Override specific settings
playtester --config examples/monopoly_config.json --steps 200 --seed 123
```

**Config file format:**

```json
{
  "url": "https://example.com/game",
  "steps": 100,
  "controller": "vlm",
  "seed": 42,
  "game_context": {
    "name": "My Game",
    "goal": "Complete all levels",
    "controls": {
      "click": "Interact with objects",
      "keys": "Arrow keys to move, Space to jump"
    },
    "known_bugs": [
      "UI freeze on level 3",
      "Score not saving"
    ]
  }
}
```

See `examples/` directory for more examples.

### Using Game Context

Game context helps the VLM make informed decisions:

```bash
# Provide context via CLI
playtester --url https://game.example.com \
    --controller vlm \
    --game-name "Platformer" \
    --game-goal "Reach the exit door in each level" \
    --game-controls "Arrow keys move, Space jumps, Click interacts" \
    --known-bugs "Level 3 door may not open, Fall detection inconsistent"

# Or via config file (recommended for complex games)
playtester --config my_game_config.json
```

The VLM will use this context to:
- Understand the game objective
- Know which controls are available
- Watch for specific known issues
- Make more informed action decisions

### Output Structure

```
output/
├── trajectory.jsonl          # Complete session log
└── screenshots/              # Step-by-step screenshots
    ├── step_0000.png
    ├── step_0001.png
    └── ...
```

### Trajectory Format

Each line in `trajectory.jsonl` is a JSON object with a `type` field:

```json
{"type": "metadata", "schema_version": "1.0.0", "session_id": "...", "metadata": {...}}
{"type": "observation", "data": {"step": 0, "timestamp": "...", "screenshot_path": "...", ...}}
{"type": "action", "step": 0, "timestamp": "...", "data": {"type": "click", "x": 640, "y": 360}}
{"type": "observation", "data": {"step": 1, ...}}
{"type": "action", "step": 1, ...}
...
{"type": "finalize", "timestamp": "...", "metadata": {"total_steps": 50}}
```

## Programmatic Usage

```python
from pathlib import Path
from playtester.browser import BrowserEnv
from playtester.controller import RandomController
from playtester.core import TrajectoryLogger

# Initialize components
output_dir = Path("./output")
trajectory_logger = TrajectoryLogger(output_dir)
trajectory_logger.initialize({"url": "https://example.com/game"})

controller = RandomController(seed=42)
env = BrowserEnv(headless=False)

# Run playtest
env.start("https://example.com/game")

for step in range(10):
    # Observe
    screenshot_path = trajectory_logger.get_screenshot_path(step, relative=False)
    observation = env.observe(screenshot_path)
    trajectory_logger.log_observation(observation)

    # Act
    action = controller.select_action(observation)
    trajectory_logger.log_action(action, step)
    env.act(action)
    controller.on_action_executed(action)

# Clean up
env.close()
trajectory_logger.finalize()
```

## What's Implemented (MVP)

✅ **Core Infrastructure**
- Clean action → observation loop
- Serializable data models
- JSONL trajectory logging
- Screenshot capture
- Console event capture

✅ **Browser Integration**
- Playwright-based environment
- WebGL support
- Headful/headless modes
- Configurable viewport

✅ **Controllers**
- Base controller interface
- Random exploration controller
- VLM-advised controller (with stub VLM)

✅ **Extensibility**
- Clear module boundaries
- Abstract interfaces
- Versioned schemas
- Plugin-ready architecture

✅ **Deployment**
- CLI interface
- Docker support
- Configurable logging

✅ **Game Context Support**
- JSON config files for reusable setups
- CLI arguments for quick context input
- Game goal, controls, and known bugs
- Context passed to VLM for informed decisions
- Logged in trajectory for analysis

## What's NOT Implemented (By Design)

The following are intentionally deferred to maintain a clean MVP:

❌ **Real VLM Integration**
- Stub only; interface is defined
- Replace `StubVLMClient` with real API client
- Add prompt engineering, caching, rate limiting

❌ **Bug Detectors**
- No crash detection
- No soft-lock detection
- No performance monitoring
- Interface ready via `VLMClient.get_semantic_analysis()`

❌ **Advanced Observations**
- No HAR (HTTP Archive) capture
- No video recording
- No accessibility tree
- No WebGL context inspection
- Extension point exists via `Observation.extra`

❌ **Replay System**
- Trajectories are logged but not replayed
- Add `replay` command to CLI

❌ **Analysis Tools**
- No trajectory analysis utilities
- No visualization tools
- No bug report generation

❌ **Advanced Controllers**
- No learning-based controllers
- No goal-directed planning
- No coverage-guided exploration

## Design Decisions

### Why VLM as Advisor?

VLMs are powerful but:
- Have variable latency
- May fail or be unavailable
- Are expensive to query
- May produce invalid actions

Making them advisory ensures:
- Deterministic fallback behavior
- Reproducibility
- Graceful degradation
- Clear separation of concerns

### Why JSONL for Trajectories?

- **Streaming**: Can write during long sessions
- **Parseable**: Easy to process line-by-line
- **Diffable**: Git-friendly format
- **Appendable**: Safe for concurrent writes
- **Flexible**: Easy to add new entry types

### Why Playwright?

- **WebGL support**: Better than Selenium for games
- **Modern API**: Async-first, well-documented
- **Developer tools**: Built-in screenshot, video, tracing
- **Cross-browser**: Easy to test on Firefox/WebKit later

### Why No Global State?

- **Testability**: Easy to mock and unit test
- **Reproducibility**: No hidden dependencies
- **Concurrency**: Safe for parallel runs
- **Clarity**: Explicit data flow

## Extending the System

### Adding a New Action Type

1. Create action class in `src/playtester/core/action.py`:

```python
@dataclass
class ScrollAction(Action):
    delta_y: int

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "scroll", "delta_y": self.delta_y}

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'ScrollAction':
        return ScrollAction(delta_y=data["delta_y"])

    @property
    def action_type(self) -> str:
        return "scroll"
```

2. Add to `action_from_dict()` factory
3. Implement in `BrowserEnv._execute_scroll()`

### Adding a New Controller

1. Subclass `Controller` in `src/playtester/controller/`:

```python
class MyController(Controller):
    def select_action(self, observation: Observation) -> Action:
        # Your logic here
        return action
```

2. Add to `cli.py`'s `create_controller()` factory
3. Add CLI argument choice

### Adding Real VLM Integration

1. Implement `VLMClient` interface:

```python
class GPT4VisionClient(VLMClient):
    def __init__(self, api_key: str):
        self.client = openai.Client(api_key=api_key)

    def suggest_action(self, observation: Observation) -> Optional[Action]:
        # Encode screenshot, query API, parse response
        pass
```

2. Update `create_controller()` to instantiate real client
3. Add API key configuration

### Adding a Bug Detector

1. Create detector interface:

```python
class BugDetector(ABC):
    @abstractmethod
    def check(self, observation: Observation) -> Optional[dict]:
        pass
```

2. Integrate into main loop:

```python
detector = CrashDetector()
if bug := detector.check(observation):
    trajectory_logger.log_event("bug_detected", bug)
```

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests (when added)
pytest

# Type checking
mypy src/

# Linting
ruff check src/

# Formatting
black src/
```

### Code Style

- **Line length**: 100 characters
- **Type hints**: Preferred but not required
- **Docstrings**: Required for public APIs
- **Logging**: Use structured logging, not print statements

## Future Directions

This codebase is designed to support:

- **VLM Integration**: GPT-4V, Claude, Gemini, LLaVA
- **Bug Detection**: Visual artifacts, crashes, soft-locks, dead-ends
- **Performance Monitoring**: FPS, memory, network activity
- **Advanced Observation**: HAR capture, video recording, accessibility tree
- **Replay System**: Deterministic replay from trajectories
- **Analysis Tools**: Trajectory visualization, bug report synthesis
- **CI Integration**: Automated playtest runs in GitHub Actions
- **Multi-game Support**: Game-specific configurations and detectors
- **Learning Controllers**: RL, imitation learning, goal-conditioned policies

## License

[Specify license here]

## Contributing

[Add contribution guidelines here]

## Citation

If you use this codebase in research, please cite:

```
[Add citation info]
```

## Support

For issues, questions, or contributions, please [open an issue](link-to-issues) or contact the research team.