"""Postgres storage (Neon) with the same async methods as store.Store.

Used when DATABASE_URL is set, so checks, share links and API keys survive restarts and are
shared by every serverless instance. Records are stored as JSON text, like in SQLite.

Neon's pooled connection string goes through PgBouncer in transaction mode, which does not
support server-side prepared statements, so they are turned off (prepare_threshold=None).
"""

import json
import logging
from datetime import timedelta

from .apikeys import ApiKey
from .schemas import CheckRecord
from .store import KEY_COLUMNS, key_from_row, utc_now

log = logging.getLogger(__name__)

SCHEMA_STATEMENTS = (
    """CREATE TABLE IF NOT EXISTS checks (
      id TEXT PRIMARY KEY,
      created_at TEXT NOT NULL,
      status TEXT NOT NULL,
      record_json TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS search_cache (
      key TEXT PRIMARY KEY,
      created_at TEXT NOT NULL,
      response_json TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS daily_usage (
      day TEXT PRIMARY KEY,
      checks INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS api_keys (
      id TEXT PRIMARY KEY,
      name TEXT NOT NULL,
      key_hash TEXT NOT NULL UNIQUE,
      prefix TEXT NOT NULL,
      created_at TEXT NOT NULL,
      revoked_at TEXT,
      rate_per_minute INTEGER NOT NULL,
      daily_quota INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS key_usage (
      key_id TEXT NOT NULL,
      day TEXT NOT NULL,
      checks INTEGER NOT NULL,
      PRIMARY KEY (key_id, day)
    )""",
)


