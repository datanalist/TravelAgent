from __future__ import annotations

from typing import TYPE_CHECKING, AsyncIterator, Any

import anthropic

from src.llm.providers.base import LLMProvider, LLMResponse


def _to_anthropic_messages(messages: list[dict]) -> tuple[str | None, list[dict]]:
    """Разделяет system-сообщение и нормализует остальные."""
    system: str | None = None
    normalized: list[dict] = []
    for msg in messages:
        if msg["role"] == "system":
            system = msg["content"] if isinstance(msg["content"], str) else str(msg["content"])
        else:
            normalized.append({"role": msg["role"], "content": msg["content"]})
    return system, normalized


def _to_anthropic_tools(tools: list[dict]) -> list[dict]:
    """Конвертирует generic tool schemas в формат Anthropic ToolParam."""
    result = []
    for tool in tools:
        result.append({
            "name": tool["name"],
            "description": tool.get("description", ""),
            "input_schema": tool.get("input_schema", {"type": "object", "properties": {}}),
        })
    return result


def _extract_tool_calls(response: anthropic.types.Message) -> list[dict]:
    calls = []
    for block in response.content:
        if block.type == "tool_use":
            calls.append({
                "id": block.id,
                "name": block.name,
                "input": block.input,
            })
    return calls


def _extract_text(response: anthropic.types.Message) -> str:
    parts = []
    for block in response.content:
        if block.type == "text":
            parts.append(block.text)
    return "".join(parts)


class ClaudeProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        system, normalized_messages = _to_anthropic_messages(messages)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": normalized_messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = _to_anthropic_tools(tools)

        response = await self._client.messages.create(**kwargs)

        return LLMResponse(
            content=_extract_text(response),
            tool_calls=_extract_tool_calls(response),
            usage={
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
            model=response.model,
            finish_reason=response.stop_reason or "stop",
        )

    async def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        system, normalized_messages = _to_anthropic_messages(messages)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": normalized_messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = _to_anthropic_tools(tools)

        async with self._client.messages.stream(**kwargs) as stream_ctx:
            async for text_chunk in stream_ctx.text_stream:
                yield text_chunk
