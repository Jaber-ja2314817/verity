import json
from types import SimpleNamespace

import httpx
import openai
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


# ---- robustness ----

WRAPPED = [
    {"submit": VALID},
    {"properties": VALID},
    {"name": "submit", "arguments": VALID},
    {"name": "submit", "arguments": json.dumps(VALID)},
    json.dumps(json.dumps(VALID)),  # JSON encoded twice
]


def reply(message, finish_reason="stop"):
    usage = SimpleNamespace(prompt_tokens=100, completion_tokens=20)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice], usage=usage)


def message(tool_args: str | None = None, content: str | None = None, call_id: str | None = None,
            **extra):  # fmt: skip
    calls = None
    if tool_args is not None:
        fn = SimpleNamespace(name="submit", arguments=tool_args)
        calls = [SimpleNamespace(id=call_id, function=fn)]
    return SimpleNamespace(tool_calls=calls, content=content, **extra)


@pytest.mark.parametrize("args", WRAPPED)
async def test_wrapped_tool_arguments_are_unwrapped(args):
    raw = args if isinstance(args, str) else json.dumps(args)
    client = FakeOpenAI(tool_reply(raw))
    v = await call(client, Trace())
    assert v.label == "TRUE" and len(client.requests) == 1


async def test_wrapper_with_schema_field_is_not_unwrapped():
    client = FakeOpenAI(tool_reply({"label": "MAYBE", "x": VALID}), tool_reply(VALID))
    await call(client, Trace())
    assert len(client.requests) == 2  # invalid object with a real field: repaired, not guessed


async def test_tool_call_markup_in_content_is_parsed():
    content = f"<tool_call>{json.dumps({'name': 'submit', 'arguments': VALID})}</tool_call>"
    v = await call(FakeOpenAI(reply(message(content=content))), Trace())
    assert v.label == "TRUE"


async def test_xml_tool_call_markup_in_content_is_parsed():
    content = (
        "<tool_call>\n<function=submit>\n<parameter=label>\nTRUE\n</parameter>\n"
        "<parameter=confidence>\n90\n</parameter>\n<parameter=explanation>\nok\n</parameter>\n"
        "<parameter=cited_source_ids>\n[1]\n</parameter>\n</function>\n</tool_call>"
    )
    v = await call(FakeOpenAI(reply(message(content=content))), Trace())
    assert (v.label, v.confidence, v.cited_source_ids) == ("TRUE", 90, [1])


async def test_json_only_in_reasoning_content_is_used():
    msg = message(content="", reasoning_content=f"Final: {json.dumps(VALID)}")
    v = await call(FakeOpenAI(reply(msg)), Trace())
    assert v.label == "TRUE"


async def test_reasoning_ignored_when_tool_call_present():
    msg = message(tool_args=json.dumps(INVALID), reasoning_content=json.dumps(VALID))
    client = FakeOpenAI(reply(msg), tool_reply(VALID))
    await call(client, Trace())
    assert len(client.requests) == 2  # the invalid tool call is repaired, not replaced


async def test_empty_choices_retried_without_repair_message():
    empty = SimpleNamespace(choices=[], usage=None)
    client, trace = FakeOpenAI(empty, tool_reply(VALID)), Trace()
    v = await call(client, trace)
    assert v.label == "TRUE"
    assert len(client.requests[1]["messages"]) == 2
    assert len(trace.entries) == 2


async def test_cut_off_reply_retried_with_bigger_budget():
    cut = reply(message(tool_args='{"label": "TR'), finish_reason="length")
    client = FakeOpenAI(cut, tool_reply(VALID))
    v = await call(client, Trace(), thinking={"nvidia/fast": True})
    assert v.label == "TRUE"
    first, second = client.requests
    assert second["max_tokens"] == 2 * first["max_tokens"]
    assert second["messages"] == first["messages"]  # fresh try, no repair turn


async def test_cut_off_without_reasoning_keeps_budget():
    cut = reply(message(content=" " * 50), finish_reason="length")
    client = FakeOpenAI(cut, cut)
    with pytest.raises(StructuredOutputError, match="cut off"):
        await call(client, Trace(), thinking={"nvidia/fast": False})
    assert client.requests[0]["max_tokens"] == client.requests[1]["max_tokens"] == 4096


