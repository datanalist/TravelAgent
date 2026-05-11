from __future__ import annotations

from typing import Any, AsyncIterator

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionChunk

from src.llm.providers.base import LLMProvider, LLMResponse


def _to_openai_messages(messages: list[dict]) -> list[dict]:
    """Нормализует messages в формат OpenAI Chat Completions."""
    result = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "tool_result":
            result.append({
                "role": "tool",
                "tool_call_id": msg.get("tool_call_id", ""),
                "content": content if isinstance(content, str) else str(content),
            })
        else:
            entry: dict[str, Any] = {"role": role}
            if isinstance(content, str):
                entry["content"] = content
            else:
                entry["content"] = str(content)
            if msg.get("tool_calls"):
                entry["tool_calls"] = msg["tool_calls"]
            result.append(entry)
    return result


def _to_openai_tools(tools: list[dict]) -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {"type": "object", "properties": {}}),
            },
        }
        for tool in tools
    ]


def _extract_tool_calls(completion: ChatCompletion) -> list[dict]:
    calls = []
    choice = completion.choices[0]
    if choice.message.tool_calls:
        for tc in choice.message.tool_calls:
            import json
            try:
                input_data = json.loads(tc.function.arguments)
            except (json.JSONDecodeError, ValueError):
                input_data = {}
            calls.append({
                "id": tc.id,
                "name": tc.function.name,
                "input": input_data,
            })
    return calls


class OpenAIProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        normalized = _to_openai_messages(messages)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": normalized,
        }
        if tools:
            kwargs["tools"] = _to_openai_tools(tools)
            kwargs["tool_choice"] = "auto"

        response: ChatCompletion = await self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        return LLMResponse(
            content=choice.message.content or "",
            tool_calls=_extract_tool_calls(response),
            usage={
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
            },
            model=response.model,
            finish_reason=choice.finish_reason or "stop",
        )

    async def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        normalized = _to_openai_messages(messages)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": normalized,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = _to_openai_tools(tools)
            kwargs["tool_choice"] = "auto"

        stream = await self._client.chat.completions.create(**kwargs)
        async for chunk in stream:
            chunk: ChatCompletionChunk
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
