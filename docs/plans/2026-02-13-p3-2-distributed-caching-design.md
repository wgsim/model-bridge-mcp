# P3-2: Distributed Caching Design

## Goal

Extend the caching layer to support Redis and Disk-backed caching for persistence and distributed scenarios.

## Current State

```python
# In-memory only
class PromptCache:
    def __init__(self, ttl_seconds=300, max_entries=256)
    def get(self, key) -> str | None
    def set(self, key, value) -> None
```

## Target Architecture

```
CacheBackend (Protocol)
    ├── InMemoryCache (existing PromptCache)
    ├── DiskCache
    └── RedisCache

CacheFactory
    └── Creates backend based on config
```

## Configuration

```yaml
cache:
  backend: "memory"  # "memory" | "disk" | "redis"
  ttl_seconds: 300
  max_entries: 256

  # Disk backend options
  disk:
    path: "~/.model_bridge/cache"

  # Redis backend options
  redis:
    url: "redis://localhost:6379/0"
    prefix: "model_bridge:"
```

## Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Protocol vs ABC | Protocol | Python 3.8+ duck typing, no inheritance required |
| Redis client | redis-py | Standard, battle-tested |
| Disk format | Single file per key | Simple, works with TTL via mtime |
| Fallback | In-memory | Always available, no dependencies |

## Cache Protocol

```python
class CacheBackend(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None: ...
    def delete(self, key: str) -> None: ...
    def clear(self) -> None: ...
```

## Implementation Plan

### Step 1: Create cache protocol and refactor
- `src/model_bridge/core/cache/backend.py` - Protocol + InMemoryCache
- Rename `PromptCache` to `InMemoryCache`, keep `PromptCache` as alias

### Step 2: Implement DiskCache
- `src/model_bridge/core/cache/disk_cache.py`
- Use file mtime for TTL
- Hash key for filename

### Step 3: Implement RedisCache
- `src/model_bridge/core/cache/redis_cache.py`
- Optional dependency (import guard)

### Step 4: Create CacheFactory
- `src/model_bridge/core/cache/factory.py`
- Select backend based on config

### Step 5: Update main.py
- Use CacheFactory instead of direct PromptCache

### Step 6: Tests
- `tests/unit/test_cache_backends.py`

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/model_bridge/core/cache/__init__.py` | CREATE |
| `src/model_bridge/core/cache/backend.py` | CREATE |
| `src/model_bridge/core/cache/disk_cache.py` | CREATE |
| `src/model_bridge/core/cache/redis_cache.py` | CREATE |
| `src/model_bridge/core/cache/factory.py` | CREATE |
| `src/model_bridge/core/prompt_cache.py` | MODIFY (alias) |
| `src/model_bridge/main.py` | MODIFY |
| `tests/unit/test_cache_backends.py` | CREATE |

## Verification

1. All existing tests pass (backward compatibility)
2. DiskCache persists across restarts
3. RedisCache works with Redis server
4. Factory selects correct backend
5. TTL works for all backends