class PgStore:
    def __init__(self, database_url: str, *, max_connections: int = 5):
        from psycopg_pool import AsyncConnectionPool

        self.pool = AsyncConnectionPool(
            database_url,
            min_size=0,  # serverless: do not hold idle connections open
            max_size=max_connections,
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": None},
        )

    async def init(self) -> None:
        await self.pool.open()
        async with self.pool.connection() as conn:
            for statement in SCHEMA_STATEMENTS:
                await conn.execute(statement)

    async def aclose(self) -> None:
        await self.pool.close()

    async def _one(self, sql: str, params: tuple = ()):
        async with self.pool.connection() as conn:
            cur = await conn.execute(sql, params)
            return await cur.fetchone()

    async def _all(self, sql: str, params: tuple = ()):
        async with self.pool.connection() as conn:
            cur = await conn.execute(sql, params)
            return await cur.fetchall()

    async def _rowcount(self, sql: str, params: tuple = ()) -> int:
        async with self.pool.connection() as conn:
            cur = await conn.execute(sql, params)
            return cur.rowcount

    # ---- checks ----
    async def save_check(self, record: CheckRecord) -> None:
        await self._rowcount(
            "INSERT INTO checks (id, created_at, status, record_json) VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status, "
            "record_json = EXCLUDED.record_json",
            (record.id, record.created_at, record.status, record.model_dump_json()),
        )

    async def get_check(self, check_id: str) -> CheckRecord | None:
        row = await self._one("SELECT record_json FROM checks WHERE id = %s", (check_id,))
        return CheckRecord.model_validate_json(row[0]) if row else None

    async def _fail(self, rows, message: str) -> list[str]:
        ids = []
        for (raw,) in rows:
            record = CheckRecord.model_validate_json(raw)
            record.status = "error"
            record.error = message
            await self._rowcount(
                "UPDATE checks SET status = %s, record_json = %s WHERE id = %s "
                "AND status IN ('queued', 'running')",
                (record.status, record.model_dump_json(), record.id),
            )
            ids.append(record.id)
        return ids

    async def fail_unfinished(self, message: str, older_than_s: float = 0) -> list[str]:
        """Fail queued/running checks created at least older_than_s ago. Several instances
        share this table, so the caller passes a minimum age: a check younger than the check
        timeout may still be running on another instance."""
        cutoff = (utc_now() - timedelta(seconds=older_than_s)).isoformat()
        rows = await self._all(
            "SELECT record_json FROM checks WHERE status IN ('queued', 'running') "
            "AND created_at <= %s",
            (cutoff,),
        )
        return await self._fail(rows, message)

    async def fail_checks(self, ids: list[str], message: str) -> list[str]:
        if not ids:
            return []
        rows = await self._all(
            "SELECT record_json FROM checks WHERE id = ANY(%s) "
            "AND status IN ('queued', 'running')",
            (list(ids),),
        )
        return await self._fail(rows, message)

    # ---- search cache ----
    async def cache_get(self, key: str, max_age_hours: float) -> object | None:
        cutoff = (utc_now() - timedelta(hours=max_age_hours)).isoformat()
        row = await self._one(
            "SELECT response_json FROM search_cache WHERE key = %s AND created_at >= %s",
            (key, cutoff),
        )
        return json.loads(row[0]) if row else None

    async def cache_put(self, key: str, response: object, prune_hours: float | None = None) -> None:
        now = utc_now()
        if prune_hours is not None:
            cutoff = (now - timedelta(hours=prune_hours)).isoformat()
            await self._rowcount("DELETE FROM search_cache WHERE created_at < %s", (cutoff,))
        await self._rowcount(
            "INSERT INTO search_cache (key, created_at, response_json) VALUES (%s, %s, %s) "
            "ON CONFLICT (key) DO UPDATE SET created_at = EXCLUDED.created_at, "
            "response_json = EXCLUDED.response_json",
            (key, now.isoformat(), json.dumps(response)),
        )

    # ---- daily usage (UTC day) ----
    async def daily_count(self, day: str | None = None) -> int:
        day = day or utc_now().date().isoformat()
        row = await self._one("SELECT checks FROM daily_usage WHERE day = %s", (day,))
        return row[0] if row else 0

    async def increment_daily(self, day: str | None = None) -> int:
        day = day or utc_now().date().isoformat()
        row = await self._one(
            "INSERT INTO daily_usage (day, checks) VALUES (%s, 1) "
            "ON CONFLICT (day) DO UPDATE SET checks = daily_usage.checks + 1 RETURNING checks",
            (day,),
        )
        return row[0]

    async def try_increment_daily(self, cap: int, day: str | None = None) -> bool:
        day = day or utc_now().date().isoformat()
        if cap <= 0:
            return False
        count = await self._rowcount(
            "INSERT INTO daily_usage (day, checks) VALUES (%s, 1) "
            "ON CONFLICT (day) DO UPDATE SET checks = daily_usage.checks + 1 "
            "WHERE daily_usage.checks < %s",
            (day, cap),
        )
        return count == 1

    # ---- API keys ----
    async def create_api_key(self, key: ApiKey, key_hash: str) -> None:
        await self._rowcount(
            f"INSERT INTO api_keys ({KEY_COLUMNS}, key_hash) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (key.id, key.name, key.prefix, key.created_at, key.revoked_at,
             key.rate_per_minute, key.daily_quota, key_hash),
        )  # fmt: skip

    async def get_api_key_by_hash(self, key_hash: str) -> ApiKey | None:
        row = await self._one(
            f"SELECT {KEY_COLUMNS} FROM api_keys WHERE key_hash = %s", (key_hash,)
        )
        return key_from_row(row) if row else None

    async def list_api_keys(self) -> list[ApiKey]:
        rows = await self._all(f"SELECT {KEY_COLUMNS} FROM api_keys ORDER BY created_at")
        return [key_from_row(r) for r in rows]

    async def revoke_api_key(self, key_id: str) -> bool:
        count = await self._rowcount(
            "UPDATE api_keys SET revoked_at = %s WHERE id = %s AND revoked_at IS NULL",
            (utc_now().isoformat(), key_id),
        )
        return count == 1

    async def key_daily_count(self, key_id: str, day: str | None = None) -> int:
        day = day or utc_now().date().isoformat()
        row = await self._one(
            "SELECT checks FROM key_usage WHERE key_id = %s AND day = %s", (key_id, day)
        )
        return row[0] if row else 0

    async def try_increment_key_daily(self, key_id: str, cap: int, day: str | None = None) -> bool:
        day = day or utc_now().date().isoformat()
        if cap <= 0:
            return False
        count = await self._rowcount(
            "INSERT INTO key_usage (key_id, day, checks) VALUES (%s, %s, 1) "
            "ON CONFLICT (key_id, day) DO UPDATE SET checks = key_usage.checks + 1 "
            "WHERE key_usage.checks < %s",
            (key_id, day, cap),
        )
        return count == 1

    async def refund_key_daily(self, key_id: str, day: str | None = None) -> None:
        day = day or utc_now().date().isoformat()
        await self._rowcount(
            "UPDATE key_usage SET checks = checks - 1 "
            "WHERE key_id = %s AND day = %s AND checks > 0",
            (key_id, day),
        )

    def close(self) -> None:  # parity with Store; use aclose() in async code
        log.warning("PgStore.close() does nothing; await aclose()")
