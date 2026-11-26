"""Small in-memory sliding-window rate limiter.

Good enough for a single Render instance. If you ever run several instances,
swap the storage for Redis; the dependency interface can stay the same.
"""

import threading
import time
from collections import defaultdict, deque
from typing import Callable
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status

from app.auth import get_current_user_id


class SlidingWindowLimiter:
    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> int | None:
        """Record a hit. Returns None if allowed, else seconds to wait."""
        now = time.monotonic()
        cutoff = now - self.window_seconds

        with self._lock:
            hits = self._hits[key]

            while hits and hits[0] <= cutoff:
                hits.popleft()

            if len(hits) >= self.max_requests:
                return max(1, int(hits[0] + self.window_seconds - now) + 1)

            hits.append(now)

            # Keep memory bounded: forget keys that have gone quiet.
            if len(self._hits) > 5000:
                for stale in [k for k, v in self._hits.items() if not v]:
                    del self._hits[stale]

            return None

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def _too_many(retry_after: int, what: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=f"Too many {what}. Please wait {retry_after} seconds and try again.",
        headers={"Retry-After": str(retry_after)},
    )


def client_ip(request: Request) -> str:
    """Best-effort client IP behind Render's proxy."""
    forwarded = request.headers.get("x-forwarded-for")

    if forwarded:
        return forwarded.split(",")[0].strip()

    return request.client.host if request.client else "unknown"


# Chat: 20 messages per user per minute is plenty for a human.
chat_limiter = SlidingWindowLimiter(max_requests=20, window_seconds=60)

# Food search: 40 searches per IP per minute (typing + paging).
food_limiter = SlidingWindowLimiter(max_requests=40, window_seconds=60)


def chat_rate_limit(
    user_id: UUID = Depends(get_current_user_id),
) -> None:
    retry_after = chat_limiter.check(str(user_id))

    if retry_after is not None:
        raise _too_many(retry_after, "chat messages")


def food_search_rate_limit(request: Request) -> None:
    retry_after = food_limiter.check(client_ip(request))

    if retry_after is not None:
        raise _too_many(retry_after, "food searches")


def make_limit_dependency(
    limiter: SlidingWindowLimiter, what: str
) -> Callable[[Request], None]:
    """Build an IP-based dependency for any other public endpoint."""

    def dependency(request: Request) -> None:
        retry_after = limiter.check(client_ip(request))

        if retry_after is not None:
            raise _too_many(retry_after, what)

    return dependency
