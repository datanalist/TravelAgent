# Spec: Serving / Config — TravelAgent

## 1. Обзор

| Endpoint | Метод | Content-Type | Назначение |
|---|---|---|---|
| `/telegram/webhook` | POST | application/json | Telegram Bot API webhook |
| `/chat/stream` | POST | text/event-stream | Web SSE чат |
| `/health` | GET | application/json | Health check |

**Порт приложения:** `8000`  
**ASGI сервер:** Uvicorn

---

## 2. FastAPI / Uvicorn конфигурация

```python
# uvicorn запуск
uvicorn src.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --workers 2 \
  --timeout-keep-alive 30 \
  --log-level ${LOG_LEVEL:-info}
```

| Параметр | Значение | Обоснование |
|---|---|---|
| `workers` | 2 | I/O-bound нагрузка, LLM streaming |
| `timeout-keep-alive` | 30s | SSE соединения держатся до конца стрима |
| `timeout-graceful-shutdown` | 10s | Дать завершить активные стримы |

**SSE формат (`/chat/stream`):**
```
data: {"token": "Отличный", "done": false}\n\n
data: {"token": " выбор!", "done": false}\n\n
data: {"done": true, "metadata": {"intent": "discovery", "stage": "qualified"}}\n\n
```

---

## 3. ENV переменные

| Переменная | Обязательная | Пример | Описание |
|---|---|---|---|
| `LLM_PROVIDER` | ✅ | `claude` | Активный провайдер (`claude` / `openai` / `mistral`) |
| `LLM_MODEL` | ✅ | `claude-3-5-sonnet` | Идентификатор модели |
| `LLM_MAX_TOKENS` | ✅ | `2000` | Макс. токенов в ответе |
| `LLM_TEMPERATURE_GENERATION` | ✅ | `0.7` | Температура для генерации текста |
| `LLM_TEMPERATURE_TOOLCALL` | ✅ | `0.1` | Температура для tool-calling |
| `ANTHROPIC_API_KEY` | ✅* | `sk-ant-...` | API ключ Claude |
| `OPENAI_API_KEY` | ✅* | `sk-...` | API ключ OpenAI |
| `MISTRAL_API_KEY` | ✅* | `...` | API ключ Mistral |
| `TELEGRAM_BOT_TOKEN` | ✅ | `123456:ABC...` | Токен Telegram-бота |
| `DATABASE_URL` | ✅ | `postgresql://agent:pass@postgres/travelagent` | PostgreSQL DSN |
| `REDIS_URL` | ✅ | `redis://redis:6379/0` | Redis DSN |
| `SECRET_KEY` | ✅ | `<random 32 bytes hex>` | Секрет для подписи токенов |
| `LOG_LEVEL` | — | `INFO` | Уровень логирования (DEBUG/INFO/WARNING/ERROR) |
| `MAX_AGENT_STEPS` | — | `5` | Макс. шагов ReAct-агента за диалог |
| `RATE_LIMIT_PER_MINUTE` | — | `20` | Макс. сообщений/мин на `client_id` |
| `DB_PASSWORD` | ✅ | `...` | Пароль PostgreSQL (используется в Compose) |

> \* Обязателен ключ только активного провайдера. Остальные — для fallback.

---

## 4. LLM провайдеры

| Провайдер | Роль | Модель | Температура |
|---|---|---|---|
| Claude (Anthropic) | Основной | `claude-3-5-sonnet` | gen: 0.7 / tool: 0.1 |
| OpenAI | Альтернатива | `gpt-4o` | gen: 0.7 / tool: 0.1 |
| Mistral | Дешёвый fallback / Router | `mistral-large` | gen: 0.7 / tool: 0.1 |

**Retry / Circuit Breaker:**
- Retry: exponential backoff, 3 попытки (delays: 1s → 2s → 4s)
- Circuit Breaker: открывается после **5 ошибок за 60 секунд**, cooldown **30 секунд**
- При открытом Circuit Breaker: немедленный fallback на следующий провайдер

