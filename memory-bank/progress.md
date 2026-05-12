# Progress — TravelAgent

## Статус: PoC / Milestone 1 — Backend реализован; готовимся к User-Behaviour Evals

## Что работает (Done)

### Документация и архитектура
- [x] System Design Document (`docs/system-design.md` v1.1)
- [x] Product Proposal (`docs/product-proposal.md`)
- [x] Governance / Risk Register (`docs/governance.md`)
- [x] Спецификации модулей (`docs/specs/`)
  - spec-tools-api.md, spec-orchestrator.md, spec-memory-context.md
  - spec-serving-config.md, spec-observability.md, spec-retriever.md
- [x] Диаграммы (`docs/diagrams/`) — C4 context/container/component, data-flow, workflow-request
- [x] README.md
- [x] Спецификации команды разработки (`.cursor/agents/`): `agent-task-planner`, `agent-documentation-engineer`, `agent-travel-backend`, `agent-travel-llm`, `agent-travel-dba`, `agent-travel-security`, `agent-travel-test`
- [x] **Спецификация runtime-симулятора** (`.cursor/agents/agent-user-behaviour.md`) — генератор пользовательского поведения для системного тестирования
- [x] SKILL-stub'ы для backend-агента (`.cursor/skills/`): tool-calling-loop, decision-matrix, sse-streaming, idempotency-key, circuit-breaker
- [x] SKILL-stub'ы для llm-агента: llm-provider-adapter, prompt-hardening, few-shot-router, llm-as-judge, context-window-mgmt, output-validation
- [x] **SKILL** `user-simulator` (`.cursor/skills/user-simulator/SKILL.md`) — атомарный навык LLM-driven персонажа-симулятора (`next_turn` контракт + harness loop)
- [x] Memory Bank инициализирован и поддерживается актуальным

### Backend Core (агент: `agent-travel-backend`)
- [x] FastAPI app structure (`src/api/`) — POST `/chat`, POST `/webhook/telegram`, GET `/health`
- [x] FastAPI entry point (`src/main.py`) с lifespan (asyncpg Pool + Redis + LLMConnector)
- [x] Orchestrator (`src/orchestrator.py`) — tool-calling loop (ReAct, ADR-007 MAX_STEPS=5)
- [x] Router / Intent Classifier (`src/router.py`) — LLM + few-shot
- [x] Decision Logic (`src/decision.py`) — rule-based Guided Agent
- [x] ChatMessage / ChatRequest / ChatResponse Pydantic-модели (`src/models/`)
- [x] Config через `pydantic-settings` (`src/config.py`)

### Memory Layer (агент: `agent-travel-dba`)
- [x] Redis client + session manager (`src/memory/redis_client.py`, `src/memory/redis_session.py`)
- [x] PostgreSQL pool (`src/memory/db.py`)
- [x] Repositories: clients, sessions, messages, leads, itineraries, interactions
- [x] Retention scheduler (`src/memory/retention.py`)
- [x] Fallback Redis↔PostgreSQL (`src/memory/fallback.py`)
- [x] Rate limiter counter (`src/memory/ratelimit.py`)
- [x] Pydantic-модели данных (`src/memory/models.py`)

### LLM Layer (агент: `agent-travel-llm`)
- [x] `src/llm/providers/base.py` — абстрактный `LLMProvider`
- [x] `src/llm/connector.py` — единый интерфейс `complete()` / `stream()` (ADR-006) с retry+CB
- [x] `src/llm/providers/claude.py` — Anthropic SDK адаптер
- [x] `src/llm/providers/openai.py` — OpenAI адаптер
- [x] `src/llm/providers/mistral.py` — Mistral адаптер
- [x] `src/llm/streaming.py` — async-генератор токенов
- [x] `src/llm/resilience.py` — retry (exp backoff) + Circuit Breaker
- [x] `src/llm/usage.py` — учёт токенов и стоимости
- [x] `src/llm/output_guard.py` — `validate_output()` с regex utечки + jailbreak
- [x] `src/llm/context_builder.py` — сборка messages + усечение
- [x] `src/llm/tools_schema.py` — JSON-schema tools для LLM
- [x] `src/llm/prompts/system_prompt.py` — high-end тон + prompt hardening (V1)
- [x] `src/llm/prompts/router_prompt.py` — few-shot для 7 интентов (V1)
- [x] `src/llm/prompts/summarizer_prompt.py` — сжатие истории
- [x] `src/llm/prompts/profile_extractor_prompt.py` — LLM-extraction профиля
- [x] `src/llm/prompts/stage_prompt.py` — LLM-fallback Stage Classifier
- [x] `src/llm/prompts/tone_judge_prompt.py` — LLM-as-Judge для high-end тона (V1)
- [x] `src/llm/prompts/force_final.py` — директива при MAX_STEPS=5 (ADR-007)
- [x] `src/llm/config.py` — чтение `LLM_*` ENV через `pydantic-settings`

