# Playtester: General-purpose Browser Playtesting Agent

## Overview

Playtester is an extensible foundation codebase for automated browser-based game testing that provides clean separation between environment, policy, perception, and logging layers while maintaining production-quality code standards. This current appraoch combines low-level motion control with high-level Vision-Language Model (VLM) advisory capabilities for intelligent, reproducible game testing.

### Key Features

✨ **Hybrid Intelligence**: Combines heuristic-based, VLM-powered, and possibly reinforcement-learning based action planning
✨ **Comprehensive Monitoring**: Detects crashes, soft-locks, performance issues, and UI dead-ends
✨ **Rich Artifacts**: Video recording, console logs, DOM snapshots, and frame-by-frame screenshots
✨ **Goal-Directed Testing**: Allow specifying game testing goals.
✨ **WebGL2 Support**: Full compatibility with Godot, Unity, Three.js, and custom WebGL games

## Usage

### Quick Start

```bash
# Random controller (baseline)
playtester --url https://example.com/game --steps 50

# VLM-powered intelligent testing
playtester --url https://example.com/game \
    --steps 100 \
    --controller vlm \
    --vlm-provider gemini \
    --game-name "My Game" \
    --game-goal "Complete tutorial and reach level 2"
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

**VLM Arguments:**
- `--vlm-provider`: VLM provider to use: `stub` (default) or `gemini`
- `--gemini-api-key`: Google API key for Gemini (or set `GOOGLE_API_KEY` env var)

**Output Arguments:**
- `--record-video`: Record video of playtesting session (default: enabled)
- `--no-video`: Disable video recording

### Using Config Files

For complex setups or reusable configurations:

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
  },
  "vlm_provider": "gemini"
}
```

### Output Structure

Each playtesting session creates a timestamped directory:

```
output/
└── 20260120_143052/           # Session timestamp (YYYYMMDD_HHMMSS)
    ├── trajectory.jsonl       # Complete session log with all events
    ├── screenshots/           # Step-by-step screenshots
    │   ├── step_0000.png
    │   ├── step_0001.png
    │   └── ...
    ├── videos/                # Video recording (if enabled)
    │   └── recording.webm
    ├── console.log            # Full browser console output + errors
    └── dom_snapshots/         # DOM state at session end
        ├── snapshot.html      # Complete HTML content
        └── layout_metadata.json  # Computed layout for all elements
```

### Trajectory Format

Each line in `trajectory.jsonl` is a JSON object:

```json
{"type": "metadata", "schema_version": "1.0.0", "session_id": "...", "metadata": {...}}
{"type": "observation", "data": {"step": 0, "timestamp": "...", "screenshot_path": "...", "issues": {...}}}
{"type": "action", "step": 0, "timestamp": "...", "data": {"type": "click", "x": 640, "y": 360}}
{"type": "event", "event_type": "vlm_action_sequence_response", "data": {"raw_response": "..."}}
{"type": "event", "event_type": "video_saved", "data": {"video_path": "videos/recording.webm"}}
{"type": "event", "event_type": "issue_summary", "data": {"crashes": 0, "soft_locks": 0, ...}}
{"type": "finalize", "timestamp": "...", "metadata": {"total_steps": 50}}
```

**Event Types:**
- `metadata`: Session initialization
- `observation`: Browser state at each step (includes issue detection)
- `action`: Action executed at each step
- `event`: Notable occurrences (VLM outputs, artifacts saved, issue summary)
- `finalize`: Session completion

### Issue Detection

The playtester automatically monitors for common issues:

**Detected Issue Types:**

1. **Crashes**: Page errors, browser crashes, WebGL context loss
2. **Soft-locks**: DOM state unchanged for >10 steps despite inputs
3. **Input Deadness**: Focus loss, unresponsive controls
4. **UI Dead-ends**: Uncloseable modals, blocking overlays
5. **Performance Regressions**: Frame time >100ms, long tasks >50ms
6. **Network Failures**: HTTP 4xx/5xx errors, asset load failures

**Issue Summary Output:**

```
================================================================================
ISSUES DETECTED DURING PLAYTESTING:
  Crashes: 0
  WebGL Context Lost: 0
  Soft-locks: 2
  Focus Issues: 0
  UI Dead-ends: 1
  Performance Issues: 5
  Network Failures: 0
  Total Issues: 8
================================================================================
```

### Programmatic Usage

**Basic Usage (Random Controller)**:

