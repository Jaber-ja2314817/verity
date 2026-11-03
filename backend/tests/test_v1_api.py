import pytest
from fastapi.testclient import TestClient
from test_api import GOOD_TEXT, make_settings

from app.apikeys import KEY_PREFIX, bearer_token, hash_key, is_admin, new_key
from app.events import EventBus
from app.main import create_app
from app.schemas import (
    ClaimResult,
    Evidence,
    ExtractedClaim,
    JuryResult,
    PlannedQuery,
    Source,
    Verdict,
)
from app.store import Store

ADMIN = "a" * 32
ADMIN_HEADERS = {"Authorization": f"Bearer {ADMIN}"}


def verdict(label="FALSE", conf=91, cited=(1,)) -> Verdict:
    return Verdict(
        label=label, confidence=conf, explanation="It is not.", cited_source_ids=list(cited)
    )


def source(i: int, url: str) -> Source:
    return Source(id=i, url=url, title=f"T{i}", domain=url.split("/")[2], content="c",
                  published_date="2026-10-30", reliability="high")  # fmt: skip


async def finish(check_id, req, deps):
    """Stands in for the pipeline: completes the check with one claim and two sources."""
    record = await deps.store.get_check(check_id)
    v = verdict()
    evidence = [
        Evidence(source=source(1, "https://a.com/x"), stance="refutes", quote="Q one.",
                 quote_verified=True, note="n"),
        Evidence(source=source(2, "https://b.org/y"), stance="irrelevant", quote="",
                 quote_verified=False, note=""),
    ]  # fmt: skip
    record.claims = [
        ClaimResult(
            id=1, text="Wall visible", queries=[PlannedQuery(query="q", intent="neutral")],
            evidence=evidence, search="news",
            result=JuryResult(draft=v, jury=v, agreed=True, debated=False, final=v),
        )  # fmt: skip
    ]
    record.language = "en"
    record.status = "done"
    record.totals = {"duration_s": 4.2, "cost_usd": 0.01}
    record.skipped_claims = [
        ExtractedClaim(id=2, text="I love walls", checkworthy=False, reason="opinion")
    ]
    await deps.store.save_check(record)


class Recorder:
    def __init__(self):
        self.reqs = []

    async def __call__(self, check_id, req, deps):
        self.reqs.append(req)
        await finish(check_id, req, deps)


@pytest.fixture
def env(tmp_path, fake_llm, fake_search):
    store = Store(tmp_path)
    recorder = Recorder()

    def build(**kw):
        return create_app(
            make_settings(tmp_path, admin_secret=ADMIN, **kw),
            llm=fake_llm, search=fake_search, store=store, events=EventBus(), run_check=recorder,
        )  # fmt: skip

    yield build, store, recorder
    store.close()


def new_api_key(client: TestClient, **body) -> tuple[str, dict]:
    r = client.post("/api/admin/keys", json={"name": "Partner", **body}, headers=ADMIN_HEADERS)
    assert r.status_code == 201, r.text
    data = r.json()
    return data["key"], data


def auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


def post(client: TestClient, key: str, body: dict | None = None, **params):
    """POST /v1/checks; the default body is one valid claim."""
    body = {"text": GOOD_TEXT} if body is None else body
    return client.post("/v1/checks", params=params or None, json=body, headers=auth(key))


# ---- key helpers
def test_new_key_is_random_prefixed_and_hashed():
    a, ha = new_key()
    b, hb = new_key()
    assert a.startswith(KEY_PREFIX) and a != b and ha == hash_key(a) != hb
    assert len(a) > 40


def test_bearer_token_and_admin_check():
    assert bearer_token("Bearer abc") == "abc" and bearer_token("bearer abc") == "abc"
    assert bearer_token("Basic abc") is None and bearer_token("Bearer ") is None
    assert bearer_token(None) is None
    assert is_admin("Bearer s3cret", "s3cret")
    assert not is_admin("Bearer nope", "s3cret")
    assert not is_admin("Bearer ", "") and not is_admin(None, "s3cret")


# ---- admin endpoints
def test_admin_is_off_without_a_secret(tmp_path, fake_llm, fake_search):
    store = Store(tmp_path)
    # admin_secret="" explicitly: Settings also reads real environment variables, so an
    # ADMIN_SECRET exported in the developer's shell must not turn the endpoints on here.
    app = create_app(make_settings(tmp_path, admin_secret=""), llm=fake_llm, search=fake_search,
                     store=store, events=EventBus(), run_check=Recorder())  # fmt: skip
    with TestClient(app) as client:
        assert client.get("/api/admin/keys", headers=ADMIN_HEADERS).status_code == 404
    store.close()


def test_admin_rejects_wrong_secret_and_locks_out_guessing(env):
    build, *_ = env
    with TestClient(build()) as client:
        bad = {"Authorization": "Bearer " + "b" * 32}
        assert client.get("/api/admin/keys").status_code == 401
        for _ in range(9):
            assert client.get("/api/admin/keys", headers=bad).status_code == 401
        assert client.get("/api/admin/keys", headers=bad).status_code == 429
        assert client.get("/api/admin/keys", headers=ADMIN_HEADERS).status_code == 429  # locked


