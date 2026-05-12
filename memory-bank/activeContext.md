# Active Context — TravelAgent

## Текущий фокус

**Статус проекта:** PoC / Milestone 1 — Backend реализован, готовимся к фазе системного тестирования  
**Фаза:** Подготовка User-Behaviour Evals (LLM-driven симуляция пользователя)

Production-код в `src/` реализован: FastAPI app, Orchestrator (ReAct + ADR-007 MAX_STEPS=5), Router, Decision Logic, Memory Layer (Redis + PostgreSQL repositories), LLM Connector (Claude/OpenAI/Mistral), Tools Layer (search_tours, create_lead, get/update_client_profile, get_policy_info), Telegram + Web channels, Output Guard. Базовые тесты (unit / integration / acceptance) написаны.

**Следующий этап** — построение пайплайна **User-Behaviour Evals**: runtime-агент, симулирующий поведение клиента (включая edge cases E1–E7 и prompt-injection), для автоматического замера метрик качества ответов системы против SLO §9.5.

## Что уже есть

### Документация и архитектура
- `docs/system-design.md` v1.1 — System Design Document (источник истины)
- `docs/product-proposal.md` — продуктовое обоснование + метрики
- `docs/governance.md` — реестр рисков, PII, логирование
- `docs/specs/` — спецификации: `spec-tools-api.md`, `spec-orchestrator.md`, `spec-memory-context.md`, `spec-serving-config.md`, `spec-observability.md`, `spec-retriever.md`
- `docs/diagrams/` — C4 диаграммы (context, container, component), data-flow, workflow-request
- `.cursor/agents/` — спецификации команды разработки: `agent-task-planner`, `agent-documentation-engineer`, `agent-travel-backend`, `agent-travel-llm`, `agent-travel-dba`, `agent-travel-security`, `agent-travel-test`, **`agent-user-behaviour`** (new)
- `.cursor/skills/` — атомарные SKILLs: `tool-calling-loop`, `decision-matrix`, `sse-streaming`, `idempotency-key`, `circuit-breaker`, `llm-provider-adapter`, `prompt-hardening`, `few-shot-router`, `llm-as-judge`, `context-window-mgmt`, `output-validation`, **`user-simulator`** (new)
- `README.md` — описание проекта
- `memory-bank/` — Memory Bank инициализирован

### Production-код (`src/`)
- `src/api/router.py` — POST `/chat`, POST `/webhook/telegram`, GET `/health`
- `src/main.py` — FastAPI app с lifespan (asyncpg Pool + Redis + LLMConnector)
- `src/orchestrator.py` — Orchestrator с tool-calling loop (ReAct, MAX_STEPS=5)
- `src/router.py` — Intent Classifier (LLM + few-shot)
- `src/decision.py` — rule-based Decision Logic (Guided Agent)
- `src/llm/` — connector, провайдеры (Claude/OpenAI/Mistral), streaming, resilience, output_guard, context_builder, tools_schema, prompts (system/router/summarizer/profile/stage/tone_judge/force_final)
- `src/memory/` — db (asyncpg), redis_client, redis_session, repositories (clients, sessions, messages, leads, itineraries, interactions), retention, fallback, ratelimit
- `src/tools/` — base, executor, policy, leads, client_profile, search_tours
- `src/channels/telegram.py` — Telegram webhook handler
- `src/models/` — chat, tools (Pydantic-модели)
- `src/config.py` — settings (pydantic-settings)

### Тесты (`tests/`)
- `tests/unit/` — test_router, test_decision, test_orchestrator, test_tools, test_memory, test_repositories, test_llm
- `tests/integration/` — test_api_endpoints, test_router_decision, test_telegram_channel, test_orchestrator_flow
- `tests/acceptance/` — test_lead_qualification, test_objection_handling, test_max_steps_fallback
- `tests/conftest.py` — глобальные фикстуры (mock_pool, fake_redis, mock_llm_connector, etc.)

## Чего нет (предстоит реализовать)

### User-Behaviour Evals (текущий фокус — MVP)
- `tests/evals/` — раздел не создан
- `agent-user-behaviour` — runtime-симулятор (спецификация и SKILL готовы; реализация — следующий шаг)
- Personas YAML (`high_end_decisive`, `adversarial_redteam` для MVP)
- Scenarios YAML (`happy_warm_destination`, `e6_prompt_injection` для MVP)
- `simulator/` — user_agent.py, client.py (in-process wrapper над `process_message()`), harness.py
- 4 judges — `tone`, `injection`, `hallucination`, `pii_leak`
- `tracing/langfuse_client.py` — обёртка над Langfuse SDK
- `runners/run_suite.py` — CLI entry point
- Зависимости: `langfuse`, `pyyaml` (через `uv add --dev`)