```python
from pathlib import Path
from datetime import datetime
from playtester.browser import BrowserEnv
from playtester.controller import RandomController
from playtester.core import TrajectoryLogger

# Create session directory
session_timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
session_dir = Path("./output") / session_timestamp
session_dir.mkdir(parents=True, exist_ok=True)

# Initialize trajectory logger
trajectory_logger = TrajectoryLogger(session_dir, session_id=session_timestamp)
trajectory_logger.initialize({
    "url": "https://example.com/game",
    "steps": 10,
    "controller": "random"
})

# Initialize controller and browser
controller = RandomController(seed=42)
video_dir = session_dir / "videos"
env = BrowserEnv(headless=False, record_video=True, video_dir=video_dir)

# Run playtest
env.start("https://example.com/game")

for step in range(10):
    # Observe (captures screenshot + console + issues)
    screenshot_path = trajectory_logger.get_screenshot_path(step, relative=False)
    observation = env.observe(screenshot_path)
    trajectory_logger.log_observation(observation)

    # Act
    action = controller.select_action(observation)
    trajectory_logger.log_action(action, step)
    env.act(action)
    controller.on_action_executed(action)

# Clean up (saves video, console log, DOM snapshot)
video_path = env.close(output_dir=session_dir)

# Generate issue summary
issue_summary = trajectory_logger.generate_issue_summary()
trajectory_logger.log_event("issue_summary", issue_summary)

# Finalize
trajectory_logger.finalize({"total_steps": 10})

print(f"Session complete: {session_dir}")
print(f"Total issues: {issue_summary.get('total_issues', 0)}")
```


---

## Assumptions

The playtester is built on several key assumptions about automated game testing:

### 1. Vision-First Approach
**Assumption**: Visual information (screenshots) is the primary signal for understanding game state, similar to how human players perceive games.

**Rationale**:
- Games are designed for visual consumption
- Screenshots capture UI, game state, and visual bugs
- Enables testing games without access to internal state
- Generalizes across different game engines and implementations

**Limitations**:
- Audio cues are not captured
- Hidden state (player stats, inventory) may not be visible
- Requires VLM to interpret complex visual scenes

### 2. Action Sequences Over Single Actions
**Assumption**: Meaningful game progress requires coherent sequences of related actions rather than isolated random inputs.

**Rationale**:
- Human players execute multi-step strategies (e.g., "navigate to menu, select options, change setting")
- Action sequences have clear goals and expected outcomes
- Enables goal achievement evaluation
- More efficient than purely random exploration

**Implementation**: VLM generates 2-5 action sequences with specific goals.

### 3. VLM as Advisory, Not Authoritative
**Assumption**: VLMs are powerful but unreliable, requiring deterministic fallback behavior.

**Rationale**:
- VLMs have variable latency (100ms-5s per query)
- API calls may fail or timeout
- VLMs may produce invalid actions
- Expensive to query continuously
- Reproducibility requires deterministic behavior

**Implementation**: VLM is consulted only when action queue is empty; random controller provides fallback.

### 4. Issue Detection via Observable Signals
**Assumption**: Most game issues manifest as observable signals (crashes, frozen UI, network errors, performance drops) rather than requiring deep game state inspection.

**Rationale**:
- Critical bugs affect player experience visibly
- Browser APIs expose crashes, errors, network failures
- DOM state changes indicate soft-locks
- Performance APIs measure frame time and long tasks

**Coverage**: Detects crashes, soft-locks, input deadness, UI dead-ends, performance regressions, network failures.

### 5. Reproducibility Through Seeding
**Assumption**: Deterministic random number generation enables reproducible playtesting for debugging and regression testing.

**Rationale**:
- Bugs must be reproducible to fix
- Regression testing requires consistent behavior
- Enables A/B testing of different strategies

**Implementation**: All randomness (action selection, timing) uses seeded RNG.

---

## Design Choices

### Why VLM as Advisor?

**Decision**: Make VLM advisory rather than directly controlling the browser.

**Alternatives Considered**:
1. **VLM as Driver**: VLM directly controls browser via tool use
   - ❌ Slow (1-5s per action)
   - ❌ Unreliable (API failures break testing)
   - ❌ Not reproducible

2. **Pure Heuristic**: No VLM, only random/scripted actions
   - ❌ Cannot understand game context
   - ❌ No goal-directed behavior
   - ✅ Fast and reliable

3. **Hybrid (Chosen)**: VLM suggests action sequences, controller executes
   - ✅ Goal-directed intelligence from VLM
   - ✅ Fast execution (VLM queried only when queue empty)
   - ✅ Graceful degradation (fallback to heuristics)
   - ✅ Reproducible (deterministic fallback)

### Why JSONL for Trajectories?

**Decision**: Use JSONL (JSON Lines) format for trajectory logging.

**Alternatives Considered**:
1. **Single JSON file**: `{"observations": [...], "actions": [...]}`
   - ❌ Cannot stream during long sessions
   - ❌ Risk of corruption on crash

