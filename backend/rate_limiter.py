"""
Rate limiter for BiliSum API calls.
Provides an asyncio-based token bucket algorithm to throttle requests
to Bilibili APIs. Adapted from Bili23-Downloader's TokenBucket.
"""

import asyncio
import time


class TokenBucket:
    """Async token bucket for rate limiting.

    Tokens refill at a configurable rate. When rate is 0, the bucket is
    unlimited and consume() returns immediately. Uses asyncio.Lock for
    thread-safe coordination across coroutines.

    Adapted from Bili23-Downloader's threading-based TokenBucket
    (src/util/download/downloader/downloader.py L33-75).
    """

    def __init__(self, rate_bytes_per_sec: float = 0, burst_size: int = 0):
        """
        Args:
            rate_bytes_per_sec: Token refill rate (tokens per second).
                0 means unlimited --- consume() returns immediately.
            burst_size: Maximum tokens the bucket can hold.
                0 means use rate_bytes_per_sec as the burst cap.
        """
        self.rate = rate_bytes_per_sec
        self.burst_size = burst_size if burst_size > 0 else rate_bytes_per_sec
        self.tokens = float(self.burst_size)
        self.last_refill = time.monotonic()
        self.lock = asyncio.Lock()

    async def consume(self, amount: int = 1):
        """Consume tokens from the bucket, sleeping if necessary.

        If the rate is 0 (unlimited), returns immediately without acquiring
        the lock. Otherwise refills tokens based on elapsed time, deducts
        the requested amount, and sleeps in 0.1-second increments until
        enough tokens have been replenished.

        Args:
            amount: Number of tokens to consume (default 1).
        """
        if self.rate <= 0:
            return

        async with self.lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.last_refill = now

            # Refill tokens based on elapsed time
            self.tokens += elapsed * self.rate
            if self.tokens > self.burst_size:
                self.tokens = self.burst_size

            self.tokens -= amount

            if self.tokens >= 0:
                return  # enough tokens available

            # Calculate required sleep time to replenish the deficit
            sleep_time = -self.tokens / self.rate

        # Sleep outside the lock so other coroutines can proceed.
        # Granularity of 0.1 s per iteration, matching the upstream design.
        while sleep_time > 0:
            await asyncio.sleep(min(0.1, sleep_time))
            sleep_time -= 0.1

    def set_rate(self, rate_bytes_per_sec: float):
        """Update the refill rate and reset the bucket to full."""
        self.rate = rate_bytes_per_sec
        self.tokens = float(self.burst_size)
        self.last_refill = time.monotonic()


class APIRateLimiter:
    """High-level rate limiter for Bilibili API calls.

    Wraps TokenBucket to provide a simple ``acquire()`` interface that
    blocks until a call slot is available. Use before every B站 API
    request to stay within rate limits.
    """

    def __init__(self, calls_per_second: float = 1.0):
        """
        Args:
            calls_per_second: Maximum API calls per second (default 1.0).
        """
        burst = max(1, int(calls_per_second)) if calls_per_second >= 1 else 1
        self.bucket = TokenBucket(
            rate_bytes_per_sec=calls_per_second,
            burst_size=burst,
        )

    async def acquire(self):
        """Block until a call slot is available.

        Call this before every Bilibili API request to throttle::

            limiter = APIRateLimiter(calls_per_second=2.0)
            async with httpx.AsyncClient() as client:
                await limiter.acquire()
                response = await client.get("https://api.bilibili.com/...")
        """
        await self.bucket.consume(1)
