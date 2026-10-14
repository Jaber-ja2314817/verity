import asyncio
import hashlib
import logging
from typing import Any, TypedDict
from urllib.parse import urlsplit

from .schemas import Source
from .store import Store

log = logging.getLogger(__name__)

TAVILY_TIMEOUT_S = 30
EXTRACT_FAILED = "Could not read that page. Try pasting the text instead."


class RawResult(TypedDict):
    url: str
    title: str
    content: str
    favicon: str | None
    score: float


class IngestError(Exception):
    """User-facing ingest problem; str(e) is safe to show to users."""


def _host(url: str) -> str:
    host = (urlsplit(url.strip()).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def normalize_url(url: str) -> str:
    """Lowercase host, no www., no trailing slash, no query string or fragment."""
    path = urlsplit(url.strip()).path.rstrip("/")
    return f"{_host(url)}{path}"


def _to_raw(r: dict) -> RawResult | None:
    url = r.get("url")
    if not url:
        return None
    return RawResult(
        url=url,
        title=r.get("title") or url,
        content=r.get("content") or "",
        favicon=r.get("favicon"),
        score=float(r.get("score") or 0.0),
    )


def collect_sources(
    results_per_query: list[list[RawResult]],
    *,
    max_per_domain: int,
    max_total: int,
    source_chars: int,
    start_id: int = 1,
    exclude_urls: frozenset[str] | set[str] = frozenset(),
) -> list[Source]:
    """Merge, dedupe by normalize_url (also skipping exclude_urls, given normalized), sort by
    score desc, cap per domain and total, trim content, number ids from start_id."""
    best: dict[str, RawResult] = {}
    for results in results_per_query:
        for r in results:
            key = normalize_url(r["url"])
            if key in exclude_urls:
                continue
            if key not in best or r.get("score", 0) > best[key].get("score", 0):
                best[key] = r
    ranked = sorted(best.values(), key=lambda r: r.get("score", 0), reverse=True)

    sources: list[Source] = []
    per_domain: dict[str, int] = {}
    for r in ranked:
        if len(sources) >= max_total:
            break
        domain = _host(r["url"])
        if per_domain.get(domain, 0) >= max_per_domain:
            continue
        per_domain[domain] = per_domain.get(domain, 0) + 1
        sources.append(
            Source(
                id=start_id + len(sources),
                url=r["url"],
                title=r.get("title") or r["url"],
                domain=domain,
                content=(r.get("content") or "")[:source_chars],
                favicon=r.get("favicon"),
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
        self.cache_hours = cache_hours
        self.max_input_chars = max_input_chars

    def _cache_key(self, query: str) -> str:
        return hashlib.sha256(f"{query}|{self.depth}|{self.max_results}".encode()).hexdigest()

    async def search_web(self, query: str) -> list[RawResult]:
        key = self._cache_key(query)
        response = await self.store.cache_get(key, self.cache_hours)
        if response is None:
            response = await asyncio.wait_for(
                self.client.search(
                    query=query,
                    search_depth=self.depth,
                    max_results=self.max_results,
                    include_answer=False,  # never: it would add a non-NVIDIA AI answer
                    include_raw_content=False,
                    include_favicon=True,
                ),
                TAVILY_TIMEOUT_S,
            )
            await self.store.cache_put(key, response)
        results = (response or {}).get("results") or []
        return [raw for r in results if isinstance(r, dict) and (raw := _to_raw(r))]

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
        if response.get("failed_results") or not content.strip():
            raise IngestError(EXTRACT_FAILED)
        return content[: self.max_input_chars * 2]
