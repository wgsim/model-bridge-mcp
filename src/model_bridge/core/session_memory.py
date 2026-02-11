"""In-memory session memory for ask continuity."""

from __future__ import annotations

import time
from collections import defaultdict


class SessionMemory:
    """Keep short rolling context per session id."""

    def __init__(self, ttl_seconds: int = 1800, max_turns: int = 6) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_turns = max_turns
        self._store: dict[str, tuple[float, list[str]]] = defaultdict(lambda: (0.0, []))

    def get_context(self, session_id: str) -> list[str]:
        ts, turns = self._store.get(session_id, (0.0, []))
        if not turns:
            return []
        if time.time() - ts > self.ttl_seconds:
            self._store.pop(session_id, None)
            return []
        return list(turns)

    def append_turn(self, session_id: str, summary: str) -> None:
        _, turns = self._store.get(session_id, (0.0, []))
        turns = list(turns)
        turns.append(summary)
        if len(turns) > self.max_turns:
            turns = turns[-self.max_turns :]
        self._store[session_id] = (time.time(), turns)

