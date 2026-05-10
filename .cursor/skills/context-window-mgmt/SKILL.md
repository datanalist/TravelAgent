# Skill: context-window-mgmt

Управление контекст-окном LLM: сборка `messages` в правильном порядке + стратегия усечения при превышении лимитов токенов. Реализуется в `src/llm/context_builder.py` и используется во всех LLM-вызовах основного агента.

## Когда использовать

- При создании `src/llm/context_builder.py` (главный сборщик messages)
- При появлении нового источника контекста (например, vector retrieval)
- При деградации latency p95 — возможно, нужно агрессивнее усекать
- При росте стоимости диалога — усиление усечения / снижение `recent_messages` count

## Что делает

1. Принимает `AgentContext`: профиль, summary, recent messages, текущее сообщение, search-results.
2. Считает токены каждой секции (через `tiktoken` или провайдер-специфичный counter).
3. Собирает `messages` в каноническом порядке (см. ниже).
4. При превышении пороговых значений — применяет стратегию усечения по приоритету.
5. Возвращает финальный `list[Message]` для передачи в `LLM Connector`.

## Канонический порядок контекста

```text
1. [system_prompt]         ← роль, стиль, правила, scope (~600 токенов)
2. [client_profile]        ← бюджет, предпочтения, segment (~200 токенов)
3. [conversation_summary]  ← сжатая история из Summarizer (~300 токенов)
4. [recent_messages]       ← последние 3–5 сообщений (полные, ~1500 токенов)
5. [tool_observations]     ← результаты последних tool-calls (~500 токенов)
6. [current_message]       ← входящее сообщение пользователя
```

## Стратегия усечения (по `spec-memory-context.md` §7.3)

```python
total = count_tokens(all_sections)

if total > 12_000:
    # Уровень 1: расширенное сжатие
    recent_messages = recent_messages[-3:]  # 5 → 3 сообщения
    search_results = search_results[:5]     # top-N=5
    # conversation_summary заменяет полную историю

if total > 15_500:
    # Уровень 2: аварийное усечение
    drop(client_profile)  # оставить только ключевые факты в summary
    recent_messages = recent_messages[-2:]
    # system_prompt НИКОГДА не усекается
```

## Контракт (input → output)

```python
def build_agent_messages(
    context: AgentContext,
    *,
    max_context_tokens: int = 16_000,
    soft_limit: int = 12_000,
    hard_limit: int = 15_500,
) -> list[Message]:
    """returns ordered messages list, ready for LLM Connector"""

@dataclass
class AgentContext:
    system_prompt: str
    client_profile: dict | None
    conversation_summary: dict | None
    recent_messages: list[Message]   # 3–5 last
    tool_observations: list[Message] # из текущего tool-loop
    current_message: str
    search_results: list[Tour] | None  # для усечения top-N
```

## Правила и инварианты

- `system_prompt` — **никогда не усекается** (роль и запреты обязательны)
- `current_message` — **никогда не усекается** (это сам запрос)
- Порядок секций — **строго канонический** (не переставлять); важно для consistency и кэша провайдера
- `recent_messages`: 5 в нормальном режиме, 3 при `total > 12_000`, 2 при `total > 15_500`
- `search_tours` результаты — **усекаются до top-N=5** при > 10 совпадений (на стороне tool, не здесь — но context-builder должен это учитывать)
- Token counter — **per-provider** (Anthropic ≠ OpenAI ≠ Mistral); используй correct tokenizer
- Если после Уровня 2 `total > max_context_tokens` → возврат `ContextOverflowError` (Orchestrator решает: force-final или сжатие через ad-hoc Summarizer)
- Профиль клиента — **сериализуется в JSON** для system-сообщения (или вставляется в первое user-сообщение под маркером `[PROFILE]`)
- Conversation summary — структурированный JSON (`{client_facts, current_request, stage, last_shown_tours}`), не свободный текст
- Tool observations добавляются как `{role: "tool", content: <observation>, tool_call_id: <id>}` (формат OpenAI; провайдер-адаптер нормализует)
- При `client_profile = None` — не добавлять секцию вообще (не вставлять `null`)

## Бюджет токенов (типовой)

| Секция | Норма | Сжатие L1 | Сжатие L2 |
|---|---|---|---|
| system_prompt | 600 | 600 | 600 |
| client_profile | 200 | 200 | 0 (drop) |
| conversation_summary | 300 | 300 | 300 |
| recent_messages | 1500 (×5) | 900 (×3) | 600 (×2) |
| tool_observations | 500 | 300 | 200 |
| search_results | 1500 (top-10) | 750 (top-5) | 750 (top-5) |
| current_message | 200 | 200 | 200 |
| **Итого** | ~4800 | ~3250 | ~2650 |

(Запас остаётся под ответ ≤ 2000 токенов и буфер 1–2K.)

## Ограничения / SLA

| Параметр | Значение | Источник |
|---|---|---|
| Max context | 16 000 токенов | spec-memory-context §7.2 |
| Soft limit (L1 сжатие) | 12 000 токенов | spec-memory-context §7.3 |
| Hard limit (L2 сжатие) | 15 500 токенов | spec-memory-context §7.3 |
| Max recent_messages | 5 | системный лимит |
| Min recent_messages | 2 | сохранение коротко-срочного контекста |
| Top-N search_tours | 5 | spec-memory-context §7.2 |

## Используется агентами

- `agent-travel-llm` — **владелец реализации** (`src/llm/context_builder.py`)
- `agent-travel-backend` — потребитель в `src/orchestrator.py` (передаёт `AgentContext` → получает `messages`)

## Связанные документы

- `docs/specs/spec-memory-context.md` §7 (Context Window Management — основной источник)
- `docs/system-design.md` §5.5 (порядок контекста)
- `memory-bank/systemPatterns.md` (Context Window для LLM)
- `.cursor/skills/prompt-hardening/SKILL.md` (что обязательно в system_prompt)

## Статус

Backlog — реализация при разработке `src/llm/context_builder.py`.
