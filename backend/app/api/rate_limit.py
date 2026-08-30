"""Process-local sliding-window rate limiter for analysis endpoints.

MVP scope: an in-memory limiter keyed by user email. Fine for a single
deployable service; replace with a distributed store if the service scales
beyond one process.
"""

import threading
import time
from collections import deque

from fastapi import Depends

from app.api.deps import CurrentUser, get_current_user
from app.core.config import settings
from app.core.errors import AppError, ErrorCode

_MAX_TRACKED_KEYS = 4096


class SlidingWindowLimiter:
    """Allow at most `max_requests` hits per `window_seconds` sliding window."""

    def __init__(self, max_requests: int, window_seconds: float) -> None:
        self.max_requests = max(1, int(max_requests))
        self.window_seconds = float(window_seconds)
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def allowance(self, key: str) -> tuple[bool, int]:
        """Return (allowed, remaining_after_this_call)."""
        now = time.monotonic()
        with self._lock:
            window = self._hits.get(key)
            if window is None:
                window = deque()
                self._hits[key] = window
            while window and now - window[0] >= self.window_seconds:
                window.popleft()
            if len(window) >= self.max_requests:
                return False, 0
            window.append(now)
            self._evict_if_needed()
            return True, self.max_requests - len(window)

    def _evict_if_needed(self) -> None:
        if len(self._hits) <= _MAX_TRACKED_KEYS:
            return
        for key in [k for k, window in self._hits.items() if not window]:
            del self._hits[key]
        # drop oldest keys if still over budget (dict preserves insertion order)
        while len(self._hits) > _MAX_TRACKED_KEYS:
            self._hits.pop(next(iter(self._hits)))


_limiter = SlidingWindowLimiter(settings.rate_limit_requests, settings.rate_limit_window_seconds)


def check_analysis_rate(user: CurrentUser = Depends(get_current_user)) -> None:
    allowed, _ = _limiter.allowance(user.email)
    if not allowed:
        raise AppError(
            ErrorCode.RATE_LIMITED,
            "analysis rate limit exceeded",
            status_code=429,
            details={"retry_after_seconds": int(_limiter.window_seconds)},
        )