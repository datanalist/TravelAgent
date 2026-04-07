# Спецификация: Agent Orchestrator

**Модули:** `src/orchestrator.py`, `src/router.py`, `src/decision.py`  
**Версия:** 1.0 | **Статус:** Draft

---

## 1. Обзор

| Модуль | Файл | Ответственность |
|--------|------|-----------------|
| **Orchestrator** | `src/orchestrator.py` | Главный контроллер: координирует весь pipeline обработки сообщения |
| **Router** | `src/router.py` | Классификация intent по входящему сообщению (LLM + few-shot + JSON schema) |
| **Decision Logic** | `src/decision.py` | Определение `target_stage`, `action`, `available_tools` на основе stage + intent |

---

## 2. Pipeline обработки запроса

```
Client (Telegram / Web)
  │
  ▼
FastAPI endpoint  ──→  auth check + rate limit (20 msg/min per client_id)
  │
  ▼
Нормализатор  ──→  ChatMessage(client_id, session_id, text, channel, timestamp)
  │
  ▼
Orchestrator
  ├─ резолвит/создаёт client + session  (PostgreSQL)
  ├─ Router  ──→  intent
  ├─ Memory Layer  ──→  summary (Redis) + client_profile (PostgreSQL) + stage (Redis)
  ├─ Decision Logic  ──→  target_stage, action, available_tools
  ├─ LLM Connector  ──→  system_prompt + memory + message + available_tools
  │
  │   ┌─────────────── Tool-calling loop (ReAct) ───────────────┐
  │   │  LLM → tool_call → backend executes → observation → LLM │
  │   │  (max 5 шагов, при превышении — принудительный ответ)   │
  │   └──────────────────────────────────────────────────────────┘
  │
  ├─ финальный ответ → Web (SSE) / Telegram
  ├─ Conversation Summarizer  ──→  Redis (session summary)
  ├─ Profile Updater  ──→  PostgreSQL (client_profile)
  ├─ Stage Tracker  ──→  Redis (stage)
  └─ log_interaction  ──→  PostgreSQL (activity log)
```

---

## 3. Router — классификация intent

**Метод:** LLM-вызов с few-shot примерами + JSON schema валидация ответа.  
**Temperature:** `0.0–0.2`

### Intent-типы

| Intent | Описание |
|--------|----------|
| `small_talk` | Приветствие, светский разговор |
| `discovery` | Сбор требований к туру |
| `pricing_budget` | Вопросы о ценах, бюджете |
| `itinerary_search` | Подбор конкретных вариантов |
| `policy_info` | Визы, документы, ограничения |
| `objection` | Работа с возражениями |
| `crm_event` | CRM-события, контакты |

### JSON schema ответа Router

```json
{
  "intent": "discovery",
  "confidence": 0.92
}
```

---

## 4. Decision Logic — Guided Agent (ADR-004)

Decision Logic **не управляет** вызовами tools напрямую — он определяет **область допустимых действий** для LLM. LLM самостоятельно решает, какие tools из `available_tools` вызвать и с какими параметрами.

### Воронка стадий

```
cold ──→ discovery ──→ qualified ──→ proposal ──→ objection ──┐
  ▲                                      │                     │
  │                                      ▼                     │
follow_up                             closing ◄────────────────┘
```

| Переход | Условие |
|---------|---------|
| `cold → discovery` | Любой входящий запрос |
| `discovery → qualified` | Наличие бюджета + направления в профиле |
| `qualified → proposal` | После успешного `search_tours` |
| `proposal → objection` | Intent = `objection` |
| `proposal/objection → closing` | Явное согласие клиента |
| `follow_up → discovery` | Возврат клиента после паузы |

### Матрица stage + intent → available_tools

