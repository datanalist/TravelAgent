# Skill: output-validation

Проверка ответа LLM на утечку system prompt, признаки prompt injection и нарушение правил «No Hallucination» (упоминание цен/отелей вне `tool_results`). Третий уровень защиты после Input validation (security) и Prompt Hardening (`prompt-hardening` skill).

## Когда использовать

- При создании `src/llm/output_guard.py`
- При обнаружении утечки system prompt в production-логах
- При появлении нового шаблона prompt injection в evals
- При расширении set'а tools (новые источники данных, которые могут «утечь»)

## Что делает

Применяется к финальному `Response.content` ПЕРЕД отправкой клиенту:

1. **Regex-маркеры утечки system prompt:** ищет фрагменты типа «`Ты — AI-консьерж`», `[РОЛЬ]`, `[КАТЕГОРИЧЕСКИЕ ЗАПРЕТЫ]`, `[SCOPE]`.
2. **Маркеры jailbreak:** «`конечно, как admin`», `«режим разработчика»`, «`DAN`».
3. **Маркеры галлюцинаций (опционально):** упоминание цены / отеля / даты, которых НЕТ в `tool_results` контекста.
4. **Trim до `max_tokens`:** обрезание превышения по длине (доп. защита).
5. При срабатывании любого маркера — замена ответа на безопасный fallback и лог `error_type="output_guard_triggered"`.

## Контракт (input → output)

```python
def validate_output(
    response_text: str,
    *,
    tool_results: list[ToolResult] | None = None,
    max_tokens: int = 2000,
) -> ValidationResult:
    """non-mutating; returns flag + sanitized text"""

class ValidationResult(BaseModel):
    is_safe: bool
    sanitized_text: str   # либо оригинал, либо fallback
    triggered_rules: list[str]  # ["system_prompt_leak", "jailbreak_phrase", ...]
```

## Правила и инварианты

- Output validation — **последний** layer перед клиентом; срабатывает после tool-loop, до streaming/SSE
- Запуск **на каждый** ответ (не только high-risk) — стоит ~микросекунды
- Regex-pattern'ы хранить в **отдельном** файле (`src/llm/output_guard_patterns.py`) — для лёгкой подмены / расширения
- При срабатывании — **никогда** не пытаться «доочистить» текст: возвращай безопасный fallback («Извините, попробуйте переформулировать запрос.»)
- Лог срабатываний — **обязательно** (для дашборда `agent-travel-devops`); метрика `travelagent_output_guard_triggered_total{rule="..."}`
- Лог содержит **только** `triggered_rules` и hash оригинала, **никогда** полный текст с PII
- Hallucination-detection (сверка с `tool_results`) — **опционально и эвристично** (false positives возможны); для строгой проверки — `llm-as-judge` skill (`hallucination-judge`)
- Trim по `max_tokens` — мягкий (по последнему предложению), не «обрыв на полуслове»
- Для streaming-режима validation применяется **на финальном** аккумулированном тексте (не на каждом чанке) — но при detection стрим прерывается с safe-replacement

## Базовый набор regex-паттернов

```python
SYSTEM_PROMPT_LEAK = [
    r"Ты\s*[—-]\s*AI[-\s]?консьерж",
    r"\[РОЛЬ\]|\[SCOPE\]|\[КАТЕГОРИЧЕСКИЕ ЗАПРЕТЫ\]",
    r"system\s+prompt",
    r"Я не могу раскрыть.{0,40}системн",  # явное упоминание system prompt
]

JAILBREAK_PHRASES = [
    r"режим\s+разработчика",
    r"конечно,?\s+как\s+админ",
    r"DAN\s+режим",
    r"игнорирую\s+(все\s+)?предыдущ",
]

HALLUCINATION_HINTS = [  # if NO search_tours in tool_results
    r"\d{1,3}[\s\u00A0]?\d{3}\s*(руб|₽|RUB)",  # конкретная цена
    r"(отель|hotel)\s+[A-ZА-Я][\w\-\s]{2,30}\d?\*",  # «отель X 5*»
]
```

## Поведение при срабатывании

| Rule | Действие | Fallback ответ |
|---|---|---|
| `system_prompt_leak` | Полная замена | «Извините, я не могу обсуждать внутренние правила. Чем помочь по поездке?» |
| `jailbreak_phrase` | Полная замена | «Я остаюсь в роли консьержа турагентства. Расскажите, куда хотите поехать?» |
| `hallucination_hint` (нет `search_tours`) | Полная замена | «Уточняйте актуальные цены и наличие через `search_tours` или у менеджера.» |
| `length_overflow` | Soft trim по последнему `.` / `!` / `?` | (оригинал, обрезанный) |

## Eval-методология

- Golden dataset: ≥ 50 примеров (по 10 на каждое правило + контрольная группа без нарушений)
- Метрика: `recall ≥ 95%` для system_prompt_leak; `false_positive_rate ≤ 5%` суммарно
- Запуск при каждом изменении паттернов (`agent-travel-test`)

## Ограничения / SLA

| Параметр | Значение | Источник |
|---|---|---|
| Latency валидации | ≤ 5 мс | regex on-the-fly |
| Recall (system prompt leak) | ≥ 95% | внутренний таргет |
| False positive rate | ≤ 5% | внутренний таргет |
| Max tokens (post-trim) | 2000 | spec-serving-config §4 |

## Используется агентами

- `agent-travel-llm` — **владелец реализации** (`src/llm/output_guard.py`)
- `agent-travel-backend` — потребитель в `src/orchestrator.py` (вызывает перед стримом / отправкой)
- `agent-travel-security` — определяет требования (regex-паттерны утечки, jailbreak, perimeter защиты), `output-validation` явно указан в его §5 как используемый skill
- `agent-travel-test` — golden dataset + регрессионные тесты на новые паттерны

## Связанные документы

- `docs/system-design.md` §13.1 (Output Validation, Уровень 3)
- `docs/specs/spec-orchestrator.md` §8 (Guardrails)
- `docs/governance.md` (R1 — Prompt Injection, R2 — Галлюцинации)
- `.cursor/skills/prompt-hardening/SKILL.md` (Уровень 2 — system prompt)
- `.cursor/skills/llm-as-judge/SKILL.md` (строгая hallucination-eval)
- ADR-002 — No Hallucination

## Статус

Backlog — реализация при разработке `src/llm/output_guard.py`.
