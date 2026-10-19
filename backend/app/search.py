import asyncio
import hashlib
import json
import logging
import re
from datetime import UTC, date, datetime
from email.utils import parsedate_to_datetime
from typing import Any, NotRequired, TypedDict
from urllib.parse import urlsplit

import httpx
from tavily.errors import TimeoutError as TavilyTimeoutError

from .reliability import domain_reliability
from .schemas import Reliability, Source
from .store import Store

log = logging.getLogger(__name__)

TAVILY_TIMEOUT_S = 30
SEARCH_RETRY_DELAY_S = 1.5
# asyncio.wait_for raises the builtin; the Tavily client raises its own on its timeout
TRANSIENT_SEARCH_ERRORS = (TimeoutError, TavilyTimeoutError, httpx.TransportError)
EXTRACT_FAILED = "Could not read that page. Try pasting the text instead."
RAW_CACHE_CHARS = 50_000  # cleaned page text kept per search result (cache size bound)
PASSAGE_SEP = "\n[...]\n"
# Soft ranking preference: added to Tavily's 0..1 relevance score.
TIER_BONUS: dict[Reliability, float] = {"high": 0.15, "medium": 0.05, "unknown": 0.0, "low": -0.15}


class RawResult(TypedDict):
    url: str
    title: str
    content: str  # Tavily's query-relevant snippet (or chunks with advanced depth)
    favicon: str | None
    score: float
    raw_content: NotRequired[str]  # cleaned full page text, when requested
    published_date: NotRequired[str | None]


class SearchUnavailable(RuntimeError):
    """Web search kept failing (timeouts/connection errors) after a retry."""


class IngestError(Exception):
    """User-facing ingest problem; str(e) is safe to show to users."""


def _host(url: str) -> str:
    host = (urlsplit(url.strip()).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


SECOND_LEVELS = frozenset({"co", "com", "org", "net", "gov", "ac", "edu", "gob", "gouv", "go"})


def _site(host: str) -> str:
    """Registrable domain for the per-domain cap: en.wikipedia.org -> wikipedia.org,
    news.bbc.co.uk -> bbc.co.uk."""
    labels = host.split(".")
    n = 3 if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in SECOND_LEVELS else 2
    return ".".join(labels[-n:])


def normalize_url(url: str) -> str:
    """Lowercase host, no www., no trailing slash, no query string or fragment."""
    path = urlsplit(url.strip()).path.rstrip("/")
    return f"{_host(url)}{path}"


def iso_date(value: object) -> str | None:
    """YYYY-MM-DD from an ISO or RFC 2822 date string, else None."""
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    try:
        if re.match(r"\d{4}-\d{2}-\d{2}", value):
            return datetime.fromisoformat(value[:10]).date().isoformat()
        return parsedate_to_datetime(value).date().isoformat()
    except (ValueError, TypeError, IndexError):
        return None


MONTHS = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}
_MONTH = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
# A date counts only right after an explicit label ("Published", "Updated on", "Last edited
# on", ...), so dates mentioned in the article body are not taken as the page date.
_DATE_LABEL = re.compile(
    r"\b(?:published|posted|updated|last (?:updated|modified|edited|reviewed)|date)\b"
    r"(?: on)?(?:[^\n\d]|\d{1,2}:\d{2}){0,25}?"  # gap may hold a time like "3:04 PM EDT, Mon"
    r"(?:(\d{4})-(\d{2})-(\d{2})"
    rf"|(\d{{1,2}}) {_MONTH},? (\d{{4}})"
    rf"|{_MONTH} (\d{{1,2}}),? (\d{{4}}))",
    re.IGNORECASE,
)
PAGE_DATE_HEAD_CHARS = 3000


def page_date(text: str, today: date | None = None) -> str | None:
    """YYYY-MM-DD of the first labelled date near the top of a page (or Wikipedia's "last
    edited on" footer), else None. Never guesses from unlabelled dates."""
    candidates = [text[:PAGE_DATE_HEAD_CHARS]]
    if (i := text.lower().rfind("last edited on")) >= 0:
        candidates.append(text[i : i + 60])
    today = today or datetime.now(UTC).date()
    for chunk in candidates:
        if not (m := _DATE_LABEL.search(chunk)):
            continue
        g = m.groups()
        if g[0]:
            y, mo, d = int(g[0]), int(g[1]), int(g[2])
        elif g[3]:
            y, mo, d = int(g[5]), MONTHS[g[4].lower()], int(g[3])
        else:
            y, mo, d = int(g[8]), MONTHS[g[6].lower()], int(g[7])
        try:
            found = date(y, mo, d)
        except ValueError:
            continue
        if date(1990, 1, 1) <= found <= today:
            return found.isoformat()
    return None


_URL_DATE = re.compile(r"/((?:19|20)\d{2})[/-](\d{1,2})[/-](\d{1,2})(?:/|$|[-_])")


def url_date(url: str, today: date | None = None) -> str | None:
    """YYYY-MM-DD from a dated URL path like /2026/04/14/ (common for news), else None."""
    if not (m := _URL_DATE.search(urlsplit(url).path)):
        return None
    try:
        found = date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None
    return (
        found.isoformat()
        if date(1990, 1, 1) <= found <= (today or datetime.now(UTC).date())
        else None
    )


