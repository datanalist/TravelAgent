from __future__ import annotations

from typing import AsyncIterator

from src.llm.config import LLMConfig
from src.llm.providers.base import LLMProvider, LLMResponse


def _build_provider(config: LLMConfig) -> LLMProvider:
    provider_name = config.provider.lower()
    if provider_name == "claude":
        from src.llm.providers.claude import ClaudeProvider
        return ClaudeProvider(api_key=config.anthropic_api_key, model=config.model)
    elif provider_name == "openai":
        from src.llm.providers.openai import OpenAIProvider
        return OpenAIProvider(api_key=config.openai_api_key, model=config.model)
    elif provider_name == "mistral":
        from src.llm.providers.mistral import MistralProvider
        return MistralProvider(api_key=config.mistral_api_key, model=config.model)
    else:
        raise ValueError(f"Неизвестный провайдер: {provider_name!r}. Допустимые: claude, openai, mistral")


class LLMConnector:
    """Единый async-интерфейс поверх всех LLM-провайдеров (ADR-006)."""

    def __init__(self, config: LLMConfig) -> None:
        self._config = config
        self._provider: LLMProvider = _build_provider(config)

    @property
    def provider_name(self) -> str:
        return self._config.provider

    @property
    def model(self) -> str:
        return self._config.model

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse:
        """Синхронный (не-стриминговый) вызов LLM.

        Resilience (retry / Circuit Breaker) применяется снаружи через resilience.py.
        """
        temp = temperature if temperature is not None else self._config.temperature_generation
        tokens = max_tokens if max_tokens is not None else self._config.max_tokens
        return await self._provider.complete(
            messages=messages,
            tools=tools,
            temperature=temp,
            max_tokens=tokens,
        )

    async def stream(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        """Стриминговый вызов LLM — async-генератор строк-токенов."""
        temp = temperature if temperature is not None else self._config.temperature_generation
        tokens = max_tokens if max_tokens is not None else self._config.max_tokens
        async for token in self._provider.stream(
            messages=messages,
            tools=tools,
            temperature=temp,
            max_tokens=tokens,
        ):
            yield token