2. **SQLite database**:
   - ❌ More complex (schema migrations, queries)
   - ❌ Not human-readable
   - ❌ Harder to diff in version control

3. **JSONL (Chosen)**: One JSON object per line
   - ✅ Streaming writes during long sessions
   - ✅ Easy to parse line-by-line
   - ✅ Git-friendly (line-based diffs)
   - ✅ Safe for concurrent writes (append-only)
   - ✅ Human-readable with `cat` or `jq`
   - ✅ Flexible schema evolution

### Why Playwright Over Selenium?

**Decision**: Use Playwright for browser automation.

**Alternatives Considered**:
1. **Selenium**:
   - ❌ Older architecture (WebDriver protocol)
   - ❌ Worse WebGL support
   - ❌ Less reliable for modern SPAs

2. **Puppeteer**:
   - ❌ Chrome-only (Playwright supports Firefox/WebKit)
   - ❌ Less feature-rich

3. **Playwright (Chosen)**:
   - ✅ Modern async-first API
   - ✅ Better WebGL/WebGL2 support (ANGLE + SwiftShader)
   - ✅ Built-in video recording
   - ✅ Rich developer tools (tracing, screenshots, network capture)
   - ✅ Cross-browser support (Chromium, Firefox, WebKit)
   - ✅ Active development and support

### Why Session-Based Output Organization?

**Decision**: Each playtest session creates a timestamped directory with all artifacts.

**Rationale**:
- **Isolation**: Multiple playtests don't interfere
- **Traceability**: Timestamp makes sessions easy to identify
- **Completeness**: All artifacts (video, screenshots, logs) in one place
- **Cleanup**: Easy to delete old sessions
- **Analysis**: Easy to compare sessions side-by-side

**Structure**:
```
output/
└── 20260120_143052/           # Timestamp: YYYYMMDD_HHMMSS
    ├── trajectory.jsonl       # Complete log
    ├── screenshots/           # Frame-by-frame
    ├── videos/                # Video recording
    ├── console.log            # Browser console
    └── dom_snapshots/         # HTML + layout metadata
```

### Why No Global State?

**Decision**: Avoid global variables and singletons; pass dependencies explicitly.

**Rationale**:
- **Testability**: Easy to mock and unit test
- **Reproducibility**: No hidden dependencies
- **Concurrency**: Safe for parallel runs
- **Clarity**: Explicit data flow makes code easier to understand
- **Debugging**: Easier to trace issues without hidden state

---

## System Architecture

### Engineering Architecture

The playtester follows a clean layered architecture with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────────┐
│                          CLI Layer                               │
│  (Argument parsing, session orchestration, logging)              │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      v
┌─────────────────────────────────────────────────────────────────┐
│                      Controller Layer                            │
│  (Policy: RandomController, VLMAdvisedController)                │
│  - Selects actions based on observations                         │
│  - Maintains action queue (for VLM sequences)                    │
│  - Falls back to heuristics on VLM failure                       │
└─────────────────┬─────────────────────┬─────────────────────────┘
                  │                     │
         select_action()        suggest_action_sequence()
                  │                     │
                  v                     v
┌───────────────────────────┐  ┌──────────────────────────────────┐
│    BrowserEnv Layer       │  │      VLM Client Layer            │
│  (Environment interface)  │  │  (Advisory intelligence)         │
│  - Executes actions       │  │  - Analyzes screenshots          │
│  - Captures observations  │  │  - Generates action sequences    │
│  - Detects issues         │  │  - Evaluates goal achievement    │
│  - Records console events │  │  - Context-aware prompts         │
│  - Saves DOM snapshots    │  │  - Logs raw VLM outputs          │
└─────────┬─────────────────┘  └──────────────────────────────────┘
          │
          v
