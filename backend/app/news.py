"""News search (GNews or NewsData.io) for the Auto and News modes.

Free news plans return only a short snippet, so each article page is downloaded here to get text
the quote check can verify against. A page that is blocked, paywalled or not HTML falls back to
the snippet. Results come back in the same RawResult shape as web search results.
"""

import asyncio
import hashlib
import ipaddress
import json
import logging
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import httpx

from .search import RAW_CACHE_CHARS, RawResult, clean_markdown, iso_date
from .store import Store

if TYPE_CHECKING:
    from .config import Settings

log = logging.getLogger(__name__)

NEWS_TIMEOUT_S = 15
PAGE_TIMEOUT_S = 10
PAGE_MAX_BYTES = 1_500_000
PAGE_CONCURRENCY = 4
MIN_PAGE_CHARS = 300  # shorter than this and the page is probably a consent wall or a stub
USER_AGENT = "Mozilla/5.0 (compatible; VerityFactCheck/1.0)"
QUERY_MAX_CHARS = 200
SKIP_TAGS = frozenset(
    "script style noscript nav footer header aside form svg iframe button select".split()
)
TEXT_TAGS = frozenset("p h1 h2 h3 h4 li blockquote".split())


class NewsUnavailable(RuntimeError):
    """The news API failed, refused the key, or its quota is used up. Callers fall back to web
    search, so a news outage never fails a check."""


