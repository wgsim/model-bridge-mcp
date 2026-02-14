"""In-memory prompt cache with TTL and bounded size.

This module is deprecated. Use model_bridge.core.cache instead.
Kept for backward compatibility.
"""

from __future__ import annotations

# Re-export from new location for backward compatibility
from model_bridge.core.cache.backend import InMemoryCache, PromptCache

__all__ = ["PromptCache", "InMemoryCache"]
