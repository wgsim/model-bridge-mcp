"""Unit tests for TaskTracker (P2 task monitor)."""

from __future__ import annotations

import time

from model_bridge.core.task_tracker import TaskTracker


class TestTaskTracker:
    """Test TaskTracker operations."""

    def test_register_returns_id(self):
        tracker = TaskTracker()
        task_id = tracker.register("codex", "hello world")
        assert isinstance(task_id, str)
        assert len(task_id) == 12

    def test_register_and_list_active(self):
        tracker = TaskTracker()
        task_id = tracker.register("gemini", "test prompt")
        active = tracker.list_active()
        assert len(active) == 1
        assert active[0]["task_id"] == task_id
        assert active[0]["provider"] == "gemini"
        assert active[0]["prompt_preview"] == "test prompt"
        assert active[0]["elapsed_seconds"] >= 0

    def test_deregister_removes_task(self):
        tracker = TaskTracker()
        task_id = tracker.register("ollama", "prompt")
        assert tracker.count() == 1
        tracker.deregister(task_id)
        assert tracker.count() == 0

    def test_deregister_nonexistent_is_noop(self):
        tracker = TaskTracker()
        tracker.deregister("nonexistent_id")
        assert tracker.count() == 0

    def test_count_reflects_active_tasks(self):
        tracker = TaskTracker()
        assert tracker.count() == 0
        id1 = tracker.register("a", "p1")
        id2 = tracker.register("b", "p2")
        assert tracker.count() == 2
        tracker.deregister(id1)
        assert tracker.count() == 1
        tracker.deregister(id2)
        assert tracker.count() == 0

    def test_prompt_preview_truncated_at_80(self):
        tracker = TaskTracker()
        long_prompt = "x" * 200
        tracker.register("codex", long_prompt)
        active = tracker.list_active()
        assert len(active[0]["prompt_preview"]) == 80

    def test_prompt_preview_strips_newlines(self):
        tracker = TaskTracker()
        tracker.register("codex", "line1\nline2\nline3")
        active = tracker.list_active()
        assert "\n" not in active[0]["prompt_preview"]

    def test_multiple_tasks_listed(self):
        tracker = TaskTracker()
        tracker.register("codex", "p1")
        tracker.register("gemini", "p2")
        tracker.register("ollama", "p3")
        active = tracker.list_active()
        assert len(active) == 3
        providers = {t["provider"] for t in active}
        assert providers == {"codex", "gemini", "ollama"}