┌─────────────────────────────────────────────────────────────────┐
│                    Playwright/Browser Layer                      │
│  (Chromium with WebGL2 support)                                  │
│  - Renders game in browser                                       │
│  - Executes actions (click, keypress, mouse_move)               │
│  - Captures screenshots                                          │
│  - Records video                                                 │
│  - Emits console events                                          │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      v
┌─────────────────────────────────────────────────────────────────┐
│                    Core Data Models Layer                        │
│  (Serializable data structures)                                  │
│  - Observation (screenshot, console, DOM, issues)                │
│  - Action (wait, click, keypress, mouse_move)                   │
│  - IssueDetection (crashes, soft-locks, performance)            │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      v
┌─────────────────────────────────────────────────────────────────┐
│                    Trajectory Logger Layer                       │
│  (Structured logging to JSONL)                                   │
│  - Appends observations, actions, events                         │
│  - Generates issue summaries                                     │
│  - Manages screenshot/video paths                                │
│  - Versioned schema (v1.0.0)                                     │
└─────────────────────────────────────────────────────────────────┘
```

**Key Design Patterns**:
- **Separation of Concerns**: Each layer has a single responsibility
- **Dependency Injection**: Dependencies passed explicitly (no globals)
- **Interface Segregation**: Abstract base classes define contracts
- **Strategy Pattern**: Controllers implement interchangeable policies
- **Observer Pattern**: Browser events captured via Playwright listeners
- **Factory Pattern**: Action deserialization via `action_from_dict()`

### Playtest Agent Architecture

The agent operates in a **goal-directed action sequence loop**:

```
┌────────────────────────────────────────────────────────────────┐
│                     PLAYTEST LOOP                               │
└────────────────────────────────────────────────────────────────┘

Step N:
  ┌──────────────────┐
  │ 1. OBSERVE       │──────────────────────────────────┐
  │  - Screenshot    │                                  │
  │  - Console events│                                  │
  │  - DOM state     │                                  │
  │  - Issue detect  │                                  │
  └────────┬─────────┘                                  │
           │                                            │
           v                                            │
  ┌──────────────────┐                                  │
  │ 2. DECIDE        │                                  │
  │                  │                                  │
  │ Action queue     │                                  │
  │ empty?           │                                  │
  └────────┬─────────┘                                  │
           │                                            │
     ┌─────┴─────┐                                      │
     │ YES   NO  │                                      │
     v           v                                      │
┌─────────┐  ┌─────────┐                               │
│ VLM     │  │ Use     │                               │
│ Query   │  │ Queued  │                               │
└────┬────┘  │ Action  │                               │
     │       └────┬────┘                               │
     │            │                                     │
     v            │                                     │
┌──────────────┐  │      ┌──────────────────┐          │
│ Evaluate     │  │      │ 3. EXECUTE       │          │
│ Previous Goal│  │      │  - Send action   │          │
│ (if any)     │  │      │    to browser    │          │
└──────┬───────┘  │      │  - Wait for      │          │
       │          │      │    completion    │          │
       v          │      └────────┬─────────┘          │
┌──────────────┐  │               │                    │
│ Generate New │  │               v                    │
│ Action       │  │      ┌──────────────────┐          │
│ Sequence     │  │      │ 4. LOG           │          │
│ (2-5 actions)│  │      │  - Observation   │          │
│ with Goal    │  │      │  - Action        │          │
└──────┬───────┘  │      │  - VLM outputs   │          │
       │          │      │  - Issues        │          │
       │          │      └────────┬─────────┘          │
       └──────────┴──────────────┬┘                    │
                                 │                     │
                                 └─────────────────────┘
                                 Step N+1 begins

┌─────────────────────────────────────────────────────────────┐
│ ACTION SEQUENCE EXAMPLE                                      │
├─────────────────────────────────────────────────────────────┤
│ Goal: "Navigate to settings menu"                           │
│ Actions:                                                     │
│   1. mouse_move(1200, 50)   # Hover over settings icon     │
│   2. wait(300)               # Wait for hover effect        │
│   3. click(1200, 50)         # Click settings               │
│   4. wait(500)               # Wait for menu to open        │
└─────────────────────────────────────────────────────────────┘
```

**VLM Integration Details**:

1. **When to Query VLM**:
   - Action queue is empty (all previous actions executed)
   - At start of session (no actions yet)

2. **VLM Input**:
   - Screenshot of current state
   - Game context (goal, controls, known bugs)
   - Recent action history (last 5 sequences)
   - Previous goal (if any)
   - Actions taken for previous goal (if any)

3. **VLM Output**:
   - **Action Sequence**: `{"goal": "...", "actions": [...]}`
   - **Semantic Analysis**: Goal achievement, game state assessment, next recommendations

4. **Fallback Behavior**:
   - VLM unavailable → Random controller
   - VLM timeout → Random controller
   - Invalid actions → Filter and use valid ones, or fallback

**Hierarchical Planning Architecture (Stub)**:

The system includes a stub implementation for hierarchical planning that combines VLM strategic planning with RL tactical execution:

```
┌─────────────────────────────────────────────────────────────┐
│              HIERARCHICAL CONTROLLER (STUB)                  │
└─────────────────────────────────────────────────────────────┘

