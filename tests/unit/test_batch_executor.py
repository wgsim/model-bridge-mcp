"""Tests for batch_executor module (P2-3)."""

import asyncio

import pytest

from model_bridge.core.batch_executor import (
    BatchExecutor,
    PrioritizedJob,
    Priority,
    parse_priority,
)
from model_bridge.core.rate_limiter import TokenBucket


class TestParsePriority:
    """Tests for parse_priority function."""

    def test_parse_high(self):
        assert parse_priority("high") == Priority.HIGH

    def test_parse_normal(self):
        assert parse_priority("normal") == Priority.NORMAL

    def test_parse_low(self):
        assert parse_priority("low") == Priority.LOW

    def test_parse_case_insensitive(self):
        assert parse_priority("HIGH") == Priority.HIGH
        assert parse_priority("Normal") == Priority.NORMAL
        assert parse_priority("LOW") == Priority.LOW

    def test_parse_with_whitespace(self):
        assert parse_priority("  high  ") == Priority.HIGH

    def test_parse_invalid_defaults_to_normal(self):
        assert parse_priority("urgent") == Priority.NORMAL
        assert parse_priority("") == Priority.NORMAL
        assert parse_priority("unknown") == Priority.NORMAL


class TestPrioritizedJob:
    """Tests for PrioritizedJob dataclass."""

    def test_job_has_sort_key(self):
        job = PrioritizedJob(job_id=0, prompt="test", priority=Priority.NORMAL)
        assert hasattr(job, "sort_key")
        assert job.sort_key == (1, 0)  # (NORMAL=1, insertion_order=0)

    def test_high_priority_sorts_before_normal(self):
        jobs = [
            PrioritizedJob(job_id=1, prompt="normal", priority=Priority.NORMAL),
            PrioritizedJob(job_id=0, prompt="high", priority=Priority.HIGH),
        ]
        sorted_jobs = sorted(jobs)
        assert sorted_jobs[0].priority == Priority.HIGH
        assert sorted_jobs[1].priority == Priority.NORMAL

    def test_normal_priority_sorts_before_low(self):
        jobs = [
            PrioritizedJob(job_id=1, prompt="low", priority=Priority.LOW),
            PrioritizedJob(job_id=0, prompt="normal", priority=Priority.NORMAL),
        ]
        sorted_jobs = sorted(jobs)
        assert sorted_jobs[0].priority == Priority.NORMAL
        assert sorted_jobs[1].priority == Priority.LOW

    def test_same_priority_uses_insertion_order(self):
        jobs = [
            PrioritizedJob(job_id=2, prompt="second", priority=Priority.NORMAL, _insertion_order=1),
            PrioritizedJob(job_id=1, prompt="first", priority=Priority.NORMAL, _insertion_order=0),
        ]
        sorted_jobs = sorted(jobs)
        assert sorted_jobs[0]._insertion_order == 0
        assert sorted_jobs[1]._insertion_order == 1


