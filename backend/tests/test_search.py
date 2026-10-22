from datetime import date

import pytest
from tavily.errors import ForbiddenError, InvalidAPIKeyError, UsageLimitExceededError

from app import search as search_module
from app.search import (
    IngestError,
    RawResult,
    Search,
    collect_sources,
    normalize_url,
    url_date,
)
from app.store import Store


class FakeTavily:
    def __init__(self, search_response=None, extract_response=None, extract_error=None):
        self.search_response = search_response or {"results": []}
        self.extract_response = extract_response
        self.extract_error = extract_error
        self.search_calls: list[dict] = []
        self.extract_calls: list[dict] = []

    async def search(self, **kwargs):
        self.search_calls.append(kwargs)
        return self.search_response

    async def extract(self, **kwargs):
        self.extract_calls.append(kwargs)
        if self.extract_error:
            raise self.extract_error
        return self.extract_response


def rr(url: str, score: float = 0.5, content: str = "c", title: str = "T") -> RawResult:
    return RawResult(url=url, title=title, content=content, favicon=None, score=score)


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path)
    yield s
    s.close()


def make(store, client, **kw) -> Search:
    return Search("key", store, client=client, **kw)


async def test_search_params_and_defensive_reads(store):
    client = FakeTavily(
        {
            "results": [
                {"url": "https://a.com/x", "score": 0.9},
                {"title": "no url"},
                {"url": "https://b.com", "title": "B", "content": "body", "favicon": "f.ico"},
                {
                    "url": "https://c.com",
                    "raw_content": "![i](p.png)\n[Home](/)\nText with a [link](/l).",
                    "published_date": "Mon, 14 Oct 2024 12:00:00 GMT",
                    "extra": "dropped",
                },
            ]
        }
    )
    results = await make(store, client, depth="basic", max_results=5).search_web("q")
    call = client.search_calls[0]
    assert call["include_answer"] is False
    assert call["include_raw_content"] == "markdown" and call["include_favicon"] is True
    assert call["search_depth"] == "basic" and call["max_results"] == 5
    assert "chunks_per_source" not in call
    assert results[0] == rr("https://a.com/x", 0.9, "", "https://a.com/x")
    assert results[1] == RawResult(
        url="https://b.com", title="B", content="body", favicon="f.ico", score=0.0
    )
    assert results[2]["raw_content"] == "Text with a link."  # cleaned before caching
    assert results[2]["published_date"] == "2024-10-14"


async def test_published_date_falls_back_to_labelled_page_date(store):
    page = {"url": "https://a.com", "raw_content": "# T\nUpdated: 2 May 2024\nIn 1999 it rained."}
    client = FakeTavily({"results": [page, {"url": "https://b.com", "raw_content": "In 1999."}]})
    results = await make(store, client).search_web("q")
    assert results[0]["published_date"] == "2024-05-02"
    assert "published_date" not in results[1]


async def test_advanced_depth_sends_chunks_and_raw_can_be_off(store):
    client = FakeTavily()
    await make(store, client, depth="advanced", raw_content=False, chunks_per_source=2).search_web(
        "q"
    )
    call = client.search_calls[0]
    assert call["search_depth"] == "advanced" and call["chunks_per_source"] == 2
    assert call["include_raw_content"] is False


async def test_cache_hit_skips_tavily(store):
    client = FakeTavily({"results": [{"url": "https://a.com", "score": 1}]})
    search = make(store, client)
    first = await search.search_web("same query")
    second = await search.search_web("same query")
    assert first == second and len(client.search_calls) == 1
    await search.search_web("other query")
    assert len(client.search_calls) == 2


@pytest.mark.parametrize(
    "a, b",
    [
        ({"depth": "basic"}, {"depth": "advanced"}),
        ({"max_results": 5}, {"max_results": 6}),
        ({"raw_content": True}, {"raw_content": False}),
        (
            {"depth": "advanced", "chunks_per_source": 1},
            {"depth": "advanced", "chunks_per_source": 3},
        ),
    ],
)
async def test_cache_key_depends_on_every_param(store, a, b):
    client = FakeTavily({"results": []})
    await make(store, client, **a).search_web("q")
    await make(store, client, **b).search_web("q")
    assert len(client.search_calls) == 2


