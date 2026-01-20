# WebGL/WebGL2 Support

This document explains how the playtester handles WebGL and WebGL2 games, including configuration, troubleshooting, and technical details.

## Overview

The playtester uses Playwright with Chromium to run browser-based games. WebGL/WebGL2 support is critical for testing modern web games, including those built with:

- **Godot Engine** (WebGL2 export)
- **Unity WebGL** (WebGL1/2)
- **Three.js** (WebGL1/2)
- **Babylon.js** (WebGL1/2)
- **Custom WebGL games**

## Current Configuration

### Browser Launch Arguments

The playtester uses the following configuration for WebGL2 support:

```python
browser_args = [
    '--enable-webgl',              # Enable WebGL 1.0
    '--enable-webgl2',             # Enable WebGL 2.0
    '--use-gl=angle',              # Use ANGLE (Almost Native Graphics Layer Engine)
    '--use-angle=swiftshader',     # SwiftShader backend for ANGLE (software rendering)
    '--enable-features=WebGL2ComputeContext',
    '--disable-blink-features=AutomationControlled',
    '--disable-gpu-vsync',
    '--enable-unsafe-webgpu',
]
```

### Why ANGLE + SwiftShader?

**ANGLE (Almost Native Graphics Layer Engine)**:
- Translates OpenGL ES calls to DirectX/Vulkan/Metal
- Better WebGL2 compatibility than direct OpenGL
- Industry standard (used by Chrome, Firefox, Edge)

