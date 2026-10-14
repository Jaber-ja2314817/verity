from collections import defaultdict

import pytest
from pydantic import BaseModel

from app.trace import Trace


class FakeLLM:
    """Stands in for app.llm.LLM. Returns queued objects per step name and records calls."""

    def __init__(self):
        self.queues: dict[str, list[BaseModel | Exception]] = defaultdict(list)
        self.calls: list[dict] = []

    def queue(self, step: str, *results: BaseModel | Exception) -> None:
        self.queues[step].extend(results)

    async def structured(self, *, trace, step, model, system, user, schema, **_):
        self.calls.append({"step": step, "model": model, "system": system, "user": user})
        trace.record(step=step, model=model, usage=None, latency_s=0.0)
        if not self.queues[step]:
            raise AssertionError(f"FakeLLM: nothing queued for step {step!r}")
        result = self.queues[step].pop(0)
        if isinstance(result, Exception):
            raise result
        assert isinstance(result, schema), f"{step}: queued {type(result)}, expected {schema}"
        return result


@pytest.fixture
def fake_llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def trace() -> Trace:
    return Trace()


class FakeSearch:
    """Stands in for app.search.Search. Fixed results per query, fixed page for extract_url."""

    def __init__(self, results: dict | None = None, page: str = "", default: list | None = None):
        self.results: dict[str, list[dict]] = results or {}
        self.default: list[dict] = default or []  # returned for queries not in results
        self.page = page
        self.queries: list[str] = []
        self.extracted: list[str] = []

    async def search_web(self, query: str) -> list[dict]:
        self.queries.append(query)
        return list(self.results.get(query, self.default))

    async def extract_url(self, url: str) -> str:
        self.extracted.append(url)
        return self.page


def raw_result(url: str, content: str, score: float = 0.5, title: str = "T") -> dict:
    return {"url": url, "title": title, "content": content, "favicon": None, "score": score}


@pytest.fixture
def fake_search() -> FakeSearch:
    return FakeSearch()
