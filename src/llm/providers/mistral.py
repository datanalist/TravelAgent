from __future__ import annotations

import json
from typing import Any, AsyncIterator

from mistralai import Mistral
from mistralai.models import AssistantMessage, ChatCompletionResponse, UserMessage, SystemMessage

from src.llm.providers.base import LLMProvider, LLMResponse


def _to_mistral_messages(messages: list[dict]) -> list[Any]:
    """Нормализует messages в формат Mistral SDK."""
    result = []
    for msg in messages:
        role = msg["role"]
        content = msg["content"] if isinstance(msg["content"], str) else str(msg["content"])
        if role == "system":
            result.append(SystemMessage(content=content))
        elif role == "user":
            result.append(UserMessage(content=content))
        elif role == "assistant":
            result.append(AssistantMessage(content=content))
        else:
            result.append(UserMessage(content=content))
    return result


def _to_mistral_tools(tools: list[dict]) -> list[dict]:
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


def _extract_tool_calls(response: ChatCompletionResponse) -> list[dict]:
    calls = []
    choice = response.choices[0] if response.choices else None
    if not choice:
        return calls
    msg = choice.message
    if hasattr(msg, "tool_calls") and msg.tool_calls:
        for tc in msg.tool_calls:
            try:
                input_data = json.loads(tc.function.arguments) if tc.function.arguments else {}
            except (json.JSONDecodeError, ValueError):
                input_data = {}
            calls.append({
                "id": tc.id or "",
                "name": tc.function.name,
                "input": input_data,
            })
    return calls


class MistralProvider(LLMProvider):
    def __init__(self, api_key: str, model: str) -> None:
        self._client = Mistral(api_key=api_key)
        self._model = model

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        normalized = _to_mistral_messages(messages)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": normalized,
        }
        if tools:
            kwargs["tools"] = _to_mistral_tools(tools)
            kwargs["tool_choice"] = "auto"

        response: ChatCompletionResponse = await self._client.chat.complete_async(**kwargs)
        choice = response.choices[0] if response.choices else None
        content = ""
        if choice and hasattr(choice.message, "content") and choice.message.content:
            content = choice.message.content

        usage = response.usage
        return LLMResponse(
            content=content,
            tool_calls=_extract_tool_calls(response),
            usage={
                "input_tokens": usage.prompt_tokens if usage else 0,
                "output_tokens": usage.completion_tokens if usage else 0,
            },
            model=response.model or self._model,
            finish_reason=(choice.finish_reason.value if choice and choice.finish_reason else "stop"),
        )

    async def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None,
        temperature: float,
        max_tokens: int,
    ) -> AsyncIterator[str]:
        normalized = _to_mistral_messages(messages)

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": normalized,
        }
        if tools:
            kwargs["tools"] = _to_mistral_tools(tools)
            kwargs["tool_choice"] = "auto"

        async for event in await self._client.chat.stream_async(**kwargs):
            if event.data.choices:
                delta = event.data.choices[0].delta
                if hasattr(delta, "content") and delta.content:
                    yield delta.content