**Ограничения по стоимости:**
- Макс. токенов на ответ: **2000**
- Дневной бюджет LLM: **$100–200**
- Целевая стоимость диалога (10 сообщений): **≤ $0.15**

---

## 5. Docker Compose — сервисы

| Сервис | Образ | Порт | Назначение |
|---|---|---|---|
| `app` | `./Dockerfile` | 8000 | FastAPI приложение |
| `postgres` | `postgres:15` | 5432 | Основная БД |
| `redis` | `redis:7-alpine` | 6379 | Session memory, кэш |
| `prometheus` | `prom/prometheus` | 9090 | Сбор метрик |
| `grafana` | `grafana/grafana` | 3000 | Дашборды |

```yaml
services:
  app:
    build: .
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [postgres, redis]

  postgres:
    image: postgres:15
    volumes: [pgdata:/var/lib/postgresql/data]
    environment:
      POSTGRES_DB: travelagent
      POSTGRES_USER: agent
      POSTGRES_PASSWORD: ${DB_PASSWORD}

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru

  prometheus:
    image: prom/prometheus

  grafana:
    image: grafana/grafana
```

---

## 6. Health Check

**Endpoint:** `GET /health`  
**Ожидаемый статус:** `200 OK`

**Что проверяет:**
- Доступность PostgreSQL (простой `SELECT 1`)
- Доступность Redis (`PING`)
- Наличие конфигурации LLM-провайдера (ключ задан)

**Формат ответа:**
```json
{
  "status": "ok",
  "postgres": "ok",
  "redis": "ok",
  "llm_provider": "claude"
}
```

При деградации одного из компонентов:
```json
{
  "status": "degraded",
  "postgres": "ok",
  "redis": "error",
  "llm_provider": "claude"
}
```
HTTP-статус при `degraded`: `200` (приложение живо, но работает в fallback-режиме).

---

## 7. Graceful Shutdown

Последовательность при получении `SIGTERM`:

1. Uvicorn перестаёт принимать новые соединения
2. Активные SSE-стримы получают `data: {"done": true, "error": "shutdown"}\n\n` и закрываются
3. In-flight запросы к LLM ждут завершения (таймаут **10 секунд**)
4. Закрываются пулы соединений PostgreSQL и Redis
5. Процесс завершается с кодом `0`

---

## 8. Dev vs Prod

| Параметр | Dev | Prod |
|---|---|---|
| Публичный endpoint | ngrok tunnel | Ingress / Load Balancer |
| HTTPS | ngrok (автоматически) | Let's Encrypt |
| LLM | Claude (без алертов) | Claude + cost alerts при >$150/день |
| CRM | Таблица `leads` в PostgreSQL | HubSpot / amoCRM API |
| Мониторинг | Prometheus + Grafana (local) | Managed observability (Grafana Cloud / Datadog) |
| `LOG_LEVEL` | `DEBUG` | `INFO` |
| Uvicorn workers | 1 | 2+ |
| Telegram webhook | `ngrok_url/telegram/webhook` | `https://domain.com/telegram/webhook` |

---

## 9. SLO и операционные ограничения

### SLO (Service Level Objectives)

| Метрика | Target |
|---|---|
| Time-to-first-token (p50) | ≤ 2 секунды |
| Полный ответ (p95) | ≤ 15 секунд |
| First response (бизнес) | < 5 секунд |
| Uptime | ≥ 95% |

### Ограничения

| Параметр | Значение |
|---|---|
| Rate limit на `client_id` | 20 сообщений/мин |
| Max токенов на ответ | 2000 |
| Max шагов ReAct-агента | 5 |
| Дневной бюджет LLM | $100–200 |
| Стоимость диалога (10 msg) | ≤ $0.15 |
| Redis maxmemory | 256 MB (`allkeys-lru`) |

### Graceful Degradation

| Компонент | Сбой | Поведение |
|---|---|---|
| LLM API | Недоступен / таймаут | Retry 3x → fallback провайдер → «Сервис временно недоступен» |
| Redis | Недоступен | Работа без session memory (stateless fallback) |
| PostgreSQL | Недоступен | Аварийный режим: базовый ответ, без персонализации, без записи лидов |
