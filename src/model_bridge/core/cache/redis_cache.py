"""Redis-backed cache implementation (P3-2)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from model_bridge.core.cache.backend import build_key as _build_key

logger = logging.getLogger("model_bridge.cache.redis")

# Optional import - redis is not required
try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    redis = None  # type: ignore
    REDIS_AVAILABLE = False


class RedisCacheError(Exception):
    """Error raised when Redis operations fail."""
    pass


class RedisCache:
    """Redis-backed cache with TTL support.

    Suitable for distributed deployments and sharing cache across
    multiple instances.

    Requires: pip install redis
    """

    def __init__(
        self,
        url: str = "redis://localhost:6379/0",
        prefix: str = "model_bridge:",
        ttl_seconds: int = 300,
        max_entries: int = 10000,  # Used for stats only
    ) -> None:
        """Initialize the Redis cache.

        Args:
            url: Redis connection URL
            prefix: Key prefix for namespacing
            ttl_seconds: Default time-to-live for entries
            max_entries: Max entries (for stats, not enforced by Redis)

        Raises:
            RedisCacheError: If redis package is not installed
        """
        if not REDIS_AVAILABLE:
            raise RedisCacheError(
                "Redis cache requires the 'redis' package. "
                "Install it with: pip install redis"
            )

        self.url = url
        self.prefix = prefix
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._client: redis.Redis | None = None

    @staticmethod
    def build_key(payload: dict[str, Any]) -> str:
        """Build a cache key from a payload dict."""
        return _build_key(payload)

    def _full_key(self, key: str) -> str:
        """Add prefix to key."""
        return f"{self.prefix}{key}"

    async def _get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            self._client = redis.from_url(self.url)
        return self._client

    async def get(self, key: str) -> str | None:
        """Get a value from the cache."""
        try:
            client = await self._get_client()
            value = await client.get(self._full_key(key))
            if value is None:
                return None
            return value.decode("utf-8") if isinstance(value, bytes) else value
        except Exception as e:
            logger.warning("Redis get failed for key %s: %s", key, e)
            return None

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        """Set a value in the cache."""
        ttl = ttl_seconds or self.ttl_seconds
        try:
            client = await self._get_client()
            await client.setex(self._full_key(key), ttl, value)
        except Exception as e:
            logger.warning("Redis set failed for key %s: %s", key, e)

    async def delete(self, key: str) -> None:
        """Delete a value from the cache."""
        try:
            client = await self._get_client()
            await client.delete(self._full_key(key))
        except Exception as e:
            logger.warning("Redis delete failed for key %s: %s", key, e)

    async def clear(self) -> None:
        """Clear all entries with this prefix from the cache."""
        try:
            client = await self._get_client()
            # Find all keys with our prefix and delete them
            pattern = f"{self.prefix}*"
            cursor = 0
            while True:
                cursor, keys = await client.scan(cursor, match=pattern, count=100)
                if keys:
                    await client.delete(*keys)
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning("Redis clear failed: %s", e)

    async def close(self) -> None:
        """Close the Redis connection."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        try:
            client = await self._get_client()
            # Count keys with our prefix
            pattern = f"{self.prefix}*"
            count = 0
            cursor = 0
            while True:
                cursor, keys = await client.scan(cursor, match=pattern, count=100)
                count += len(keys)
                if cursor == 0:
                    break

            return {
                "backend": "redis",
                "url": self.url.replace(
                    self.url.split("@")[-1].split("/")[0], "***"
                ) if "@" in self.url else self.url,
                "prefix": self.prefix,
                "entry_count": count,
                "ttl_seconds": self.ttl_seconds,
                "max_entries": self.max_entries,
            }
        except Exception as e:
            return {
                "backend": "redis",
                "error": str(e),
            }

    # Synchronous wrappers for backward compatibility.
    # New call sites should prefer async methods.
    @staticmethod
    def _run_sync(coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        raise RedisCacheError(
            "RedisCache sync wrapper called inside a running event loop; use await get/set instead."
        )

    def get_sync(self, key: str) -> str | None:
        """Synchronous get wrapper for compatibility."""
        return self._run_sync(self.get(key))

    def set_sync(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        """Synchronous set wrapper for compatibility."""
        self._run_sync(self.set(key, value, ttl_seconds))
