import asyncio
import json
import secrets
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .schemas import CheckRecord

SCHEMA = """
CREATE TABLE IF NOT EXISTS checks (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  status TEXT NOT NULL,
  record_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS search_cache (
  key TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  response_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS daily_usage (
  day TEXT PRIMARY KEY,
  checks INTEGER NOT NULL
);
"""


def new_id() -> str:
    return secrets.token_urlsafe(8)


def utc_now() -> datetime:
    return datetime.now(UTC)


class Store:
    """SQLite storage for checks, the search cache and daily usage. All methods are async."""

    def __init__(self, data_dir: str | Path):
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        self.path = Path(data_dir) / "verity.db"
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._lock = asyncio.Lock()
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    async def _run(self, fn):
        async with self._lock:
            return await asyncio.to_thread(fn)

    # ---- checks ----
    async def save_check(self, record: CheckRecord) -> None:
        def fn():
            self._conn.execute(
                "INSERT INTO checks (id, created_at, status, record_json) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status, "
                "record_json=excluded.record_json",
                (record.id, record.created_at, record.status, record.model_dump_json()),
            )
            self._conn.commit()

        await self._run(fn)

    async def get_check(self, check_id: str) -> CheckRecord | None:
        def fn():
            return self._conn.execute(
                "SELECT record_json FROM checks WHERE id = ?", (check_id,)
            ).fetchone()

        row = await self._run(fn)
        return CheckRecord.model_validate_json(row[0]) if row else None

    # ---- search cache ----
    async def cache_get(self, key: str, max_age_hours: float) -> object | None:
        cutoff = (utc_now() - timedelta(hours=max_age_hours)).isoformat()

        def fn():
            return self._conn.execute(
                "SELECT response_json FROM search_cache WHERE key = ? AND created_at >= ?",
                (key, cutoff),
            ).fetchone()

        row = await self._run(fn)
        return json.loads(row[0]) if row else None

    async def cache_put(self, key: str, response: object) -> None:
        def fn():
            self._conn.execute(
                "INSERT OR REPLACE INTO search_cache (key, created_at, response_json) "
                "VALUES (?, ?, ?)",
                (key, utc_now().isoformat(), json.dumps(response)),
            )
            self._conn.commit()

        await self._run(fn)

    # ---- daily usage (UTC day) ----
    async def daily_count(self, day: str | None = None) -> int:
        day = day or utc_now().date().isoformat()

        def fn():
            return self._conn.execute(
                "SELECT checks FROM daily_usage WHERE day = ?", (day,)
            ).fetchone()

        row = await self._run(fn)
        return row[0] if row else 0

    async def increment_daily(self, day: str | None = None) -> int:
        day = day or utc_now().date().isoformat()

        def fn():
            self._conn.execute(
                "INSERT INTO daily_usage (day, checks) VALUES (?, 1) "
                "ON CONFLICT(day) DO UPDATE SET checks = checks + 1",
                (day,),
            )
            self._conn.commit()
            return self._conn.execute(
                "SELECT checks FROM daily_usage WHERE day = ?", (day,)
            ).fetchone()[0]

        return await self._run(fn)

    def close(self) -> None:
        self._conn.close()
