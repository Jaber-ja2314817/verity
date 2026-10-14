import pytest

from app.search import IngestError, RawResult, Search, collect_sources, normalize_url
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
            ]
        }
    )
    results = await make(store, client, depth="basic", max_results=5).search_web("q")
    call = client.search_calls[0]
    assert call["include_answer"] is False
    assert call["include_raw_content"] is False and call["include_favicon"] is True
    assert call["search_depth"] == "basic" and call["max_results"] == 5
    assert results[0] == rr("https://a.com/x", 0.9, "", "https://a.com/x")
    assert results[1] == RawResult(
        url="https://b.com", title="B", content="body", favicon="f.ico", score=0.0
    )


async def test_cache_hit_skips_tavily(store):
    client = FakeTavily({"results": [{"url": "https://a.com", "score": 1}]})
    search = make(store, client)
    first = await search.search_web("same query")
    second = await search.search_web("same query")
    assert first == second and len(client.search_calls) == 1
    await search.search_web("other query")
    assert len(client.search_calls) == 2


async def test_cache_key_depends_on_depth(store):
    client = FakeTavily({"results": []})
    await make(store, client, depth="basic").search_web("q")
    await make(store, client, depth="advanced").search_web("q")
    assert len(client.search_calls) == 2


async def test_extract_ok_and_truncated(store):
    client = FakeTavily(extract_response={"results": [{"raw_content": "x" * 50}]})
    text = await make(store, client, max_input_chars=10).extract_url("https://a.com")
    assert text == "x" * 20
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
