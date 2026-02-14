"""Batch execution with priority queue and rate limiting (P2-3)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from model_bridge.core.rate_limiter import TokenBucket


class Priority(IntEnum):
    """Priority levels for batch jobs."""

    HIGH = 0
    NORMAL = 1
    LOW = 2


def parse_priority(value: str) -> Priority:
    """Parse priority string to Priority enum.

    Args:
        value: Priority string ("high", "normal", "low")

    Returns:
        Priority enum value, defaults to NORMAL for invalid input
    """
    mapping = {
        "high": Priority.HIGH,
        "normal": Priority.NORMAL,
        "low": Priority.LOW,
    }
    return mapping.get(value.lower().strip(), Priority.NORMAL)


@dataclass(order=True)
class PrioritizedJob:
    """Job with priority for heap-based scheduling.

    The sort_key ensures jobs are sorted by (priority, insertion_order),
    so high priority jobs run first, and ties are broken by insertion order.
    """

    sort_key: tuple[int, int] = field(init=False)
    job_id: int = field(compare=False)
    prompt: str = field(compare=False)
    priority: Priority = field(compare=False)
    _insertion_order: int = field(default=0, compare=False)

    def __post_init__(self) -> None:
        self.sort_key = (int(self.priority), self._insertion_order)


class BatchExecutor:
    """Execute batch jobs with priority and rate limiting.

    This executor supports:
    - Priority-based job ordering (HIGH > NORMAL > LOW)
    - Token bucket rate limiting to control request rate
    - Concurrent execution with configurable max concurrency
    - Progress callbacks for streaming results
    """

    def __init__(
        self,
        rate_limiter: TokenBucket | None = None,
        max_concurrency: int = 3,
    ) -> None:
        """Initialize the batch executor.

        Args:
            rate_limiter: Optional TokenBucket for rate limiting
            max_concurrency: Maximum number of concurrent jobs (default: 3)
        """
        self.rate_limiter = rate_limiter
        self.max_concurrency = max_concurrency

    async def execute_sequential(
        self,
        jobs: list[PrioritizedJob],
        executor: Callable[[int, str], asyncio.Future[dict]],
        progress_callback: Callable[[int, int], asyncio.Future[None]] | None = None,
    ) -> list[dict]:
        """Execute jobs sequentially in priority order.

        Args:
            jobs: List of PrioritizedJob instances
            executor: Async function to execute each job (job_id, prompt) -> result
            progress_callback: Optional callback for progress updates (completed, total)

        Returns:
            List of results in original job_id order
        """
        sorted_jobs = sorted(jobs)
        results: list[dict] = [None] * len(jobs)  # type: ignore

        for i, job in enumerate(sorted_jobs):
            if self.rate_limiter:
                await self.rate_limiter.acquire(tokens=1.0)

            result = await executor(job.job_id, job.prompt)
            results[job.job_id] = result

            if progress_callback:
                await progress_callback(i + 1, len(jobs))

        return results

    async def execute_parallel(
        self,
        jobs: list[PrioritizedJob],
        executor: Callable[[int, str], asyncio.Future[dict]],
        progress_callback: Callable[[int, int], asyncio.Future[None]] | None = None,
    ) -> list[dict]:
        """Execute jobs in parallel with priority-aware scheduling.

        Jobs are started in priority order but may complete in any order.
        Rate limiting is applied before each job starts.

        Args:
            jobs: List of PrioritizedJob instances
            executor: Async function to execute each job (job_id, prompt) -> result
            progress_callback: Optional callback for progress updates (completed, total)

        Returns:
            List of results in original job_id order
        """
        sorted_jobs = sorted(jobs)
        results: list[dict] = [None] * len(jobs)  # type: ignore
        completed = [0]
        lock = asyncio.Lock()
        sem = asyncio.Semaphore(self.max_concurrency)

        async def run_job(job: PrioritizedJob) -> None:
            async with sem:
                if self.rate_limiter:
                    await self.rate_limiter.acquire(tokens=1.0)

                result = await executor(job.job_id, job.prompt)
                results[job.job_id] = result

                async with lock:
                    completed[0] += 1
                    if progress_callback:
                        await progress_callback(completed[0], len(jobs))

        await asyncio.gather(*[run_job(job) for job in sorted_jobs])
        return results
