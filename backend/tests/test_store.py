import asyncio

import pytest

from app.schemas import CheckRecord
from app.store import Store, new_id


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path)
    yield s
    s.close()


def record(id_: str, status: str = "queued") -> CheckRecord:
    return CheckRecord(
        id=id_,
        created_at="2026-10-14T00:00:00+00:00",
        status=status,
        input_type="text",
        input_preview="hello",
    )


async def test_check_roundtrip_and_upsert(store):
    cid = new_id()
    await store.save_check(record(cid))
    assert (await store.get_check(cid)) == record(cid)
    await store.save_check(record(cid, "done"))
    assert (await store.get_check(cid)).status == "done"


async def test_unknown_check_is_none(store):
    assert await store.get_check("nope") is None


async def test_cache_hit_and_expiry(store):
    await store.cache_put("k", {"results": [1]})
    assert await store.cache_get("k", max_age_hours=24) == {"results": [1]}
    assert await store.cache_get("k", max_age_hours=0) is None
    assert await store.cache_get("missing", max_age_hours=24) is None


async def test_daily_counter(store):
    assert await store.daily_count("2026-10-14") == 0
    assert await store.increment_daily("2026-10-14") == 1
    assert await store.increment_daily("2026-10-14") == 2
    assert await store.daily_count("2026-10-14") == 2
    assert await store.daily_count("2026-10-15") == 0


async def test_daily_cap_increment_is_atomic(store):
    results = await asyncio.gather(*(store.try_increment_daily(3, "2026-10-14") for _ in range(10)))
    assert results.count(True) == 3
    assert await store.daily_count("2026-10-14") == 3
    assert await store.try_increment_daily(0, "2026-10-15") is False


async def test_save_check_serializes_at_call_time(store):
    rec = record("r1")
    pending = asyncio.create_task(store.save_check(rec))
    await asyncio.sleep(0)  # the save has started and now waits for its worker thread
    rec.status = "done"  # changed while the write waits: the write keeps the old state
    await pending
    assert (await store.get_check("r1")).status == "queued"


async def test_concurrent_saves_keep_call_order(store):
    recs = [record("r1", status) for status in ("queued", "running", "done")]
    await asyncio.gather(*(store.save_check(r) for r in recs))
    assert (await store.get_check("r1")).status == "done"


async def test_cancelled_call_does_not_break_store(store):
    task = asyncio.create_task(store.save_check(record("r1")))
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    await store.save_check(record("r2"))
    assert await store.get_check("r2") is not None


async def test_fail_unfinished_marks_only_open_checks(store):
    for cid, status in [("a", "queued"), ("b", "running"), ("c", "done"), ("d", "error")]:
        await store.save_check(record(cid, status))
    assert sorted(await store.fail_unfinished("restarted")) == ["a", "b"]
    a, c = await store.get_check("a"), await store.get_check("c")
    assert (a.status, a.error) == ("error", "restarted")
    assert c.status == "done"
