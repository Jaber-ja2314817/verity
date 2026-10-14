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
