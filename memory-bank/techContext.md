# Tech Context — TravelAgent

## Технологический стек

| Компонент | Технология |
|---|---|
| Backend | FastAPI (Python 3.11+) |
| LLM (основной) | Claude claude-3-5-sonnet (Anthropic) |
| LLM (альтернатива) | OpenAI gpt-4o |
| LLM (fallback/Router) | Mistral mistral-large |
| Session Memory | Redis (TTL 24h) |
| Persistent Storage | PostgreSQL |
| Vector Store (future) | pgvector / Qdrant |
| Каналы | Telegram Bot API, Web SSE |
| Деплой (dev) | Docker + ngrok |
| Деплой (prod) | Docker + Ingress/LB |
| Мониторинг | Prometheus / Grafana (или аналог) |
| Пакетный менеджер | uv |
| Линтер/формат | ruff |

## Конфигурация через ENV

```
LLM_PROVIDER=claude          # claude | openai | mistral
LLM_MODEL=claude-3-5-sonnet
LLM_MAX_TOKENS=2000
LLM_TEMPERATURE_GENERATION=0.7
LLM_TEMPERATURE_TOOLCALL=0.1
```

## CLI-команды разработки

```bash
uv add <pkg>               # Добавить зависимость
uv run <script>            # Запуск скрипта
ruff format && ruff check  # Форматирование + линтинг
```

## API Endpoints

| Endpoint | Метод | Назначение |
|---|---|---|
| `/telegram/webhook` | POST | Telegram Update JSON |
| `/chat/stream` | POST | Web SSE (`text/event-stream`) |
| `/health` | GET | Health check |

## SSE формат

```
data: {"token": "Отличный", "done": false}\n\n
data: {"token": " выбор!", "done": false}\n\n
data: {"done": true, "metadata": {"intent": "discovery", "stage": "qualified"}}\n\n
```

## Технические ограничения

| Метрика | Цель |
|---|---|
| Latency p50 (first token) | ≤ 2 сек |
| Latency p95 (полный ответ) | ≤ 15 сек |
| Rate Limit | 20 msg/min на клиента |
| Max tool-calls/сообщение | 5 |
| Max токенов/ответ | 2000 |
| LLM context window | 16K токенов |
| Стоимость 10 сообщений | ≤ $0.15 |
| Uptime (демо) | ≥ 95% |

## Структура проекта (целевая)

```
TravelAgent/
├── README.md
├── docs/
│   ├── system-design.md       ← источник истины
│   ├── product-proposal.md
│   ├── governance.md
│   ├── specs/                 ← спецификации модулей
│   └── diagrams/              ← C4, data-flow диаграммы
├── src/
│   ├── api/                   ← FastAPI endpoints
│   ├── channels/              ← TG, Web адаптеры
│   ├── orchestrator.py
│   ├── router.py
│   ├── decision.py
│   ├── memory/                ← Redis + PostgreSQL
│   ├── llm/connector.py       ← LLM абстракция
│   ├── tools/                 ← search_tours и др.
│   └── crm/adapter.py
├── data/                      ← каталог туров, seed
├── tests/
└── memory-bank/               ← Memory Bank (этот файл)
```

## Зависимости агентов

```
agent-travel-llm → agent-travel-backend (tool-calling интерфейс)
agent-travel-backend → agent-travel-dba (PostgreSQL, Redis)
agent-travel-security → agent-travel-backend (auth middleware)
agent-travel-test → все
agent-travel-devops → все
```
