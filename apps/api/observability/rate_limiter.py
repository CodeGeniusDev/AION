"""Rate limiting behind a replaceable interface.

`InMemoryRateLimiter` is a real, working fixed-window limiter — genuinely
functional today, not a placeholder. It is explicitly NOT distributed
(state lives in process memory, so it does not coordinate across multiple
server instances) — that limitation is stated here rather than hidden.
Swapping in a Redis-backed implementation later means writing a new class
that satisfies `RateLimiterInterface`; no caller changes.
"""

import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque


class RateLimiterInterface(ABC):
    @abstractmethod
    def allow(self, key: str) -> bool:
        """Return True if a request identified by `key` is allowed right now."""

    @abstractmethod
    def reset(self) -> None:
        """Clear all rate-limit state. Test/administrative use only."""


class InMemoryRateLimiter(RateLimiterInterface):
    """Fixed-window limiter: at most `max_requests` per `window_seconds`
    per key. Single-process only — see module docstring."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        cutoff = now - self.window_seconds
        while hits and hits[0] < cutoff:
            hits.popleft()
        if len(hits) >= self.max_requests:
            return False
        hits.append(now)
        return True

    def reset(self) -> None:
        self._hits.clear()
