import asyncio
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import httpx
from openai import (
    APIConnectionError,
    APIStatusError,
    AsyncOpenAI,
    RateLimitError,
)
from pydantic import BaseModel, ValidationError

from .config import StructuredMode
from .jsonutil import extract_json, inline_refs, strip_think
from .trace import Trace

T = TypeVar("T", bound=BaseModel)

log = logging.getLogger(__name__)

THINKING_MAX_TOKENS = 16384  # reasoning tokens count toward max_tokens
MAX_TOKENS_CAP = 32768  # ceiling when a truncated reply is retried with a bigger budget
MUST_CALL_SUBMIT = "You must call the submit tool with your final answer."
# A non-streamed reply arrives in one piece, so the read timeout must cover the whole
# generation (a long reasoning answer from the judge model). Connecting should be fast.
REQUEST_TIMEOUT = httpx.Timeout(90.0, connect=10.0)
# Transient API errors (connection, timeout, 429, 5xx) are retried here, not by the SDK, so
# the total time stays bounded: no new attempt starts after RETRY_BUDGET_S, which keeps one
# call inside the 240 s check timeout in the common case.
RETRY_DELAYS_S = (1.0, 3.0, 8.0)
RETRY_BUDGET_S = 120.0
MAX_RETRY_AFTER_S = 15.0
ECHO_MAX_CHARS = 4000  # how much of a bad reply is sent back in the repair turn
# Raw tool-call markup some chat templates leave in `content` when the server parser misses it.
XML_FUNCTION_RE = re.compile(r"<function=[^>]*>")
XML_PARAM_RE = re.compile(r"<parameter=([^>\s]+)>\s*(.*?)\s*</parameter>", re.S)


class StructuredOutputError(RuntimeError):
    pass


def _xml_tool_args(text: str) -> str | None:
    """Arguments from `<function=submit><parameter=x>v</parameter>…` text, as JSON, or None."""
    if not XML_FUNCTION_RE.search(text):
        return None
    args: dict[str, Any] = {}
    for name, value in XML_PARAM_RE.findall(text):
        try:
            args[name] = json.loads(value)
        except ValueError:
            args[name] = value
    return json.dumps(args) if args else None


def _load(raw: Any) -> Any:
    """JSON text -> Python value. Tolerates prose around it and JSON encoded twice."""
    for _ in range(3):
        if not isinstance(raw, str):
            return raw
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = json.loads(extract_json(raw))
    return raw


def parse_output[M: BaseModel](raw: Any, schema: type[M]) -> M:
    """Validate model output against schema.

    Also accepts the object wrapped in one extra key whose name is not a schema field, e.g.
    {"submit": {...}}, {"properties": {...}} or {"name": "submit", "arguments": {...}}.
    """
    obj = _load(raw)
    try:
        return schema.model_validate(obj)
    except ValidationError:
        if not isinstance(obj, dict) or set(obj) & set(schema.model_fields):
            raise
        inner = []
        for value in obj.values():
            try:
                value = _load(value)
            except ValueError:
                continue
            if isinstance(value, dict):
                inner.append(value)
        if len(inner) != 1:
            raise
        return schema.model_validate(inner[0])


def _is_transient(e: Exception) -> bool:
    """Connection errors and timeouts (APITimeoutError is a subclass), 408/409/429 and 5xx."""
    if isinstance(e, APIConnectionError):
        return True
    if isinstance(e, APIStatusError):
        return e.status_code in (408, 409, 429) or e.status_code >= 500
    return False


def _retry_after(e: Exception) -> float | None:
    """Seconds from a 429's Retry-After header, if any."""
    if not isinstance(e, RateLimitError):
        return None
    try:
        return float(e.response.headers.get("retry-after", ""))
    except (TypeError, ValueError):
        return None


def _candidates(msg: Any) -> list[str]:
    """Places the answer may be, best first: tool call, tool-call markup, content.

    The reasoning text is used only when the reply has nothing else.
    """
    found: list[str] = []
    if msg is None:
        return found
    if msg.tool_calls:
        found.append(msg.tool_calls[0].function.arguments or "")
    content = msg.content or ""
    if xml := _xml_tool_args(content):
        found.append(xml)
    if strip_think(content):
        found.append(content)
    if found:
        return found
    # Reasoning models sometimes put the final JSON only in their reasoning text.
    for field in ("reasoning_content", "reasoning"):
        text = getattr(msg, field, None)
        if isinstance(text, str) and text.strip():
            found.append(text)
            break
    return found


def _parse_message[M: BaseModel](msg: Any, schema: type[M]) -> M:
    candidates = _candidates(msg)
    if not candidates:
        raise ValueError("the reply was empty (no tool call and no content)")
    first_error: Exception | None = None
    for raw in candidates:
        try:
            return parse_output(raw, schema)
        except (ValidationError, ValueError, TypeError) as e:
            first_error = first_error or e
    assert first_error is not None
    raise first_error


