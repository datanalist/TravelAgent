# Progress — TravelAgent

## Статус: PoC / Milestone 1 — Инициализация

## Что работает (Done)

### Документация и архитектура
- [x] System Design Document (`docs/system-design.md` v1.1)
- [x] Product Proposal (`docs/product-proposal.md`)
- [x] Governance / Risk Register (`docs/governance.md`)
- [x] Спецификации модулей (`docs/specs/`)
  - spec-tools-api.md
  - spec-orchestrator.md
  - spec-memory-context.md
  - spec-serving-config.md
  - spec-observability.md
  - spec-retriever.md
- [x] Диаграммы (`docs/diagrams/`) — C4 context/container/component, data-flow, workflow-request
- [x] README.md
- [x] Спецификации агентов (`.cursor/agents/`): `agent-task-planner`, `agent-documentation-engineer`, `agent-travel-backend`, `agent-travel-llm`, `agent-travel-dba`, `agent-travel-security`, `agent-travel-test`
- [x] SKILL-stub'ы для backend-агента (`.cursor/skills/`): tool-calling-loop, decision-matrix, sse-streaming, idempotency-key, circuit-breaker (статус Backlog)
- [x] SKILL-stub'ы для llm-агента (`.cursor/skills/`): llm-provider-adapter, prompt-hardening, few-shot-router, llm-as-judge, context-window-mgmt, output-validation (статус Backlog); shared SKILLs (`circuit-breaker`, `sse-streaming`) обновлены — добавлен `agent-travel-llm` в "Используется агентами", уточнено владение реализацией
- [x] Memory Bank инициализирован

## Что предстоит сделать (Backlog)

### Backend Core (агент: `agent-travel-backend`)
- [ ] FastAPI app structure (`src/api/`)
- [ ] Нормализатор ChatMessage
- [ ] Orchestrator (`src/orchestrator.py`)
- [ ] Router / Intent Classifier (`src/router.py`)
- [ ] Decision Logic (`src/decision.py`)

### Memory Layer
- [ ] Redis session manager (`src/memory/redis.py`)
- [ ] PostgreSQL schema (clients, sessions, messages, leads)
- [ ] Conversation Summarizer
- [ ] Profile Updater
- [ ] Stage Tracker

### LLM Layer (агент: `agent-travel-llm`)
- [ ] `src/llm/providers/base.py` — абстрактный `LLMProvider`
- [ ] `src/llm/connector.py` — единый интерфейс `complete()` / `stream()` (ADR-006) с встроенным retry+CB
- [ ] `src/llm/providers/claude.py` — Anthropic SDK адаптер (основной)
- [ ] `src/llm/providers/openai.py` — OpenAI адаптер (альтернатива)
- [ ] `src/llm/providers/mistral.py` — Mistral адаптер (Router / fallback)
- [ ] `src/llm/streaming.py` — async-генератор токенов (источник для SSE-адаптера в backend)
- [ ] `src/llm/resilience.py` — retry (exp backoff 1s→2s→4s) + Circuit Breaker (5/60s → 30s)
- [ ] `src/llm/usage.py` — учёт токенов и стоимости (per provider/model)
- [ ] `src/llm/output_guard.py` — validate_output() с regex-маркерами утечки + jailbreak
- [ ] `src/llm/context_builder.py` — сборка messages в каноническом порядке + усечение L1/L2
- [ ] `src/llm/tools_schema.py` — JSON-schema tools для LLM (на базе Pydantic backend, без `log_interaction`)
- [ ] `src/llm/prompts/system_prompt.py` — high-end тон + prompt hardening + No Hallucination (V1)
- [ ] `src/llm/prompts/router_prompt.py` — few-shot для 7 интентов + JSON schema (V1)
- [ ] `src/llm/prompts/summarizer_prompt.py` — сжатие истории в 3–5 фактов
- [ ] `src/llm/prompts/profile_extractor_prompt.py` — LLM-extraction профиля
- [ ] `src/llm/prompts/stage_prompt.py` — (опц.) LLM-fallback Stage Classifier
- [ ] `src/llm/prompts/tone_judge_prompt.py` — LLM-as-Judge для high-end тона (V1)
- [ ] `src/llm/prompts/force_final.py` — директива при `MAX_STEPS = 5` (ADR-007)
- [ ] `src/llm/config.py` — чтение `LLM_*` ENV через `pydantic-settings`

### Tools Layer
- [ ] `search_tours` (stub/local DB)
- [ ] `get_client_profile`
- [ ] `update_client_profile`
- [ ] `create_lead`
- [ ] `update_lead_stage`
- [ ] `get_policy_info`

### Channels
- [ ] Telegram webhook handler (`src/channels/telegram.py`)
- [ ] Web SSE endpoint (`src/channels/web.py`)

### Data
- [ ] Каталог туров (500–1000 записей) `data/`
- [ ] Seed-скрипты

### DevOps
- [ ] Dockerfile + docker-compose
- [ ] ngrok для dev
- [ ] Health check endpoint

### Tests
- [ ] Unit-тесты: Router, Decision Logic
- [ ] Integration-тесты: Orchestrator workflow
- [ ] Acceptance-сценарии

## Известные проблемы / Риски

| Риск | Статус |
|---|---|
| R2 Галлюцинации по турам | Митигирован архитектурно (ADR-002) |
| R6 Недоступность LLM API | Митигирован Circuit Breaker (ADR-006) |
| R4 Утечка PII | Задокументировано в governance.md; реализация предстоит |
| R9 Нарушение high-end тона | Требует тщательной калибровки system prompt |

## Метрики успеха PoC

| Метрика | Цель |
|---|---|
| Конверсия в лид | ≥ 15% |
| Точность Router | ≥ 85% |
| Latency p50 first token | ≤ 2 сек |
| High-end tone оценка | ≥ 75% |
