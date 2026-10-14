from collections.abc import Callable
from typing import Any

from .schemas import TraceEntry


class Trace:
    """Records every model call of one check: tokens, latency and cost."""

    def __init__(
        self,
        prices: dict[str, tuple[float, float]] | None = None,
        on_record: Callable[[TraceEntry], None] | None = None,
    ):
        self.prices = prices or {}  # model -> (USD per 1M input tokens, USD per 1M output tokens)
        self.on_record = on_record
        self.entries: list[TraceEntry] = []

    def cost(self, model: str, input_tokens: int | None, output_tokens: int | None) -> float | None:
        if model not in self.prices or input_tokens is None or output_tokens is None:
            return None
        price_in, price_out = self.prices[model]
        return (input_tokens * price_in + output_tokens * price_out) / 1_000_000

    def record(self, *, step: str, model: str, usage: Any, latency_s: float) -> TraceEntry:
        input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)
        entry = TraceEntry(
            step=step,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_s=round(latency_s, 3),
            cost_usd=self.cost(model, input_tokens, output_tokens),
        )
        self.entries.append(entry)
        if self.on_record:
            self.on_record(entry)
        return entry

    def totals(self) -> dict:
        return {
            "model_calls": len(self.entries),
            "input_tokens": sum(e.input_tokens or 0 for e in self.entries),
            "output_tokens": sum(e.output_tokens or 0 for e in self.entries),
            "cost_usd": round(sum(e.cost_usd or 0.0 for e in self.entries), 6),
        }
