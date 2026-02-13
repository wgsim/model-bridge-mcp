"""Lightweight in-memory tracker for active subprocess calls."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass


@dataclass
class ActiveTask:
    """Represents a currently running subprocess task."""

    task_id: str
    provider: str
    prompt_preview: str
    start_time: float


class TaskTracker:
    """Thread-safe tracker for active subprocess calls."""

    def __init__(self) -> None:
        self._tasks: dict[str, ActiveTask] = {}
        self._lock = threading.Lock()

    def register(self, provider: str, prompt: str) -> str:
        """Register a new active task and return its ID."""
        task_id = uuid.uuid4().hex[:12]
        preview = prompt[:80].replace("\n", " ")
        task = ActiveTask(
            task_id=task_id,
            provider=provider,
            prompt_preview=preview,
            start_time=time.time(),
        )
        with self._lock:
            self._tasks[task_id] = task
        return task_id

    def deregister(self, task_id: str) -> None:
        """Remove a completed task."""
        with self._lock:
            self._tasks.pop(task_id, None)

    def list_active(self) -> list[dict]:
        """Return list of currently active tasks with elapsed time."""
        now = time.time()
        with self._lock:
            return [
                {
                    "task_id": t.task_id,
                    "provider": t.provider,
                    "prompt_preview": t.prompt_preview,
                    "elapsed_seconds": round(now - t.start_time, 1),
                }
                for t in self._tasks.values()
            ]

    def count(self) -> int:
        """Return number of active tasks."""
        with self._lock:
            return len(self._tasks)
