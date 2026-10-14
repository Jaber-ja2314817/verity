import asyncio
from collections import defaultdict, deque

HISTORY = 200
TERMINAL = {"done", "error"}


class EventBus:
    """In-memory per-check event fan-out for SSE. Works because we run ONE Uvicorn worker."""

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._history: dict[str, deque[dict]] = defaultdict(lambda: deque(maxlen=HISTORY))

    def emit(self, check_id: str, type_: str, **data) -> dict:
        event = {"type": type_, **data}
        self._history[check_id].append(event)
        for q in self._subscribers.get(check_id, []):
            q.put_nowait(event)
        return event

    def history(self, check_id: str) -> list[dict]:
        return list(self._history.get(check_id, []))

    def subscribe(self, check_id: str) -> asyncio.Queue:
        """New queue that receives live events from now on (use history() to catch up)."""
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers[check_id].append(q)
        return q

    def unsubscribe(self, check_id: str, q: asyncio.Queue) -> None:
        subs = self._subscribers.get(check_id, [])
        if q in subs:
            subs.remove(q)
        if not subs:
            self._subscribers.pop(check_id, None)