class _ArticleText(HTMLParser):
    """Collects the text of paragraphs, headings and list items outside page chrome."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0
        self._block = 0
        self._buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in SKIP_TAGS:
            self._skip += 1
        elif tag in TEXT_TAGS and not self._skip:
            self._flush()
            self._block += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag in TEXT_TAGS and self._block:
            self._block -= 1
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._block and not self._skip:
            self._buf.append(data)

    def _flush(self) -> None:
        text = " ".join("".join(self._buf).split())
        self._buf = []
        if len(text) >= 25:  # drop captions, buttons and one-word menu items
            self.parts.append(text)


def html_to_text(html: str) -> str:
    parser = _ArticleText()
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # noqa: BLE001 - broken markup: keep whatever was collected
        pass
    parser._flush()
    return "\n\n".join(parser.parts)


def is_public_http_url(url: str) -> bool:
    """http(s) URL whose host is not localhost or a private/loopback/link-local IP literal."""
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host:
        return False
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True
    return ip.is_global


def _rank_score(i: int) -> float:
    """News APIs give no relevance score; keep their order (best first)."""
    return max(0.3, 1.0 - 0.07 * i)


def parse_gnews(response: Any) -> list[dict]:
    """GNews /search response -> [{url, title, snippet, published, outlet}]."""
    out = []
    for a in (response or {}).get("articles") or []:
        if isinstance(a, dict) and a.get("url"):
            snippet = " ".join(
                x.strip() for x in (a.get("description"), a.get("content")) if x and x.strip()
            )
            out.append(
                {
                    "url": a["url"],
                    "title": a.get("title") or a["url"],
                    "snippet": snippet,
                    "published": iso_date(a.get("publishedAt")),
                }
            )
    return out


def parse_newsdata(response: Any) -> list[dict]:
    """NewsData.io /latest response -> same shape. Free plans put a paywall notice in content."""
    out = []
    for a in (response or {}).get("results") or []:
        if isinstance(a, dict) and a.get("link"):
            content = a.get("content") or ""
            if "ONLY AVAILABLE IN PAID PLANS" in content.upper():
                content = ""
            parts = (a.get("description"), content)
            snippet = " ".join(x.strip() for x in parts if x and x.strip())
            out.append(
                {
                    "url": a["link"],
                    "title": a.get("title") or a["link"],
                    "snippet": snippet,
                    "published": iso_date((a.get("pubDate") or "").replace(" ", "T", 1)),
                }
            )
    return out


class NewsSearch:
    def __init__(
        self,
        provider: str,
        api_key: str,
        store: Store,
        *,
        max_results: int = 8,
        lookback_days: int = 30,
        cache_hours: float = 24,
        fetch_pages: bool = True,
        client: httpx.AsyncClient | None = None,  # a test fake or a client with a mock transport
    ):
        if provider not in ("gnews", "newsdata"):
            raise ValueError(f"unknown news provider {provider!r}")
        self.provider = provider
        self.api_key = api_key
        self.store = store
        self.max_results = max_results
        self.lookback_days = lookback_days
        self.cache_hours = cache_hours
        self.fetch_pages = fetch_pages
        self.client = client or httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, follow_redirects=True, max_redirects=3
        )
        self._pages = asyncio.Semaphore(PAGE_CONCURRENCY)

    def _request(self, query: str) -> tuple[str, dict[str, Any]]:
        q = " ".join(query.split())[:QUERY_MAX_CHARS]
        if self.provider == "gnews":
            since = (datetime.now(UTC) - timedelta(days=self.lookback_days)).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            return "https://gnews.io/api/v4/search", {
                "q": q, "max": min(self.max_results, 10), "from": since,
                "sortby": "relevance", "apikey": self.api_key,
            }  # fmt: skip
        return "https://newsdata.io/api/1/latest", {
            "q": q, "apikey": self.api_key, "removeduplicate": 1,
        }  # fmt: skip

    def _cache_key(self, query: str) -> str:
        url, params = self._request(query)
        params = {k: v for k, v in params.items() if k not in ("apikey", "from")}
        blob = json.dumps(
            {"u": url, "p": params, "v": 1, "pages": self.fetch_pages}, sort_keys=True
        )
        return hashlib.sha256(blob.encode()).hexdigest()

    async def search_news(self, query: str) -> list[RawResult]:
        key = self._cache_key(query)
        cached = await self.store.cache_get(key, self.cache_hours)
        if cached is None:
            cached = {"results": await self._fetch(query)}
            await self.store.cache_put(key, cached, prune_hours=self.cache_hours)
        return [r for r in cached.get("results") or [] if isinstance(r, dict) and r.get("url")]

    async def _fetch(self, query: str) -> list[RawResult]:
        url, params = self._request(query)
        try:
            res = await asyncio.wait_for(self.client.get(url, params=params), NEWS_TIMEOUT_S)
        except (TimeoutError, httpx.TransportError) as e:
            raise NewsUnavailable(f"News search failed: {type(e).__name__}") from e
        if res.status_code >= 400:
            # Never log the URL: it carries the API key.
            log.error("news api %s returned HTTP %s", self.provider, res.status_code)
            raise NewsUnavailable(f"News search refused (HTTP {res.status_code})")
        try:
            body = res.json()
        except ValueError as e:
            raise NewsUnavailable("News search returned invalid JSON") from e
        articles = (parse_gnews if self.provider == "gnews" else parse_newsdata)(body)
        articles = articles[: self.max_results]
        pages = await asyncio.gather(
            *(self._page_text(a["url"]) if self.fetch_pages else _none() for a in articles)
        )
        results: list[RawResult] = []
        for i, (a, page) in enumerate(zip(articles, pages, strict=True)):
            raw = RawResult(
                url=a["url"], title=a["title"], content=a["snippet"], favicon=None,
                score=_rank_score(i),
            )  # fmt: skip
            if page:
                raw["raw_content"] = page
            if a["published"]:
                raw["published_date"] = a["published"]
            results.append(raw)
        return results

    async def _page_text(self, url: str) -> str:
        """Readable article text, or "" when the page cannot be used."""
        if not is_public_http_url(url):
            return ""
        try:
            async with self._pages:
                html = await asyncio.wait_for(self._download(url), PAGE_TIMEOUT_S)
        except Exception as e:  # noqa: BLE001 - blocked, paywalled or slow pages are routine
            log.info("article page skipped (%s): %s", type(e).__name__, urlsplit(url).hostname)
            return ""
        text = clean_markdown(html_to_text(html))
        return text[:RAW_CACHE_CHARS] if len(text) >= MIN_PAGE_CHARS else ""

    async def _download(self, url: str) -> str:
        async with self.client.stream("GET", url) as res:
            if res.status_code >= 400:
                return ""
            if not is_public_http_url(str(res.url)):  # a redirect to an internal address
                return ""
            if "html" not in res.headers.get("content-type", "").lower():
                return ""
            body = bytearray()
            async for chunk in res.aiter_bytes():
                body += chunk
                if len(body) > PAGE_MAX_BYTES:
                    break
            return bytes(body).decode(res.encoding or "utf-8", errors="replace")


async def _none() -> str:
    return ""


def news_from_settings(s: "Settings", store: Store) -> NewsSearch | None:
    """The news client for these settings, or None when NEWS_PROVIDER is empty (news off)."""
    if not s.news_provider:
        return None
    return NewsSearch(
        s.news_provider,
        s.news_api_key,
        store,
        max_results=s.news_max_results,
        lookback_days=s.news_lookback_days,
        cache_hours=s.search_cache_hours,
        fetch_pages=s.news_fetch_pages,
    )
