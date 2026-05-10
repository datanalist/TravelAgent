# Active Context — TravelAgent

## Текущий фокус

**Статус проекта:** PoC / Milestone 1  
**Фаза:** Инициализация — код (`src/`) ещё не написан

Проект находится на стадии планирования и документирования архитектуры. Вся архитектура зафиксирована в `docs/system-design.md` (v1.1, 2026-04-06). Реализация backend ещё не начата.

## Что уже есть

- `docs/system-design.md` — полный System Design Document (источник истины)
- `docs/product-proposal.md` — продуктовое обоснование + метрики
- `docs/governance.md` — реестр рисков, PII, логирование
- `docs/specs/` — спецификации: `spec-tools-api.md`, `spec-orchestrator.md`, `spec-memory-context.md`, `spec-serving-config.md`, `spec-observability.md`, `spec-retriever.md`
- `docs/diagrams/` — C4 диаграммы (context, container, component), data-flow, workflow-request
- `.cursor/agents/` — спецификации агентов: `agent-task-planner.md`, `agent-documentation-engineer.md`, `agent-travel-backend.md`, `agent-travel-llm.md`, `agent-travel-dba.md`, `agent-travel-security.md`, `agent-travel-test.md`
- `.cursor/skills/` — атомарные SKILLs для агентов: `tool-calling-loop`, `decision-matrix`, `sse-streaming`, `idempotency-key`, `circuit-breaker` (все stub, статус Backlog)
- `README.md` — описание проекта
- `memory-bank/` — только что инициализирован

## Чего нет (предстоит реализовать)

- `src/` — весь backend-код (FastAPI, Orchestrator, Router, Decision Logic, Memory, LLM Connector, Tools)
- `data/` — каталог туров, seed-данные
- `tests/` — тесты
- Docker-конфигурация
- Telegram Bot настройка
- Web-чат SPA

## Активные решения / ограничения

- Язык: только русский
- LLM по умолчанию: Claude claude-3-5-sonnet
- БД сессий: Redis; профиль: PostgreSQL
- Нет реальных CRM/агрегаторов — только заглушки
- Агенты в `.cursor/agents/` — команда разработки

## Следующие шаги

1. Изучить `docs/rules/task.md` (если существует) для текущей задачи
2. Запустить `agent-task-planner` для декомпозиции задачи
3. Начать реализацию согласно плану (порядок: DBA схема → Backend Core → LLM Connector → Tools)

## Последние изменения

- 2026-05-10: Инициализирован Memory Bank (все 6 core-файлов)
- 2026-05-10: Создана спецификация `.cursor/agents/agent-travel-test.md` (QA / Test-инженер: unit/integration/acceptance/evals/perf/security, golden dataset, SLO-таргеты §9.5, edge cases E1–E7)
- 2026-05-10: Создана спецификация `.cursor/agents/agent-travel-security.md` — security-инженер (auth, rate limit, prompt/tool injection, PII, secrets, audit). Устранено расхождение пути в `.cursor/rules/project-global.mdc` (`docs/agents/` → `.cursor/agents/`)
- 2026-05-10: Создана спецификация `agent-travel-llm` (`.cursor/agents/agent-travel-llm.md`) — отвечает за `src/llm/` (Connector, провайдеры, streaming, промпты, retry/CB, output validation); чёткие границы с `agent-travel-backend` (LLM SDK импортируется только в `src/llm/providers/*`, backend получает единый интерфейс `LLM Connector` + готовые промпты + JSON-schema tools)
- 2026-05-10: Создана спецификация `agent-travel-backend` (`.cursor/agents/agent-travel-backend.md`) + 5 SKILL-stub'ов в `.cursor/skills/` (tool-calling-loop, decision-matrix, sse-streaming, idempotency-key, circuit-breaker)
- 2026-05-10: Создана спецификация `agent-travel-dba` (`.cursor/agents/agent-travel-dba.md`) — отвечает за `src/memory/` (схема PostgreSQL: clients/client_profile/sessions/messages/leads/itineraries/interactions; Alembic-миграции; репозитории/DAO; Redis-сессии с TTL 24h; idempotency на уровне БД; Stage Tracker storage; fallback Redis↔PostgreSQL; retention 90д/14д). Чёткие границы с backend (не пишет бизнес-логику tools), llm (не пишет промпты Summarizer/Profile Updater — только хранит результат), security (даёт только Redis-counter для rate-limit, политика 429 — security)
