import time
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from fastapi import Request

from .store import Store

PER_IP_MESSAGE = "You're checking a lot quickly. Please wait {seconds} seconds and try again."
DAILY_CAP_MESSAGE = (
    "Verity has reached today's free limit. Try again tomorrow, or browse the examples."
)


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip()
    if first:
        return first
    return request.client.host if request.client else "unknown"


def seconds_until_utc_midnight(now: datetime | None = None) -> int:
    now = now or datetime.now(UTC)
    midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return max(1, int((midnight - now).total_seconds()))


class RateLimitExceeded(Exception):
    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


class SlidingWindow:
    """In-memory per-key sliding window: at most `limit` hits per `window_s` seconds."""

    def __init__(self, limit: int, window_s: float, clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window_s = window_s
        self.clock = clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits[key]
        while hits and hits[0] <= now - self.window_s:
            hits.popleft()
        return hits

    def retry_after(self, key: str) -> int | None:
        """Seconds until the key may try again, or None if it is under the limit."""
        now = self.clock()
        hits = self._prune(key, now)
        if len(hits) < self.limit:
            if not hits:
                self._hits.pop(key, None)
            return None
        return max(1, int(hits[0] + self.window_s - now + 0.999))

    def hit(self, key: str) -> None:
        now = self.clock()
        self._prune(key, now).append(now)


class RateLimiter:
    """Per-IP sliding window plus a per-UTC-day cap stored in SQLite.

    Call check() after validation and record() only once the check is accepted, so requests
    rejected by validation or by a limit are never counted.
    """

    def __init__(
        self,
        store: Store,
        *,
        per_ip: int,
        window_s: float,
        daily_cap: int,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.store = store
        self.daily_cap = daily_cap
        self.window = SlidingWindow(per_ip, window_s, clock)

    async def check(self, ip: str) -> None:
        wait = self.window.retry_after(ip)
        if wait is not None:
            raise RateLimitExceeded(PER_IP_MESSAGE.format(seconds=wait), wait)
        if await self.store.daily_count() >= self.daily_cap:
            raise RateLimitExceeded(DAILY_CAP_MESSAGE, seconds_until_utc_midnight())

    async def record(self, ip: str) -> None:
        self.window.hit(ip)
        await self.store.increment_daily()
