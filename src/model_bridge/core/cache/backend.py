"""Cache backend protocol and implementations (P3-2)."""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from typing import Any, Protocol


def build_key(payload: dict[str, Any]) -> str:
    """Build a cache key from a payload dict.

    Args:
        payload: Dictionary of values to hash

    Returns:
        SHA256 hash of the sorted payload
    """
    raw = repr(sorted(payload.items())).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class CacheBackend(Protocol):
    """Protocol for cache backends.

    Any class implementing these methods can be used as a cache backend.
    """

    def get(self, key: str) -> str | None:
        """Get a value from the cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        ...

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        """Set a value in the cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time-to-live in seconds (None = use default)
        """
        ...

    def delete(self, key: str) -> None:
        """Delete a value from the cache.

        Args:
            key: Cache key
        """
        ...

    def clear(self) -> None:
        """Clear all entries from the cache."""
        ...


class InMemoryCache:
    """In-memory cache with TTL and bounded size.

    This is the default cache backend, suitable for single-instance deployments.
    """

    def __init__(self, ttl_seconds: int = 300, max_entries: int = 256) -> None:
        """Initialize the in-memory cache.

        Args:
            ttl_seconds: Default time-to-live for entries
            max_entries: Maximum number of entries to store
        """
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._store: OrderedDict[str, tuple[float, str]] = OrderedDict()

    @staticmethod
    def build_key(payload: dict[str, Any]) -> str:
        """Build a cache key from a payload dict.

        Args:
            payload: Dictionary of values to hash

        Returns:
            SHA256 hash of the sorted payload
        """
        return build_key(payload)

    def get(self, key: str) -> str | None:
        """Get a value from the cache."""
        item = self._store.get(key)
        if item is None:
            return None
        ts, value = item
        if time.time() - ts > self.ttl_seconds:
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        """Set a value in the cache."""
        # Note: ttl_seconds is ignored for in-memory cache (uses default)
        self._store[key] = (time.time(), value)
        self._store.move_to_end(key)
        while len(self._store) > self.max_entries:
            self._store.popitem(last=False)

    def delete(self, key: str) -> None:
        """Delete a value from the cache."""
        self._store.pop(key, None)

    def clear(self) -> None:
        """Clear all entries from the cache."""
        self._store.clear()


# Backward compatibility alias
PromptCache = InMemoryCache