_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_NAV_LEFTOVER = re.compile(r"[\s*\-+|•·>#,]*")


def clean_markdown(text: str) -> str:
    """Drop images and lines that are only links (menus, footers); keep link text elsewhere."""
    lines = []
    for line in _IMAGE.sub("", text).splitlines():
        if (
            not line.lstrip().startswith("#")
            and _LINK.search(line)
            and _NAV_LEFTOVER.fullmatch(_LINK.sub("", line))
        ):
            continue
        lines.append(_LINK.sub(r"\1", line).replace("**", "").rstrip())
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


STOPWORDS = frozenset(
    "the and for are was were has have had that this with from not but its his her their they "
    "them than then into over about after before more most less any all can could will would "
    "been being who what when where which why how one two also only very such there here".split()
)
MAX_UNIT_CHARS = 400


def _token(word: str) -> str:
    return word[:-1] if len(word) > 4 and word.endswith("s") else word


def claim_terms(claim: str) -> dict[str, float]:
    """Content words of the claim; numbers weigh more since claims often hinge on them."""
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", claim.lower())  # 21,196 -> 21196, as in _unit_score
    terms: dict[str, float] = {}
    for word in re.findall(r"\w+", text):
        if any(c.isdigit() for c in word):
            terms[word] = 3.0
        elif len(word) >= 3 and word not in STOPWORDS:
            terms[_token(word)] = 1.0
    return terms


def _units(text: str) -> list[tuple[int, int]]:
    """(start, end) spans of sentences, long ones split at whitespace."""
    spans = []
    for m in re.finditer(r"[^\n]+?(?:[.!?](?=\s)|\n|$)", text):
        start, end = m.start(), m.end()
        while end - start > MAX_UNIT_CHARS:
            cut = text.rfind(" ", start + 1, start + MAX_UNIT_CHARS)
            cut = cut if cut > start else start + MAX_UNIT_CHARS
            spans.append((start, cut))
            start = cut
        if text[start:end].strip():
            spans.append((start, end))
    return spans


def _unit_score(sentence: str, terms: dict[str, float]) -> float:
    text = re.sub(r"(?<=\d),(?=\d{3}\b)", "", sentence.lower())
    words = {_token(w) for w in re.findall(r"\w+", text)} | set(re.findall(r"\w+", text))
    return sum(weight for term, weight in terms.items() if term in words)


def select_passages(text: str, claim: str, budget: int) -> str:
    """Best claim-matching sentences, then their neighbours, up to budget chars, in page order.
    Empty string when no sentence matches the claim well enough."""
    terms = claim_terms(claim)
    units = _units(text)
    scores = [_unit_score(text[a:b], terms) for a, b in units]
    chosen: set[int] = set()

    def render(idx: set[int]) -> str:
        parts, prev = [], -2
        for i in sorted(idx):
            if i == prev + 1:
                parts[-1] = (parts[-1][0], units[i][1])
            else:
                parts.append(units[i])
            prev = i
        return PASSAGE_SEP.join(text[a:b].strip() for a, b in parts)

    threshold = min(2.0, sum(terms.values()))  # one shared common word is not a match
    ranked = sorted(range(len(units)), key=lambda i: (-scores[i], i))
    seeds = [i for i in ranked if threshold > 0 and scores[i] >= threshold]
    context = [n for i in seeds for n in (i - 1, i + 1) if 0 <= n < len(units)]
    # Matching sentences first, best first; then their neighbours as context.
    for j in seeds + context:
        if j not in chosen and len(render(chosen | {j})) <= budget:
            chosen.add(j)
    return render(chosen)


def source_text(r: RawResult, claim: str, budget: int) -> str:
    """Claim-relevant passages from the full page when available, else Tavily's snippet."""
    snippet = (r.get("content") or "").strip()
    raw = r.get("raw_content") or ""
    if claim and raw:
        if passages := select_passages(raw, claim, budget):
            return passages
    return snippet[:budget]


def _to_raw(r: dict) -> RawResult | None:
    url = r.get("url")
    if not url:
        return None
    raw = RawResult(
        url=url,
        title=r.get("title") or url,
        content=r.get("content") or "",
        favicon=r.get("favicon"),
        score=float(r.get("score") or 0.0),
    )
    if r.get("raw_content"):
        raw["raw_content"] = r["raw_content"]
    if day := iso_date(r.get("published_date")):
        raw["published_date"] = day
    return raw


def _rank_score(r: RawResult) -> float:
    return r.get("score", 0) + TIER_BONUS[domain_reliability(_host(r["url"]))]


