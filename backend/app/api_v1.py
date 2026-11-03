"""The public Verity API (mounted at /v1) and the admin endpoints that manage its keys.

Both are built by factories that get the main app's state through `get_state()`, because a
mounted sub-app does not share app.state with the app it is mounted in.
"""

import asyncio
import time
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from .apikeys import LISTED_PREFIX_CHARS, ApiKey, hash_key, is_admin, new_key
from .pipeline.evidence import usable
from .ratelimit import DAILY_CAP_MESSAGE, SlidingWindow, client_ip, seconds_until_utc_midnight
from .schemas import (
    CheckRecord,
    CheckRequest,
    Label,
    Reliability,
    SearchMode,
    SearchRoute,
    Stance,
    validate_check_request,
)
from .store import new_id, utc_now

WAIT_POLL_SECONDS = 0.5
ADMIN_FAILURES = 10  # wrong admin secrets per IP per window
ADMIN_WINDOW_SECONDS = 600
QUOTA_MESSAGE = "This API key has used its daily quota. It resets at 00:00 UTC."
INVALID_KEY_MESSAGE = "Missing or invalid API key. Send it as 'Authorization: Bearer vrt_...'."
DESCRIPTION = """
Check claims, headlines and articles against the web and the news.

Send `Authorization: Bearer <your API key>` with every request.

**Serverless hosts:** use `?wait=true` there. Without it the check runs in the background after
the response, which a serverless host may pause.
"""


# ---- response shapes (the stable public contract; the internal record can change freely) ----
class V1Source(BaseModel):
    id: int
    url: str
    title: str
    domain: str
    published_date: str | None = None
    reliability: Reliability = "unknown"
    stance: Stance
    quote: str = Field(description="Sentence copied word for word from the source (verified)")
    cited: bool = Field(description="The verdict relied on this source")


class V1Claim(BaseModel):
    id: int
    text: str
    verdict: Label
    confidence: int = Field(ge=0, le=100, description="0-100")
    explanation: str
    models_agreed: bool = Field(description="Both independent models reached the same verdict")
    search: SearchRoute = Field(description="Where the sources came from: web, news or mixed")
    sources: list[V1Source]


class V1SkippedClaim(BaseModel):
    text: str
    reason: str


class V1Check(BaseModel):
    id: str
    status: str = Field(description="queued, running, done or error")
    created_at: str
    language: str | None = None
    error: str | None = None
    duration_s: float | None = None
    claims: list[V1Claim] = []
    skipped_claims: list[V1SkippedClaim] = []


class V1CheckRequest(BaseModel):
    text: str | None = Field(
        default=None, description="A claim, headline or article text. Send text or url, not both."
    )
    url: str | None = Field(default=None, description="Link to an article to check")
    mode: SearchMode = Field(
        default="auto",
        description="auto: news search for recent events, web for settled facts; "
        "news: news first; web: web search only",
    )


class V1Usage(BaseModel):
    key_id: str
    name: str
    rate_per_minute: int
    daily_quota: int
    used_today: int
    remaining_today: int


def to_v1(record: CheckRecord) -> V1Check:
    claims = []
    for c in sorted(record.claims, key=lambda c: c.id):
        final = c.result.final
        cited = set(final.cited_source_ids)
        claims.append(
            V1Claim(
                id=c.id,
                text=c.text,
                verdict=final.label,
                confidence=final.confidence,
                explanation=final.explanation,
                models_agreed=c.result.agreed,
                search=c.search,
                sources=[
                    V1Source(
                        id=e.source.id,
                        url=e.source.url,
                        title=e.source.title,
                        domain=e.source.domain,
                        published_date=e.source.published_date,
                        reliability=e.source.reliability,
                        stance=e.stance,
                        quote=e.quote,
                        cited=e.source.id in cited,
                    )
                    for e in usable(c.evidence)
                ],
            )
        )
    duration = record.totals.get("duration_s")
    return V1Check(
        id=record.id,
        status=record.status,
        created_at=record.created_at,
        language=record.language,
        error=record.error,
        duration_s=duration if isinstance(duration, int | float) else None,
        claims=claims,
        skipped_claims=[
            V1SkippedClaim(text=s.text, reason=s.reason) for s in record.skipped_claims
        ],
    )