Step N:
  ┌──────────────────┐
  │ OBSERVE          │
  │  - Screenshot    │
  │  - Game state    │
  └────────┬─────────┘
           │
           v
  ┌──────────────────┐
  │ VLM PLANNER      │────────────────────────────────┐
  │ (High-Level)     │                                │
  │                  │  Every N steps or              │
  │ Analyzes state   │  when sub-goal achieved        │
  │ Sets sub-goal:   │                                │
  │ "Navigate to     │                                │
  │  settings menu"  │                                │
  └────────┬─────────┘                                │
           │                                          │
           │ sub-goal                                 │
           v                                          │
  ┌──────────────────┐                                │
  │ RL CONTROLLER    │                                │
  │ (Low-Level)      │◀───────────────────────────────┘
  │                  │  Receives new sub-goal
  │ Learns to        │
  │ achieve sub-goal │
  │ efficiently      │
  │                  │
  │ Executes:        │
  │ • click          │
  │ • keypress       │
  │ • mouse_move     │
  │ • wait           │
  └────────┬─────────┘
           │
           v
  ┌──────────────────┐
  │ BROWSER ACTION   │
  └──────────────────┘

Benefits:
  ✓ VLM provides strategic direction (what to do)
  ✓ RL learns efficient tactics (how to do it)
  ✓ Faster than pure VLM (RL executes without API calls)
  ✓ More intelligent than pure RL (VLM provides guidance)

Implementation:
  • RLLowLevelController: Stub that randomly selects actions
  • HierarchicalController: Combines VLM + RL (stub mode)
  • See: src/playtester/controller/rl_low_level.py
```

**Note**: The hierarchical architecture is currently a **stub implementation**. The RL controller randomly selects actions rather than learning from experience. A production implementation would include:
- Neural network policy (PPO, SAC, or DQN)
- Vision encoder for processing screenshots
- Temporal model (LSTM/Transformer) for action history
- Reward computation based on sub-goal achievement
- Training infrastructure with replay buffer and policy updates

**Issue Detection Pipeline**:

Issues are detected at every observation:

```
Observation Capture
       │
       v
┌──────────────────────────────────────────┐
│ Parallel Issue Detection                 │
├──────────────────────────────────────────┤
│ • Page crash listener                    │
│ • WebGL context loss (injected JS)      │
│ • DOM state hashing (soft-lock)         │
│ • Focus check (input deadness)          │
│ • Modal/overlay detection (UI deadend)  │
│ • Performance API (frame time, tasks)   │
│ • Network error tracking (4xx/5xx)      │
└──────────────────┬───────────────────────┘
                   │
                   v
            ┌──────────────┐
            │ IssueDetection│
            │   object      │
            └──────┬────────┘
                   │
                   v
         ┌─────────────────────┐
         │ Logged to trajectory│
         └─────────────────────┘
                   │
                   v
         ┌─────────────────────┐
         │ Aggregated at end   │
         │ into issue summary  │
         └─────────────────────┘
```

---

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

# Install package in editable mode
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

### VLM Setup (Optional)

To use Google Gemini for intelligent playtesting:

```bash
# Install Gemini dependencies
pip install google-generativeai pillow

# Set API key (get from https://makersuite.google.com/app/apikey)
export GOOGLE_API_KEY="your-api-key-here"
```

---


**Hierarchical Controller (Stub)**:

```python
from pathlib import Path
from playtester.browser import BrowserEnv
from playtester.controller.rl_low_level import HierarchicalController, RLLowLevelController
from playtester.vlm import create_vlm_client
from playtester.core import TrajectoryLogger

# Initialize VLM client (optional - stub works without VLM)
vlm_client = create_vlm_client(
    provider="gemini",
    api_key="your-api-key",
    game_name="My Game",
    game_goal="Complete the tutorial"
)

# Initialize RL low-level controller
rl_controller = RLLowLevelController(
    seed=42,
    viewport_width=1280,
    viewport_height=720
)

# Initialize hierarchical controller
controller = HierarchicalController(
    seed=42,
    vlm_client=vlm_client,
    rl_controller=rl_controller,
    viewport_width=1280,
    viewport_height=720,
    subgoal_timeout=10  # Request new sub-goal every 10 steps
)

# Initialize environment and logger
session_dir = Path("./output/hierarchical_test")
session_dir.mkdir(parents=True, exist_ok=True)
trajectory_logger = TrajectoryLogger(session_dir)
trajectory_logger.initialize({
    "url": "https://example.com/game",
    "controller": "hierarchical",
    "subgoal_timeout": 10
})

video_dir = session_dir / "videos"
env = BrowserEnv(headless=False, record_video=True, video_dir=video_dir)
env.start("https://example.com/game")

