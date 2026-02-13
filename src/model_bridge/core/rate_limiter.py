"""Token bucket rate limiter for batch execution (P2-3)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class TokenBucket:
    """Token bucket rate limiter for controlling request rate.

    Attributes:
        rate: Tokens added per second
        capacity: Maximum tokens in bucket
        tokens: Current token count
        last_update: Timestamp of last token update
    """

    rate: float  # tokens per second
    capacity: float  # max tokens
    tokens: float = field(default=0.0)
    last_update: float = field(default_factory=time.monotonic)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self):
        if self.tokens == 0:
            self.tokens = self.capacity

    async def acquire(self, tokens: float = 1.0, timeout: float | None = None) -> bool:
        """Acquire tokens from the bucket.

        Args:
            tokens: Number of tokens to acquire
            timeout: Maximum time to wait (None = wait forever)

        Returns:
            True if tokens acquired, False if timeout
        """
        if tokens > self.capacity:
            raise ValueError(f"Requested {tokens} tokens exceeds capacity {self.capacity}")

        start_time = time.monotonic()

        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self.last_update
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
                self.last_update = now

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True

                if timeout is not None:
                    elapsed_wait = time.monotonic() - start_time
                    if elapsed_wait >= timeout:
                        return False

                # Wait for tokens to be available
                wait_time = (tokens - self.tokens) / self.rate
                await asyncio.sleep(min(wait_time, 0.1))

    def try_acquire(self, tokens: float = 1.0) -> bool:
        """Try to acquire tokens without waiting.

        Args:
            tokens: Number of tokens to acquire

        Returns:
            True if tokens acquired, False if not enough tokens

        Raises:
            ValueError: If requested tokens exceed capacity
        """
        if tokens > self.capacity:
            raise ValueError(f"Requested {tokens} tokens exceeds capacity {self.capacity}")

        now = time.monotonic()
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now

        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    @property
    def available_tokens(self) -> float:
        """Current available tokens (without updating)."""
        now = time.monotonic()
        elapsed = now - self.last_update
        return min(self.capacity, self.tokens + elapsed * self.rate)


@dataclass
class RateLimiterConfig:
    """Configuration for rate limiter."""

    requests_per_second: float = 10.0
    burst_capacity: float = 20.0

    def create_bucket(self) -> TokenBucket:
        """Create a TokenBucket from this config."""
        return TokenBucket(
            rate=self.requests_per_second,
            capacity=self.burst_capacity,
        )
