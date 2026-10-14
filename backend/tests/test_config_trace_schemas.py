from types import SimpleNamespace

import pytest

from app.config import Settings, startup_problems
from app.schemas import CheckRequest, validate_check_request
from app.trace import Trace


def settings(**kw) -> Settings:
    base = dict(
        nebius_api_key="k", tavily_api_key="t", model_fast="nvidia/fast", model_judge="nvidia/judge"
    )
    return Settings(_env_file=None, **(base | kw))


def test_defaults_match_env_example():
    s = Settings(_env_file=None)
    assert s.max_claims == 3 and s.tavily_search_depth == "basic"
    assert s.structured_mode_fast == "tool_forced"
    assert s.nebius_base_url == "https://api.tokenfactory.nebius.com/v1/"


def test_valid_settings_have_no_problems():
    assert startup_problems(settings()) == []


def test_missing_keys_reported():
    problems = startup_problems(settings(nebius_api_key="", tavily_api_key=" "))
    assert "NEBIUS_API_KEY is not set" in problems and "TAVILY_API_KEY is not set" in problems


def test_same_models_rejected():
    assert any("different" in p for p in startup_problems(settings(model_judge="nvidia/fast")))


def test_non_nvidia_model_rejected():
    assert any("NVIDIA" in p for p in startup_problems(settings(model_judge="meta/llama")))


def test_trace_totals_and_unknown_price():
    trace = Trace(prices={"nvidia/fast": (0.06, 0.24)})
    usage = SimpleNamespace(prompt_tokens=1_000_000, completion_tokens=1_000_000)
    trace.record(step="a", model="nvidia/fast", usage=usage, latency_s=1.23456)
    trace.record(step="b", model="nvidia/other", usage=usage, latency_s=1.0)
    trace.record(step="c", model="nvidia/fast", usage=None, latency_s=1.0)
    assert trace.entries[0].cost_usd == pytest.approx(0.30)
    assert trace.entries[0].latency_s == 1.235
    assert trace.entries[1].cost_usd is None and trace.entries[2].cost_usd is None
    assert trace.totals() == {
        "model_calls": 3,
        "input_tokens": 2_000_000,
        "output_tokens": 2_000_000,
        "cost_usd": 0.3,
    }


def test_trace_on_record_callback():
    seen = []
    Trace(on_record=seen.append).record(step="s", model="m", usage=None, latency_s=0)
    assert len(seen) == 1


@pytest.mark.parametrize(
    "req",
    [
        CheckRequest(),
        CheckRequest(text="a" * 30, url="https://x.com"),
        CheckRequest(text="   too short   "),
        CheckRequest(text="a" * 101),
        CheckRequest(url="ftp://x.com/file"),
        CheckRequest(url="https://x.com/" + "a" * 2000),
    ],
)
def test_bad_requests_rejected(req):
    with pytest.raises(ValueError):
        validate_check_request(req, max_input_chars=100)


def test_good_requests_trimmed():
    assert validate_check_request(CheckRequest(text="  " + "a" * 30 + " "), 100).text == "a" * 30
    assert validate_check_request(CheckRequest(url=" https://x.com "), 100).url == "https://x.com"
