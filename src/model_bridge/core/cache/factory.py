"""Cache factory for creating cache backends (P3-2)."""

from __future__ import annotations

import logging
from typing import Any

from model_bridge.core.cache.backend import CacheBackend, InMemoryCache

logger = logging.getLogger("model_bridge.cache.factory")


def create_cache(config: dict[str, Any] | None = None) -> CacheBackend:
    """Create a cache backend based on configuration.

    Args:
        config: Configuration dict with cache settings

    Returns:
        CacheBackend instance

    Configuration format:
        cache:
          backend: "memory"  # "memory" | "disk" | "redis"
          ttl_seconds: 300
          max_entries: 256
          disk:
            path: "~/.model_bridge/cache"
          redis:
            url: "redis://localhost:6379/0"
            prefix: "model_bridge:"

    Defaults to in-memory cache if no config or invalid backend.
    """
    if config is None:
        return InMemoryCache()

    cache_config = config.get("cache", {})
    backend = cache_config.get("backend", "memory")
    ttl_seconds = cache_config.get("ttl_seconds", 300)
    max_entries = cache_config.get("max_entries", 256)

    if backend == "disk":
        return _create_disk_cache(cache_config, ttl_seconds, max_entries)
    elif backend == "redis":
        return _create_redis_cache(cache_config, ttl_seconds, max_entries)
    else:
        if backend != "memory":
            logger.warning("Unknown cache backend '%s', falling back to memory", backend)
        return InMemoryCache(ttl_seconds=ttl_seconds, max_entries=max_entries)


def _create_disk_cache(
    cache_config: dict[str, Any],
    ttl_seconds: int,
    max_entries: int,
) -> CacheBackend:
    """Create a disk cache backend."""
    from model_bridge.core.cache.disk_cache import DiskCache

    disk_config = cache_config.get("disk", {})
    cache_dir = disk_config.get("path", "~/.model_bridge/cache")

    logger.info("Creating disk cache at %s", cache_dir)
    return DiskCache(
        cache_dir=cache_dir,
        ttl_seconds=ttl_seconds,
        max_entries=max_entries,
    )


def _create_redis_cache(
    cache_config: dict[str, Any],
    ttl_seconds: int,
    max_entries: int,
) -> CacheBackend:
    """Create a Redis cache backend."""
    try:
        from model_bridge.core.cache.redis_cache import RedisCache, RedisCacheError

        redis_config = cache_config.get("redis", {})
        url = redis_config.get("url", "redis://localhost:6379/0")
        prefix = redis_config.get("prefix", "model_bridge:")

        logger.info("Creating Redis cache at %s", url.split("@")[-1] if "@" in url else url)
        return RedisCache(
            url=url,
            prefix=prefix,
            ttl_seconds=ttl_seconds,
            max_entries=max_entries,
        )
    except RedisCacheError as e:
        logger.warning("Redis cache not available: %s, falling back to memory", e)
        return InMemoryCache(ttl_seconds=ttl_seconds, max_entries=max_entries)


def get_cache_backend_name(cache: CacheBackend) -> str:
    """Get the name of a cache backend.

    Args:
        cache: CacheBackend instance

    Returns:
        Backend name string
    """
    cache_type = type(cache).__name__
    if cache_type == "InMemoryCache":
        return "memory"
    elif cache_type == "DiskCache":
        return "disk"
    elif cache_type == "RedisCache":
        return "redis"
    return cache_type.lower()
