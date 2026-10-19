import asyncio
from collections import OrderedDict, defaultdict, deque

HISTORY = 200  # events kept per check
MAX_CHECKS = 200  # checks whose history is kept; the oldest is dropped first
TERMINAL = {"done", "error"}


class EventBus:
    """In-memory per-check event fan-out for SSE. Works because we run ONE Uvicorn worker."""

    def __init__(self, max_checks: int = MAX_CHECKS):
        self.max_checks = max_checks
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._history: OrderedDict[str, deque[dict]] = OrderedDict()

    def emit(self, check_id: str, type_: str, **data) -> dict:
        event = {"type": type_, **data}
        if check_id not in self._history:
            self._history[check_id] = deque(maxlen=HISTORY)
            while len(self._history) > self.max_checks:
                self._history.popitem(last=False)  # bounded memory: forget the oldest check
        self._history[check_id].append(event)
        for q in self._subscribers.get(check_id, []):
            q.put_nowait(event)
        return event

    def history(self, check_id: str) -> list[dict]:
        return list(self._history.get(check_id, []))

    def subscribe(self, check_id: str) -> asyncio.Queue:
        """New queue that receives live events from now on.

        To catch up without gaps or duplicates, call history() right after subscribe(), with
        no await in between.
        """
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers[check_id].append(q)
        return q

    def unsubscribe(self, check_id: str, q: asyncio.Queue) -> None:
        subs = self._subscribers.get(check_id, [])
        if q in subs:
            subs.remove(q)
        if not subs:
            self._subscribers.pop(check_id, None)