def _repair_turn(msg: Any, error: Exception, mode: StructuredMode) -> list[dict]:
    """Messages that show the model its invalid reply and ask for a corrected one.

    A tool call is answered with a `tool` message tied to its id (the OpenAI tool-calling
    contract). Servers re-parse the arguments of earlier tool calls, so that form is used only
    when they are valid JSON; otherwise the bad reply is quoted in a user message.
    """
    problem = f"Your previous output was invalid: {str(error)[:500]}."
    hint = (
        "Reply again with only a JSON object that matches the schema exactly."
        if mode == "text_json"
        else "Call the submit tool again with arguments that match the schema exactly."
    )
    call = msg.tool_calls[0] if msg is not None and msg.tool_calls else None
    if call is not None:
        args = call.function.arguments or ""
        try:
            json.loads(args)
            valid_json = True
        except ValueError:
            valid_json = False
        if valid_json and len(args) <= ECHO_MAX_CHARS and getattr(call, "id", None):
            assistant = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.function.name or "submit", "arguments": args},
                    }
                ],
            }
            tool = {"role": "tool", "tool_call_id": call.id, "content": f"{problem} {hint}"}
            return [assistant, tool]
        previous = args
    else:
        previous = strip_think(msg.content if msg is not None else "")
    turn: list[dict] = []
    if previous.strip():
        turn.append({"role": "assistant", "content": previous[:ECHO_MAX_CHARS]})
    turn.append({"role": "user", "content": f"{problem} {hint}"})
    return turn


class LLM:
    """Token Factory client. Every model call in the app goes through structured()."""

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        *,
        modes: dict[str, StructuredMode] | None = None,
        thinking: dict[str, bool] | None = None,
        client: Any = None,
    ):
        # max_retries=0: _create() retries transient errors itself, within a time budget.
        self.client = client or AsyncOpenAI(
            base_url=base_url, api_key=api_key, timeout=REQUEST_TIMEOUT, max_retries=0
        )
        self.modes = modes or {}  # model id -> how to get structured output from it
        self.thinking = thinking or {}  # model id -> reasoning on/off (unset: model default)
        self.sleep: Callable[[float], Awaitable[None]] = asyncio.sleep  # tests replace it
        self.clock: Callable[[], float] = time.monotonic

    async def _create(self, step: str, **request: Any) -> Any:
        """One chat completion, retrying transient API errors with backoff."""
        started = self.clock()
        for attempt in range(len(RETRY_DELAYS_S) + 1):
            try:
                return await self.client.chat.completions.create(**request)
            except Exception as e:
                if not _is_transient(e) or attempt == len(RETRY_DELAYS_S):
                    raise
                delay = RETRY_DELAYS_S[attempt]
                if (hinted := _retry_after(e)) is not None:
                    delay = min(max(delay, hinted), MAX_RETRY_AFTER_S)
                if self.clock() - started + delay > RETRY_BUDGET_S:
                    raise
                log.warning(
                    "%s: transient API error (%s), retry %d in %.0f s",
                    step,
                    type(e).__name__,
                    attempt + 1,
                    delay,
                )
                await self.sleep(delay)
        raise AssertionError("unreachable")

    async def structured(
        self,
        *,
        trace: Trace,
        step: str,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int | None = None,
        mode: StructuredMode | None = None,
        thinking: bool | None = None,
    ) -> T:
        mode = mode or self.modes.get(model, "tool_forced")
        json_schema = inline_refs(schema.model_json_schema())
        # The schema goes in the prompt too: Nebius docs say prompt + parameter works better.
        system = (
            f"{system}\n\nYour answer must be a JSON object matching this schema:\n"
            f"{json.dumps(json_schema)}"
        )
        if mode == "tool_auto":
            system = f"{system}\n\n{MUST_CALL_SUBMIT}"
        elif mode == "text_json":
            system = f"{system}\n\nReply with only the JSON object, no other text."

        kwargs: dict[str, Any] = {}
        if thinking is None:
            thinking = self.thinking.get(model)
        if thinking is not None:
            kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": thinking}}
        max_tokens = max_tokens or (THINKING_MAX_TOKENS if thinking is not False else 4096)
        if mode != "text_json":
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": "submit",
                        "description": f"Submit the final {schema.__name__} result.",
                        "parameters": json_schema,
                    },
                }
            ]
            kwargs["tool_choice"] = (
                {"type": "function", "function": {"name": "submit"}}
                if mode == "tool_forced"
                else "auto"
            )

        messages: list[dict] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        last_error: Exception | None = None
        for _attempt in range(2):  # 1 try + 1 retry/repair; the SDK already retries API errors
            t0 = time.perf_counter()
            resp = await self._create(
                step,
                model=model,
                messages=messages,
                temperature=0.1,
                max_tokens=max_tokens,
                **kwargs,
            )
            trace.record(
                step=step,
                model=model,
                usage=getattr(resp, "usage", None),
                latency_s=time.perf_counter() - t0,
            )
            choice = resp.choices[0] if getattr(resp, "choices", None) else None
            msg = getattr(choice, "message", None)
            finish_reason = getattr(choice, "finish_reason", None)
            try:
                return _parse_message(msg, schema)
            except (ValidationError, ValueError, TypeError, AttributeError) as e:
                last_error = e
                log.warning(
                    "%s: invalid output (%s, finish_reason=%s): %r",
                    step,
                    e,
                    finish_reason,
                    "\n".join(_candidates(msg))[:2000],
                )
            if finish_reason == "length":
                # Cut off: a repair turn would be cut off too. Ask again with a bigger budget.
                last_error = StructuredOutputError(
                    f"reply cut off at max_tokens={max_tokens} ({last_error})"
                )
                # Without reasoning, a cut-off reply is usually a repetition loop, not a long
                # answer, so only reasoning calls get the bigger budget.
                if thinking is not False:
                    max_tokens = min(max_tokens * 2, MAX_TOKENS_CAP)
            elif msg is not None:
                messages = messages + _repair_turn(msg, last_error, mode)
        raise StructuredOutputError(f"{step}: model output invalid after repair: {last_error}")
