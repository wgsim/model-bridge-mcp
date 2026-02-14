"""Disk-backed cache implementation (P3-2)."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("model_bridge.cache.disk")


class DiskCache:
    """Disk-backed cache with TTL support.

    Files are stored with modification time used for TTL checking.
    Suitable for persistence across restarts and sharing between processes.
    """

    def __init__(
        self,
        cache_dir: str | Path = "~/.model_bridge/cache",
        ttl_seconds: int = 300,
        max_entries: int = 1000,
    ) -> None:
        """Initialize the disk cache.

        Args:
            cache_dir: Directory to store cache files
            ttl_seconds: Default time-to-live for entries
            max_entries: Maximum number of entries (cleanup on set)
        """
        self.cache_dir = Path(cache_dir).expanduser()
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def build_key(payload: dict[str, Any]) -> str:
        """Build a cache key from a payload dict."""
        raw = repr(sorted(payload.items())).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _key_to_path(self, key: str) -> Path:
        """Convert a cache key to a file path."""
        # Use first 2 chars as subdirectory for filesystem efficiency
        subdir = self.cache_dir / key[:2]
        subdir.mkdir(exist_ok=True)
        return subdir / f"{key}.cache"

    def get(self, key: str) -> str | None:
        """Get a value from the cache."""
        path = self._key_to_path(key)

        if not path.exists():
            return None

        # Check TTL via mtime
        mtime = path.stat().st_mtime
        if time.time() - mtime > self.ttl_seconds:
            try:
                path.unlink()
            except OSError:
                pass
            return None

        try:
            return path.read_text(encoding="utf-8")
        except OSError as e:
            logger.debug("Failed to read cache file %s: %s", path, e)
            return None

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        """Set a value in the cache."""
        path = self._key_to_path(key)

        try:
            path.write_text(value, encoding="utf-8")
            # Note: We use the file's mtime for TTL, so no separate TTL storage needed
            # For custom TTL, we'd need to store it separately - for now use default

            # Cleanup old entries if we exceed max_entries
            self._cleanup_if_needed()

        except OSError as e:
            logger.warning("Failed to write cache file %s: %s", path, e)

    def delete(self, key: str) -> None:
        """Delete a value from the cache."""
        path = self._key_to_path(key)
        try:
            path.unlink(missing_ok=True)
        except OSError as e:
            logger.debug("Failed to delete cache file %s: %s", path, e)

    def clear(self) -> None:
        """Clear all entries from the cache."""
        try:
            for subdir in self.cache_dir.iterdir():
                if subdir.is_dir():
                    for cache_file in subdir.glob("*.cache"):
                        cache_file.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Failed to clear cache: %s", e)

    def _cleanup_if_needed(self) -> None:
        """Remove old entries if we exceed max_entries."""
        # Collect all cache files with their mtimes
        files = []
        try:
            for subdir in self.cache_dir.iterdir():
                if subdir.is_dir():
                    for cache_file in subdir.glob("*.cache"):
                        try:
                            mtime = cache_file.stat().st_mtime
                            files.append((mtime, cache_file))
                        except OSError:
                            pass
        except OSError:
            return

        # Remove oldest files if we exceed max_entries
        if len(files) > self.max_entries:
            files.sort(key=lambda x: x[0])  # Sort by mtime (oldest first)
            to_remove = len(files) - self.max_entries
            for _, path in files[:to_remove]:
                try:
                    path.unlink()
                except OSError:
                    pass

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        count = 0
        total_size = 0
        try:
            for subdir in self.cache_dir.iterdir():
                if subdir.is_dir():
                    for cache_file in subdir.glob("*.cache"):
                        count += 1
                        try:
                            total_size += cache_file.stat().st_size
                        except OSError:
                            pass
        except OSError:
            pass

        return {
            "backend": "disk",
            "cache_dir": str(self.cache_dir),
            "entry_count": count,
            "total_size_bytes": total_size,
            "ttl_seconds": self.ttl_seconds,
            "max_entries": self.max_entries,
        }
