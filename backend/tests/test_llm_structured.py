import json
from types import SimpleNamespace

import pytest

from app.llm import LLM, StructuredOutputError
from app.schemas import Verdict
from app.trace import Trace

VALID = {"label": "TRUE", "confidence": 90, "explanation": "ok", "cited_source_ids": [1]}
INVALID = {"label": "MAYBE", "confidence": 90, "explanation": "ok", "cited_source_ids": [1]}


def tool_reply(args: dict | str):
    raw = args if isinstance(args, str) else json.dumps(args)
    call = SimpleNamespace(function=SimpleNamespace(name="submit", arguments=raw))
    return _resp(SimpleNamespace(tool_calls=[call], content=None))


def text_reply(content: str):
    return _resp(SimpleNamespace(tool_calls=None, content=content))


def _resp(message):
    usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


class FakeOpenAI:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests: list[dict] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.requests.append(kwargs)
        return self.replies.pop(0)


async def call(client: FakeOpenAI, trace: Trace, **kw) -> Verdict:
    llm = LLM(client=client, modes=kw.pop("modes", None), thinking=kw.pop("thinking", None))
    return await llm.structured(
        trace=trace,
        step="verdict",
        model="nvidia/fast",
        system="sys",
        user="u",
        schema=Verdict,
        **kw,
    )


async def test_tool_call_arguments_parse():
    client, trace = FakeOpenAI(tool_reply(VALID)), Trace()
    v = await call(client, trace)
    assert v.label == "TRUE" and v.cited_source_ids == [1]
    req = client.requests[0]
    assert req["tool_choice"] == {"type": "function", "function": {"name": "submit"}}
    assert req["temperature"] == 0.1
    assert "$ref" not in json.dumps(req["tools"])


async def test_text_reply_with_json_parses():
    content = f"<think>reasoning</think>Sure: {json.dumps(VALID)}"
    v = await call(FakeOpenAI(text_reply(content)), Trace())
    assert v.confidence == 90


async def test_invalid_then_valid_repairs():
    client, trace = FakeOpenAI(tool_reply(INVALID), tool_reply(VALID)), Trace()
    v = await call(client, trace)
    assert v.label == "TRUE"
    repair = client.requests[1]["messages"][-1]
    assert repair["role"] == "user" and "invalid" in repair["content"]


async def test_invalid_twice_raises():
    client = FakeOpenAI(tool_reply(INVALID), text_reply("not json"))
    with pytest.raises(StructuredOutputError, match="verdict"):
        await call(client, Trace())
    assert len(client.requests) == 2  # never more than one repair


async def test_trace_recorded_for_each_attempt():
    trace = Trace(prices={"nvidia/fast": (1.0, 2.0)})
    await call(FakeOpenAI(tool_reply("{bad"), tool_reply(VALID)), trace)
    assert len(trace.entries) == 2
    e = trace.entries[0]
    assert (e.step, e.model, e.input_tokens, e.output_tokens) == ("verdict", "nvidia/fast", 100, 20)
    assert e.cost_usd == pytest.approx((100 * 1.0 + 20 * 2.0) / 1_000_000)


async def test_tool_auto_mode_from_model_setting():
    client = FakeOpenAI(tool_reply(VALID))
    await call(client, Trace(), modes={"nvidia/fast": "tool_auto"})
    req = client.requests[0]
    assert req["tool_choice"] == "auto"
    assert "must call the submit tool" in req["messages"][0]["content"]


async def test_text_json_mode_sends_no_tools():
    client = FakeOpenAI(text_reply(json.dumps(VALID)))
    v = await call(client, Trace(), mode="text_json")
    assert v.label == "TRUE"
    assert "tools" not in client.requests[0]
    assert '"confidence"' in client.requests[0]["messages"][0]["content"]  # schema in prompt


async def test_thinking_setting_sent_as_chat_template_kwargs():
    client = FakeOpenAI(tool_reply(VALID), tool_reply(VALID), tool_reply(VALID))
    await call(client, Trace(), thinking={"nvidia/fast": False})
    await call(client, Trace(), thinking={"nvidia/fast": True})
    await call(client, Trace())
    off, on, unset = client.requests
    assert off["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert off["max_tokens"] == 4096
    assert on["extra_body"] == {"chat_template_kwargs": {"enable_thinking": True}}
    assert on["max_tokens"] == 16384
    assert "extra_body" not in unset


async def test_thinking_per_call_overrides_model_setting():
    client = FakeOpenAI(tool_reply(VALID))
    llm = LLM(client=client, thinking={"nvidia/fast": False})
    await llm.structured(
        trace=Trace(),
        step="s",
        model="nvidia/fast",
        system="sys",
        user="u",
        schema=Verdict,
        thinking=True,
    )
    assert client.requests[0]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": True}}