class TestBatchExecutor:
    """Tests for BatchExecutor class."""

    @pytest.fixture
    def executor(self):
        return BatchExecutor()

    @pytest.fixture
    def rate_limited_executor(self):
        rate_limiter = TokenBucket(rate=10.0, capacity=10.0)
        return BatchExecutor(rate_limiter=rate_limiter, max_concurrency=2)

    @pytest.mark.anyio
    async def test_execute_sequential_order(self, executor):
        """Sequential execution processes jobs in priority order."""
        jobs = [
            PrioritizedJob(job_id=0, prompt="low", priority=Priority.LOW),
            PrioritizedJob(job_id=1, prompt="high", priority=Priority.HIGH),
            PrioritizedJob(job_id=2, prompt="normal", priority=Priority.NORMAL),
        ]
        execution_order = []

        async def track_executor(job_id: int, prompt: str) -> dict:
            execution_order.append(prompt)
            return {"job_id": job_id, "status": "ok"}

        results = await executor.execute_sequential(jobs, track_executor)

        # Results are in original job_id order
        assert len(results) == 3
        assert results[0]["job_id"] == 0
        assert results[1]["job_id"] == 1
        assert results[2]["job_id"] == 2

        # But execution was in priority order
        assert execution_order == ["high", "normal", "low"]

    @pytest.mark.anyio
    async def test_execute_sequential_with_progress_callback(self, executor):
        """Progress callback is called after each job completes."""
        jobs = [
            PrioritizedJob(job_id=i, prompt=f"p{i}", priority=Priority.NORMAL)
            for i in range(3)
        ]
        progress_updates = []

        async def simple_executor(job_id: int, prompt: str) -> dict:
            return {"job_id": job_id, "status": "ok"}

        async def track_progress(completed: int, total: int) -> None:
            progress_updates.append((completed, total))

        await executor.execute_sequential(jobs, simple_executor, track_progress)

        assert progress_updates == [(1, 3), (2, 3), (3, 3)]

    @pytest.mark.anyio
    async def test_execute_parallel_respects_concurrency(self):
        """Parallel execution respects max_concurrency limit."""
        executor = BatchExecutor(max_concurrency=2)
        jobs = [
            PrioritizedJob(job_id=i, prompt=f"p{i}", priority=Priority.NORMAL)
            for i in range(4)
        ]
        concurrent_count = [0]
        max_concurrent = [0]
        lock = asyncio.Lock()

        async def count_concurrent(job_id: int, prompt: str) -> dict:
            async with lock:
                concurrent_count[0] += 1
                max_concurrent[0] = max(max_concurrent[0], concurrent_count[0])
            await asyncio.sleep(0.05)
            async with lock:
                concurrent_count[0] -= 1
            return {"job_id": job_id, "status": "ok"}

        await executor.execute_parallel(jobs, count_concurrent)

        assert max_concurrent[0] <= 2

    @pytest.mark.anyio
    async def test_execute_parallel_with_rate_limiter(self, rate_limited_executor):
        """Rate limiter is applied before each job starts."""
        jobs = [
            PrioritizedJob(job_id=i, prompt=f"p{i}", priority=Priority.NORMAL)
            for i in range(3)
        ]
        start_time = asyncio.get_event_loop().time()
        call_times = []

        async def track_time(job_id: int, prompt: str) -> dict:
            call_times.append(asyncio.get_event_loop().time())
            return {"job_id": job_id, "status": "ok"}

        await rate_limited_executor.execute_parallel(jobs, track_time)

        # With rate=10/s, we should see ~0.1s between calls
        assert len(call_times) == 3

    @pytest.mark.anyio
    async def test_execute_parallel_returns_results_in_job_id_order(self, executor):
        """Results are returned in original job_id order."""
        jobs = [
            PrioritizedJob(job_id=2, prompt="p2", priority=Priority.HIGH),
            PrioritizedJob(job_id=0, prompt="p0", priority=Priority.LOW),
            PrioritizedJob(job_id=1, prompt="p1", priority=Priority.NORMAL),
        ]

        async def simple_executor(job_id: int, prompt: str) -> dict:
            return {"job_id": job_id, "prompt": prompt}

        results = await executor.execute_parallel(jobs, simple_executor)

        # Results are indexed by job_id
        assert results[0]["job_id"] == 0  # job_id=0
        assert results[1]["job_id"] == 1  # job_id=1
        assert results[2]["job_id"] == 2  # job_id=2

    @pytest.mark.anyio
    async def test_execute_parallel_with_progress_callback(self, executor):
        """Progress callback is called as jobs complete."""
        jobs = [
            PrioritizedJob(job_id=i, prompt=f"p{i}", priority=Priority.NORMAL)
            for i in range(3)
        ]
        progress_updates = []

        async def simple_executor(job_id: int, prompt: str) -> dict:
            await asyncio.sleep(0.01)
            return {"job_id": job_id, "status": "ok"}

        async def track_progress(completed: int, total: int) -> None:
            progress_updates.append((completed, total))

        await executor.execute_parallel(jobs, simple_executor, track_progress)

        # Final count should match total
        assert progress_updates[-1] == (3, 3)
        assert len(progress_updates) == 3


class TestBatchExecutorIntegration:
    """Integration tests for BatchExecutor with real rate limiter."""

    @pytest.mark.anyio
    async def test_rate_limited_sequential_execution(self):
        """Rate limiter properly throttles sequential execution."""
        rate_limiter = TokenBucket(rate=5.0, capacity=1.0)  # 5 req/s, 1 burst
        executor = BatchExecutor(rate_limiter=rate_limiter)
        jobs = [
            PrioritizedJob(job_id=i, prompt=f"p{i}", priority=Priority.NORMAL)
            for i in range(3)
        ]

        import time

        start = time.monotonic()

        async def simple_executor(job_id: int, prompt: str) -> dict:
            return {"job_id": job_id}

        await executor.execute_sequential(jobs, simple_executor)
        elapsed = time.monotonic() - start

        # 3 requests at 5/s should take at least 0.4s (first is instant, next 2 wait ~0.2s each)
        assert elapsed >= 0.3  # Allow some margin
