# System Patterns — TravelAgent

## Архитектура верхнего уровня

```
Channels (TG / Web)
    ↓
API Gateway (FastAPI) — Auth + Rate Limit + Нормализатор → ChatMessage
    ↓
Orchestrator
    ├── Router (Intent Classifier — LLM + few-shot)
    ├── Decision Logic (rule-based: stage + action + available_tools)
    ├── Memory Layer (Redis short-term + PostgreSQL long-term)
    └── LLM Connector → Tools Layer
```

## Ключевые архитектурные решения (ADR)

| ADR | Решение |
|---|---|
| ADR-001 | Единый FastAPI backend для TG + Web (каналы — только адаптеры) |
| ADR-002 | LLM = reasoning, не оракул; данные — только из deterministic tools |
| ADR-003 | Redis (TTL 24h) — session; PostgreSQL — профиль + история |
| ADR-004 | Rule-based Decision Logic (Guided Agent паттерн); LLM выбирает tools из разрешённого набора |
| ADR-005 | SSE streaming для Web; Telegram — полный ответ |
| ADR-006 | Абстракция LLM Connector над Claude/OpenAI/Mistral |
| ADR-007 | Max 5 tool-calls на сообщение (защита от циклов + контроль бюджета) |

## Паттерн Guided Agent

Decision Logic определяет:
- `target_stage` — куда двигаться по воронке
- `action` — рекомендуемое поведение
- `available_tools` — какие tools LLM *может* вызвать

LLM самостоятельно решает, какие именно tools вызвать и с какими параметрами. Нельзя вызвать `create_lead` на стадии `cold`.

## Tool-Calling Loop (ReAct)

```
LLM получает контекст → нужен tool? 
    ДА → tool call → Backend выполняет → Observation → LLM (шаг ≤ 5?)
    НЕТ → Финальный ответ
```

## Модули системы

| Модуль | Файл/Пакет | Тип |
|---|---|---|
| Channels | `src/channels/` | Adapter |
| API Gateway | `src/api/` | Middleware |
| Orchestrator | `src/orchestrator.py` | Core |
| Router | `src/router.py` | Core |
| Decision Logic | `src/decision.py` | Core |
| Memory Layer | `src/memory/` | Storage |
| LLM Connector | `src/llm/connector.py` | Integration |
| Tools Layer | `src/tools/` | Tools |
| CRM Adapter | `src/crm/adapter.py` | Integration |

## Intent-типы (Router)

`small_talk` | `discovery` | `pricing_budget` | `itinerary_search` | `policy_info` | `objection` | `crm_event`

## Стадии воронки (Stage Tracker)

`cold` → `discovery` → `qualified` → `proposal` → `objection` / `closing` → `follow_up`

## Memory Layer

### Краткосрочная (Redis, TTL 24h)
- `session:{id}:summary` — сжатая история
- `session:{id}:stage` — текущая стадия
- `session:{id}:scratchpad` — рабочий буфер

### Долгосрочная (PostgreSQL)
- `clients` — профиль клиента
- `sessions` — история сессий + summary
- `messages` — история сообщений
- `leads` — CRM-лиды

## Context Window (порядок для LLM)

```
[system_prompt] → [client_profile] → [conversation_summary] → [recent_messages(3-5)] → [current_message]
```
Лимит: 16K токенов. При превышении — summary заменяет полную историю.

## Guardrails

1. Input: max 2000 символов, эвристики (ignore/system/prompt), санитизация
2. Процесс: max 5 шагов агента, rate limit 20 msg/min
3. Output: output validation, фильтрация system prompt leak
4. LLM API: retry (3x) + Circuit Breaker (5 ошибок за 60с → cooldown 30с)

## Tools

| Tool | Назначение |
|---|---|
| `search_tours` | Поиск туров по параметрам |
| `get_client_profile` | Загрузка профиля из PostgreSQL |
| `update_client_profile` | Обновление профиля |
| `create_lead` | Создание лида (idempotency key) |
| `update_lead_stage` | Смена стадии лида |
| `get_policy_info` | Визы, страховки, ограничения |
| `log_interaction` | Логирование (только программный вызов Orchestrator) |