async def test_cached_response_is_shrunk(store):
    client = FakeTavily({"results": [{"url": "https://a.com", "raw_content": "x" * 60_000}]})
    search = make(store, client)
    await search.search_web("q")
    cached = await store.cache_get(search._cache_key("q", search._params()), 24)
    assert len(cached["results"][0]["raw_content"]) == 50_000


async def test_extract_ok_and_truncated(store):
    page = "* [Home](/)\n* [News](/n)\n# Title [here](/t)\n" + "x" * 50
    client = FakeTavily(extract_response={"results": [{"raw_content": page}]})
    text = await make(store, client, max_input_chars=10).extract_url("https://a.com")
    assert text == "# Title here\nxxxxxxx"  # menu lines dropped before the cut
    assert client.extract_calls[0] == {
        "urls": ["https://a.com"],
        "format": "markdown",
        "extract_depth": "basic",
    }


@pytest.mark.parametrize(
    "client",
    [
        FakeTavily(extract_response={"results": [], "failed_results": [{"url": "u"}]}),
        FakeTavily(extract_response={"results": [{"raw_content": "  "}]}),
        FakeTavily(extract_response={"results": [{"raw_content": "ok"}], "failed_results": [1]}),
        FakeTavily(extract_error=RuntimeError("boom")),
    ],
)
async def test_extract_errors_raise_ingest_error(store, client):
    with pytest.raises(IngestError, match="Could not read that page"):
        await make(store, client).extract_url("https://a.com")


def test_normalize_url():
    assert normalize_url("https://WWW.Example.com/Path/?q=1#frag") == "example.com/Path"
    assert normalize_url("http://example.com/Path") == "example.com/Path"


def collect(results, **kw):
    opts = {"max_per_domain": 2, "max_total": 8, "source_chars": 1500} | kw
    return collect_sources(results, **opts)


def test_collect_dedupes_and_sorts():
    sources = collect(
        [
            [rr("https://a.com/1", 0.2), rr("https://www.b.com/x/?utm=1", 0.9)],
            [rr("https://b.com/x", 0.5), rr("https://c.org/y", 0.7)],
        ]
    )
    assert [s.url for s in sources] == [
        "https://www.b.com/x/?utm=1",
        "https://c.org/y",
        "https://a.com/1",
    ]
    assert [s.id for s in sources] == [1, 2, 3]
    assert sources[0].domain == "b.com"


def test_collect_caps_domain_and_total_and_trims():
    results = [[rr(f"https://a.com/{i}", 1 - i / 10, "z" * 100) for i in range(5)]]
    results.append([rr(f"https://d{i}.com", 0.01) for i in range(10)])
    sources = collect(results, max_per_domain=2, max_total=4, source_chars=10)
    assert len(sources) == 4
    assert sum(s.domain == "a.com" for s in sources) == 2
    assert all(len(s.content) <= 10 for s in sources)


def test_collect_exclude_and_start_id():
    sources = collect(
        [[rr("https://a.com/1", 0.9), rr("https://b.com/2", 0.5)]],
        start_id=4,
        exclude_urls={normalize_url("https://www.a.com/1/")},
    )
    assert [(s.id, s.url) for s in sources] == [(4, "https://b.com/2")]


def test_collect_sets_reliability_and_date_and_prefers_reliable_sources():
    results = [
        [
            rr("https://www.reddit.com/r/x", 0.80),
            rr("https://blog.example.com/p", 0.70),
            rr("https://www.reuters.com/a", 0.60),
        ]
    ]
    results[0][2]["published_date"] = "2024-01-02"
    sources = collect(results, max_total=2)
    assert [(s.domain, s.reliability) for s in sources] == [
        ("reuters.com", "high"),
        ("blog.example.com", "unknown"),
    ]
    assert sources[0].published_date == "2024-01-02" and sources[1].published_date is None


