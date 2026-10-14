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
