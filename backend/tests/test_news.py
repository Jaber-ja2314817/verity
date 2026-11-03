import asyncio

import httpx
import pytest
from conftest import FakeLLM, FakeSearch, raw_result
from test_pipeline import (
    PAGE_A,
    PAGE_B,
    QUOTE_A,
    QUOTE_B,
    assess,
    claim,
    run,
    settings,
    verdict,
)

from app.events import EventBus
from app.news import (
    NewsSearch,
    NewsUnavailable,
    html_to_text,
    is_public_http_url,
    parse_gnews,
    parse_newsdata,
)
from app.pipeline.orchestrator import Deps
from app.schemas import (
    CheckRequest,
    ClaimExtraction,
    PlannedQuery,
    QueryPlan,
    validate_check_request,
)
from app.store import Store

ARTICLE = (
    "<html><head><title>x</title><script>var a = 'ignore me';</script></head><body>"
    "<nav><p>Home | World | Sport | Weather and many other menu items</p></nav>"
    "<article><h1>Wall visible from orbit, claim debunked again</h1>"
    f"<p>{QUOTE_A} Several agencies have repeated this finding over the years.</p>"
    "<p>Photographs taken from the station show cities and airports clearly, but the wall "
    "is far too narrow to pick out without a long lens.</p>"
    "<p>Officials said the finding would be included in the next edition of the guide.</p>"
    "</article><footer><p>Copyright notice and long legal text goes here for the site.</p></footer>"
    "</body></html>"
)
GNEWS = {
    "articles": [
        {
            "title": "Wall debunked",
            "description": "Short description.",
            "content": "Content snippet…",
            "url": "https://news-a.com/2026/10/30/wall",
            "publishedAt": "2026-10-30T08:00:00Z",
        },
        {
            "title": "Second outlet",
            "description": "Other description of the same story.",
            "content": "",
            "url": "https://news-b.org/wall",
            "publishedAt": "2026-10-31T09:00:00Z",
        },
    ]
}


def mock_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)


def gnews_handler(calls: list[httpx.Request], status: int = 200):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "gnews.io":
            return httpx.Response(status, json=GNEWS if status == 200 else {"errors": ["x"]})
        if request.url.host == "news-a.com":
            return httpx.Response(200, text=ARTICLE, headers={"content-type": "text/html"})
        return httpx.Response(404, text="gone")

    return handler


# ---- parsing and page text
def test_parse_gnews_joins_description_and_content():
    out = parse_gnews(GNEWS)
    urls = [a["url"] for a in out]
    assert urls == ["https://news-a.com/2026/10/30/wall", "https://news-b.org/wall"]
    assert out[0]["snippet"] == "Short description. Content snippet…"
    assert out[0]["published"] == "2026-10-30"
    assert parse_gnews({}) == [] and parse_gnews(None) == []


def test_parse_newsdata_drops_paywall_notice_and_parses_date():
    out = parse_newsdata(
        {
            "results": [
                {
                    "title": "T",
                    "link": "https://n.com/a",
                    "description": "Desc.",
                    "content": "ONLY AVAILABLE IN PAID PLANS",
                    "pubDate": "2026-10-30 08:15:00",
                },
                {"title": "no link"},
            ]
        }
    )
    assert out == [
        {"url": "https://n.com/a", "title": "T", "snippet": "Desc.", "published": "2026-10-30"}
    ]


def test_html_to_text_keeps_article_paragraphs_only():
    text = html_to_text(ARTICLE)
    assert QUOTE_A in text and "far too narrow" in text
    assert "ignore me" not in text and "menu items" not in text and "legal text" not in text


@pytest.mark.parametrize(
    "url,ok",
    [
        ("https://example.com/a", True),
        ("http://127.0.0.1/admin", False),
        ("http://localhost:8000/x", False),
        ("http://10.0.0.5/x", False),
        ("http://169.254.169.254/latest/meta-data", False),
        ("ftp://example.com/x", False),
        ("not a url", False),
    ],
)
def test_is_public_http_url(url, ok):
    assert is_public_http_url(url) is ok


# ---- the client
async def test_news_search_reads_pages_and_falls_back_to_snippet(tmp_path):
    calls: list[httpx.Request] = []
    news = NewsSearch("gnews", "KEY", Store(tmp_path), client=mock_client(gnews_handler(calls)))

    results = await news.search_news("great wall visible from space")

    a, b = results
    assert QUOTE_A in a["raw_content"] and a["published_date"] == "2026-10-30"
    assert "raw_content" not in b  # page returned 404: only the snippet is left
    assert b["content"] == "Other description of the same story."
    assert a["score"] > b["score"]
    api = calls[0]
    assert api.url.params["apikey"] == "KEY" and "great wall" in api.url.params["q"]


