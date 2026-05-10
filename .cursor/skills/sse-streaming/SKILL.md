# Skill: sse-streaming

Адаптация LLM-стрима в Server-Sent Events (SSE) для веб-канала. Преобразует чанки токенов от LLM Connector в формат `text/event-stream` согласно контракту.

## Когда использовать

- При реализации `src/channels/web.py` (endpoint `POST /chat/stream`)
- Когда нужно отдавать клиенту inkremental-ответ с метаданными (`intent`, `stage`)
- При интеграции LLM-стрима с FastAPI `StreamingResponse`

## Что делает

1. Получает async-итератор чанков от `LLM Connector`.
2. Каждый чанк → SSE-фрейм `data: {"token": "...", "done": false}\n\n`.
3. По завершении — финальный фрейм `data: {"done": true, "metadata": {...}}\n\n`.
4. Корректно закрывает соединение при `client disconnect` / cancel.

## Контракт (input → output)

Двухуровневый: источник чанков и адаптация в SSE — разные зоны ответственности.

```python
# Источник (agent-travel-llm, src/llm/streaming.py):
async def stream(messages, tools, ...) -> AsyncIterator[str]:
    """yields raw token strings from LLM provider"""

# SSE-адаптер (agent-travel-backend, src/channels/web.py):
async def sse_stream(
    chunks: AsyncIterator[str],
    metadata: dict,  # {intent, stage, tokens_used, latency_ms, ...}
) -> AsyncIterator[bytes]:
    """yields SSE frames in text/event-stream format"""
```

FastAPI:

```python
@router.post("/chat/stream")
async def chat_stream(...):
    return StreamingResponse(
        sse_stream(llm_chunks, metadata),
        media_type="text/event-stream",
    )
```

## Формат фреймов (techContext.md)

```
data: {"token": "Отличный", "done": false}\n\n
data: {"token": " выбор!", "done": false}\n\n
data: {"done": true, "metadata": {"intent": "discovery", "stage": "qualified"}}\n\n
```

## Правила и инварианты

- Между фреймами строго `\n\n` (требование SSE)
- JSON в одной строке (без переносов)
- Первый токен должен начать поступать клиенту в течение **2 с** (p50, `techContext.md`)
- Финальный фрейм `done: true` — обязателен (без него клиент не закроет стрим)
- `metadata` отдаётся **только** в финальном фрейме (не в каждом чанке)
- При client disconnect → отменяем underlying LLM-вызов через `asyncio.CancelledError`
- При ошибке LLM в середине стрима → последний фрейм `data: {"done": true, "error": "..."}` (без stack trace)
- Telegram канал — **не использует** SSE (полный ответ через `bot.send_message`)

## Ограничения / SLA

| Параметр | Значение | Источник |
|---|---|---|
| Latency p50 (first token) | ≤ 2 с | `techContext.md` |
| Media type | `text/event-stream` | RFC 6202 |
| Encoding | UTF-8 | — |

## Используется агентами

- `agent-travel-llm` — **источник чанков**: `LLM Connector.stream(...)` в `src/llm/streaming.py` (нормализация стрима провайдера к `AsyncIterator[str]`)
- `agent-travel-backend` — **SSE-адаптер**: `src/channels/web.py` упаковывает чанки в `text/event-stream` и подключает к `StreamingResponse`

## Связанные документы

- `memory-bank/techContext.md` (SSE формат, API endpoints)
- `memory-bank/systemPatterns.md` (ADR-005)
- `docs/specs/spec-orchestrator.md` (общий pipeline)
- `.cursor/skills/llm-provider-adapter/SKILL.md` (источник `AsyncIterator[str]` — `provider.stream(...)` нормализует чанки SDK)
- `.cursor/skills/circuit-breaker/SKILL.md` (стрим обёрнут в CB на уровне `LLM Connector`; при `CircuitOpenError` стрим прерывается с safe-replacement)
- ADR-005 — SSE для Web, полный ответ для Telegram

## Статус

Backlog — реализация навыка предстоит при разработке `src/channels/web.py`.
