import json
import time
from typing import Any, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

from .config import StructuredMode
from .jsonutil import extract_json, inline_refs
from .trace import Trace

T = TypeVar("T", bound=BaseModel)

MUST_CALL_SUBMIT = "You must call the submit tool with your final answer."


class StructuredOutputError(RuntimeError):
    pass


class LLM:
    """Token Factory client. Every model call in the app goes through structured()."""

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        *,
        modes: dict[str, StructuredMode] | None = None,
        client: Any = None,
    ):
        self.client = client or AsyncOpenAI(
            base_url=base_url, api_key=api_key, timeout=90, max_retries=2
        )
        self.modes = modes or {}  # model id -> how to get structured output from it

    async def structured(
        self,
        *,
        trace: Trace,
        step: str,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        max_tokens: int = 4096,
        mode: StructuredMode | None = None,
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

        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        last_error: Exception | None = None
        for _attempt in range(2):  # 1 try + 1 repair; the SDK already retries network errors
            t0 = time.perf_counter()
            resp = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.1,
                max_tokens=max_tokens,
                **kwargs,
            )
            trace.record(
                step=step, model=model, usage=resp.usage, latency_s=time.perf_counter() - t0
            )
            msg = resp.choices[0].message
            try:
                if msg.tool_calls:
                    raw = msg.tool_calls[0].function.arguments
                else:
                    raw = extract_json(msg.content or "")
                return schema.model_validate_json(raw)
            except (ValidationError, ValueError, TypeError, IndexError, AttributeError) as e:
                last_error = e
                retry_hint = (
                    "Reply again with only a JSON object that matches the schema exactly."
                    if mode == "text_json"
                    else "Call the submit tool again with arguments that match the schema exactly."
                )
                messages.append(
                    {
                        "role": "user",
                        "content": f"Your previous output was invalid: {str(e)[:500]}. "
                        + retry_hint,
                    }
                )
        raise StructuredOutputError(f"{step}: model output invalid after repair: {last_error}")