async def _wait_until_finished(store: Any, check_id: str, seconds: float) -> None:
    """Poll the store (not the in-process event bus), so it works whichever instance runs it."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        record = await store.get_check(check_id)
        if record is None or record.status in ("done", "error"):
            return
        await asyncio.sleep(WAIT_POLL_SECONDS)


# ---- the public API ----
def create_v1_app(
    get_state: Callable[[], Any], start: Callable[[Any, CheckRecord, CheckRequest], None]
) -> FastAPI:
    api = FastAPI(title="Verity API", version="1.0", description=DESCRIPTION)
    bearer = HTTPBearer(auto_error=False, description="Your Verity API key (vrt_...)")
    windows: dict[str, SlidingWindow] = {}  # per key, in memory (per server instance)

    @api.exception_handler(RequestValidationError)
    async def bad_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse({"detail": "Invalid request body."}, status_code=400)

    async def current_key(
        creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ) -> ApiKey:
        if creds is None or not creds.credentials:
            raise HTTPException(401, INVALID_KEY_MESSAGE, headers={"WWW-Authenticate": "Bearer"})
        key = await get_state().store.get_api_key_by_hash(hash_key(creds.credentials))
        if key is None or key.revoked_at is not None:
            raise HTTPException(401, INVALID_KEY_MESSAGE, headers={"WWW-Authenticate": "Bearer"})
        return key

    def window_for(key: ApiKey) -> SlidingWindow:
        win = windows.get(key.id)
        if win is None or win.limit != key.rate_per_minute:
            win = windows[key.id] = SlidingWindow(key.rate_per_minute, 60)
        return win

    @api.post(
        "/checks",
        status_code=202,
        response_model=V1Check,
        summary="Check a claim, headline or article",
        responses={200: {"description": "Finished (when wait=true and the check completed)"}},
    )
    async def create_check(
        body: V1CheckRequest,
        response: Response,
        key: Annotated[ApiKey, Depends(current_key)],
        wait: bool = False,
    ):
        """Starts a check. Returns 202 with the check `id` to poll at `GET /v1/checks/{id}`.
        With `wait=true` the request holds until the verdict is ready (up to about two
        minutes) and returns 200 with the full result; if it takes longer you get 202 and
        poll as usual."""
        state = get_state()
        try:
            req = validate_check_request(
                CheckRequest(text=body.text, url=body.url, mode=body.mode),
                state.settings.max_input_chars,
            )
        except ValueError as e:
            raise HTTPException(400, str(e)) from e

        win = window_for(key)
        retry = win.retry_after(key.id)
        if retry is not None:
            raise HTTPException(
                429,
                f"Rate limit: {key.rate_per_minute} checks per minute for this key.",
                headers={"Retry-After": str(retry)},
            )
        win.hit(key.id)
        admitted = False
        try:
            if not await state.store.try_increment_key_daily(key.id, key.daily_quota):
                raise HTTPException(
                    429, QUOTA_MESSAGE,
                    headers={"Retry-After": str(seconds_until_utc_midnight())},
                )  # fmt: skip
            if not await state.store.try_increment_daily(state.settings.daily_check_cap):
                await state.store.refund_key_daily(key.id)  # not this key's fault
                raise HTTPException(
                    503, DAILY_CAP_MESSAGE,
                    headers={"Retry-After": str(seconds_until_utc_midnight())},
                )  # fmt: skip
            admitted = True
        finally:
            if not admitted:
                win.undo(key.id)

        submitted = req.text or req.url or ""
        record = CheckRecord(
            id=new_id(),
            created_at=utc_now().isoformat(),
            status="queued",
            input_type="text" if req.text else "url",
            input_preview=submitted[:300],
            input=submitted,
            api_key_id=key.id,
        )
        await state.store.save_check(record)
        start(state, record, req)
        if wait:
            await _wait_until_finished(state.store, record.id, state.settings.api_wait_seconds)
        fresh = await state.store.get_check(record.id) or record
        response.status_code = 200 if fresh.status in ("done", "error") else 202
        return to_v1(fresh)

    @api.get("/checks/{check_id}", response_model=V1Check, summary="Get a check")
    async def get_check(check_id: str, key: Annotated[ApiKey, Depends(current_key)]):
        """Status and, once `status` is `done`, the verdict for each claim. Only the key that
        started a check can read it."""
        record = await get_state().store.get_check(check_id)
        if record is None or record.api_key_id != key.id:
            raise HTTPException(404, "Check not found.")
        return to_v1(record)

    @api.get("/usage", response_model=V1Usage, summary="Your key's limits and usage today")
    async def usage(key: Annotated[ApiKey, Depends(current_key)]):
        used = await get_state().store.key_daily_count(key.id)
        return V1Usage(
            key_id=key.id,
            name=key.name,
            rate_per_minute=key.rate_per_minute,
            daily_quota=key.daily_quota,
            used_today=used,
            remaining_today=max(0, key.daily_quota - used),
        )

    return api


# ---- admin: manage keys (protected by ADMIN_SECRET) ----
class NewKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    rate_per_minute: int | None = Field(default=None, ge=1, le=600)
    daily_quota: int | None = Field(default=None, ge=1, le=100_000)


def create_admin_router(get_state: Callable[[], Any]) -> APIRouter:
    router = APIRouter(prefix="/api/admin", include_in_schema=False)
    failures = SlidingWindow(ADMIN_FAILURES, ADMIN_WINDOW_SECONDS)

    async def require_admin(request: Request) -> None:
        state = get_state()
        secret = state.settings.admin_secret
        if not secret:
            raise HTTPException(404, "Not found.")  # key management is switched off
        ip = client_ip(request, state.settings.trusted_proxy_hops)
        wait = failures.retry_after(ip)
        if wait is not None:
            raise HTTPException(429, "Too many attempts.", headers={"Retry-After": str(wait)})
        if not is_admin(request.headers.get("authorization"), secret):
            failures.hit(ip)
            raise HTTPException(401, "Invalid admin secret.")

    @router.post("/keys", status_code=201, dependencies=[Depends(require_admin)])
    async def create_key(body: NewKeyRequest):
        """Creates a key. The plaintext `key` is returned only here; store it now."""
        state = get_state()
        plaintext, key_hash = new_key()
        key = ApiKey(
            id=new_id(),
            name=body.name.strip(),
            prefix=plaintext[:LISTED_PREFIX_CHARS],
            created_at=utc_now().isoformat(),
            rate_per_minute=body.rate_per_minute or state.settings.api_default_rate_per_minute,
            daily_quota=body.daily_quota or state.settings.api_default_daily_quota,
        )
        await state.store.create_api_key(key, key_hash)
        return {**key.model_dump(), "key": plaintext}

    @router.get("/keys", dependencies=[Depends(require_admin)])
    async def list_keys():
        store = get_state().store
        keys = await store.list_api_keys()
        used = await asyncio.gather(*(store.key_daily_count(k.id) for k in keys))
        return [{**k.model_dump(), "used_today": n} for k, n in zip(keys, used, strict=True)]

    @router.delete("/keys/{key_id}", dependencies=[Depends(require_admin)])
    async def revoke_key(key_id: str):
        if not await get_state().store.revoke_api_key(key_id):
            raise HTTPException(404, "No active key with that id.")
        return {"revoked": True, "id": key_id}

    return router
