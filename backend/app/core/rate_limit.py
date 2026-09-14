"""Per-user rate limiting on draft creation (Phase 5).

Any authenticated user — including end_user — may draft an edit (via Suggest
or Ask's edit-instruction handoff): drafting is always safe, since nothing
ever writes to a real document without a reviewer/admin's explicit approval
(see app/api/approvals.py). What drafting shouldn't be is unbounded, so a
single user can't flood the approval queue with junk. Rate-limited, not
role-restricted — the write-time gate already does the real access control.

Same two-implementation pattern as app.agents.detect.graph_store.GraphStore:
a real backend (Redis — provisioned since Phase 0's docker-compose but never
actually used until now) and an in-memory one so the mocked test suite never
needs Docker. Redis being unreachable fails OPEN (allows the request, logs a
warning) rather than blocking drafting entirely — consistent with how every
other piece of optional infra in this project degrades.
"""

from __future__ import annotations

import abc
import logging
import time

import redis

from app.config import settings

logger = logging.getLogger("pactscan.rate_limit")


class DraftRateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"Draft rate limit exceeded — retry after {retry_after_seconds}s")


class RateLimiter(abc.ABC):
    @abc.abstractmethod
    def increment_and_check(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """Increments the counter for ``key`` and returns
        (allowed, retry_after_seconds). retry_after_seconds is 0 when allowed."""


class RedisRateLimiter(RateLimiter):
    def __init__(self, client: "redis.Redis | None" = None) -> None:
        # redis-py connects lazily — constructing this never touches the
        # network; only the first actual command below can fail.
        self._client = client or redis.Redis.from_url(settings.redis_url)

    def increment_and_check(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        try:
            count = self._client.incr(key)
            if count == 1:
                self._client.expire(key, window_seconds)
            if count <= limit:
                return True, 0
            ttl = self._client.ttl(key)
            return False, max(int(ttl), 1)
        except redis.RedisError:
            logger.warning(
                "Redis unreachable — draft rate limit not enforced for this request", exc_info=True
            )
            return True, 0


class InMemoryRateLimiter(RateLimiter):
    """Fixed-window counter kept in process memory — mocked tests only."""

    def __init__(self) -> None:
        self._counts: dict[str, tuple[int, float]] = {}

    def increment_and_check(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.time()
        count, expiry = self._counts.get(key, (0, 0.0))
        if now >= expiry:
            count, expiry = 0, now + window_seconds
        count += 1
        self._counts[key] = (count, expiry)
        if count <= limit:
            return True, 0
        return False, max(int(expiry - now), 1)


_default_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _default_limiter
    if _default_limiter is None:
        _default_limiter = RedisRateLimiter()
    return _default_limiter


def check_draft_rate_limit(user_id: str, limiter: RateLimiter | None = None) -> None:
    limiter = limiter or get_rate_limiter()
    allowed, retry_after = limiter.increment_and_check(
        f"draft_rate:{user_id}",
        settings.draft_rate_limit_max,
        settings.draft_rate_limit_window_seconds,
    )
    if not allowed:
        raise DraftRateLimitExceeded(retry_after)
