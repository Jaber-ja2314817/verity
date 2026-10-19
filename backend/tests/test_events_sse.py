import asyncio

from fastapi.testclient import TestClient

from app import main
from app.events import EventBus
from app.main import INTERRUPTED_MESSAGE, create_app
from app.pipeline.orchestrator import GENERIC_MESSAGE
from app.store import Store
from tests.test_api import GOOD_TEXT, _read_events, _record, make_settings


def make_app(tmp_path, fake_llm, fake_search, run_check=None, store=None, bus=None):
    store = store or Store(tmp_path)
    bus = bus or EventBus()

    async def noop(check_id, req, deps):
        return None

    app = create_app(
        make_settings(tmp_path),
        llm=fake_llm,
        search=fake_search,
        store=store,
        events=bus,
        run_check=run_check or noop,
    )
    return app, store, bus


def test_event_bus_keeps_bounded_history():
    bus = EventBus(max_checks=2)
    for cid in ("a", "b", "c"):
        bus.emit(cid, "ingest_done", chars=1)
    assert bus.history("a") == []
    assert [e["type"] for e in bus.history("c")] == ["ingest_done"]


def test_sse_replays_earlier_events_then_streams_live(tmp_path, fake_llm, fake_search):
    app, store, bus = make_app(tmp_path, fake_llm, fake_search)
    with TestClient(app) as client:
        client.portal.call(store.save_check, _record("running"))
        bus.emit("abc123", "ingest_done", chars=10)
        bus.emit("abc123", "model_call", step="extract_claims")
        original = bus.subscribe

        def subscribe_then_finish(check_id):
            q = original(check_id)
            asyncio.get_running_loop().call_soon(lambda: bus.emit(check_id, "done", totals={}))
            return q

        bus.subscribe = subscribe_then_finish
        events = _read_events(client, "abc123")
    store.close()
    assert [e["type"] for e in events] == ["snapshot", "ingest_done", "model_call", "done"]


def test_sse_sends_ping_events_while_idle(tmp_path, fake_llm, fake_search, monkeypatch):
    monkeypatch.setattr(main, "KEEP_ALIVE_SECONDS", 0.01)
    app, store, bus = make_app(tmp_path, fake_llm, fake_search)
    with TestClient(app) as client:
        client.portal.call(store.save_check, _record("running"))
        original = bus.subscribe

        def subscribe_then_finish_later(check_id):
            q = original(check_id)
            done = lambda: bus.emit(check_id, "done", totals={})  # noqa: E731
            asyncio.get_running_loop().call_later(0.1, done)
            return q

        bus.subscribe = subscribe_then_finish_later
        events = _read_events(client, "abc123")
    store.close()
    types = [e["type"] for e in events]
    assert types[0] == "snapshot" and types[-1] == "done"
    assert "ping" in types


def test_crashed_run_check_finishes_record_with_error(tmp_path, fake_llm, fake_search):
    async def crash(check_id, req, deps):
        raise RuntimeError("store exploded")

    app, store, bus = make_app(tmp_path, fake_llm, fake_search, run_check=crash)
    with TestClient(app) as client:
        check_id = client.post("/api/checks", json={"text": GOOD_TEXT}).json()["id"]
        client.portal.call(asyncio.sleep, 0.05)
        record = client.get(f"/api/checks/{check_id}").json()
        events = _read_events(client, check_id)
    store.close()
    assert (record["status"], record["error"]) == ("error", GENERIC_MESSAGE)
    assert bus.history(check_id)[-1] == {"type": "error", "message": GENERIC_MESSAGE}
    assert events[-1] == {"type": "error", "message": GENERIC_MESSAGE}


def test_startup_fails_checks_left_running_by_previous_process(tmp_path, fake_llm, fake_search):
    store = Store(tmp_path)
    app, _, _ = make_app(tmp_path, fake_llm, fake_search, store=store)
    asyncio.run(store.save_check(_record("running")))
    with TestClient(app) as client:
        record = client.get("/api/checks/abc123").json()
    store.close()
    assert (record["status"], record["error"]) == ("error", INTERRUPTED_MESSAGE)


def test_shutdown_cancels_running_checks_and_fails_them(tmp_path, fake_llm, fake_search):
    started = []

    async def hang(check_id, req, deps):
        started.append(check_id)
        await asyncio.sleep(3600)

    app, store, _ = make_app(tmp_path, fake_llm, fake_search, run_check=hang)
    with TestClient(app) as client:
        check_id = client.post("/api/checks", json={"text": GOOD_TEXT}).json()["id"]
        client.portal.call(asyncio.sleep, 0.01)
        assert started == [check_id]
    record = asyncio.run(store.get_check(check_id))
    store.close()
    assert record.status == "error" and record.error == INTERRUPTED_MESSAGE
