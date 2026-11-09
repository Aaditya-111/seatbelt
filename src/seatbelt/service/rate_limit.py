from collections import deque
from collections.abc import Callable
from math import ceil
from threading import Lock
from time import monotonic


class InMemoryRateLimiter:
    """Thread-safe sliding-window limiter for a single application process."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = monotonic,
        max_keys: int = 10_000,
    ) -> None:
        if max_keys < 1:
            raise ValueError("max_keys must be positive")

        self._clock = clock
        self._max_keys = max_keys
        self._buckets: dict[str, deque[float]] = {}
        self._windows: dict[str, int] = {}
        self._lock = Lock()
        self._calls = 0

    def allow(
        self,
        key: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        if limit < 1 or window_seconds < 1:
            raise ValueError("Rate limit and window must be positive")

        now = self._clock()

        with self._lock:
            self._calls += 1
            bucket = self._buckets.get(key)

            if bucket is None:
                if len(self._buckets) >= self._max_keys:
                    self._prune(now)
                if len(self._buckets) >= self._max_keys:
                    return False, window_seconds

                bucket = deque()
                self._buckets[key] = bucket
                self._windows[key] = window_seconds
            elif self._windows[key] != window_seconds:
                raise ValueError("A rate-limit key cannot change its window")

            cutoff = now - window_seconds
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if not bucket:
                bucket.append(now)
                return True, 0

            if len(bucket) >= limit:
                retry_after = max(1, ceil(bucket[0] + window_seconds - now))
                return False, retry_after

            bucket.append(now)

            if self._calls % 256 == 0:
                self._prune(now)

            return True, 0

    def _prune(self, now: float) -> None:
        stale = [
            key
            for key, bucket in self._buckets.items()
            if not bucket
            or bucket[-1] <= now - self._windows[key]
        ]
        for key in stale:
            self._buckets.pop(key, None)
            self._windows.pop(key, None)
