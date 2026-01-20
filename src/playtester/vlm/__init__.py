"""
VLM (Vision-Language Model) client interface.

The VLM is treated as an ADVISOR, not a driver. It provides suggestions
that the controller may choose to follow, ignore, or override.
"""

from .client import VLMClient, StubVLMClient

__all__ = ["VLMClient", "StubVLMClient"]
