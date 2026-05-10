# Skill: decision-matrix

Реализация rule-based матрицы Decision Logic: на вход — `(stage, intent)`, на выход — `(target_stage, action, available_tools)`. Без LLM-вызовов.

## Когда использовать

- При реализации `src/decision.py`
- Когда нужно определить, какие tools разрешить LLM на текущем шаге
- При расширении воронки стадий или intent-типов

## Что делает

Реализует паттерн **Guided Agent** (ADR-004):

- Decision Logic не вызывает tools напрямую и не управляет LLM
- Определяет **область допустимых действий** для LLM
- LLM сам решает, какие tools из `available_tools` вызвать и с какими параметрами
- Также вычисляет переход воронки (`current_stage → target_stage`) и рекомендуемое `action`

## Контракт (input → output)

```python
def decide(stage: Stage, intent: Intent, profile: ClientProfile) -> Decision:
    """
    Decision = {
        target_stage: Stage,
        action: str,                  # рекомендуемое поведение для LLM
        available_tools: list[str],   # подмножество зарегистрированных tools
    }
    """
```

## Правила и инварианты

### Воронка стадий (spec-orchestrator §4)

```
cold → discovery → qualified → proposal → objection ──┐
  ▲                                │                   │
  │                                ▼                   │
follow_up                       closing ◄──────────────┘
```

| Переход | Условие |
|---|---|
| `cold → discovery` | Любой входящий запрос |
| `discovery → qualified` | Бюджет + направление в профиле |
| `qualified → proposal` | После успешного `search_tours` |
| `proposal → objection` | Intent = `objection` |
| `proposal/objection → closing` | Явное согласие клиента |
| `follow_up → discovery` | Возврат после паузы |

### Матрица доступности tools (spec-tools-api §6)

| Tool | cold | discovery | qualified | proposal | objection | closing |
|---|---|---|---|---|---|---|
| `search_tours` | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| `get_client_profile` | ✓ | ✓ | ✓ | — | — | — |
| `update_client_profile` | — | — | ✓ | ✓ | — | — |
| `get_policy_info` | ✓ | ✓ | ✓ | — | — | — |
| `create_lead` | — | — | — | ✓ | — | ✓ |
| `update_lead_stage` | — | — | — | — | ✓ | ✓ |
| `log_interaction` | — | — | — | — | — | — | (никогда не передаётся LLM) |

### Инварианты

- **Чисто детерминирован** — никаких LLM-вызовов внутри `decision.py`
- **Idempotent** — одни и те же входы → один и тот же выход
- **Side-effect free** — не пишет в БД, не логирует business-события
- `log_interaction` **никогда** не попадает в `available_tools`
- Любой неизвестный intent → fallback `discovery`
- Любая неизвестная stage → fallback `cold`

## Ограничения / SLA

- Latency: < 1 мс (in-memory lookup)
- Без внешних зависимостей (нет I/O)

## Используется агентами

- `agent-travel-backend`

## Связанные документы

- `docs/specs/spec-orchestrator.md` §4 (Decision Logic, матрица переходов)
- `docs/specs/spec-tools-api.md` §6 (матрица доступности tools)
- `memory-bank/systemPatterns.md` (Guided Agent)
- `.cursor/skills/few-shot-router/SKILL.md` (источник `intent` — входной параметр `decide()`)
- ADR-004 — Guided Agent pattern

## Статус

Backlog — реализация навыка предстоит при разработке `src/decision.py`.