### Прочее (out of MVP)
- Расширение E1–E7 evals (полная матрица)
- Structural metrics (Router/Decision/Tool-call accuracy против ground-truth)
- Goal Success / Refusal Correctness judges
- HTTP-режим прогона (через `/chat` к запущенному приложению)
- CI-интеграция (smoke в pre-merge, full nightly)
- Baseline diff (`reports/baseline.json` + регрессии)
- Real CRM / агрегаторы туров / API авиакомпаний
- Оплата и бронирование
- Голос, мультиязычность (только русский)
- Авторизация с историей между сессиями (базовая сессия)
- Мобильное приложение, A/B-тестирование

## Активные решения / ограничения

### Архитектурные
- Язык: только русский
- LLM по умолчанию: Claude claude-3-5-sonnet
- БД сессий: Redis; профиль: PostgreSQL
- Нет реальных CRM/агрегаторов — только заглушки
- Агенты в `.cursor/agents/` — команда разработки + runtime-симулятор

### User-Behaviour Evals (фиксации по итогам обсуждения)
- **Scope MVP:** scaffolding + harness + LLM-симулятор + 4 базовых judge + 1 happy-path + 1 red-team сценарий
- **Execution mode:** in-process (`process_message()` напрямую с моками pool/redis из существующего `conftest.py`)
- **LLM симулятора:** та же модель, что у агента (Claude через существующий `LLMConnector`); temperature 0.3–0.5, max_tokens 300
- **Determinism:** полностью LLM-driven (persona + goal + playbook_hints), без принудительных forced_turns
- **Judges:** `tone`, `injection`, `hallucination`, `pii_leak` (4 шт.)
- **Tracing:** Langfuse (через документацию из langfuse skill); JSONL fallback при отсутствии `LANGFUSE_*` ENV
- **Self-eval bias:** smыслы оценщиков (judges) используют LLM с другим system-prompt и temperature; в полной версии — другой провайдер

## Следующие шаги

1. **Сейчас (документация готова):**
   - `.cursor/agents/agent-user-behaviour.md` — спецификация роли (готов)
   - `.cursor/skills/user-simulator/SKILL.md` — атомарный навык (готов)
   - Обновлён Memory Bank

2. **MVP реализация (по этапам, когда пользователь даст команду):**
   - Step 1: `uv add --dev langfuse pyyaml`
   - Step 2: Scaffolding `tests/evals/` (директории + `__init__.py`)
   - Step 3: Pydantic-модели (Persona, Scenario, Turn, ConversationRecord)
   - Step 4: `simulator/client.py` (in-process wrapper)
   - Step 5: `simulator/user_agent.py` (LLM-driven `next_turn`)
   - Step 6: `simulator/harness.py` (conversation loop + JSONL writer)
   - Step 7: 2 persona + 2 scenario YAML
   - Step 8: 4 judges (`tone`, `injection`, `hallucination`, `pii_leak`)
   - Step 9: `tracing/langfuse_client.py` (с graceful fallback)
   - Step 10: `runners/run_suite.py` (CLI)
   - Step 11: End-to-end прогон + проверка JSONL + Langfuse trace

3. **После MVP:**
   - Расширение persona/scenario до полного E1–E7 покрытия
   - Structural metrics (Router/Decision/Tool-call accuracy)
   - Goal Success / Refusal judges
   - CI-интеграция

## Последние изменения

- 2026-05-11: Зафиксирован план MVP User-Behaviour Evals (вопросы и ответы в чате). Создана спецификация `.cursor/agents/agent-user-behaviour.md` (runtime-симулятор пользователя для системного тестирования: persona + scenario, in-process прогон через `process_message()`, JSONL recordings + Langfuse трейсинг, 4 базовых judge). Создан SKILL `.cursor/skills/user-simulator/SKILL.md` (LLM-driven `next_turn` контракт, шаблон system-промпта, harness-loop, persona consistency-метрики)
- 2026-05-10: Инициализирован Memory Bank (все 6 core-файлов)
- 2026-05-10: Создана спецификация `.cursor/agents/agent-travel-test.md` (QA / Test-инженер: unit/integration/acceptance/evals/perf/security, golden dataset, SLO-таргеты §9.5, edge cases E1–E7)
- 2026-05-10: Создана спецификация `.cursor/agents/agent-travel-security.md` — security-инженер (auth, rate limit, prompt/tool injection, PII, secrets, audit)
- 2026-05-10: Создана спецификация `agent-travel-llm` (`.cursor/agents/agent-travel-llm.md`)
- 2026-05-10: Создана спецификация `agent-travel-backend` (`.cursor/agents/agent-travel-backend.md`) + 5 SKILL-stub'ов
- 2026-05-10: Создана спецификация `agent-travel-dba` (`.cursor/agents/agent-travel-dba.md`)
