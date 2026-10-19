import asyncio
import json
import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse

from .config import Settings, get_settings, startup_problems
from .events import TERMINAL, EventBus
from .llm import LLM
from .pipeline import orchestrator
from .pipeline.orchestrator import Deps
from .ratelimit import RateLimiter, RateLimitExceeded, client_ip
from .schemas import CheckRecord, CheckRequest, validate_check_request
from .search import Search
from .store import Store, new_id, utc_now

log = logging.getLogger("verity")

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BACKEND_DIR.parent
EXAMPLES_PATH = BACKEND_DIR / "seed" / "examples.json"
# The frontend falls back to polling when the stream sends no message for 10 s, and SSE
# comment lines do not count as messages, so the keep-alive is a real (ignored) event.
KEEP_ALIVE_SECONDS = 5.0
PING = {"type": "ping"}
INTERRUPTED_MESSAGE = "The server restarted before this check finished. Please run it again."
SHUTDOWN_GRACE_SECONDS = 5.0

PLACEHOLDER_HTML = (
    "<!doctype html><html><head><meta charset='utf-8'><title>Verity</title></head>"
    "<body><h1>Verity</h1><p>The frontend has not been built yet. "
    "The API is available under /api.</p></body></html>"
)

RunCheck = Callable[[str, CheckRequest, Deps], Awaitable[None]]


APP_DIR = Path(__file__).resolve().parent


def _first_existing(*candidates: Path) -> Path:
    return next((c for c in candidates if c.exists()), candidates[-1])


def _static_dir() -> Path:
    """STATIC_DIR env, else app/static (Docker image), else frontend/dist (local dev)."""
    if env := os.environ.get("STATIC_DIR"):
        return Path(env)
    return _first_existing(APP_DIR / "static", REPO_DIR / "frontend" / "dist")


def _benchmark_path() -> Path:
    """BENCHMARK_PATH env, else /app/eval/... (Docker image), else repo eval/... (local dev)."""
    if env := os.environ.get("BENCHMARK_PATH"):
        return Path(env)
    rel = Path("eval") / "results" / "latest.json"
    return _first_existing(BACKEND_DIR / rel, REPO_DIR / rel)


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


def _final_event(record: CheckRecord) -> dict:
    if record.status == "error":
        return {"type": "error", "message": record.error or "The check failed."}
    return {"type": "done", "totals": record.totals}


async def _guarded(coro: Awaitable[None], state: Any, check_id: str) -> None:
    """Run a check; if it crashes outside its own error handling, still finish the record so
    clients waiting on the event stream get an error instead of keep-alives forever."""
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except Exception:
        log.exception("check_id=%s crashed", check_id)
        try:
            record = await state.store.get_check(check_id)
            if record is not None and record.status not in TERMINAL:
                record.status = "error"
                record.error = orchestrator.GENERIC_MESSAGE
                await state.store.save_check(record)
        finally:
            state.events.emit(check_id, "error", message=orchestrator.GENERIC_MESSAGE)


