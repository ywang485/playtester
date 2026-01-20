# Using Gemini VLM for Playtesting

This guide explains how to use Google's Gemini 2.0 Flash model as a VLM advisor for playtesting.

## Setup

### 1. Install Dependencies

```bash
pip install google-generativeai pillow
```

### 2. Get a Gemini API Key

1. Go to [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Create an API key
3. Set it as an environment variable:

```bash
export GOOGLE_API_KEY="your-api-key-here"
# Or alternatively:
export GEMINI_API_KEY="your-api-key-here"
```

## Usage

### Option 1: CLI with Environment Variable

If you've set `GOOGLE_API_KEY` or `GEMINI_API_KEY` as an environment variable:

```bash
playtester \
    --url https://research-monopoly.vercel.app \
    --steps 100 \
    --controller vlm \
    --vlm-provider gemini \
    --game-goal "Win at Monopoly" \
    --game-controls "Click to interact" \
    --verbose
```

### Option 2: CLI with API Key Argument

```bash
playtester \
    --url https://research-monopoly.vercel.app \
    --steps 100 \
    --controller vlm \
    --vlm-provider gemini \
    --gemini-api-key "your-api-key-here" \
    --game-goal "Win at Monopoly"
```

### Option 3: Config File

Use the provided Monopoly config with Gemini:

```bash
# Set API key as environment variable first
export GOOGLE_API_KEY="your-api-key-here"

# Run with config
playtester --config examples/monopoly_gemini_config.json
```

Or include the API key in the config file:

```json
{
  "url": "https://your-game.com",
  "controller": "vlm",
  "vlm_provider": "gemini",
  "gemini_api_key": "your-api-key-here",
  "game_context": {
    "name": "My Game",
    "goal": "Complete all levels"
  }
}
```

**Note:** For security, it's recommended to use environment variables instead of putting API keys in config files.

## How Gemini Works

The Gemini VLM client:

1. **Takes screenshots** at each step
2. **Receives game context** (goal, controls, known bugs)
3. **Maintains state** across steps (recent actions, observations)
4. **Generates action suggestions** based on visual analysis
5. **Returns structured JSON** with the next action to take

### What Gemini Sees

For each step, Gemini receives:

```
System Prompt:
- Game name and objective
- Available controls
- Known bugs to watch for
- Test focus areas

Step Context:
- Current step number
- Recent action history
- Console events
- Page metadata

Visual Input:
- Screenshot of current game state
```

### Gemini's Response

Gemini responds with JSON specifying an action:

```json
{"type": "click", "x": 640, "y": 360}
{"type": "keypress", "key": "Space"}
{"type": "wait", "duration_ms": 1000}
```

## State Management

The Gemini client maintains state across steps:

```python
client.state = {
    "step_count": 0,
    "recent_actions": [],  # Last 5 actions taken
    "max_recent_actions": 5,
    "observations_summary": []
}
```

This allows Gemini to make more informed decisions based on recent history.

## Troubleshooting

### "google-generativeai package not installed"

```bash
pip install google-generativeai pillow
```

### "Gemini API key required"

Make sure you've either:
- Set `GOOGLE_API_KEY` or `GEMINI_API_KEY` environment variable
- Passed `--gemini-api-key` CLI argument
- Included `gemini_api_key` in config file

### "Screenshot not found"

This usually means the output directory structure is incorrect. The Gemini client resolves relative screenshot paths using the output directory.

### Rate Limits

Gemini has rate limits. If you hit them:
- Reduce the number of steps
- Increase wait times between VLM queries (modify `query_interval` in code)
- Use the `stub` provider for testing without API calls

## Cost Considerations

- **Gemini 2.0 Flash** is optimized for speed and cost
- Each step sends one image + text prompt
- For 100 steps, expect ~100 API calls
- Monitor your usage in Google AI Studio

## Example Session

```bash
# 1. Set API key
export GOOGLE_API_KEY="your-key"

# 2. Run with Gemini
playtester \
    --url https://research-monopoly.vercel.app \
    --steps 50 \
    --controller vlm \
    --vlm-provider gemini \
    --game-name "Monopoly" \
    --game-goal "Buy properties and win" \
    --game-controls "Click to roll dice, buy property, pay rent" \
    --known-bugs "UI freeze on doubles, Card rendering issues" \
    --verbose

# 3. Check output
cat output/trajectory.jsonl
ls output/screenshots/
```

## Advanced: Custom Gemini Client

You can create a custom Gemini client with different settings:

```python
from playtester.vlm.gemini import GeminiVLMClient
from pathlib import Path

client = GeminiVLMClient(
    api_key="your-key",
    game_context={
        "name": "My Game",
        "goal": "Complete all levels"
    },
    output_dir=Path("./output"),
    model_name="gemini-2.0-flash-exp",  # Or other Gemini models
    temperature=0.7,  # Higher = more creative, lower = more deterministic
    max_output_tokens=256
)

# Use in your controller
from playtester.controller import VLMAdvisedController

controller = VLMAdvisedController(
    seed=42,
    vlm_client=client,
    query_interval=5  # Query VLM every 5 steps
)
```

## Comparing Stub vs Gemini

| Feature | Stub | Gemini |
|---------|------|--------|
| **Cost** | Free | API costs |
| **Speed** | Instant | ~1-2s per query |
| **Actions** | Always `wait(1000ms)` | Context-aware decisions |
| **Use Case** | Testing, debugging | Real playtesting |
| **Setup** | None | API key required |

## Next Steps

- Try different `temperature` values for varied behavior
- Adjust `query_interval` to balance cost vs responsiveness
- Provide detailed game context for better decisions
- Use the trajectory logs to analyze Gemini's decision-making
