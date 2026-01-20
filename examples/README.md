# Examples

This directory contains example configurations and usage patterns for the playtester.

## Basic Configuration

`basic_config.json` shows a minimal configuration for running a playtest session.

While the CLI doesn't currently support loading from config files, this shows the
structure of configuration data that could be used programmatically:

```python
import json
from pathlib import Path
from playtester.cli import run_playtest

# Load config
with open("examples/basic_config.json") as f:
    config = json.load(f)

# Run playtest
run_playtest(
    url=config["url"],
    steps=config["steps"],
    output_dir=Path(config["output_dir"]),
    controller_type=config["controller"],
    seed=config.get("seed"),
    viewport_width=config["viewport"]["width"],
    viewport_height=config["viewport"]["height"]
)
```

## Future Examples

Additional examples to be added:

- `vlm_config.json`: Configuration with real VLM integration
- `custom_controller.py`: Example custom controller implementation
- `trajectory_analysis.py`: Script to analyze trajectory files
- `bug_detector.py`: Example bug detector implementation