def create_app(
    settings: Settings | None = None,
    *,
    llm: Any = None,
    search: Any = None,
    store: Store | None = None,
    events: EventBus | None = None,
    run_check: RunCheck | None = None,
) -> FastAPI:
    """Build the app. Tests inject fakes; production builds real clients in the lifespan."""
    injected = any(x is not None for x in (llm, search, store, events, run_check))

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        s = settings or get_settings()
        logging.basicConfig(
            level=s.log_level.upper(),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        if not injected:
            problems = startup_problems(s)
            if problems:
                raise RuntimeError("Verity cannot start: " + "; ".join(problems))
        st = store or Store(s.data_dir)
        app.state.settings = s
        app.state.store = st
        app.state.events = events or EventBus()
        app.state.limiter = RateLimiter(
            st,
            per_ip=s.rate_limit_per_ip,
            window_s=s.rate_limit_window_seconds,
            daily_cap=s.daily_check_cap,
        )
        app.state.deps = Deps(
            settings=s,
            llm=llm
            or LLM(
                s.nebius_base_url,
                s.nebius_api_key,
                modes=s.structured_modes,
                thinking=s.thinking,
            ),
            search=search
            or Search(
                s.tavily_api_key,
                st,
                depth=s.tavily_search_depth,
                max_results=s.tavily_max_results,
                raw_content=s.tavily_raw_content,
                chunks_per_source=s.tavily_chunks_per_source,
                cache_hours=s.search_cache_hours,
                max_input_chars=s.max_input_chars,
            ),
            store=st,
            events=app.state.events,
            semaphore=asyncio.Semaphore(s.max_concurrent_checks),
        )
        app.state.run_check = run_check or orchestrator.run_check
        app.state.tasks = set()  # strong references, so running checks are not GC'd
        stale = await st.fail_unfinished(INTERRUPTED_MESSAGE)
        if stale:
            log.warning("marked %d unfinished checks from a previous run as failed", len(stale))
        log.info("Verity started (fast=%s, judge=%s)", s.model_fast, s.model_judge)
        yield
        tasks = list(app.state.tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=SHUTDOWN_GRACE_SECONDS)
            await st.fail_unfinished(INTERRUPTED_MESSAGE)
        if store is None:
            st.close()

    app = FastAPI(title="Verity", lifespan=lifespan)

    @app.exception_handler(RequestValidationError)
    async def bad_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"detail": "Invalid request body."}, status_code=400)

    @app.get("/api/health")
    async def health(request: Request) -> dict:
        s: Settings = request.app.state.settings
        return {
            "ok": True,
            "models": {"fast": s.model_fast, "judge": s.model_judge},
            "version": os.environ.get("GIT_SHA", "dev"),
        }

    @app.post("/api/checks", status_code=202)
    async def create_check(body: CheckRequest, request: Request):
        state = request.app.state
        try:
            req = validate_check_request(body, state.settings.max_input_chars)
        except ValueError as e:
            return JSONResponse({"detail": str(e)}, status_code=400)

        ip = client_ip(request)
        try:
            await state.limiter.acquire(ip)
        except RateLimitExceeded as e:
            return JSONResponse(
                {"detail": e.message},
                status_code=429,
                headers={"Retry-After": str(e.retry_after)},
            )

        record = CheckRecord(
            id=new_id(),
            created_at=utc_now().isoformat(),
            status="queued",
            input_type="text" if req.text else "url",
            input_preview=(req.text or req.url or "")[:300],
        )
        await state.store.save_check(record)

        coro = state.run_check(record.id, req, state.deps)
        task = asyncio.create_task(_guarded(coro, state, record.id))
        state.tasks.add(task)
        task.add_done_callback(state.tasks.discard)
        log.info("check %s queued (%s)", record.id, record.input_type)
        return {"id": record.id}

    @app.get("/api/checks/{check_id}")
    async def get_check(check_id: str, request: Request):
        record = await request.app.state.store.get_check(check_id)
        if record is None:
            return JSONResponse({"detail": "Check not found."}, status_code=404)
        return record

    @app.get("/api/checks/{check_id}/events")
    async def check_events(check_id: str, request: Request):
        state = request.app.state
        if await state.store.get_check(check_id) is None:
            return JSONResponse({"detail": "Check not found."}, status_code=404)

        async def stream() -> AsyncIterator[str]:
            bus: EventBus = state.events
            # Subscribe before reading the record so no event is missed, and take the history
            # in the same step (no await in between) so none is sent twice.
            queue = bus.subscribe(check_id)
            past = bus.history(check_id)
            try:
                record = await state.store.get_check(check_id)
                if record is None:
                    return
                yield _sse({"type": "snapshot", "record": record.model_dump()})
                if record.status in TERMINAL:
                    yield _sse(_final_event(record))
                    return
                # Replay what happened before we subscribed: the record holds no live progress
                # (stages, model calls) until claims finish.
                for event in past:
                    yield _sse(event)
                    if event.get("type") in TERMINAL:
                        return
                while True:
                    try:
                        event = await asyncio.wait_for(queue.get(), KEEP_ALIVE_SECONDS)
                    except TimeoutError:
                        yield _sse(PING)
                        continue
                    yield _sse(event)
                    if event.get("type") in TERMINAL:
                        return
            finally:
                bus.unsubscribe(check_id, queue)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/examples")
    async def examples():
        return json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))

    @app.get("/api/benchmark")
    async def benchmark():
        path = _benchmark_path()
        if not path.is_file():
            return JSONResponse({"detail": "No benchmark results yet."}, status_code=404)
        return json.loads(path.read_text(encoding="utf-8"))

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse({"detail": "Not found."}, status_code=404)
        dist = _static_dir().resolve()
        index = dist / "index.html"
        if not index.is_file():
            return HTMLResponse(PLACEHOLDER_HTML)
        candidate = (dist / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(dist):
            return FileResponse(candidate)
        return FileResponse(index, media_type="text/html")

    return app


app = create_app()