**SwiftShader**:
- Software renderer (doesn't require GPU)
- Works in headless environments
- Works in Docker/CI without GPU access
- Supports WebGL2 fully

### Headless Mode Additional Args

In headless mode, additional arguments are added:

```python
'--disable-gpu',           # Force software rendering
'--disable-dev-shm-usage', # Avoid shared memory issues in containers
'--no-sandbox',            # Required for some environments
```

## Verifying WebGL Support

### Method 1: Browser Console

After starting a playtest, check the trajectory logs for console output:

```bash
playtester --url https://your-game.com --steps 5 --verbose
# Check output/trajectory.jsonl for console events
```

### Method 2: Manual Test Page

Create a test HTML file:

```html
<!DOCTYPE html>
<html>
<body>
    <canvas id="test"></canvas>
    <script>
        const canvas = document.getElementById('test');
        const gl2 = canvas.getContext('webgl2');
        if (gl2) {
            console.log('WebGL2 supported!');
            console.log('Vendor:', gl2.getParameter(gl2.VENDOR));
            console.log('Renderer:', gl2.getParameter(gl2.RENDERER));
            console.log('Version:', gl2.getParameter(gl2.VERSION));
        } else {
            console.error('WebGL2 NOT supported');
        }
    </script>
</body>
</html>
```

Run:

```bash
playtester --url file:///path/to/test.html --steps 1 --verbose
```

### Method 3: Programmatic Check

```python
from playtester.browser import BrowserEnv

env = BrowserEnv(headless=False)
env.start("https://get.webgl.org/webgl2/")

# Check console for WebGL2 support messages
import time
time.sleep(5)

# Screenshot should show green if WebGL2 works
screenshot_path = Path("./webgl2_test.png")
observation = env.observe(screenshot_path)

for event in observation.console_events:
    print(f"[{event.level}] {event.text}")

env.close()
```

## Common Issues and Solutions

### Issue 1: "WebGL2 not supported" Error

**Symptoms:**
```
The following features required to run Godot projects on the Web are missing:
WebGL2 - Check web browser configuration and hardware support
```

**Solution:**

This error occurred in earlier versions. Update to the latest code:

```bash
git pull origin main
pip install -e .
```

The new configuration uses ANGLE + SwiftShader which properly exposes WebGL2.

### Issue 2: Black Screen / No Rendering

**Symptoms:**
- Screenshots show black screen
- Console shows no errors

**Possible Causes:**
1. Game hasn't finished loading
2. WebGL context initialization delay
3. Canvas not properly sized

**Solutions:**

```bash
# Give more time for initial load
playtester --url https://game.com --steps 50 --controller random

# Use wait action to let game initialize
# Check first few screenshots to see when rendering starts
```

### Issue 3: "GPU process not available" in Headless

**Symptoms:**
```
[ERROR] GPU process not available
```

**Solution:**

This is expected in headless mode. SwiftShader software rendering will be used automatically. This is normal and doesn't affect functionality.

### Issue 4: Docker WebGL Issues

**Symptoms:**
- WebGL works locally but not in Docker
- "SharedArrayBuffer not supported" errors

**Solution:**

Ensure Docker has proper mesa libraries:

```dockerfile
RUN apt-get install -y \
    libgl1-mesa-dri \
    libgl1-mesa-glx \
    libegl1-mesa \
    libgles2-mesa
```

This is already in the provided Dockerfile.

### Issue 5: Performance Issues with Software Rendering

**Symptoms:**
- Low FPS
- Stuttering
- Slow screenshot capture

**Explanation:**

SwiftShader is CPU-based, so performance will be slower than hardware-accelerated rendering. This is acceptable for playtesting but not for performance benchmarking.

**Mitigation:**

```bash
# Reduce step count
playtester --url https://game.com --steps 20

# Use longer wait actions to let game stabilize
# (Configure in controller or use VLM with appropriate suggestions)
```

## Advanced Configuration

### Using Hardware Acceleration (Local Only)

If you want to use GPU acceleration for better performance (local testing only, won't work in Docker):

Modify `src/playtester/browser/env.py`:

```python
# Replace:
'--use-angle=swiftshader',

# With:
'--use-angle=default',  # Use system GPU
```

**Note:** This won't work in:
- Headless mode
- Docker containers
- CI/CD environments
- Servers without GPU

### Custom WebGL Settings

You can customize WebGL settings programmatically:

```python
from playtester.browser import BrowserEnv

class CustomBrowserEnv(BrowserEnv):
    def start(self, url: str):
        # Override browser args before launch
        self._custom_args = [
            '--enable-webgl',
            '--enable-webgl2',
            '--your-custom-flag',
        ]
        super().start(url)
```

## Testing Different Game Engines

### Godot Engine

Godot uses WebGL2 by default:

```bash
playtester --url https://your-godot-game.com \
    --steps 100 \
    --controller vlm \
    --vlm-provider gemini \
    --game-name "Godot Game"
```

**Gotchas:**
- Godot requires WebGL2 (not WebGL1)
- First load may be slow (WASM compilation)
- Check console for "Engine started successfully" message

### Unity WebGL

Unity can use WebGL1 or WebGL2:

```bash
playtester --url https://your-unity-game.com \
    --steps 100 \
    --game-controls "WASD to move, Mouse to look"
```

**Gotchas:**
- Unity builds can be large (long initial load)
- May show Unity splash screen for several seconds
- Check for "UnityLoader" console messages

### Three.js / Custom WebGL

Most compatible:

```bash
playtester --url https://your-threejs-demo.com \
    --steps 50 \
    --controller random
```

## Debugging WebGL Issues

### Enable WebGL Debug Output

Add to browser context (modify `env.py`):

```python
# In start() method, before page.goto():
await self._page.evaluate("""
    const canvas = document.querySelector('canvas');
    if (canvas) {
        const gl = canvas.getContext('webgl2');
        if (gl) {
            console.log('WebGL2 Context:', {
                vendor: gl.getParameter(gl.VENDOR),
                renderer: gl.getParameter(gl.RENDERER),
                version: gl.getParameter(gl.VERSION),
                maxTextureSize: gl.getParameter(gl.MAX_TEXTURE_SIZE)
            });
        }
    }
""")
```

### Check WebGL Extensions

```javascript
// Add to page context
const gl = canvas.getContext('webgl2');
console.log('WebGL2 Extensions:', gl.getSupportedExtensions());
```

### Monitor WebGL Errors

```javascript
// Inject into page
const gl = canvas.getContext('webgl2');
const oldGetError = gl.getError.bind(gl);
gl.getError = function() {
    const error = oldGetError();
    if (error !== gl.NO_ERROR) {
        console.error('WebGL Error:', error);
    }
    return error;
};
```

## Technical Details

### ANGLE Architecture

```
WebGL2 Call
    ↓
ANGLE (Translation Layer)
    ↓
SwiftShader (Software Renderer)
    ↓
CPU-based Rendering
    ↓
Canvas Output
```

### SwiftShader Capabilities

SwiftShader supports:
- ✅ WebGL 1.0
- ✅ WebGL 2.0
- ✅ OpenGL ES 3.0
- ✅ EGL 1.5
- ❌ WebGPU (limited)
- ❌ Hardware acceleration

### Performance Characteristics

| Operation | Hardware GPU | SwiftShader |
|-----------|--------------|-------------|
| Simple 2D | 1000+ FPS | 60 FPS |
| 3D Game | 120+ FPS | 15-30 FPS |
| Screenshot | ~10ms | ~50ms |
| Memory | GPU VRAM | System RAM |

## Best Practices

1. **Test with representative games**: Run on actual target games, not just test pages

2. **Check console logs**: Always inspect console events for WebGL errors

3. **Use verbose logging**: Run with `--verbose` for detailed WebGL initialization logs

4. **Monitor screenshots**: Verify rendering is working by checking initial screenshots

5. **Account for load times**: Wait sufficient steps for game initialization

6. **Test both headless and headful**: Some issues only appear in specific modes

## Resources

- [WebGL Specification](https://www.khronos.org/webgl/)
- [WebGL2 Reference](https://www.khronos.org/webgl/wiki/WebGL_2.0)
- [ANGLE Project](https://chromium.googlesource.com/angle/angle)
- [SwiftShader](https://github.com/google/swiftshader)
- [Godot WebGL Export](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_web.html)

## Getting Help

If you encounter WebGL issues:

1. Check this document first
2. Run with `--verbose` and capture logs
3. Create a minimal reproduction case
4. Open an issue with:
   - Game engine and version
   - Browser configuration
   - Console logs
   - Screenshots
   - Trajectory file
