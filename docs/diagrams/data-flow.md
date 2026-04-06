# Data Flow — TravelAgent

> Как данные проходят через систему: что читается/пишется в каждом хранилище, что логируется, что уходит во внешние API.

Источник: `docs/system-design.md` (§4–5, §10, §13–14).

## Диаграмма

```mermaid
flowchart TB
  subgraph Ingress["Вход"]
    C[Клиент: Telegram / Web]
    API[FastAPI: auth, нормализация → ChatMessage]
  end

  subgraph Core["Обработка запроса"]
    OR[Orchestrator]
    RT[Router: intent]
    MEM[Memory Layer]
    DL[Decision Logic]
    LLM[LLM Connector]
    TL[Tools Layer]
  end

  subgraph Egress["Исход"]
    OUT[Ответ: SSE Web / Telegram Bot API]
  end

  subgraph Obs["Наблюдаемость"]
    LOG[JSON structured logs]
    PM[Prometheus: histograms / counters]
  end

  C --> API
  API --> RL[Rate limit]
  RL -.->|INCR / GET, TTL 1 min| R_RL["Redis: ratelimit:{client_id}"]

  API --> OR
  OR -.->|UPSERT| PG_OR["PostgreSQL: clients, sessions"]

  OR --> RT
  RT -.->|классификация intent| EXT_LLM[(Claude / OpenAI / Mistral)]
  EXT_LLM -.->|intent JSON| RT
  RT -->|intent| OR

  OR --> MEM
  R_MEM["Redis: session summary, stage"] -.->|read, TTL 24h| MEM
  PG_MEM["PostgreSQL: client_profile;\nfallback sessions.summary"] -.->|read| MEM

  OR --> DL
  DL -->|"stage · action · available_tools"| OR

  OR -->|"контекст + available_tools"| LLM
  LLM -.->|запрос: system_prompt, summary,\nrecent_messages, client_profile,\nuser text, tools| EXT_LLM
  EXT_LLM -.->|ответ / tool_calls| LLM
  LLM -->|"tool_calls / ответ"| OR

  OR -->|"вызов tool"| TL
  TL -->|"observations"| OR
  TL -.->|write scratchpad, TTL 24h| R_SCR["Redis: session:{id}:scratchpad"]
  TL -.->|read/write leads, itineraries, messages| PG_TL["PostgreSQL"]

  OR --> OUT
  OUT -.->|text + inline_keyboard| TGAPI[(Telegram Bot API)]

  OR --> SUM[Summarizer + Profile Updater + Stage Tracker]
  SUM -.->|write summary, stage| R_SUM["Redis"]
  SUM -.->|sessions.summary, stage,\nmessages, client_profile| PG_SUM["PostgreSQL"]

  OR -.->|log_interaction, структура §14.3| LOG
  API -.->|travelagent_request_*, errors| PM
  LLM -.->|tokens, cost, steps| PM
  TL -.->|travelagent_tool_calls_total| PM

  subgraph PII["PII-граница"]
    N1["В LLM: не сырые имя / email / телефон;\ntelegram_id не в открытом виде в логах"]
    N2["Логи: client_id_hash, session_id, channel,\nintent, stage, tools_called, latency_ms,\ntokens_used, cost_usd, agent_steps"]
    N3["Не логировать: полный текст с PII"]
  end
```

## Пояснения по хранилищам

| Хранилище | Что пишется | Когда / контекст |
|-----------|-------------|------------------|
| **Redis** `session:{id}:summary` | JSON, сжатая история | Summarizer после хода; чтение в Memory Layer на каждом сообщении |
| **Redis** `session:{id}:stage` | Строка стадии воронки | Stage Tracker после хода; чтение в Memory Layer |
| **Redis** `session:{id}:scratchpad` | JSON, временные данные (промежуточные результаты `search_tours` и т.п.) | В цикле агента между шагами; TTL 24h |
| **Redis** `ratelimit:{client_id}` | Счётчик | На ingress; TTL 1 min |
| **PostgreSQL** `clients` | Профиль: `telegram_id`, имя, email, phone, segment, … | Резолв/создание клиента Orchestrator |
| **PostgreSQL** `client_profile` | `budget_range`, destinations, `travel_style`, `constraints` | Чтение в Memory; обновление Profile Updater |
| **PostgreSQL** `sessions` | `client_id`, channel, stage, summary | Создание/обновление сессии; fallback summary если Redis истёк |
| **PostgreSQL** `messages` | content, role, metadata (intent, stage, tokens, latency) | Персист сообщений пользователя/агента |
| **PostgreSQL** `leads` | status, budget, destination, travel_dates | Tool `create_lead` / смена стадии |
| **PostgreSQL** `itineraries` | Варианты туров для лида | Привязка к `lead_id` после подбора |
| **LLM API** | system prompt, **обезличенный/структурированный** профиль предпочтений, summary, недавние реплики, описания tools | Каждый вызов Router/основного агента; **без сырых PII** (имя, email, телефон не в контекст) |
| **Telegram Bot API** | Текст ответа, `inline_keyboard` | Исходящее сообщение в TG |
| **CRM API** (будущее) | Данные лидов | Синхронизация после квалификации |
| **Логи (JSON)** | `client_id_hash`, `session_id`, channel, intent, stage, `tools_called`, latency, tokens, cost, `agent_steps` | Структурированное логирование; **не** полный текст с PII |
| **Prometheus** | `travelagent_request_duration_seconds`, `travelagent_llm_tokens_total`, `travelagent_llm_cost_usd_total`, `travelagent_tool_calls_total`, `travelagent_agent_steps_total`, `travelagent_errors_total` (+ gauge/counter из §14.1 при необходимости) | Скрапинг метрик сервиса |

### Связка с метриками и логами

- В **логах** отражаются агрегаты и идентификаторы без чувствительного содержимого; **telegram_id** — только хэш (см. §13.2–13.3 SDD).
- **Prometheus** агрегирует latency, токены, стоимость, число вызовов tools и шагов агента, ошибки — без телеметрии по содержимому сообщений.
