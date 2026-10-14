import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.events import EventBus
from app.main import create_app
from app.schemas import CheckRecord
from app.store import Store

GOOD_TEXT = "The Great Wall of China is visible from space with the naked eye."


def make_settings(tmp_path, **kw) -> Settings:
    base = dict(
        nebius_api_key="k",
        tavily_api_key="t",
        model_fast="nvidia/fast",
        model_judge="nvidia/judge",
        data_dir=str(tmp_path),
        max_input_chars=200,
    )
    return Settings(_env_file=None, **(base | kw))


class RecordingRunCheck:
    def __init__(self):
        self.calls: list[tuple] = []

    def __call__(self, check_id, req, deps):
        self.calls.append((check_id, req, deps))  # recorded when the task is created
        return self._noop()

    async def _noop(self) -> None:
        return None


@pytest.fixture
def env(tmp_path, fake_llm, fake_search):
    store = Store(tmp_path)
    run_check = RecordingRunCheck()
    app = create_app(
        make_settings(tmp_path),
        llm=fake_llm,
        search=fake_search,
        store=store,
        events=EventBus(),
        run_check=run_check,
    )
    with TestClient(app) as client:
        yield client, run_check, store, fake_llm
    store.close()


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"text": GOOD_TEXT, "url": "https://example.com"},
        {"text": "too short"},
        {"text": "a" * 201},
        {"url": "example.com/page"},
        {"url": "ftp://example.com/page"},
        {"url": "https://example.com/" + "a" * 2000},
        {"text": 123},
    ],
)
def test_bad_input_returns_400(env, body):
    client, run_check, _, _ = env
    r = client.post("/api/checks", json=body)
    assert r.status_code == 400
    assert r.json()["detail"]
    assert run_check.calls == []


def test_non_json_body_returns_400(env):
    client, _, _, _ = env
    r = client.post("/api/checks", content="nope", headers={"content-type": "application/json"})
    assert r.status_code == 400


def test_valid_text_returns_202_and_starts_check(env):
    client, run_check, store, _ = env
    r = client.post("/api/checks", json={"text": f"  {GOOD_TEXT}  "})
    assert r.status_code == 202
    check_id = r.json()["id"]
    assert len(run_check.calls) == 1
    called_id, req, deps = run_check.calls[0]
    assert called_id == check_id and req.text == GOOD_TEXT and deps.store is store

    record = client.get(f"/api/checks/{check_id}").json()
    assert record["status"] == "queued"
    assert record["input_type"] == "text"
    assert record["input_preview"] == GOOD_TEXT


def test_valid_url_returns_202(env):
    client, run_check, _, _ = env
    r = client.post("/api/checks", json={"url": "https://example.com/article"})
    assert r.status_code == 202
    assert run_check.calls[0][1].url == "https://example.com/article"
    assert client.get(f"/api/checks/{r.json()['id']}").json()["input_type"] == "url"


def test_unknown_check_returns_404(env):
    client, _, _, _ = env
    assert client.get("/api/checks/nope").status_code == 404
    assert client.get("/api/checks/nope/events").status_code == 404


def test_health_makes_no_llm_call(env):
    client, _, _, fake_llm = env
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["models"] == {"fast": "nvidia/fast", "judge": "nvidia/judge"}
    assert "version" in body
    assert fake_llm.calls == []


def test_spa_fallback_returns_html(env, tmp_path, monkeypatch):
    client, _, _, _ = env
    r = client.get("/c/abc")
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>INDEX</html>")
    (dist / "assets" / "app.js").write_text("console.log(1)")
    monkeypatch.setenv("STATIC_DIR", str(dist))
    assert "INDEX" in client.get("/c/abc").text
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert "INDEX" in client.get("/../../etc/passwd").text


def test_unknown_api_path_is_404_not_html(env):
    client, _, _, _ = env
    assert client.get("/api/nope").status_code == 404


def test_examples(env):
    client, _, _, _ = env
    examples = client.get("/api/examples").json()
    assert len(examples) == 6
    assert all(set(e) == {"title", "type", "value"} for e in examples)


def test_benchmark(env, tmp_path, monkeypatch):
    client, _, _, _ = env
    monkeypatch.setenv("BENCHMARK_PATH", str(tmp_path / "missing.json"))
    assert client.get("/api/benchmark").status_code == 404
    path = tmp_path / "latest.json"
    path.write_text('{"accuracy": 0.9}')
    monkeypatch.setenv("BENCHMARK_PATH", str(path))
    assert client.get("/api/benchmark").json() == {"accuracy": 0.9}


def _read_events(client, check_id) -> list[dict]:
    events = []
    with client.stream("GET", f"/api/checks/{check_id}/events") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["cache-control"] == "no-cache"
        assert r.headers["x-accel-buffering"] == "no"
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(json.loads(line[6:]))
    return events


def _record(status: str, **kw) -> CheckRecord:
    return CheckRecord(
        id="abc123",
        created_at="2026-10-14T00:00:00+00:00",
        status=status,
        input_type="text",
        input_preview="x",
        **kw,
    )


def test_sse_finished_check_sends_snapshot_then_done(env):
    client, _, store, _ = env
    client.portal.call(store.save_check, _record("done", totals={"model_calls": 4}))
    events = _read_events(client, "abc123")
    assert [e["type"] for e in events] == ["snapshot", "done"]
    assert events[0]["record"]["id"] == "abc123"
    assert events[1]["totals"] == {"model_calls": 4}


def test_sse_failed_check_sends_error(env):
    client, _, store, _ = env
    client.portal.call(store.save_check, _record("error", error="Something went wrong."))
    events = _read_events(client, "abc123")
    assert events[-1] == {"type": "error", "message": "Something went wrong."}


def test_sse_running_check_streams_live_events(tmp_path, fake_llm, fake_search):
    store, bus = Store(tmp_path), EventBus()

    async def run_check(check_id, req, deps):
        deps.events.emit(check_id, "claims_found", claims=[], skipped=0, language="en")
        deps.events.emit(check_id, "done", totals={"model_calls": 1})

    app = create_app(
        make_settings(tmp_path),
        llm=fake_llm,
        search=fake_search,
        store=store,
        events=bus,
        run_check=run_check,
    )
    with TestClient(app) as client:
        client.portal.call(store.save_check, _record("running"))
        original_subscribe = bus.subscribe
        tasks = []

        def subscribe_then_run(check_id):
            q = original_subscribe(check_id)
            tasks.append(
                asyncio.get_running_loop().create_task(run_check(check_id, None, app.state.deps))
            )
            return q

        bus.subscribe = subscribe_then_run
        events = _read_events(client, "abc123")
    store.close()
    assert [e["type"] for e in events] == ["snapshot", "claims_found", "done"]
    assert bus._subscribers == {}


def test_import_safe_without_keys(monkeypatch):
    for key in ("NEBIUS_API_KEY", "TAVILY_API_KEY", "MODEL_FAST", "MODEL_JUDGE"):
        monkeypatch.delenv(key, raising=False)
    app = create_app(Settings(_env_file=None))
    with pytest.raises(RuntimeError, match="NEBIUS_API_KEY"):
        with TestClient(app):
            pass
