"""Unit tests for token bucket rate limiter (P2-3)."""

from __future__ import annotations

import asyncio
import pytest
import time

from model_bridge.core.rate_limiter import TokenBucket, RateLimiterConfig


class TestTokenBucket:
    """Test TokenBucket rate limiter."""

    def test_create_token_bucket(self):
        """Test creating a token bucket."""
        bucket = TokenBucket(rate=10.0, capacity=20.0)
        assert bucket.rate == 10.0
        assert bucket.capacity == 20.0
        assert bucket.tokens == 20.0  # Starts full

    def test_create_token_bucket_with_initial_tokens(self):
        """Test creating a token bucket with initial tokens."""
        bucket = TokenBucket(rate=10.0, capacity=20.0, tokens=5.0)
        assert bucket.tokens == 5.0

    def test_try_acquire_success(self):
        """Test acquiring tokens when available."""
        bucket = TokenBucket(rate=10.0, capacity=20.0)
        result = bucket.try_acquire(5.0)
        assert result is True
        assert bucket.tokens <= 15.0  # May have refilled slightly

    def test_try_acquire_fails_when_insufficient(self):
        """Test acquiring tokens when not enough available."""
        bucket = TokenBucket(rate=10.0, capacity=20.0, tokens=3.0)
        result = bucket.try_acquire(5.0)
        assert result is False
        # tokens may have refilled slightly, just check it's around 3
        assert bucket.tokens < 5.0

    def test_try_acquire_exceeds_capacity_raises(self):
        """Test that acquiring more than capacity raises error."""
        bucket = TokenBucket(rate=10.0, capacity=20.0)
        with pytest.raises(ValueError):
            bucket.try_acquire(25.0)

    def test_tokens_refill_over_time(self):
        """Test that tokens refill over time."""
        bucket = TokenBucket(rate=10.0, capacity=20.0, tokens=0.0)
        bucket.last_update = time.monotonic() - 1.0  # 1 second ago

        # After 1 second at rate 10, should have 10 tokens
        assert bucket.available_tokens >= 9.9

    @pytest.mark.anyio
    async def test_async_acquire_immediate(self):
        """Test async acquire when tokens available."""
        bucket = TokenBucket(rate=10.0, capacity=20.0)
        result = await bucket.acquire(5.0, timeout=0.1)
        assert result is True
        assert bucket.tokens <= 15.0

    @pytest.mark.anyio
    async def test_async_acquire_timeout(self):
        """Test async acquire with timeout when insufficient tokens."""
        # Create with small capacity and small rate
        bucket = TokenBucket(rate=0.5, capacity=1.0)
        # Exhaust tokens
        bucket.tokens = 0.0
        bucket.last_update = time.monotonic()
        # Try to acquire 1 token - should timeout since rate is 0.5/s
        result = await bucket.acquire(1.0, timeout=0.1)
        assert result is False  # Can't get 1 token in 0.1s at rate 0.5/s

    @pytest.mark.anyio
    async def test_async_acquire_waits_for_tokens(self):
        """Test that async acquire waits for tokens to refill."""
        bucket = TokenBucket(rate=100.0, capacity=100.0, tokens=0.0)
        # Should acquire after ~0.02 seconds
        start = time.monotonic()
        result = await bucket.acquire(2.0, timeout=1.0)
        elapsed = time.monotonic() - start
        assert result is True
        assert elapsed < 0.5  # Should complete quickly


class TestRateLimiterConfig:
    """Test RateLimiterConfig."""

    def test_create_config(self):
        """Test creating rate limiter config."""
        config = RateLimiterConfig(requests_per_second=5.0, burst_capacity=10.0)
        assert config.requests_per_second == 5.0
        assert config.burst_capacity == 10.0

    def test_create_bucket_from_config(self):
        """Test creating bucket from config."""
        config = RateLimiterConfig(requests_per_second=5.0, burst_capacity=10.0)
        bucket = config.create_bucket()
        assert bucket.rate == 5.0
        assert bucket.capacity == 10.0

    def test_default_config(self):
        """Test default configuration values."""
        config = RateLimiterConfig()
        assert config.requests_per_second == 10.0
        assert config.burst_capacity == 20.0