async def test_news_search_is_cached(tmp_path):
    calls: list[httpx.Request] = []
    news = NewsSearch("gnews", "KEY", Store(tmp_path), client=mock_client(gnews_handler(calls)))
    await news.search_news("same query")
    n = len(calls)
    again = await news.search_news("same query")
    assert len(calls) == n and len(again) == 2


@pytest.mark.parametrize("status", [401, 403, 429, 500])
async def test_news_search_error_status_raises_news_unavailable(tmp_path, status):
    news = NewsSearch(
        "gnews", "KEY", Store(tmp_path), client=mock_client(gnews_handler([], status))
    )
    with pytest.raises(NewsUnavailable) as e:
        await news.search_news("q")
    assert "KEY" not in str(e.value)


async def test_news_search_does_not_fetch_private_article_urls(tmp_path):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.host)
        if request.url.host == "gnews.io":
            return httpx.Response(
                200,
                json={"articles": [{"title": "T", "description": "d", "url": "http://10.0.0.5/x"}]},
            )
        return httpx.Response(200, text=ARTICLE, headers={"content-type": "text/html"})

    news = NewsSearch("gnews", "K", Store(tmp_path), client=mock_client(handler))
    [r] = await news.search_news("q")
    assert seen == ["gnews.io"] and "raw_content" not in r


# ---- request mode
def test_check_request_mode_defaults_to_auto_and_survives_validation():
    assert CheckRequest(text="x" * 30).mode == "auto"
    req = validate_check_request(CheckRequest(text="x" * 30, mode="news"), 5000)
    assert req.mode == "news"
    by_url = validate_check_request(CheckRequest(url="https://a.com/x", mode="web"), 5000)
    assert by_url.mode == "web"
    with pytest.raises(ValueError):
        CheckRequest(text="x", mode="bogus")  # pydantic's ValidationError is a ValueError


# ---- routing in the pipeline
class FakeNews:
    def __init__(self, results: list[dict] | None = None, error: Exception | None = None):
        self.results = results or []
        self.error = error
        self.queries: list[str] = []

    async def search_news(self, query: str) -> list[dict]:
        self.queries.append(query)
        if self.error:
            raise self.error
        return list(self.results)


def plan(*qs: str, time_sensitive: bool) -> QueryPlan:
    return QueryPlan(
        queries=[PlannedQuery(query=q, intent="neutral") for q in qs], time_sensitive=time_sensitive
    )


def news_deps(tmp_path, fake_llm: FakeLLM, web: FakeSearch, news: FakeNews | None, **kw) -> Deps:
    return Deps(
        settings=settings(news_provider="gnews", news_api_key="k", **kw),
        llm=fake_llm,
        search=web,
        store=Store(tmp_path),
        events=EventBus(),
        semaphore=asyncio.Semaphore(3),
        today=lambda: "2026-11-03",
        news=news,
    )


def queue_one_claim(llm: FakeLLM, *, time_sensitive: bool, qs=("q1", "q2", "q3")) -> None:
    llm.queue("extract_claims", ClaimExtraction(language="en", claims=[claim(1, "Wall")]))
    llm.queue("plan_queries[claim 1]", plan(*qs, time_sensitive=time_sensitive))
    llm.queue(
        "assess_evidence[claim 1]",
        assess((1, "refutes", QUOTE_A), (2, "refutes", QUOTE_B), (3, "refutes", QUOTE_A)),
    )
    llm.queue("verdict_draft[claim 1]", verdict("FALSE", 80, cited=(1, 2)))
    llm.queue("verdict_jury[claim 1]", verdict("FALSE", 80, cited=(1, 2)))


THREE_NEWS = [
    raw_result("https://news-a.com/1", PAGE_A, 0.9),
    raw_result("https://news-b.org/2", PAGE_B, 0.8),
    raw_result("https://news-c.net/3", PAGE_A.replace("Intro", "Different intro"), 0.7),
]


async def test_news_mode_with_enough_sources_uses_no_tavily(tmp_path, fake_llm, fake_search):
    news = FakeNews(THREE_NEWS)
    deps = news_deps(tmp_path, fake_llm, fake_search, news)
    queue_one_claim(fake_llm, time_sensitive=False)

    rec = await run(deps, CheckRequest(text="Some long enough claim text.", mode="news"))

    assert rec.status == "done"
    assert rec.claims[0].search == "news"
    assert fake_search.queries == []  # 0 Tavily calls
    assert news.queries == ["q1", "q2"]  # news_queries_per_claim = 2
    found = next(e for e in deps.events.history("chk1") if e["type"] == "sources_found")
    assert found["route"] == "news" and found["count"] == 3