### Tools Layer
- [x] `src/tools/base.py` — абстрактный Tool
- [x] `src/tools/executor.py` — ToolExecutor (DI набор tools для Orchestrator)
- [x] `src/tools/search_tours.py` — поиск туров (stub-данные)
- [x] `src/tools/client_profile.py` — get/update profile
- [x] `src/tools/leads.py` — create_lead (+ idempotency), update_lead_stage
- [x] `src/tools/policy.py` — get_policy_info

### Channels
- [x] `src/channels/telegram.py` — Telegram webhook handler
- [ ] Web SSE endpoint (`src/channels/web.py`) — пока через `/chat` (без SSE)

### Тесты (агент: `agent-travel-test`)
- [x] Unit-тесты: test_router, test_decision, test_orchestrator, test_tools, test_memory, test_repositories, test_llm
- [x] Integration-тесты: test_api_endpoints, test_router_decision, test_telegram_channel, test_orchestrator_flow
- [x] Acceptance-сценарии: test_lead_qualification, test_objection_handling, test_max_steps_fallback
- [x] Глобальные фикстуры (`tests/conftest.py`, `tests/integration/conftest.py`): mock_pool, fake_redis, mock_llm_connector, make_llm_response, make_router_response

## Что предстоит сделать (Backlog)

### User-Behaviour Evals — MVP (текущий фокус, агенты: `agent-user-behaviour` + `agent-travel-test`)

**Документация (готово):**
- [x] Спецификация `agent-user-behaviour` (`.cursor/agents/agent-user-behaviour.md`)
- [x] SKILL `user-simulator` (`.cursor/skills/user-simulator/SKILL.md`)
- [x] Memory Bank актуализирован (фиксации MVP-решений)

**Реализация (предстоит):**
- [ ] Зависимости: `uv add --dev langfuse pyyaml`
- [ ] Scaffolding `tests/evals/` (директории + `__init__.py` + `.gitkeep` для recordings/reports)
- [ ] Pydantic-модели: `Persona`, `Scenario`, `Turn`, `ConversationRecord` (в `tests/evals/simulator/models.py`)
- [ ] `tests/evals/conftest.py` — фикстуры для evals (переиспользование mock_pool / fake_redis)
- [ ] `tests/evals/simulator/client.py` — in-process wrapper над `process_message()`
- [ ] `tests/evals/simulator/user_agent.py` — `UserBehaviourAgent` (LLM-driven `next_turn`)
- [ ] `tests/evals/simulator/harness.py` — conversation loop + JSONL writer
- [ ] `tests/evals/personas/high_end_decisive.yaml`
- [ ] `tests/evals/personas/adversarial_redteam.yaml`
- [ ] `tests/evals/scenarios/happy_warm_destination.yaml`
- [ ] `tests/evals/scenarios/e6_prompt_injection.yaml`
- [ ] `tests/evals/tracing/langfuse_client.py` — обёртка с graceful fallback
- [ ] `tests/evals/judges/base.py` — общий контракт `JudgeVerdict`
- [ ] `tests/evals/judges/tone_judge.py` — high-end tone (использует существующий `tone_judge_prompt.py`)
- [ ] `tests/evals/judges/injection_judge.py` — утечка system prompt / role override
- [ ] `tests/evals/judges/hallucination_judge.py` — сравнение reply vs `search_tours` results
- [ ] `tests/evals/judges/pii_leak_judge.py` — regex (output_guard) + LLM-fallback
- [ ] `tests/evals/runners/run_suite.py` — CLI entry point
- [ ] `tests/evals/README.md` — how-to-run + how-to-add persona/scenario
- [ ] End-to-end прогон: 2 persona × 2 scenario × ~6 turns; JSONL + Langfuse trace; 4 judge scores

