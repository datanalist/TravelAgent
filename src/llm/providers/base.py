from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class LLMResponse:
    content: str
    tool_calls: list[dict]  # [{"name": str, "input": dict, "id": str}]
    usage: dict  # {"input_tokens": int, "output_tokens": int}
    model: str
    finish_reason: str = "stop"


class LLMProvider(ABC):
    @abstractmethod
    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse: ...

    @abstractmethod
    async def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]: ...