| Stage | Intent | available_tools |
|-------|--------|-----------------|
| `cold`, `discovery` | любой | `search_tours`, `get_policy_info`, `get_client_profile` |
| `qualified` | `itinerary_search` | `search_tours`, `get_client_profile`, `update_client_profile`, `get_policy_info` |
| `proposal` | любой | `search_tours`, `create_lead`, `update_client_profile` |
| `objection` | любой | `search_tours`, `update_lead_stage` |
| `closing` | любой | `create_lead`, `update_lead_stage` |

---

## 5. Tool-calling loop (ReAct pattern)

```python
# Псевдокод
async def run_agent(context: AgentContext) -> str:
    steps = 0
    messages = build_initial_messages(context)

    while steps < MAX_STEPS:
        response = await llm.complete(messages, tools=context.available_tools)

        if response.finish_reason == "stop":
            return response.content  # финальный ответ

        for tool_call in response.tool_calls:
            observation = await execute_tool(tool_call)
            messages.append(tool_result(tool_call.id, observation))

        steps += 1

    # MAX_STEPS превышен
    return await llm.complete(messages + [force_final_prompt()])
```

**Диаграмма одного шага:**

```
LLM response
  ├── finish_reason = "stop"  ──→  финальный ответ (выход)
  └── tool_calls present
        ├── execute tool_1  ──→  observation_1
        ├── execute tool_2  ──→  observation_2
        └── append to messages  ──→  следующий шаг
```

---

## 6. Stop conditions

| Условие | Поведение |
|---------|-----------|
| LLM вернул финальный ответ (нет tool_calls) | Выход из loop, ответ клиенту |
| Превышен лимит шагов (`steps > 5`) | Принудительный LLM-вызов с директивой «сформируй ответ из имеющихся данных» |
| Ошибка tool (любая) | Graceful degradation: добавить `error_observation`, продолжить с доступными данными |

---

## 7. Retry / Fallback стратегии

| Компонент | Стратегия |
|-----------|-----------|
| **LLM API** | Exponential backoff, 3 попытки (1s → 2s → 4s) |
| **Circuit Breaker** | Open после 5 ошибок за 60с → cooldown 30с |
| **Redis (session memory)** | Ошибка → продолжить без session summary, базовый ответ |
| **PostgreSQL** | Ошибка → аварийный режим, логирование, ответ без профиля клиента |
| **search_tours (пустой результат)** | Ответ: «По вашим параметрам вариантов не найдено» |
| **Max steps превышен** | Промежуточный результат с пояснением клиенту |

---

## 8. Guardrails

### Input validation (3 уровня)

| Уровень | Проверка | Действие при нарушении |
|---------|----------|------------------------|
| 1 | Длина > 2000 символов | Отклонить, сообщить клиенту |
| 2 | Ключевые слова: `ignore`, `forget`, `system`, `prompt` | Поставить флаг `injection_suspected`, залогировать |
| 3 | Санитизация спецсимволов (`<`, `>`, `{`, `}` и пр.) | Escape перед передачей в LLM |

**Rate limit:** 20 сообщений/минуту per `client_id` (429 при превышении).

### Output validation

- Ответ не должен содержать фрагменты system prompt (regex-проверка маркеров)
- Фильтрация ответов с признаками prompt injection
- Tools scope: LLM не имеет доступа к файловой системе или прямым SQL-запросам — только к зарегистрированным tools

---

## 9. Ограничения

| Параметр | Значение |
|----------|----------|
| Max шагов агента | `5` |
| Max токенов на ответ | `2000` |
| Max контекст | `16K токенов` |
| Temperature (генерация ответа) | `0.4–0.7` |
| Temperature (routing / tool-calling) | `0.0–0.2` |
| Rate limit | `20 msg/min` per `client_id` |
| Max длина входящего сообщения | `2000 символов` |

---

## Связанные документы

- `docs/system-design.md` — источник истины по архитектуре
- `docs/specs/spec-memory-context.md` — Memory Layer
- ADR-004: Guided Agent pattern
- ADR-007: Max steps enforcement
