# Skill: tool-calling-loop

Реализация ReAct-цикла оркестрации между LLM и набором tools с жёстким лимитом шагов и graceful-завершением.

## Когда использовать

- При реализации `src/orchestrator.py` (главный цикл агента)
- Когда нужно вызывать LLM, обрабатывать `tool_calls`, добавлять observation и повторять
- Любая задача, где LLM получает `available_tools` и принимает решения о вызовах

## Что делает

Цикл ReAct:

1. Собирает initial messages из контекста (system, profile, summary, recent, current).
2. Вызывает `llm.complete(messages, tools=available_tools)`.
3. Если `finish_reason == "stop"` → возвращает финальный ответ.
4. Если есть `tool_calls` → выполняет каждый, добавляет observation в messages.
5. Инкрементирует счётчик шагов; при `steps > MAX_STEPS` (= 5) — форсирует финальный ответ директивой «сформируй ответ из имеющихся данных».
6. При ошибке tool → добавляет `error_observation`, продолжает (graceful).

## Контракт (input → output)

```python
async def run_agent(context: AgentContext) -> AgentResult:
    """
    context: client_id, session_id, messages, available_tools, llm_connector, executor
    returns: AgentResult(final_text, steps, tools_called, tokens_used, latency_ms)
    """
```

## Правила и инварианты

- `MAX_STEPS = 5` (ADR-007, `spec-orchestrator.md` §9) — нарушать запрещено
- LLM передаются **только** `available_tools` от Decision Logic — не весь набор (ADR-004)
- `log_interaction` **никогда** не входит в `available_tools` (`spec-tools-api.md` §2.7)
- При `MAX_STEPS` превышен — повторный LLM-вызов с `force_final_prompt`, не raise
- Любая ошибка tool → `error_observation` в messages, цикл продолжается
- Каждый tool оборачивается в `asyncio.wait_for(...)` с таймаутом из `spec-tools-api.md` §3
- Несколько `tool_calls` в одном response → выполнять параллельно через `asyncio.gather`
- Счётчик шагов и список `tools_called` записываются в `InteractionEvent` (для `log_interaction`)

## Ограничения / SLA

| Параметр | Значение | Источник |
|---|---|---|
| Max steps | 5 | ADR-007 |
| Latency p95 (полный ответ) | ≤ 15 с | `techContext.md` |
| Параллелизм tool-calls в одном шаге | без лимита (но осторожно с DB) | — |

## Используется агентами

- `agent-travel-backend`

## Связанные документы

- `docs/specs/spec-orchestrator.md` §5 (псевдокод цикла)
- `docs/specs/spec-orchestrator.md` §6 (stop conditions)
- `docs/specs/spec-orchestrator.md` §7 (retry / fallback)
- `memory-bank/systemPatterns.md` (Tool-Calling Loop)
- `.cursor/skills/circuit-breaker/SKILL.md` (обёртка над каждым LLM-вызовом цикла; уже встроена в `LLM Connector`)
- `.cursor/skills/context-window-mgmt/SKILL.md` (сборка messages перед каждым шагом цикла, в т.ч. при добавлении observations)
- `.cursor/skills/output-validation/SKILL.md` (валидация финального ответа перед возвратом из цикла)
- ADR-004, ADR-007

## Статус

Backlog — реализация навыка предстоит при разработке `src/orchestrator.py`.