# Run playtest with hierarchical planning
for step in range(50):
    screenshot_path = trajectory_logger.get_screenshot_path(step, relative=False)
    observation = env.observe(screenshot_path)
    trajectory_logger.log_observation(observation)

    # Hierarchical controller:
    # - VLM sets sub-goals every N steps
    # - RL controller executes actions to achieve sub-goal
    action = controller.select_action(observation)
    trajectory_logger.log_action(action, step)
    env.act(action)

env.close(output_dir=session_dir)
trajectory_logger.finalize({"total_steps": 50})

print("Hierarchical playtesting complete!")
print("Note: This is a STUB implementation - RL controller uses random actions")
```

---

## What's Implemented

✅ **Core Infrastructure**
- Clean action → observation loop
- Serializable data models
- JSONL trajectory logging with rich event types
- Screenshot capture at every step
- Console event capture with full session logging
- Video recording (Playwright native)
- Session-based output organization (timestamped directories)

✅ **Browser Integration**
- Playwright-based environment
- Full WebGL2 support (ANGLE + SwiftShader)
- Compatible with Godot, Unity, Three.js
- Headful/headless modes
- Configurable viewport
- Software rendering (works without GPU)
- Mouse move action support

✅ **Issue Detection & Monitoring**
- **Crash Detection**: Page errors, browser crashes, WebGL context loss
- **Soft-lock Detection**: DOM state hashing to detect frozen states
- **Input Deadness**: Focus loss detection
- **UI Dead-ends**: Modal and overlay blocking detection
- **Performance Monitoring**: Frame time measurement, long task detection (>50ms)
- **Network Failures**: HTTP 4xx/5xx errors, asset load failures
- **Automated Reporting**: Issue summary generated and logged at session end

✅ **DOM Capture**
- Full HTML snapshot at session end
- Computed layout metadata for all elements
- Bounding boxes, computed styles, interactive element detection
- Element-specific attributes (href, input type, button state)

✅ **Controllers**
- Base controller interface
- Random exploration controller
- VLM-advised controller with action sequence support
  - Receives 2-5 action sequences from VLM
  - Evaluates goal achievement between sequences
  - Deterministic fallback behavior
- **Hierarchical controller (stub implementation)**
  - VLM high-level planner sets sub-goals
  - RL low-level controller executes primitive actions to achieve sub-goals
  - See [src/playtester/controller/rl_low_level.py](src/playtester/controller/rl_low_level.py)

✅ **VLM Integration**
- Google Gemini 2.0 Flash support
- **Action Sequence Generation**: VLM suggests 2-5 actions with specific goals
- **Goal-Directed Planning**: VLM evaluates goal achievement before new sequences
- Context-aware prompt engineering
- State management across steps
- Raw VLM output logging to trajectory
- Semantic analysis for goal achievement evaluation
- Stub VLM for testing without API calls

✅ **Extensibility**
- Clear module boundaries
- Abstract interfaces
- Versioned schemas (v1.0.0)
- Plugin-ready architecture
- Comprehensive event logging

✅ **Deployment**
- CLI interface with rich argument support
- Docker support
- Configurable logging (standard + verbose)
- Per-session output directories

---

## Known Issues

### 1. Finding UI Element Positions from Pure Vision Signal

**Problem**: The VLM must infer clickable UI element positions from screenshots alone, without access to DOM structure or element bounding boxes during action generation.

**Current Approach**:
- VLM analyzes screenshot visually
- Generates pixel coordinates for clicks
- No semantic understanding of UI hierarchy

**Limitations**:
- **Imprecise Targeting**: VLM may misidentify button boundaries, especially for:
  - Small buttons or icons
  - Buttons with non-standard shapes
  - Overlapping UI elements
  - Dynamic/animated UI
- **No Affordance Information**: VLM cannot distinguish clickable vs non-clickable elements without visual cues
- **Resolution Sensitivity**: Coordinate accuracy depends on screenshot resolution and VLM's spatial reasoning
- **Hidden Interactivity**: Elements with no visual indication of interactivity (e.g., transparent overlays) are not detectable

**Partial Mitigations**:
- DOM snapshots captured at session end (but not available during action generation)
- Layout metadata includes interactive element detection (post-hoc analysis)
- VLM can use mouse_move to explore hover effects

**Future Solutions**:
- Provide DOM accessibility tree to VLM alongside screenshot
- Use element bounding boxes from DOM for precise targeting
- Hybrid approach: VLM identifies element semantically, DOM provides coordinates
- Computer vision models fine-tuned for UI element detection

### 2. Gemini API Rate Limits

**Problem**: Free tier has request limits (15 RPM, 1500 RPD for Gemini 2.0 Flash).

**Impact**: Long playtesting sessions (>50 steps) may hit rate limits with VLM controller.

**Mitigation**:
- Action sequences reduce query frequency (2-5 actions per VLM call)
- Fallback to random controller when rate limited
- Consider paid tier for production use

### 3. Soft-Lock False Positives

**Problem**: Some games have intentional pauses (loading screens, cutscenes) that trigger soft-lock detection.

**Impact**: False positives in issue reports.

**Mitigation**:
- Threshold set to >10 steps unchanged (reduces false positives)
- Manual review of flagged soft-locks
- Future: Detect loading indicators/progress bars

### 4. WebGL Context Loss Not Always Recoverable

**Problem**: When WebGL context is lost, the game may not recover gracefully.

**Impact**: Session may need to restart.

**Current Handling**:
- Detected and logged
- No automatic recovery

**Future**: Auto-restart browser on context loss with configurable retry policy.

### 5. Performance Monitoring Availability

**Problem**: Performance API (frame timing, long tasks) not available in all browsers or configurations.

**Impact**: Performance issues may not be detected on some platforms.

**Mitigation**: Graceful degradation when API unavailable.

---

## Future Directions

### Near-Term (Next 6 Months)

#### 1. Maintain Mental Model of Game State

**Goal**: Build and maintain a structured representation of game state beyond visual observations.

**Approach**:
- **State Extraction**: VLM periodically analyzes screenshots to extract:
  - Player status (health, score, position)
  - Game phase (menu, gameplay, pause, game over)
  - Available actions (visible buttons, accessible areas)
  - Recent state changes

- **State Update**: Incremental updates based on:
  - New screenshots
  - Interaction history (actions taken, responses observed)
  - Game description (from context)

- **State Querying**: Controller queries mental model to:
  - Avoid revisiting solved areas
  - Identify unexplored regions
  - Detect anomalies (stuck in loop, unexpected state)

**Benefits**:
- More efficient exploration (avoid redundant actions)
- Better bug detection (detect impossible states)
- Improved goal-directed behavior

**Challenges**:
- State representation (how to structure mental model?)
- State consistency (handle partial observability)
- VLM hallucination (validate extracted state)

#### 2. Hierarchical Planning (VLM + RL) ⚠️ STUB IMPLEMENTED

**Status**: Stub implementation available at [src/playtester/controller/rl_low_level.py](src/playtester/controller/rl_low_level.py)

**Goal**: Combine high-level planning from VLM with low-level action selection from RL.

**Architecture**:
```
VLM (High-Level Planner)
    └─> Generates sub-goals: "Navigate to menu", "Collect item", "Defeat enemy"
         │
         v
