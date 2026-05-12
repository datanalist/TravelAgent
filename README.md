# TravelAgent — AI-консьерж для туроператора

> Мультиагентная система, которая увеличивает выручку и конверсию туроператора/турагентства за счёт AI-консьержа, берущего на себя значимую часть первичных продаж и сервиса в digital-каналах.

**Статус:** PoC | Milestone 1

---

## Содержание

- [Что делает](#что-делает)
- [Архитектура](#архитектура)
- [Быстрый старт](#быстрый-старт)
- [Конфигурация](#конфигурация)
- [Запуск в Docker](#запуск-в-docker)
- [Локальный запуск без Docker](#локальный-запуск-без-docker)
- [Миграции базы данных](#миграции-базы-данных)
- [Telegram-бот: webhook через ngrok](#telegram-бот-webhook-через-ngrok)
- [API-эндпоинты](#api-эндпоинты)
- [Тесты](#тесты)
- [Структура проекта](#структура-проекта)
- [Документация](#документация)

---

## Что делает

1. Клиент общается в **Telegram-боте** или **Web-чате** — единый backend, общая сессия по `client_id`
2. Агент **квалифицирует запрос** — собирает бюджет, даты, направление, стиль отдыха
3. Агент ведёт **экспертный диалог** — уточняет предпочтения, адаптирует тон (в т.ч. high-end)
4. Агент **подбирает туры** — вызов `search_tours`, ранжирование и объяснение выбора
5. Агент **создаёт лид в CRM** (таблица `leads`)
6. Агент **обновляет профиль клиента** — бюджет, направления, предпочтения
7. Ответы **стримятся** в реальном времени (SSE для Web)

---

## Архитектура

```
Telegram / Web
      │
      ▼
 FastAPI (src/main.py)
      │
      ├── POST /webhook/telegram  → channels/telegram.py
      ├── POST /chat              → api/router.py
      └── GET  /health
                │
                ▼
         orchestrator.py  ← ReAct loop (max 5 шагов)
                │
      ┌─────────┼─────────┐
      ▼         ▼         ▼
  llm/       tools/    memory/
connector   executor  (Redis + PG)
```

**Стек:**

| Компонент    | Технология                                  |
|--------------|---------------------------------------------|
| Backend      | FastAPI + Python 3.11                       |
| LLM          | Anthropic Claude (основной), OpenAI, Mistral |
| Сессии       | Redis 7                                     |
| База данных  | PostgreSQL 16                               |
| Каналы       | Telegram Bot API, Web SSE                   |
| Деплой (dev) | Docker Compose + ngrok                      |

---

## Быстрый старт

### Предварительные требования

- Docker 24+ и Docker Compose plugin (`docker compose version`)
- Или Python 3.11+ для локального запуска
- API-ключ Anthropic (или OpenAI/Mistral)
- Telegram-бот (токен от [@BotFather](https://t.me/BotFather))
- ngrok для dev-туннеля (опционально)

### 1. Клонировать и настроить окружение

```bash
git clone <repo-url> TravelAgent
cd TravelAgent
cp .env.example .env
```

Открыть `.env` и заполнить значения (см. раздел [Конфигурация](#конфигурация)).

### 2. Запустить через Docker Compose

```bash
docker compose up -d --build
```

Первый запуск занимает ~2 минуты (сборка образа, скачивание postgres/redis).

### 3. Применить миграции

```bash
docker compose exec app alembic -c alembic/alembic.ini upgrade head
```

### 4. Проверить здоровье

```bash
curl http://localhost:8000/health
# {"status":"ok","postgres":"ok","redis":"ok"}
```

---

## Конфигурация

Все переменные хранятся в файле `.env` (не коммитится в git).

```dotenv
# === LLM ===
# Активный провайдер: claude | openai | mistral
LLM_PROVIDER=claude

# Ключи провайдеров (нужен только ключ для активного провайдера)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
MISTRAL_API_KEY=...

# Модель по умолчанию (если не задана — используется дефолт провайдера)
# claude  → claude-3-5-sonnet-20241022
# openai  → gpt-4o
# mistral → mistral-large-latest
LLM_MODEL=

# Токены и температура (опционально)
LLM_MAX_TOKENS=2000
LLM_TEMPERATURE_GENERATION=0.5
LLM_TEMPERATURE_TOOLCALL=0.1

# === База данных ===
# В Docker Compose DATABASE_URL переопределяется автоматически
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/travelagent
REDIS_URL=redis://localhost:6379/0

# === Telegram ===
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
# URL вашего публичного сервера / ngrok-туннеля
TELEGRAM_WEBHOOK_URL=https://<your-domain>/webhook/telegram

# === App ===
MAX_STEPS=5             # Максимум шагов ReAct-цикла на сообщение
MAX_RECENT_MESSAGES=10  # Последних сообщений в контексте LLM
```

> **Замечание по Docker Compose:** переменные `DATABASE_URL` и `REDIS_URL` в `docker-compose.yml` указывают на имена сервисов (`postgres`, `redis`), переопределяя значения из `.env`. Для локального запуска без Docker используйте `localhost`.

---

## Запуск в Docker

### Полный запуск (с пересборкой)

```bash
docker compose up -d --build
```

### Только пересборка приложения (без пересборки postgres/redis)

```bash
docker compose build --no-cache app
docker compose up -d app
```

### Просмотр логов

```bash
# Все сервисы
docker compose logs -f

# Только приложение
docker compose logs -f app

# Последние 50 строк
docker compose logs --tail=50 app
```

### Остановка

```bash
docker compose down          # остановить контейнеры
docker compose down -v       # + удалить volumes (сбросит БД и Redis)
```

### Перезапуск только приложения

```bash
docker compose restart app
```

---

## Локальный запуск без Docker

Для разработки удобно запускать только postgres и redis в Docker, а приложение — напрямую.

### 1. Запустить инфраструктуру

```bash
docker compose up -d postgres redis
```

### 2. Создать виртуальное окружение

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Настроить `.env`

Убедитесь, что `DATABASE_URL` и `REDIS_URL` указывают на `localhost`:

```dotenv
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/travelagent
REDIS_URL=redis://localhost:6379/0
```

### 4. Применить миграции

```bash
alembic -c alembic/alembic.ini upgrade head
```

### 5. Запустить приложение

```bash
PYTHONPATH=. uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Флаг `--reload` включает hot-reload при изменении файлов.

---

## Миграции базы данных

Миграции хранятся в `alembic/versions/`. Используется [Alembic](https://alembic.sqlalchemy.org/).

```bash
# Применить все миграции
docker compose exec app alembic -c alembic/alembic.ini upgrade head

# Откатить последнюю миграцию
docker compose exec app alembic -c alembic/alembic.ini downgrade -1

# Текущая версия схемы
docker compose exec app alembic -c alembic/alembic.ini current

# История миграций
docker compose exec app alembic -c alembic/alembic.ini history --verbose
```

**Схема БД:** `clients`, `client_profile`, `sessions`, `messages`, `leads`, `itineraries`, `interactions`.

---

## Telegram-бот: webhook через ngrok

Для локальной разработки Telegram требует публичный HTTPS-URL. ngrok создаёт туннель к локальному серверу.

### 1. Установить ngrok

```bash
# Ubuntu/Debian через snap
sudo snap install ngrok

# Или скачать с https://ngrok.com/download
```

### 2. Авторизоваться (один раз)

```bash
ngrok config add-authtoken <ваш_токен_с_dashboard.ngrok.com>
```

### 3. Запустить туннель

```bash
ngrok http 8000
```

Вы увидите URL вида `https://xxxx-xx-xx.ngrok-free.dev`. Скопируйте его.

### 4. Обновить `.env`

```dotenv
TELEGRAM_WEBHOOK_URL=https://xxxx-xx-xx.ngrok-free.dev/webhook/telegram
```

Перезапустить приложение:

```bash
docker compose restart app
# или при локальном запуске — перезапустить uvicorn
```

### 5. Зарегистрировать webhook в Telegram

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://xxxx-xx-xx.ngrok-free.dev/webhook/telegram"
# {"ok":true,"result":true,"description":"Webhook was set"}
```

### 6. Проверить регистрацию

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo"
```

> **Замечание:** URL ngrok меняется при каждом запуске (бесплатный план). При рестарте ngrok нужно повторить шаги 4–5.

---

## API-эндпоинты

### `GET /health`

Проверка состояния сервиса.

```bash
curl http://localhost:8000/health
# {"status":"ok","postgres":"ok","redis":"ok"}
```

### `POST /chat`

Отправить сообщение через Web-интерфейс.

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Привет, хочу тур в Мальдивы на 2 недели",
    "telegram_id": 123456789,
    "channel": "web"
  }'
```

Ответ:

```json
{
  "reply": "Отлично! Расскажите подробнее...",
  "session_id": "uuid",
  "stage": "qualification",
  "lead_id": null
}
```

### `POST /webhook/telegram`

Принимает обновления от Telegram. Не вызывается напрямую — Telegram отправляет сюда события автоматически.

---

## Тесты

```bash
# В Docker
docker compose exec app pytest tests/ -v

# Локально (с активированным .venv)
pytest tests/ -v

# Только unit-тесты
pytest tests/unit/ -v

# Только integration-тесты (требуют запущенный postgres + redis)
pytest tests/integration/ -v

# С покрытием
pytest tests/ --cov=src --cov-report=term-missing
```

---

## Структура проекта

```
TravelAgent/
├── .env.example              # Шаблон переменных окружения
├── docker-compose.yml        # Оркестрация: app + postgres + redis
├── Dockerfile                # Многоэтапная сборка (builder + runtime)
├── requirements.txt          # Python-зависимости
│
├── alembic/                  # Миграции PostgreSQL
│   ├── alembic.ini
│   ├── env.py
│   └── versions/
│       ├── 0001_initial_schema.py
│       ├── 0002_interactions.py
│       └── 0003_indexes.py
│
├── src/
│   ├── main.py               # FastAPI app + lifespan (pool, redis, LLMConnector)
│   ├── config.py             # Глобальные настройки (Settings)
│   ├── orchestrator.py       # ReAct-цикл: LLM → tools → ответ
│   ├── router.py             # Классификатор интентов
│   ├── decision.py           # Decision logic: stage × intent → available_tools
│   │
│   ├── api/
│   │   └── router.py         # FastAPI-роуты: /chat, /health, /webhook/telegram
│   │
│   ├── channels/
│   │   └── telegram.py       # PTB webhook handler
│   │
│   ├── llm/
│   │   ├── connector.py      # Единый интерфейс над провайдерами
│   │   ├── config.py         # LLMConfig (provider, model, temperature, tokens)
│   │   ├── providers/        # claude.py | openai.py | mistral.py
│   │   ├── prompts/          # system_prompt, router_prompt, stage_prompt, ...
│   │   ├── context_builder.py
│   │   ├── tools_schema.py   # JSON-схемы инструментов для LLM
│   │   ├── output_guard.py   # Валидация ответов LLM
│   │   └── resilience.py     # Retry + Circuit Breaker
│   │
│   ├── memory/
│   │   ├── db.py             # asyncpg pool
│   │   ├── redis_client.py   # aioredis client
│   │   ├── redis_session.py  # stage, summary, scratchpad в Redis
│   │   ├── repositories/     # clients, sessions, messages, leads, interactions
│   │   └── models.py         # Pydantic-модели Memory Layer
│   │
│   ├── models/
│   │   ├── chat.py           # ChatRequest, ChatResponse
│   │   └── tools.py          # Tool input/output модели
│   │
│   └── tools/
│       ├── executor.py       # Диспетчер вызовов инструментов
│       ├── search_tours.py   # Поиск туров
│       ├── leads.py          # Создание лида в CRM
│       └── client_profile.py # Обновление профиля клиента
│
├── tests/
│   ├── unit/                 # Unit-тесты без внешних зависимостей
│   ├── integration/          # Тесты с реальным postgres + redis
│   ├── evals/                # LLM-качество: router, tone, tool-calls
│   └── acceptance/           # End-to-end сценарии
│
└── docs/
    ├── product-proposal.md
    ├── system-design.md
    ├── governance.md
    ├── specs/
    └── diagrams/
```

---

## Документация

- [Продуктовое предложение](docs/product-proposal.md) — обоснование идеи, метрики, архитектура, data flow
- [System Design](docs/system-design.md) — детальная архитектура, ADR, компонентные диаграммы
- [Governance](docs/governance.md) — реестр рисков, политика логирования, безопасность

### Спецификации компонентов (`docs/specs/`)

| Спецификация | Домен | Описание |
|---|---|---|
| [spec-orchestrator.md](docs/specs/spec-orchestrator.md) | Backend | Orchestrator, Router, Decision Logic |
| [spec-memory-context.md](docs/specs/spec-memory-context.md) | DBA | Memory Layer: Redis, PostgreSQL, Summarizer, Profile Updater |
| [spec-observability.md](docs/specs/spec-observability.md) | DevOps | Метрики, логи, алерты, evals, Prompt Management |
| [spec-tools-api.md](docs/specs/spec-tools-api.md) | Backend | Tools Layer: search_tours, create_lead, get_policy_info |
| [spec-retriever.md](docs/specs/spec-retriever.md) | Backend | Retrieval-контур, векторный поиск |
| [spec-serving-config.md](docs/specs/spec-serving-config.md) | DevOps | Конфигурация, деплой, LLM-провайдеры |

### Диаграммы (`docs/diagrams/`)

| Диаграмма | Описание |
|---|---|
| [state-machine-funnel.md](docs/diagrams/state-machine-funnel.md) | State Machine воронки продаж (cold → closing) |
| [c4-context.md](docs/diagrams/c4-context.md) | C4 Context — система в окружении |
| [c4-container.md](docs/diagrams/c4-container.md) | C4 Container — контейнеры системы |
| [c4-component.md](docs/diagrams/c4-component.md) | C4 Component — компоненты ядра |
| [data-flow.md](docs/diagrams/data-flow.md) | Поток данных |
| [workflow-request.md](docs/diagrams/workflow-request.md) | Workflow обработки запроса |
