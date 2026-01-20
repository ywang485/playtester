# Examples

This directory contains example configurations and usage patterns for the playtester.

## Configuration Files

### `basic_config.json`
Minimal configuration without game context:

```bash
playtester --config examples/basic_config.json
```

### `minimal_config.json`
Simple configuration with basic game context:

```bash
playtester --config examples/minimal_config.json
```

### `monopoly_config.json`
Comprehensive configuration for Monopoly game with full game context:

```bash
playtester --config examples/monopoly_config.json
```

This includes:
- Game goal and controls
- Known bugs to monitor
- Test focus areas
- Additional game metadata

## Configuration Schema

Config files support all CLI arguments plus game context:

```json
{
  "url": "https://example.com/game",
  "steps": 100,
  "controller": "vlm",
  "seed": 42,
  "headless": false,
  "viewport_width": 1280,
  "viewport_height": 720,
  "output_dir": "./output",
  "game_context": {
    "name": "Game Name",
    "goal": "Description of game objective",
    "controls": {
      "click": "What clicking does",
      "keys": "What keyboard controls do"
    },
    "known_bugs": [
      "Bug 1 description",
      "Bug 2 description"
    ],
    "test_focus_areas": [
      "Area 1",
      "Area 2"
    ]
  }
}
```

## Using CLI Arguments with Config Files

CLI arguments override config file values:

```bash
# Use config but override steps and seed
playtester --config examples/monopoly_config.json --steps 200 --seed 123

# Use config but override controller
playtester --config examples/monopoly_config.json --controller random

# Add/override game context from CLI
playtester --config examples/basic_config.json \
    --game-name "My Game" \
    --game-goal "Win by collecting all coins" \
    --known-bugs "UI freeze on level 3, Score not saving"
```

## Programmatic Usage

```python
import json
from pathlib import Path
from playtester.cli import load_config, run_playtest

# Load config
config = load_config(Path("examples/monopoly_config.json"))

# Run playtest with config
run_playtest(
    url=config["url"],
    steps=config["steps"],
    output_dir=Path(config.get("output_dir", "./output")),
    controller_type=config["controller"],
    seed=config.get("seed"),
    viewport_width=config.get("viewport_width", 1280),
    viewport_height=config.get("viewport_height", 720),
    game_context=config.get("game_context")
)
```

## Creating Your Own Config

1. Copy `minimal_config.json` as a starting point
2. Update the `url` to your game
3. Add game-specific context:
   - `name`: Your game's name
   - `goal`: What the player should try to achieve
   - `controls`: How to interact with the game
   - `known_bugs`: Issues you want the agent to monitor
4. Save and run:
   ```bash
   playtester --config my_game_config.json
   ```

## Future Examples

Additional examples to be added:

- `custom_controller.py`: Example custom controller implementation
- `trajectory_analysis.py`: Script to analyze trajectory files
- `bug_detector.py`: Example bug detector implementation
- `real_vlm_client.py`: Example real VLM integration
