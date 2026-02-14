"""Tests for cache backends (P3-2)."""

import tempfile
import time
from pathlib import Path

import pytest

from model_bridge.core.cache.backend import InMemoryCache, PromptCache
from model_bridge.core.cache.disk_cache import DiskCache
from model_bridge.core.cache.factory import create_cache, get_cache_backend_name


class TestInMemoryCache:
    """Tests for InMemoryCache."""

    def test_set_and_get(self):
        """Test basic set and get operations."""
        cache = InMemoryCache(ttl_seconds=60)
        cache.set("key1", "value1")

        assert cache.get("key1") == "value1"

    def test_get_missing_key(self):
        """Test getting a missing key returns None."""
        cache = InMemoryCache()
        assert cache.get("nonexistent") is None

    def test_ttl_expiration(self):
        """Test that entries expire after TTL."""
        cache = InMemoryCache(ttl_seconds=0.1)
        cache.set("key1", "value1")

        # Should be present immediately
        assert cache.get("key1") == "value1"

        # Wait for TTL to expire
        time.sleep(0.15)

        # Should be expired now
        assert cache.get("key1") is None

    def test_max_entries(self):
        """Test that cache evicts oldest entries when full."""
        cache = InMemoryCache(ttl_seconds=60, max_entries=3)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        cache.set("key4", "value4")  # Should evict key1

        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"

    def test_delete(self):
        """Test deleting a key."""
        cache = InMemoryCache()
        cache.set("key1", "value1")
        cache.delete("key1")

        assert cache.get("key1") is None

    def test_clear(self):
        """Test clearing all entries."""
        cache = InMemoryCache()
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_build_key(self):
        """Test key building from payload."""
        key1 = InMemoryCache.build_key({"a": 1, "b": 2})
        key2 = InMemoryCache.build_key({"b": 2, "a": 1})  # Same content, different order
        key3 = InMemoryCache.build_key({"a": 1, "b": 3})

        assert key1 == key2  # Order shouldn't matter
        assert key1 != key3  # Different content

    def test_lru_access(self):
        """Test LRU behavior on access."""
        cache = InMemoryCache(ttl_seconds=60, max_entries=3)

        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")

        # Access key1 to make it recently used
        cache.get("key1")

        # Add a new key - should evict key2 (oldest unused)
        cache.set("key4", "value4")

        assert cache.get("key1") == "value1"
        assert cache.get("key2") is None  # Evicted
        assert cache.get("key3") == "value3"
        assert cache.get("key4") == "value4"


class TestPromptCacheAlias:
    """Tests for PromptCache backward compatibility alias."""

    def test_is_in_memory_cache(self):
        """Test that PromptCache is InMemoryCache."""
        assert PromptCache is InMemoryCache

    def test_works_as_before(self):
        """Test that PromptCache works as before."""
        cache = PromptCache(ttl_seconds=60)
        cache.set("key", "value")
        assert cache.get("key") == "value"


class TestDiskCache:
    """Tests for DiskCache."""

    def test_set_and_get(self):
        """Test basic set and get operations."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = DiskCache(cache_dir=tmpdir, ttl_seconds=60)
            cache.set("key1", "value1")

            assert cache.get("key1") == "value1"

    def test_persistence_across_instances(self):
        """Test that data persists across cache instances."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # First instance
            cache1 = DiskCache(cache_dir=tmpdir, ttl_seconds=60)
            cache1.set("key1", "value1")

            # Second instance (same directory)
            cache2 = DiskCache(cache_dir=tmpdir, ttl_seconds=60)
            assert cache2.get("key1") == "value1"

    def test_ttl_expiration(self):
        """Test that entries expire after TTL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = DiskCache(cache_dir=tmpdir, ttl_seconds=0.1)
            cache.set("key1", "value1")

            # Should be present immediately
            assert cache.get("key1") == "value1"

            # Wait for TTL to expire
            time.sleep(0.15)

            # Should be expired now
            assert cache.get("key1") is None

    def test_delete(self):
        """Test deleting a key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = DiskCache(cache_dir=tmpdir)
            cache.set("key1", "value1")
            cache.delete("key1")

            assert cache.get("key1") is None

    def test_clear(self):
        """Test clearing all entries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = DiskCache(cache_dir=tmpdir)
            cache.set("key1", "value1")
            cache.set("key2", "value2")
            cache.clear()

            assert cache.get("key1") is None
            assert cache.get("key2") is None

    def test_build_key(self):
        """Test key building from payload."""
        key1 = DiskCache.build_key({"a": 1, "b": 2})
        key2 = DiskCache.build_key({"b": 2, "a": 1})
        assert key1 == key2

    def test_get_stats(self):
        """Test getting cache statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = DiskCache(cache_dir=tmpdir, ttl_seconds=300, max_entries=100)
            cache.set("key1", "value1")

            stats = cache.get_stats()

            assert stats["backend"] == "disk"
            assert stats["entry_count"] == 1
            assert stats["ttl_seconds"] == 300
            assert stats["max_entries"] == 100


class TestCacheFactory:
    """Tests for cache factory."""

    def test_creates_memory_cache_by_default(self):
        """Test that factory creates memory cache by default."""
        cache = create_cache()
        assert isinstance(cache, InMemoryCache)

    def test_creates_memory_cache_from_config(self):
        """Test creating memory cache from config."""
        cache = create_cache({
            "cache": {
                "backend": "memory",
                "ttl_seconds": 600,
                "max_entries": 500,
            }
        })

        assert isinstance(cache, InMemoryCache)
        assert cache.ttl_seconds == 600
        assert cache.max_entries == 500

    def test_creates_disk_cache_from_config(self):
        """Test creating disk cache from config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = create_cache({
                "cache": {
                    "backend": "disk",
                    "ttl_seconds": 600,
                    "disk": {
                        "path": tmpdir,
                    },
                }
            })

            assert isinstance(cache, DiskCache)
            assert cache.ttl_seconds == 600

    def test_falls_back_to_memory_for_unknown_backend(self):
        """Test that factory falls back to memory for unknown backend."""
        cache = create_cache({
            "cache": {
                "backend": "unknown",
            }
        })

        assert isinstance(cache, InMemoryCache)

    def test_get_cache_backend_name(self):
        """Test getting backend name."""
        assert get_cache_backend_name(InMemoryCache()) == "memory"

        with tempfile.TemporaryDirectory() as tmpdir:
            assert get_cache_backend_name(DiskCache(cache_dir=tmpdir)) == "disk"


class TestRedisCacheImport:
    """Tests for Redis cache import handling."""

    def test_import_error_when_redis_not_installed(self):
        """Test that Redis cache raises helpful error when redis not installed."""
        from model_bridge.core.cache.redis_cache import REDIS_AVAILABLE

        if not REDIS_AVAILABLE:
            from model_bridge.core.cache.redis_cache import RedisCache, RedisCacheError

            with pytest.raises(RedisCacheError, match="requires the 'redis' package"):
                RedisCache()