def test_collect_caps_per_site_across_subdomains():
    results = [[rr(f"https://{lang}.wikipedia.org/wiki/X", 0.9) for lang in ("en", "de", "fr")]]
    sources = collect(results, max_per_domain=2)
    assert [s.domain for s in sources] == ["en.wikipedia.org", "de.wikipedia.org"]


def test_collect_uses_claim_passages_from_raw_content():
    raw = "Cookie banner text here.\nThe tower is 330 metres tall since 2022.\nUnrelated footer."
    r = rr("https://a.com", content="Tavily snippet")
    r["raw_content"] = raw
    [with_claim] = collect([[r]], claim="The Eiffel tower is 330 metres tall", source_chars=45)
    assert with_claim.content == "The tower is 330 metres tall since 2022."
    [roomy] = collect([[r]], claim="The Eiffel tower is 330 metres tall")
    assert roomy.content == raw  # neighbours are kept as context when they fit
    [no_claim] = collect([[r]])
    assert no_claim.content == "Tavily snippet"
    [no_match] = collect([[r]], claim="Bananas are berries")
    assert no_match.content == "Tavily snippet"


def test_collect_skips_results_without_text():
    sources = collect([[rr("https://a.com", content=""), rr("https://b.com", 0.1)]])
    assert [s.url for s in sources] == ["https://b.com"]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://news.example.com/story/2026/04/14/titanic-anniversary/123", "2026-04-14"),
        ("https://example.com/2024-02-29-leap-day", "2024-02-29"),
        ("https://example.com/2026/02/30/bad-day", None),  # invalid date
        ("https://example.com/2099/01/01/future", None),
        ("https://example.com/report-20260414", None),  # no separators: not a dated path
        ("https://en.wikipedia.org/wiki/Titanic", None),
    ],
)
def test_url_date(url, expected):
    assert url_date(url, today=date(2026, 10, 19)) == expected


class FlakyTavily(FakeTavily):
    def __init__(self, failures: list[Exception], **kw):
        super().__init__(**kw)
        self.failures = failures

    async def search(self, **kwargs):
        self.search_calls.append(kwargs)
        if self.failures:
            raise self.failures.pop(0)
        return self.search_response


async def test_search_retries_once_on_transient_error(store, monkeypatch):
    monkeypatch.setattr(search_module, "SEARCH_RETRY_DELAY_S", 0)
    ok = {"results": [{"url": "https://a.org/x", "title": "A", "content": "c", "score": 0.5}]}
    client = FlakyTavily([TimeoutError()], search_response=ok)
    results = await Search("k", store, client=client).search_web("q")
    assert len(client.search_calls) == 2 and results[0]["url"] == "https://a.org/x"


async def test_search_gives_up_after_second_transient_error(store, monkeypatch):
    monkeypatch.setattr(search_module, "SEARCH_RETRY_DELAY_S", 0)
    client = FlakyTavily([TimeoutError(), TimeoutError()])
    with pytest.raises(search_module.SearchUnavailable, match="Web search failed"):
        await Search("k", store, client=client).search_web("q")
    assert len(client.search_calls) == 2


async def test_search_retries_once_on_tavily_rate_limit(store, monkeypatch):
    monkeypatch.setattr(search_module, "SEARCH_RETRY_DELAY_S", 0)
    client = FlakyTavily([UsageLimitExceededError("rate limited")])
    assert await Search("k", store, client=client).search_web("q") == []
    assert len(client.search_calls) == 2


@pytest.mark.parametrize("error", [ForbiddenError("plan limit"), InvalidAPIKeyError("bad key")])
async def test_search_refusal_is_search_unavailable_without_retry(store, error):
    client = FlakyTavily([error])
    with pytest.raises(search_module.SearchUnavailable, match="Web search refused"):
        await Search("k", store, client=client).search_web("q")
    assert len(client.search_calls) == 1


async def test_search_does_not_retry_other_errors(store):
    client = FlakyTavily([ValueError("bad request")])
    with pytest.raises(ValueError):
        await Search("k", store, client=client).search_web("q")
    assert len(client.search_calls) == 1