RL Policy (Low-Level Controller)
    └─> Learns to achieve sub-goals efficiently
         └─> Actions: click, keypress, mouse_move
```

**Benefits**:
- VLM provides strategic direction (what to do)
- RL learns efficient tactics (how to do it)
- Faster learning (RL only needs to solve sub-problems)
- Interpretable behavior (VLM goals are human-readable)

**Current Stub Implementation**:
- `RLLowLevelController`: Randomly selects actions (no learning)
- `HierarchicalController`: Coordinates VLM + RL (stub VLM sub-goal generation)
- Provides interface for future RL integration

**Production Implementation Roadmap**:
1. **Policy Network**: Implement PPO, SAC, or DQN agent
2. **Vision Encoder**: Process screenshots into feature vectors
3. **Temporal Model**: LSTM/Transformer for action history
4. **Sub-goal Encoding**: Text embeddings for VLM-generated sub-goals
5. **Reward Shaping**:
   - +1.0 for sub-goal achievement
   - -0.01 per step (efficiency penalty)
   - -0.5 for crashes/issues
   - +0.1 for progress toward sub-goal
6. **Training Infrastructure**:
   - Replay buffer for experience storage
   - Batch sampling and policy updates
   - Model checkpointing and evaluation
7. **Sub-goal Achievement Detection**:
   - VLM evaluates if sub-goal achieved
   - Or learned classifier for common sub-goals

#### 3. High-Level Reinforcement Learning with Action History

**Goal**: Train RL agent that learns from action history, not just current state.

**Approach**:
- **Input**: Last N observations + actions (temporal context)
- **Output**: Next action or action sequence
- **Reward**: Progress toward game objective + issue penalties

**Model**:
- Transformer or LSTM for temporal modeling
- Vision encoder for screenshots
- Action encoder for previous actions

**Benefits**:
- Learns patterns across time (e.g., "click button, wait, then expect menu")
- Avoids repeated mistakes
- Adapts to game dynamics

#### 4. Local VLM Model for Reducing Latency/Cost

**Goal**: Replace cloud API (Gemini) with local VLM for faster, cheaper inference.

**Target Models**:
- **LLaVA-7B**: Multimodal LLM, fits on consumer GPU
- **Qwen-VL-7B**: Strong vision-language performance
- **InternVL-7B**: Efficient architecture

**Requirements**:
- Model must fit in <16GB VRAM (consumer GPU)
- Inference <500ms per screenshot (acceptable latency)
- Maintains reasonable action quality

**Tradeoffs**:
- Lower quality than Gemini 2.0 Flash (acceptable for many games)
- Requires GPU (not suitable for all deployments)
- Fine-tuning needed for game-specific behavior

**Implementation Path**:
1. Benchmark existing 7B VLMs on game playtesting
2. Fine-tune best model on playtesting trajectories
3. Compare quality vs latency vs cost to Gemini
4. Offer as alternative VLM provider

### Long-Term (1-2 Years)

#### 5. Multi-Agent Coordination

**Goal**: Multiple playtesting agents collaborate to explore game more efficiently.

**Approach**:
- Agents share discovered state space
- Coordinate to avoid redundant exploration
- Specialize in different game aspects (UI testing, gameplay, stress testing)

#### 6. Automated Bug Report Generation

**Goal**: Synthesize human-readable bug reports from detected issues.

**Output**:
- Title: "Soft-lock in level 3 after collecting item"
- Reproduction steps: "1. Navigate to level 3, 2. Collect golden key, 3. Attempt to open door"
- Screenshots: Before/after state
- Trajectory: Link to full JSONL log

#### 7. Regression Testing & CI Integration

**Goal**: Automated playtest runs in GitHub Actions for regression detection.

**Workflow**:
```yaml
on: [push, pull_request]
jobs:
  playtest:
    runs-on: ubuntu-latest
    steps:
      - uses: anthropics/playtester-action@v1
        with:
          url: https://staging.mygame.com
          steps: 100
          config: playtest_config.json
      - name: Compare issues
        run: |
          compare_sessions.py \
            --baseline main.json \
            --current ${{ github.sha }}.json