### User-Behaviour Evals — Расширение (после MVP)
- [ ] Persona-расширение: `budget_conscious`, `confused_newbie`, `aggressive_objector`
- [ ] Сценарии: полное покрытие E1–E7 + остальные happy-paths (premium, policy_info, cross-channel)
- [ ] Structural metrics: Router accuracy, Decision correctness, Tool-call correctness (vs ground-truth)
- [ ] Goal Success judge, Refusal Correctness judge
- [ ] HTTP-режим прогона (через `/chat` к запущенному приложению)
- [ ] Baseline diff: `reports/baseline.json` + регрессии vs предыдущий прогон
- [ ] CI-интеграция: smoke (1 persona × E6) в pre-merge, full nightly
- [ ] Persona Consistency judge — проверка, что симулятор держит роль
- [ ] Attack Vector Coverage report — все векторы из `attack_vectors_to_try` встретились
- [ ] Cost / latency агрегаты per persona × scenario

### Backend Core — Web SSE
- [ ] `src/channels/web.py` — POST `/chat/stream` с `text/event-stream` (ADR-005)
- [ ] Интеграция с `src/llm/streaming.py` (async-генератор токенов)
- [ ] Метаданные в финальном `done: true` чанке (intent, stage, lead_id)
- [ ] Тесты SSE-формата (`tests/integration/channels/test_web_sse.py`)

### DevOps (агент: `agent-travel-devops` — спецификация ещё не создана)
- [ ] Dockerfile + docker-compose
- [ ] ngrok для dev (Telegram webhook)
- [ ] Health check endpoint расширенный (db + redis + llm provider ping)
- [ ] Prometheus metrics endpoint
- [ ] Grafana dashboards (Overview, LLM & Costs, Business & Evals)
- [ ] CI pipeline (pytest + ruff + coverage)

### Data
- [ ] Каталог туров (500–1000 записей) — сейчас stub в SearchToursTool
- [ ] Seed-скрипты для PostgreSQL + Redis (dev)

## Известные проблемы / Риски

| Риск | Статус |
|---|---|
| R1 Prompt Injection | Митигирован архитектурно (system_prompt hardening + output_guard); валидация — через `e6_prompt_injection` scenario в evals |
| R2 Галлюцинации по турам | Митигирован архитектурно (ADR-002); валидация — `hallucination_judge` в evals |
| R4 Утечка PII | Митигирован архитектурно (`output_guard` маскирование); валидация — `pii_leak_judge` в evals |
| R6 Недоступность LLM API | Митигирован Circuit Breaker (ADR-006); проверено в integration-тестах |
| R9 Нарушение high-end тона | Митигирован system_prompt калибровкой; валидация — `tone_judge` в evals |
| R10 Tool Injection | Митигирован Guided Agent (ADR-004); валидация — `e6` сценарий должен включать `force_data_without_tool` вектор |

## Метрики успеха PoC

| Метрика | Цель | Где замеряется |
|---|---|---|
| Конверсия в лид | ≥ 15% | PostgreSQL `leads` / `sessions` (после деплоя) |
| Точность Router | ≥ 85% | Structural metric в evals (после MVP) |
| Latency p50 first token | ≤ 2 сек | `tests/perf/test_latency_smoke.py` + JSONL latency в evals |
| High-end tone оценка | ≥ 75% | `tone_judge` в evals |
| Prompt injection resistance | 100% pass | `injection_judge` на `e6_prompt_injection` |
| Hallucination rate | 0% | `hallucination_judge` |
| PII в ответе | 0% | `pii_leak_judge` |

## История этапов

- **2026-05-11:** Зафиксирован план MVP User-Behaviour Evals. Создана спецификация `agent-user-behaviour` + SKILL `user-simulator`. Обновлён Memory Bank.
- **2026-05-10..11:** Реализован весь backend (`src/`): FastAPI, Orchestrator, Router, Decision, Memory Layer (Redis + PostgreSQL repositories), LLM Connector (3 провайдера + streaming + resilience), Tools (search_tours, create_lead, profile, policy), Telegram channel, Output Guard. Написаны базовые тесты (unit + integration + acceptance).
- **2026-05-10:** Инициализирован Memory Bank. Созданы спецификации команды агентов (`agent-travel-{backend,llm,dba,security,test}`, `agent-task-planner`, `agent-documentation-engineer`) и 11 SKILL-stub'ов.
- **2026-04-06:** Финализирован System Design v1.1.
