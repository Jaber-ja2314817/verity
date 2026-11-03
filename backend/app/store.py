import asyncio
import json
import secrets
import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .apikeys import ApiKey
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
CREATE TABLE IF NOT EXISTS api_keys (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  key_hash TEXT NOT NULL UNIQUE,
  prefix TEXT NOT NULL,
  created_at TEXT NOT NULL,
  revoked_at TEXT,
  rate_per_minute INTEGER NOT NULL,
  daily_quota INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS key_usage (
  key_id TEXT NOT NULL,
  day TEXT NOT NULL,
  checks INTEGER NOT NULL,
  PRIMARY KEY (key_id, day)
);
"""
KEY_COLUMNS = "id, name, prefix, created_at, revoked_at, rate_per_minute, daily_quota"


def key_from_row(row) -> ApiKey:
    return ApiKey(
        id=row[0], name=row[1], prefix=row[2], created_at=row[3], revoked_at=row[4],
        rate_per_minute=row[5], daily_quota=row[6],
    )  # fmt: skip


def make_store(data_dir: str | Path, database_url: str = ""):
    """Postgres (Neon) when DATABASE_URL is set, else the local SQLite file."""
    if database_url:
        from .store_pg import PgStore  # imported here: psycopg is only needed for Postgres

        return PgStore(database_url)
    return Store(data_dir)


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
        # The asyncio lock keeps calls in arrival order. The thread lock guarantees one statement
        # at a time on the connection even when an awaiting task is cancelled (the asyncio lock
        # is then released while the worker thread is still running).
        self._lock = asyncio.Lock()
        self._thread_lock = threading.Lock()
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    async def init(self) -> None:
        """Nothing to do: the schema is created in the constructor. (PgStore opens a pool.)"""

    async def aclose(self) -> None:
        self.close()

    def _locked(self, fn):
        with self._thread_lock:
            return fn()

    async def _run(self, fn):
        async with self._lock:
            return await asyncio.to_thread(self._locked, fn)

    # ---- checks ----
    async def save_check(self, record: CheckRecord) -> None:
        # Serialize now, on the event loop: pipeline tasks keep changing the record while the
        # write waits for its turn, and must not change it while another thread dumps it.
        row = (record.id, record.created_at, record.status, record.model_dump_json())

        def fn():
            self._conn.execute(
                "INSERT INTO checks (id, created_at, status, record_json) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status, "
                "record_json=excluded.record_json",
                row,
            )
            self._conn.commit()

        await self._run(fn)

    async def fail_unfinished(self, message: str, older_than_s: float = 0) -> list[str]:
        """Mark every queued/running check (created at least older_than_s ago) as failed: they
        died with the previous process."""
        cutoff = (utc_now() - timedelta(seconds=older_than_s)).isoformat()

        def fn():
            rows = self._conn.execute(
                "SELECT record_json FROM checks WHERE status IN ('queued', 'running') "
                "AND created_at <= ?",
                (cutoff,),
            ).fetchall()
            ids = []
            for (raw,) in rows:
                record = CheckRecord.model_validate_json(raw)
                record.status = "error"
                record.error = message
                self._conn.execute(
                    "UPDATE checks SET status = ?, record_json = ? WHERE id = ?",
                    (record.status, record.model_dump_json(), record.id),
                )
                ids.append(record.id)
            self._conn.commit()
            return ids

        return await self._run(fn)

    async def fail_checks(self, ids: list[str], message: str) -> list[str]:
        """Mark these checks failed if they are still queued or running."""

        def fn():
            done = []
            for check_id in ids:
                row = self._conn.execute(
                    "SELECT record_json FROM checks WHERE id = ? "
                    "AND status IN ('queued', 'running')",
                    (check_id,),
                ).fetchone()
                if row is None:
                    continue
                record = CheckRecord.model_validate_json(row[0])
                record.status = "error"
                record.error = message
                self._conn.execute(
                    "UPDATE checks SET status = ?, record_json = ? WHERE id = ?",
                    (record.status, record.model_dump_json(), record.id),
                )
                done.append(record.id)
            self._conn.commit()
            return done

        return await self._run(fn)

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

    async def cache_put(self, key: str, response: object, prune_hours: float | None = None) -> None:
        """Store a response. With prune_hours, also delete entries older than that, so the
        cache (up to ~250 KB of page text per query) does not grow without bound."""
        now = utc_now()

        def fn():
            if prune_hours is not None:
                cutoff = (now - timedelta(hours=prune_hours)).isoformat()
                self._conn.execute("DELETE FROM search_cache WHERE created_at < ?", (cutoff,))
            self._conn.execute(
                "INSERT OR REPLACE INTO search_cache (key, created_at, response_json) "
                "VALUES (?, ?, ?)",
                (key, now.isoformat(), json.dumps(response)),
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

    async def try_increment_daily(self, cap: int, day: str | None = None) -> bool:
        """Count one more check for the day unless the day already has `cap`. Atomic."""
        day = day or utc_now().date().isoformat()

        def fn():
            if cap <= 0:
                return False
            cur = self._conn.execute(
                "INSERT INTO daily_usage (day, checks) VALUES (?, 1) "
                "ON CONFLICT(day) DO UPDATE SET checks = checks + 1 WHERE checks < ?",
                (day, cap),
            )
            self._conn.commit()
            return cur.rowcount == 1

        return await self._run(fn)

    # ---- API keys ----
    async def create_api_key(self, key: ApiKey, key_hash: str) -> None:
        def fn():
            self._conn.execute(
                f"INSERT INTO api_keys ({KEY_COLUMNS}, key_hash) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (key.id, key.name, key.prefix, key.created_at, key.revoked_at,
                 key.rate_per_minute, key.daily_quota, key_hash),
            )  # fmt: skip
            self._conn.commit()

        await self._run(fn)

    async def get_api_key_by_hash(self, key_hash: str) -> ApiKey | None:
        def fn():
            return self._conn.execute(
                f"SELECT {KEY_COLUMNS} FROM api_keys WHERE key_hash = ?", (key_hash,)
            ).fetchone()

        row = await self._run(fn)
        return key_from_row(row) if row else None

    async def list_api_keys(self) -> list[ApiKey]:
        def fn():
            return self._conn.execute(
                f"SELECT {KEY_COLUMNS} FROM api_keys ORDER BY created_at"
            ).fetchall()

        return [key_from_row(r) for r in await self._run(fn)]

    async def revoke_api_key(self, key_id: str) -> bool:
        """True if the key existed and was active."""
        now = utc_now().isoformat()

        def fn():
            cur = self._conn.execute(
                "UPDATE api_keys SET revoked_at = ? WHERE id = ? AND revoked_at IS NULL",
                (now, key_id),
            )
            self._conn.commit()
            return cur.rowcount == 1

        return await self._run(fn)

    async def key_daily_count(self, key_id: str, day: str | None = None) -> int:
        day = day or utc_now().date().isoformat()

        def fn():
            return self._conn.execute(
                "SELECT checks FROM key_usage WHERE key_id = ? AND day = ?", (key_id, day)
            ).fetchone()

        row = await self._run(fn)
        return row[0] if row else 0

    async def try_increment_key_daily(self, key_id: str, cap: int, day: str | None = None) -> bool:
        """Count one more check for this key today unless it already has `cap`. Atomic."""
        day = day or utc_now().date().isoformat()

        def fn():
            if cap <= 0:
                return False
            cur = self._conn.execute(
                "INSERT INTO key_usage (key_id, day, checks) VALUES (?, ?, 1) "
                "ON CONFLICT(key_id, day) DO UPDATE SET checks = checks + 1 WHERE checks < ?",
                (key_id, day, cap),
            )
            self._conn.commit()
            return cur.rowcount == 1

        return await self._run(fn)

    async def refund_key_daily(self, key_id: str, day: str | None = None) -> None:
        """Undo one try_increment_key_daily (the check was refused after being counted)."""
        day = day or utc_now().date().isoformat()

        def fn():
            self._conn.execute(
                "UPDATE key_usage SET checks = checks - 1 "
                "WHERE key_id = ? AND day = ? AND checks > 0",
                (key_id, day),
            )
            self._conn.commit()

        await self._run(fn)

    def close(self) -> None:
        self._conn.close()