```

#### 8. Coverage-Guided Exploration

**Goal**: Maximize code coverage or state space coverage during playtesting.

**Approach**:
- Instrument game with coverage tracking (if source available)
- Or use heuristic coverage (unique screenshots, DOM states)
- Reward controller for discovering new states
- Prioritize under-explored areas

#### 9. Game-Specific Adapters

**Goal**: Plug-in system for game-specific behavior.

**Example**:
```python
class PlatformerAdapter(GameAdapter):
    def extract_player_position(self, observation):
        # Use VLM or CV to find player sprite
        return (x, y)

    def detect_death(self, observation):
        # Detect game-over screen
        return "GAME OVER" in observation.dom_metadata.title
```

---

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
- **Type hints**: Preferred but not required for public APIs
- **Docstrings**: Required for public APIs
- **Logging**: Use structured logging (`logger.info/debug/warning/error`), not print

### Extending the System

#### Adding a New Action Type

1. Define action in [src/playtester/core/action.py](src/playtester/core/action.py):
```python
@dataclass
class ScrollAction(Action):
    delta_y: int

    def to_dict(self) -> Dict[str, Any]:
        return {"type": "scroll", "delta_y": self.delta_y}

    @property
    def action_type(self) -> str:
        return "scroll"
```

2. Add to `action_from_dict()` factory
3. Implement in `BrowserEnv._execute_scroll()`

#### Adding a New VLM Provider

See [src/playtester/vlm/gemini.py](src/playtester/vlm/gemini.py) as reference:

```python
from playtester.vlm import VLMClient

class GPT4VisionClient(VLMClient):
    def suggest_action_sequence(self, observation):
        # 1. Load screenshot
        # 2. Build prompt with game context
        # 3. Query API
        # 4. Parse JSON response
        # 5. Return {"goal": "...", "actions": [...]}
        pass

    def get_semantic_analysis(self, observation, previous_goal, actions_taken):
        # Analyze goal achievement
        pass
```

---

## Recent Updates

### Latest Features (January 2026)

✨ **Video Recording**: Automatic recording of all playtesting sessions
✨ **Comprehensive Issue Detection**: Crashes, soft-locks, performance issues, network failures
✨ **Session Organization**: Timestamped directories for each playtest
✨ **Console Logging**: Full browser console output saved to `console.log`
✨ **DOM Snapshots**: HTML + computed layout metadata at session end
✨ **Action Sequences**: VLM generates goal-directed action sequences (2-5 actions)
✨ **Goal Evaluation**: VLM analyzes goal achievement between sequences
✨ **Mouse Move Action**: Support for hover interactions and mouse positioning
✨ **VLM Output Logging**: All raw VLM responses logged to trajectory for debugging

---

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
