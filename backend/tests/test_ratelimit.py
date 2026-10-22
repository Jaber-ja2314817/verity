import asyncio
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.events import EventBus
from app.main import create_app
from app.ratelimit import (
    SWEEP_KEYS,
    RateLimiter,
    RateLimitExceeded,
    SlidingWindow,
    client_ip,
    seconds_until_utc_midnight,
)
from app.store import Store
from tests.test_api import GOOD_TEXT, RecordingRunCheck, make_settings


@pytest.fixture
def make_client(tmp_path, fake_llm, fake_search):
    stores = []

    def make(**settings_kw):
        store = Store(tmp_path)
        stores.append(store)
        app = create_app(
            make_settings(tmp_path, **settings_kw),
            llm=fake_llm,
            search=fake_search,
            store=store,
            events=EventBus(),
            run_check=RecordingRunCheck(),
        )
        return TestClient(app)

    yield make
    for s in stores:
        s.close()


def post(client, ip: str | None = None, forwarded: str | None = None):
    """ip: the address the trusted proxy appended, after a client-supplied (forgeable) entry."""
    if forwarded is None and ip:
        forwarded = f"6.6.6.6, {ip}"
    headers = {"X-Forwarded-For": forwarded} if forwarded else {}
    return client.post("/api/checks", json={"text": GOOD_TEXT}, headers=headers)


def test_sixth_request_in_window_is_429(make_client):
    with make_client(rate_limit_per_ip=5) as client:
        for _ in range(5):
            assert post(client).status_code == 202
        r = post(client)
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
    assert "wait" in r.json()["detail"]


def test_daily_cap_is_429(make_client):
    with make_client(daily_check_cap=2) as client:
        assert post(client, "1.1.1.1").status_code == 202
        assert post(client, "2.2.2.2").status_code == 202
        r = post(client, "3.3.3.3")
    assert r.status_code == 429
    assert "today's free limit" in r.json()["detail"]
    assert int(r.headers["Retry-After"]) > 0


def test_validation_rejected_requests_not_counted(make_client):
    with make_client(rate_limit_per_ip=2, daily_check_cap=2) as client:
        for _ in range(5):
            assert client.post("/api/checks", json={"text": "short"}).status_code == 400
        assert post(client).status_code == 202
        assert post(client).status_code == 202


def test_x_forwarded_for_identifies_client(make_client):
    with make_client(rate_limit_per_ip=1) as client:
        assert post(client, "1.1.1.1").status_code == 202
        assert post(client, "1.1.1.1").status_code == 429
        assert post(client, "2.2.2.2").status_code == 202


def test_forged_leading_x_forwarded_for_entries_do_not_change_the_key(make_client):
    with make_client(rate_limit_per_ip=1) as client:
        assert post(client, forwarded="1.1.1.1").status_code == 202
        assert post(client, forwarded="2.2.2.2, 1.1.1.1").status_code == 429
        assert post(client, forwarded="3.3.3.3, 4.4.4.4, 1.1.1.1").status_code == 429


def test_zero_trusted_hops_ignores_x_forwarded_for(make_client):
    with make_client(rate_limit_per_ip=1, trusted_proxy_hops=0) as client:
        assert post(client, "1.1.1.1").status_code == 202
        assert post(client, "2.2.2.2").status_code == 429  # same peer: the test client


def _request(*forwarded: str, peer: str = "9.9.9.9") -> Request:
    headers = [(b"x-forwarded-for", f.encode()) for f in forwarded]
    return Request({"type": "http", "headers": headers, "client": (peer, 1234)})


@pytest.mark.parametrize(
    "forwarded, hops, expected",
    [
        (["1.1.1.1"], 1, "1.1.1.1"),
        (["6.6.6.6, 1.1.1.1"], 1, "1.1.1.1"),
        (["6.6.6.6, 1.1.1.1, 10.0.0.2"], 2, "1.1.1.1"),
        (["1.1.1.1"], 3, "1.1.1.1"),  # fewer entries than hops: the leftmost
        (["6.6.6.6", "1.1.1.1"], 1, "1.1.1.1"),  # several headers are one list
        (["6.6.6.6, 1.1.1.1:51234"], 1, "1.1.1.1"),
        (["[2001:db8::1]:443"], 1, "2001:db8::1"),
        (["2001:db8::1"], 1, "2001:db8::1"),
        (["1.1.1.1"], 0, "9.9.9.9"),
        ([" , "], 1, "9.9.9.9"),
        ([], 1, "9.9.9.9"),
    ],
)
def test_client_ip_counts_trusted_hops_from_the_right(forwarded, hops, expected):
    assert client_ip(_request(*forwarded), hops) == expected


def test_sliding_window_expires_old_hits():
    now = [1000.0]
    window = SlidingWindow(limit=2, window_s=60, clock=lambda: now[0])
    window.hit("a")
    now[0] += 30
    window.hit("a")
    assert window.retry_after("a") == 30
    assert window.retry_after("b") is None
    now[0] += 31
    assert window.retry_after("a") is None


def test_seconds_until_utc_midnight():
    assert seconds_until_utc_midnight(datetime(2026, 10, 14, 23, 59, 0, tzinfo=UTC)) == 60


async def test_concurrent_acquires_cannot_exceed_limits(tmp_path):
    store = Store(tmp_path)
    limiter = RateLimiter(store, per_ip=2, window_s=60, daily_cap=3)
    same_ip = await asyncio.gather(*(limiter.acquire("1.1.1.1") for _ in range(5)),
                                   return_exceptions=True)  # fmt: skip
    assert sum(r is None for r in same_ip) == 2
    others = await asyncio.gather(*(limiter.acquire(f"9.9.9.{i}") for i in range(5)),
                                  return_exceptions=True)  # fmt: skip
    assert sum(r is None for r in others) == 1  # daily cap 3 in total
    assert await store.daily_count() == 3
    store.close()


async def test_daily_cap_rejection_does_not_use_the_ip_window(tmp_path):
    store = Store(tmp_path)
    limiter = RateLimiter(store, per_ip=1, window_s=60, daily_cap=0)
    for _ in range(3):
        with pytest.raises(RateLimitExceeded, match="today's free limit"):
            await limiter.acquire("1.1.1.1")
    assert limiter.window.retry_after("1.1.1.1") is None
    store.close()


def test_sliding_window_sweeps_expired_keys():
    now = [0.0]
    window = SlidingWindow(limit=1, window_s=10, clock=lambda: now[0])
    for i in range(SWEEP_KEYS):
        window.hit(f"ip{i}")
    now[0] += 11
    window.hit("fresh")
    assert set(window._hits) == {"fresh"}
