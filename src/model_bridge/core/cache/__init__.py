"""Cache backends for model-bridge-mcp (P3-2).

Available backends:
- InMemoryCache: Default, suitable for single-instance deployments
- DiskCache: Persistent storage, survives restarts
- RedisCache: Distributed caching for multi-instance deployments

Usage:
    from model_bridge.core.cache import create_cache, InMemoryCache

    # Create cache from config
    cache = create_cache({"cache": {"backend": "disk"}})

    # Or create directly
    cache = InMemoryCache(ttl_seconds=300)

    # Use cache
    key = cache.build_key({"prompt": "hello", "model": "gpt-4"})
    cache.set(key, "response")
    value = cache.get(key)
"""

from model_bridge.core.cache.backend import AsyncCacheBackend, CacheBackend, InMemoryCache, PromptCache
from model_bridge.core.cache.disk_cache import DiskCache
from model_bridge.core.cache.factory import create_cache, get_cache_backend_name

__all__ = [
    "AsyncCacheBackend",
    "CacheBackend",
    "InMemoryCache",
    "PromptCache",
    "DiskCache",
    "create_cache",
    "get_cache_backend_name",
]
