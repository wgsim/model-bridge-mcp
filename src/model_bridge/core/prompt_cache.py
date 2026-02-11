"""In-memory prompt cache with TTL and bounded size."""

from __future__ import annotations

import hashlib
import time
from collections import OrderedDict
from typing import Any


class PromptCache:
    """Simple in-memory cache for repeated ask requests."""

    def __init__(self, ttl_seconds: int = 300, max_entries: int = 256) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._store: OrderedDict[str, tuple[float, str]] = OrderedDict()

    @staticmethod
    def build_key(payload: dict[str, Any]) -> str:
        raw = repr(sorted(payload.items())).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def get(self, key: str) -> str | None:
        item = self._store.get(key)
        if item is None:
            return None
        ts, value = item
        if time.time() - ts > self.ttl_seconds:
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return value

    def set(self, key: str, value: str) -> None:
        self._store[key] = (time.time(), value)
        self._store.move_to_end(key)
        while len(self._store) > self.max_entries:
            self._store.popitem(last=False)