async def test_repair_answers_tool_call_with_tool_message():
    bad = reply(message(tool_args=json.dumps(INVALID), call_id="call_1"))
    client = FakeOpenAI(bad, tool_reply(VALID))
    await call(client, Trace())
    assistant, tool = client.requests[1]["messages"][-2:]
    assert assistant["role"] == "assistant"
    assert assistant["tool_calls"][0]["id"] == "call_1"
    assert assistant["tool_calls"][0]["function"]["arguments"] == json.dumps(INVALID)
    assert tool["role"] == "tool" and tool["tool_call_id"] == "call_1"
    assert "invalid" in tool["content"]


async def test_repair_quotes_non_json_tool_args_in_user_turn():
    bad = reply(message(tool_args="{bad", call_id="call_1"))
    client = FakeOpenAI(bad, tool_reply(VALID))
    await call(client, Trace())
    assistant, user = client.requests[1]["messages"][-2:]
    assert assistant == {"role": "assistant", "content": "{bad"}
    assert user["role"] == "user" and "invalid" in user["content"]


# ---- transient API errors ----

URL = "https://api.example/v1/chat/completions"


def connection_error() -> Exception:
    return openai.APIConnectionError(request=httpx.Request("POST", URL))


def status_error(code: int, headers: dict | None = None) -> Exception:
    response = httpx.Response(code, headers=headers, request=httpx.Request("POST", URL))
    cls = {429: openai.RateLimitError, 400: openai.BadRequestError}.get(
        code, openai.InternalServerError
    )
    return cls("boom", response=response, body=None)


class FlakyOpenAI(FakeOpenAI):
    async def _create(self, **kwargs):
        self.requests.append(kwargs)
        item = self.replies.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def flaky_llm(*replies) -> tuple[LLM, FlakyOpenAI, list[float]]:
    client = FlakyOpenAI(*replies)
    llm = LLM(client=client)
    slept: list[float] = []

    async def sleep(s: float) -> None:
        slept.append(s)

    llm.sleep = sleep
    return llm, client, slept


async def run(llm: LLM) -> Verdict:
    return await llm.structured(
        trace=Trace(), step="s", model="nvidia/fast", system="sys", user="u", schema=Verdict
    )


async def test_transient_errors_are_retried_with_backoff():
    llm, client, slept = flaky_llm(connection_error(), status_error(503), tool_reply(VALID))
    assert (await run(llm)).label == "TRUE"
    assert len(client.requests) == 3 and slept == [1.0, 3.0]


async def test_timeout_is_retried():
    timeout = openai.APITimeoutError(request=httpx.Request("POST", URL))
    llm, client, _ = flaky_llm(timeout, tool_reply(VALID))
    assert (await run(llm)).label == "TRUE"


async def test_rate_limit_honours_retry_after():
    llm, _, slept = flaky_llm(status_error(429, {"retry-after": "6"}), tool_reply(VALID))
    await run(llm)
    assert slept == [6.0]


async def test_bad_request_is_not_retried():
    llm, client, _ = flaky_llm(status_error(400), tool_reply(VALID))
    with pytest.raises(openai.BadRequestError):
        await run(llm)
    assert len(client.requests) == 1


async def test_retries_give_up_after_last_delay():
    llm, client, slept = flaky_llm(*[connection_error() for _ in range(4)])
    with pytest.raises(openai.APIConnectionError):
        await run(llm)
    assert len(client.requests) == 4 and slept == [1.0, 3.0, 8.0]


async def test_retries_stop_at_time_budget():
    llm, client, slept = flaky_llm(connection_error(), tool_reply(VALID))
    now = [0.0]
    llm.clock = lambda: now[0]

    async def slow_call(**kwargs):
        client.requests.append(kwargs)
        now[0] += 200.0  # the first attempt hung until its timeout
        raise connection_error()

    client.chat.completions.create = slow_call
    with pytest.raises(openai.APIConnectionError):
        await run(llm)
    assert len(client.requests) == 1 and slept == []


def test_sdk_client_does_not_retry_itself():
    llm = LLM("https://api.example/v1/", "k")
    assert llm.client.max_retries == 0
    assert llm.client.timeout.connect == 10.0