def collect_sources(
    results_per_query: list[list[RawResult]],
    *,
    max_per_domain: int,
    max_total: int,
    source_chars: int,
    claim: str = "",
    start_id: int = 1,
    exclude_urls: frozenset[str] | set[str] = frozenset(),
) -> list[Source]:
    """Merge, dedupe by normalize_url (also skipping exclude_urls, given normalized), rank by
    score plus a reliability bonus, cap per site and total, cut each source to the passages that
    best match the claim (or its snippet), number ids from start_id."""
    best: dict[str, RawResult] = {}
    for results in results_per_query:
        for r in results:
            key = normalize_url(r["url"])
            if key in exclude_urls:
                continue
            if key not in best or r.get("score", 0) > best[key].get("score", 0):
                best[key] = r
    ranked = sorted(best.values(), key=_rank_score, reverse=True)

    sources: list[Source] = []
    per_site: dict[str, int] = {}
    for r in ranked:
        if len(sources) >= max_total:
            break
        domain = _host(r["url"])
        site = _site(domain)
        if per_site.get(site, 0) >= max_per_domain:
            continue
        content = source_text(r, claim, source_chars)
        if not content:
            continue
        per_site[site] = per_site.get(site, 0) + 1
        sources.append(
            Source(
                id=start_id + len(sources),
                url=r["url"],
                title=r.get("title") or r["url"],
                domain=domain,
                content=content,
                favicon=r.get("favicon"),
                published_date=r.get("published_date"),
                reliability=domain_reliability(domain),
            )
        )
    return sources


class Search:
    def __init__(
        self,
        api_key: str,
        store: Store,
        *,
        depth: str = "basic",
        max_results: int = 5,
        raw_content: bool = True,
        chunks_per_source: int = 3,
        cache_hours: float = 24,
        max_input_chars: int = 5000,
        client: Any = None,  # AsyncTavilyClient or a test fake
    ):
        if client is None:
            from tavily import AsyncTavilyClient

            client = AsyncTavilyClient(api_key=api_key)
        self.client = client
        self.store = store
        self.depth = depth
        self.max_results = max_results
        self.raw_content = raw_content
        self.chunks_per_source = chunks_per_source
        self.cache_hours = cache_hours
        self.max_input_chars = max_input_chars

    def _params(self) -> dict[str, Any]:
        params: dict[str, Any] = {
            "search_depth": self.depth,
            "max_results": self.max_results,
            "include_answer": False,  # never: it would add a non-NVIDIA AI answer
            "include_raw_content": "markdown" if self.raw_content else False,
            "include_favicon": True,
        }
        if self.depth == "advanced":
            params["chunks_per_source"] = self.chunks_per_source
        return params

    def _cache_key(self, query: str, params: dict[str, Any]) -> str:
        """Every request parameter is part of the key, plus a version for the cached shape."""
        blob = json.dumps({"q": query, "v": 4, **params}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()

    async def search_web(self, query: str) -> list[RawResult]:
        params = self._params()
        key = self._cache_key(query, params)
        response = await self.store.cache_get(key, self.cache_hours)
        if response is None:
            response = _shrink(await self._search_with_retry(query, params))
            await self.store.cache_put(key, response)
        results = (response or {}).get("results") or []
        return [raw for r in results if isinstance(r, dict) and (raw := _to_raw(r))]

    async def _search_with_retry(self, query: str, params: dict[str, Any]) -> Any:
        """One retry after a short pause on timeout or connection error (seen when many
        searches start at once); other errors and a second failure propagate."""
        for attempt in range(2):
            try:
                return await asyncio.wait_for(
                    self.client.search(query=query, **params), TAVILY_TIMEOUT_S
                )
            except TRANSIENT_SEARCH_ERRORS as e:
                if attempt:
                    raise SearchUnavailable(f"Web search failed: {type(e).__name__}") from e
                log.warning("tavily search retry for %r after %s", query[:80], type(e).__name__)
                await asyncio.sleep(SEARCH_RETRY_DELAY_S)

    async def extract_url(self, url: str) -> str:
        try:
            response = await asyncio.wait_for(
                self.client.extract(urls=[url], format="markdown", extract_depth="basic"),
                TAVILY_TIMEOUT_S,
            )
        except Exception as e:
            log.warning("tavily extract failed for %s: %s", url, e)
            raise IngestError(EXTRACT_FAILED) from e
        response = response or {}
        results = response.get("results") or []
        content = (results[0].get("raw_content") or "") if results else ""
        content = clean_markdown(content)  # menus first would otherwise eat the input budget
        if response.get("failed_results") or not content.strip():
            raise IngestError(EXTRACT_FAILED)
        return content[: self.max_input_chars * 2]


def _shrink(response: Any) -> Any:
    """Keep only the fields we use, with page text cleaned and bounded, before caching."""
    if not isinstance(response, dict):
        return response
    results = []
    for r in response.get("results") or []:
        if not isinstance(r, dict):
            continue
        kept = {k: r.get(k) for k in ("url", "title", "content", "favicon", "score")}
        kept["published_date"] = iso_date(r.get("published_date")) or url_date(r.get("url") or "")
        if isinstance(raw := r.get("raw_content"), str) and raw:
            text = clean_markdown(raw)
            kept["raw_content"] = text[:RAW_CACHE_CHARS]
            # Tavily sends published_date only for topic="news"; else use a labelled page date.
            kept["published_date"] = kept["published_date"] or page_date(text)
        results.append(kept)
    return {"results": results}
