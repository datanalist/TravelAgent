# Skill: few-shot-router

Дизайн few-shot промпта для intent-классификации (Router) с JSON-schema валидацией ответа. Используется в `src/router.py` через `LLM Connector` для определения интента входящего сообщения.

## Когда использовать

- При создании / правке `src/llm/prompts/router_prompt.py`
- При добавлении нового интента в проект (расширение enum)
- При деградации точности Router < 85% (необходима калибровка few-shot)
- Когда нужно подменить дорогой Claude на дешёвый Mistral для Router (экономия)

## Что делает

1. Собирает system-промпт с описанием 7 интентов и правилами классификации.
2. Добавляет N few-shot пар (`user → JSON-ответ`) — по 2–3 на интент.
3. Передаёт текущее сообщение клиента как последнее user-сообщение.
4. Вызывает `LLM Connector.complete(messages, temperature=0.1, max_tokens=50)` без tools.
5. Парсит ответ через JSON schema валидацию (`{intent, confidence}`).
6. При невалидном JSON / низкой confidence → fallback `intent="discovery"` (default-safe).

## Контракт (input → output)

```python
def build_router_messages(user_text: str) -> list[Message]:
    """returns messages with system + few-shot + user"""

class RouterResponse(BaseModel):
    intent: Literal[
        "small_talk", "discovery", "pricing_budget",
        "itinerary_search", "policy_info", "objection", "crm_event",
    ]
    confidence: float  # 0.0–1.0

CONFIDENCE_THRESHOLD = 0.6  # ниже → fallback на "discovery"
```

## Шаблон промпта

```text
[SYSTEM]
Классифицируй сообщение клиента турагентства по 7 интентам.
Отвечай ТОЛЬКО JSON-объектом без обрамления: {"intent": "...", "confidence": 0.0–1.0}.

Интенты:
- small_talk      — приветствие, светский разговор
- discovery       — сбор требований к туру
- pricing_budget  — вопросы о ценах, бюджете
- itinerary_search — подбор конкретных вариантов
- policy_info     — визы, документы, ограничения
- objection       — работа с возражениями («дорого», «подумаю»)
- crm_event       — контакты, согласие на связь

[FEW-SHOT]
USER: «Привет!»
ASSISTANT: {"intent": "small_talk", "confidence": 0.95}

USER: «Хочу куда-нибудь в тепло на февраль»
ASSISTANT: {"intent": "discovery", "confidence": 0.90}

USER: «Сколько стоит тур на Мальдивы на двоих?»
ASSISTANT: {"intent": "pricing_budget", "confidence": 0.88}

USER: «Покажи туры на Бали 5* до 300к»
ASSISTANT: {"intent": "itinerary_search", "confidence": 0.92}

USER: «Нужна ли виза в ОАЭ?»
ASSISTANT: {"intent": "policy_info", "confidence": 0.95}

USER: «Это слишком дорого, есть что-то проще?»
ASSISTANT: {"intent": "objection", "confidence": 0.93}

USER: «Запишите мой телефон: +7 999 …»
ASSISTANT: {"intent": "crm_event", "confidence": 0.90}

[USER]
{user_text}
```

## Правила и инварианты

- **Temperature = 0.0–0.2** обязательно (детерминизм JSON), `LLM_TEMPERATURE_TOOLCALL=0.1`
- **Tools НЕ передаются** — Router только классифицирует, не вызывает tools
- **`max_tokens ≤ 50`** — экономия (ответ — короткий JSON)
- Few-shot покрывает **все 7 интентов** (минимум по 1 примеру)
- Примеры — на **русском языке** (язык продукта)
- Edge cases в few-shot: «multi-intent» сообщение → выбрать самый сильный интент; «нечёткое» → `confidence < 0.7`
- При `confidence < CONFIDENCE_THRESHOLD` → fallback на `"discovery"` (безопасный дефолт по воронке)
- При невалидном JSON (невозможно распарсить) → fallback на `"discovery"` + лог `error_type="router_parse_fail"`
- Версионирование (`ROUTER_PROMPT_V1`) — для воспроизводимости evals
- Для Router предпочтителен **Mistral** (дешевле; spec-serving-config §4) — вызывается через тот же `LLM Connector`
- Изменение перечня интентов → синхронизация с Decision Logic (`agent-travel-backend` правит матрицу)

## Eval-методология

- Golden dataset: ≥ 100 размеченных сообщений (по 10–15 на интент + edge cases) — реализует `agent-travel-test`
- Метрика: accuracy ≥ 85% (`spec-observability.md` §4)
- Off-line запуск при каждом изменении промпта; результат в таблицу `evals`

## Ограничения / SLA

| Параметр | Значение | Источник |
|---|---|---|
| Точность Router | ≥ 85% | spec-observability §4 |
| Temperature | 0.0–0.2 | spec-orchestrator §9 |
| Max tokens / ответ | 50 | оптимизация |
| Latency | ≤ 500 мс | внутренний бюджет (часть p50 ≤ 2с) |
| Confidence threshold | 0.6 | внутренний default |

## Используется агентами

- `agent-travel-llm` — **владелец** промпта (`src/llm/prompts/router_prompt.py`)
- `agent-travel-backend` — потребитель в `src/router.py` (вызывает через `LLM Connector`, парсит JSON)
- `agent-travel-test` — golden dataset, accuracy eval

## Связанные документы

- `docs/specs/spec-orchestrator.md` §3 (Router, JSON schema)
- `docs/specs/spec-observability.md` §4 (Eval методология)
- `docs/specs/spec-serving-config.md` §4 (Mistral для Router)
- `memory-bank/systemPatterns.md` (Intent-типы)
- `.cursor/skills/decision-matrix/SKILL.md` (потребитель `intent` — Decision Logic вычисляет `available_tools` по `(stage, intent)`)
- `.cursor/skills/prompt-hardening/SKILL.md` (Router-промпт также защищается: запрет смены роли в инструкции классификатора)

## Статус

Backlog — реализация при разработке `src/llm/prompts/router_prompt.py` + `src/router.py`.