def test_admin_creates_lists_and_revokes_keys(env):
    build, store, _ = env
    with TestClient(build()) as client:
        key, created = new_api_key(client, name="News app", rate_per_minute=3, daily_quota=7)
        assert key.startswith("vrt_") and created["prefix"] == key[:10]
        assert (created["rate_per_minute"], created["daily_quota"]) == (3, 7)
        assert "key_hash" not in created

        listed = client.get("/api/admin/keys", headers=ADMIN_HEADERS).json()
        assert [k["name"] for k in listed] == ["News app"] and listed[0]["used_today"] == 0
        assert key not in str(listed) and hash_key(key) not in str(listed)

        assert client.delete(f"/api/admin/keys/{created['id']}", headers=ADMIN_HEADERS).json() == {
            "revoked": True, "id": created["id"],
        }  # fmt: skip
        again = client.delete(f"/api/admin/keys/{created['id']}", headers=ADMIN_HEADERS)
        assert again.status_code == 404
        assert client.get("/v1/usage", headers=auth(key)).status_code == 401  # revoked


def test_admin_uses_default_limits_from_settings(env):
    build, *_ = env
    with TestClient(build(api_default_rate_per_minute=4, api_default_daily_quota=9)) as client:
        _, created = new_api_key(client)
        assert (created["rate_per_minute"], created["daily_quota"]) == (4, 9)


# ---- authentication
def test_v1_requires_a_valid_key(env):
    build, *_ = env
    with TestClient(build()) as client:
        r = client.post("/v1/checks", json={"text": GOOD_TEXT})
        assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
        assert post(client, "vrt_wrong").status_code == 401
        basic = {"Authorization": "Basic xyz"}
        assert client.get("/v1/checks/abc", headers=basic).status_code == 401


# ---- creating and reading checks
def test_wait_true_returns_the_finished_check(env):
    build, _, recorder = env
    with TestClient(build()) as client:
        key, _ = new_api_key(client)
        r = post(client, key, {"text": GOOD_TEXT, "mode": "news"}, wait="true")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "done" and body["language"] == "en" and body["duration_s"] == 4.2
        [claim] = body["claims"]
        assert (claim["verdict"], claim["confidence"], claim["search"]) == ("FALSE", 91, "news")
        assert claim["models_agreed"] is True
        [src] = claim["sources"]  # the irrelevant source is not exposed
        assert src["url"] == "https://a.com/x" and src["quote"] == "Q one." and src["cited"] is True
        assert body["skipped_claims"] == [{"text": "I love walls", "reason": "opinion"}]
        assert "trace" not in body and "totals" not in body and "cost_usd" not in r.text
        assert recorder.reqs[0].mode == "news" and recorder.reqs[0].text == GOOD_TEXT


def test_without_wait_returns_202_and_the_check_can_be_polled(env):
    build, *_ = env
    with TestClient(build()) as client:
        key, _ = new_api_key(client)
        r = post(client, key)
        assert r.status_code == 202
        check_id = r.json()["id"]
        got = client.get(f"/v1/checks/{check_id}", headers=auth(key))
        assert got.status_code == 200 and got.json()["id"] == check_id
        assert got.json()["status"] in ("queued", "running", "done")


def test_a_key_cannot_read_another_keys_check_and_the_site_hides_it(env):
    build, *_ = env
    with TestClient(build()) as client:
        key_a, _ = new_api_key(client, name="A")
        key_b, _ = new_api_key(client, name="B")
        check_id = post(client, key_a, wait="true").json()["id"]
        assert client.get(f"/v1/checks/{check_id}", headers=auth(key_a)).status_code == 200
        assert client.get(f"/v1/checks/{check_id}", headers=auth(key_b)).status_code == 404
        assert client.get(f"/api/checks/{check_id}").status_code == 404
        assert client.get(f"/api/checks/{check_id}/events").status_code == 404


@pytest.mark.parametrize(
    "body",
    [{}, {"text": GOOD_TEXT, "url": "https://example.com"}, {"text": "too short"},
     {"url": "example.com/page"}, {"text": GOOD_TEXT, "mode": "bogus"}],
)  # fmt: skip
def test_bad_requests_are_400_and_not_counted(env, body):
    build, *_ = env
    with TestClient(build()) as client:
        key, _ = new_api_key(client)
        assert post(client, key, body).status_code == 400
        assert client.get("/v1/usage", headers=auth(key)).json()["used_today"] == 0


# ---- limits
def test_per_minute_limit_gives_429_with_retry_after(env):
    build, *_ = env
    with TestClient(build()) as client:
        key, _ = new_api_key(client, rate_per_minute=1, daily_quota=50)
        assert post(client, key).status_code == 202
        r = post(client, key)
        assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1
        other, _ = new_api_key(client, name="Other", rate_per_minute=1)
        assert post(client, other).status_code == 202


def test_daily_quota_gives_429_and_usage_shows_it(env):
    build, *_ = env
    with TestClient(build()) as client:
        key, _ = new_api_key(client, rate_per_minute=100, daily_quota=2)
        for _ in range(2):
            assert post(client, key).status_code == 202
        r = post(client, key)
        assert r.status_code == 429 and "daily quota" in r.json()["detail"]
        usage = client.get("/v1/usage", headers=auth(key)).json()
        assert (usage["used_today"], usage["remaining_today"], usage["daily_quota"]) == (2, 0, 2)


def test_site_wide_daily_cap_applies_and_refunds_the_key(env):
    build, *_ = env
    with TestClient(build(daily_check_cap=1)) as client:
        key, _ = new_api_key(client, rate_per_minute=100, daily_quota=10)
        assert post(client, key).status_code == 202
        r = post(client, key)
        assert r.status_code == 503 and int(r.headers["retry-after"]) >= 1
        assert client.get("/v1/usage", headers=auth(key)).json()["used_today"] == 1  # refunded


def test_v1_docs_are_served_and_list_only_the_public_endpoints(env):
    build, *_ = env
    with TestClient(build()) as client:
        assert client.get("/v1/docs").status_code == 200
        paths = client.get("/v1/openapi.json").json()["paths"]
        assert set(paths) == {"/checks", "/checks/{check_id}", "/usage"}