async def test_news_mode_with_few_sources_adds_one_web_query(tmp_path, fake_llm, fake_search):
    news = FakeNews(THREE_NEWS[:1])
    fake_search.default = [raw_result("https://web.org/x", PAGE_B, 0.9)]
    deps = news_deps(tmp_path, fake_llm, fake_search, news)
    queue_one_claim(fake_llm, time_sensitive=False)
    fake_llm.queues["assess_evidence[claim 1]"] = [
        assess((1, "refutes", QUOTE_A), (2, "refutes", QUOTE_B))
    ]

    rec = await run(deps, CheckRequest(text="Some long enough claim text.", mode="news"))

    assert rec.claims[0].search == "mixed"
    assert fake_search.queries == ["q1"]  # one Tavily call, not three
    assert [e.source.id for e in rec.claims[0].evidence] == [1, 2]


async def test_auto_mode_routes_by_time_sensitivity(tmp_path, fake_llm, fake_search):
    news = FakeNews(THREE_NEWS)
    fake_search.default = [raw_result("https://web.org/x", PAGE_A, 0.9)]
    deps = news_deps(tmp_path, fake_llm, fake_search, news)

    queue_one_claim(fake_llm, time_sensitive=True)
    rec = await run(deps, CheckRequest(text="Some long enough claim text."))
    assert rec.claims[0].search == "news" and fake_search.queries == []


async def test_auto_mode_settled_fact_uses_web(tmp_path, fake_llm, fake_search):
    news = FakeNews(THREE_NEWS)
    fake_search.default = [raw_result("https://web.org/x", PAGE_A, 0.9)]
    deps = news_deps(tmp_path, fake_llm, fake_search, news)
    queue_one_claim(fake_llm, time_sensitive=False)
    fake_llm.queues["assess_evidence[claim 1]"] = [assess((1, "refutes", QUOTE_A))]

    rec = await run(deps, CheckRequest(text="Some long enough claim text."))

    assert rec.claims[0].search == "web"
    assert news.queries == [] and fake_search.queries == ["q1", "q2", "q3"]


async def test_web_mode_never_uses_news(tmp_path, fake_llm, fake_search):
    news = FakeNews(THREE_NEWS)
    fake_search.default = [raw_result("https://web.org/x", PAGE_A, 0.9)]
    deps = news_deps(tmp_path, fake_llm, fake_search, news)
    queue_one_claim(fake_llm, time_sensitive=True)
    fake_llm.queues["assess_evidence[claim 1]"] = [assess((1, "refutes", QUOTE_A))]

    rec = await run(deps, CheckRequest(text="Some long enough claim text.", mode="web"))

    assert rec.claims[0].search == "web" and news.queries == []


async def test_news_outage_falls_back_to_web_search(tmp_path, fake_llm, fake_search):
    news = FakeNews(error=NewsUnavailable("quota"))
    fake_search.default = [raw_result("https://web.org/x", PAGE_A, 0.9)]
    deps = news_deps(tmp_path, fake_llm, fake_search, news)
    queue_one_claim(fake_llm, time_sensitive=True)
    fake_llm.queues["assess_evidence[claim 1]"] = [assess((1, "refutes", QUOTE_A))]

    rec = await run(deps, CheckRequest(text="Some long enough claim text.", mode="news"))

    assert rec.status == "done" and rec.claims[0].search == "web"
    assert fake_search.queries == ["q1", "q2", "q3"]


async def test_news_mode_without_news_configured_uses_web(tmp_path, fake_llm, fake_search):
    fake_search.default = [raw_result("https://web.org/x", PAGE_A, 0.9)]
    deps = news_deps(tmp_path, fake_llm, fake_search, None)
    queue_one_claim(fake_llm, time_sensitive=True)
    fake_llm.queues["assess_evidence[claim 1]"] = [assess((1, "refutes", QUOTE_A))]

    rec = await run(deps, CheckRequest(text="Some long enough claim text.", mode="news"))

    assert rec.claims[0].search == "web"


def test_news_provider_without_key_is_a_startup_problem():
    from app.config import startup_problems

    s = settings(news_provider="gnews", news_api_key=" ")
    assert any("NEWS_API_KEY" in p for p in startup_problems(s))
    assert not any("NEWS_API_KEY" in p for p in startup_problems(settings()))

