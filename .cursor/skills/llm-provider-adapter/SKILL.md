# Skill: llm-provider-adapter

Реализация адаптера под конкретный LLM-провайдер (Anthropic Claude / OpenAI / Mistral) поверх абстрактного `LLMProvider`. Нормализует request и response (`tool_calls`, `usage`, `finish_reason`, streaming) к единому формату для `LLM Connector`.

## Когда использовать

- При создании файла `src/llm/providers/{claude,openai,mistral}.py`
- При добавлении нового LLM-провайдера в проект
- При изменении версии SDK провайдера (миграция, breaking changes)
- Когда нужно прокинуть новый параметр через все провайдеры (например, `top_p`, `seed`)

## Что делает

1. Реализует абстрактный `LLMProvider(base.py)`: `complete()` и `stream()`.
2. Принимает унифицированный вход: `messages: list[Message]`, `tools: list[ToolSchema]`, `temperature`, `max_tokens`.
3. Транслирует в нативный формат SDK провайдера (Anthropic `Messages API` / OpenAI `chat.completions` / Mistral `chat`).
4. Парсит ответ в единый `Response{content, tool_calls, finish_reason, usage}`.
5. Для `stream()` — возвращает `AsyncIterator[str]` (только текстовые токены; tool_calls собираются и отдаются финальным событием).
6. Подсчёт токенов и стоимости — пишет в `usage` (input/output tokens + cost_usd по тарифу провайдера).

## Контракт (input → output)

```python
class LLMProvider(ABC):
    name: str

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> Response: ...

    @abstractmethod
    def stream(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> AsyncIterator[StreamChunk]: ...

class Response(BaseModel):
    content: str | None
    tool_calls: list[ToolCall]
    finish_reason: Literal["stop", "tool_calls", "length", "error"]
    usage: Usage  # tokens_in, tokens_out, cost_usd
```

## Правила и инварианты

- LLM SDK (`anthropic`, `openai`, `mistralai`) импортируется **только** в этом модуле — нигде больше в проекте (`agent-travel-llm.md` §6 инварианты)
- Нативные типы SDK **не выходят** за пределы адаптера — всегда нормализуй в `Response` / `Message` / `ToolCall`
- API-ключ читается из ENV (`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `MISTRAL_API_KEY`) через `pydantic-settings`, не hardcode
- Дефолты температур: `0.7` (generation), `0.1` (tool-call/Router) — берутся из `LLM_TEMPERATURE_*` ENV
- `max_tokens` ≤ `2000` (контроль стоимости, `spec-serving-config.md` §4)
- Все вызовы `async`; никаких блокирующих SDK-методов
- Адаптер **не реализует** retry / Circuit Breaker — это `circuit-breaker` skill, обёртка снаружи (в `LLM Connector`)
- Для `stream()`: tool_calls собираются inline (по дельтам) и эмитятся финальным `StreamChunk(done=True, tool_calls=...)`
- При получении ошибки SDK — пробрось как `LLMProviderError(provider, code, retriable: bool)`; `retriable=True` для timeout / 5xx / network, `False` для 400/401/422
- Cost calculation использует тариф из `usage.py` (per provider/model); если модель неизвестна — `cost_usd = 0` + warning лог

## Ограничения / SLA

| Параметр | Значение | Источник |
|---|---|---|
| First token latency (p50) | ≤ 2 с | techContext.md |
| Max tokens / response | 2000 | spec-serving-config §4 |
| Temperature range | 0.0 (детерминизм) — 1.0 | spec-orchestrator §9 |
| Поддерживаемые роли в `Message` | `system`, `user`, `assistant`, `tool` | OpenAI/Anthropic общий минимум |

## Используется агентами

- `agent-travel-llm` — **владелец реализации** (`src/llm/providers/*`)

## Связанные документы

- `docs/specs/spec-serving-config.md` §4 (LLM провайдеры, retry политика)
- `docs/system-design.md` §7.2 (LLM APIs, ADR-006)
- `memory-bank/techContext.md` (стек LLM, ENV-переменные)
- `.cursor/skills/circuit-breaker/SKILL.md` (внешняя обёртка над адаптером в `LLM Connector`)
- `.cursor/skills/sse-streaming/SKILL.md` (потребитель: `provider.stream()` → SSE-форматтер backend)
- `.cursor/skills/context-window-mgmt/SKILL.md` (поставщик `messages` для `complete()` / `stream()`)
- ADR-006 — Абстракция над LLM-провайдерами

## Статус

Backlog — реализация навыка предстоит при разработке `src/llm/providers/`.
