from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone

from src.llm.providers.base import LLMResponse


_COST_PER_TOKEN: dict[str, dict[str, float]] = {
    "claude-3-5-sonnet-20241022": {"input": 3.0 / 1_000_000, "output": 15.0 / 1_000_000},
    "gpt-4o": {"input": 2.5 / 1_000_000, "output": 10.0 / 1_000_000},
    "mistral-large-latest": {"input": 2.0 / 1_000_000, "output": 6.0 / 1_000_000},
}

_MODEL_FAMILY_PREFIXES: list[tuple[str, str]] = [
    ("claude-3-5-sonnet", "claude-3-5-sonnet-20241022"),
    ("gpt-4o", "gpt-4o"),
    ("mistral-large", "mistral-large-latest"),
]


def _resolve_cost_key(model: str) -> str:
    if model in _COST_PER_TOKEN:
        return model
    for prefix, key in _MODEL_FAMILY_PREFIXES:
        if model.startswith(prefix):
            return key
    return ""


def calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    key = _resolve_cost_key(model)
    rates = _COST_PER_TOKEN.get(key, {"input": 0.0, "output": 0.0})
    return input_tokens * rates["input"] + output_tokens * rates["output"]


@dataclass
class UsageRecord:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    monotonic_ts: float = field(default_factory=time.monotonic)


class UsageTracker:
    """Трекер токенов и стоимости в памяти за скользящее окно."""

    def __init__(self, window_minutes: int = 60) -> None:
        self._window_seconds = window_minutes * 60
        self._records: deque[UsageRecord] = deque()

    def record(self, response: LLMResponse, provider: str) -> UsageRecord:
        input_tokens = response.usage.get("input_tokens", 0)
        output_tokens = response.usage.get("output_tokens", 0)
        cost = calculate_cost(response.model, input_tokens, output_tokens)

        rec = UsageRecord(
            provider=provider,
            model=response.model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
        self._records.append(rec)
        self._evict_old()
        return rec

    def _evict_old(self) -> None:
        cutoff = time.monotonic() - self._window_seconds
        while self._records and self._records[0].monotonic_ts < cutoff:
            self._records.popleft()

    def get_stats(self) -> dict:
        self._evict_old()
        total_input = sum(r.input_tokens for r in self._records)
        total_output = sum(r.output_tokens for r in self._records)
        total_cost = sum(r.cost_usd for r in self._records)
        by_provider: dict[str, dict] = {}
        for r in self._records:
            p = by_provider.setdefault(r.provider, {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0})
            p["input_tokens"] += r.input_tokens
            p["output_tokens"] += r.output_tokens
            p["cost_usd"] += r.cost_usd

        return {
            "total_input_tokens": total_input,
            "total_output_tokens": total_output,
            "total_cost_usd": round(total_cost, 6),
            "records_count": len(self._records),
            "by_provider": by_provider,
            # Имена метрик Prometheus (источник для agent-travel-devops)
            "travelagent_llm_tokens_total": total_input + total_output,
            "travelagent_llm_cost_usd_total": round(total_cost, 6),
        }
