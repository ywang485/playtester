"""
VLM (Vision-Language Model) client interface.

The VLM is treated as an ADVISOR, not a driver. It provides suggestions
that the controller may choose to follow, ignore, or override.
"""

from .client import VLMClient, StubVLMClient

# Optional: Import GeminiVLMClient if google-generativeai is available
try:
    from .gemini import GeminiVLMClient
    __all__ = ["VLMClient", "StubVLMClient", "GeminiVLMClient"]
except ImportError:
    # google-generativeai not installed
    GeminiVLMClient = None
    __all__ = ["VLMClient", "StubVLMClient"]
