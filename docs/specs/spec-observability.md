# Спецификация: Observability & Evals — TravelAgent

## 1. Обзор

Observability охватывает три уровня:
- **Технический** — latency, errors, ресурсы (Prometheus + Grafana)
- **Бизнесовый** — конверсия лидов, воронка, intent-распределение (PostgreSQL + запросы)
- **Агентный (evals)** — качество routing/decision/tool-calls/tone (SLO targets, сэмплинг)

Цель: обнаруживать деградацию LLM-качества, контролировать расходы, поддерживать SLA на latency.

---

## 2. Prometheus-метрики

| Метрика | Тип | Лейблы | Описание |
|---|---|---|---|
| `travelagent_request_duration_seconds` | Histogram | `channel`, `intent`, `stage` | Latency end-to-end |
| `travelagent_llm_tokens_total` | Counter | `provider`, `model`, `direction` (input/output) | Токены по провайдеру/модели |
| `travelagent_llm_cost_usd_total` | Counter | `provider`, `model` | Стоимость LLM-запросов |
| `travelagent_tool_calls_total` | Counter | `tool_name`, `status` (ok/error) | Вызовы tools по имени |
| `travelagent_agent_steps_total` | Histogram | `channel`, `intent` | Количество шагов на сообщение |
| `travelagent_errors_total` | Counter | `component`, `error_type` | Ошибки по компоненту и типу |
| `travelagent_active_sessions` | Gauge | `channel` | Активные сессии |
| `travelagent_rate_limit_hits_total` | Counter | `channel`, `limit_type` | Срабатывания rate limit |

**Примеры PromQL:**

```promql
# p95 latency за 5 минут
histogram_quantile(0.95, rate(travelagent_request_duration_seconds_bucket[5m]))

# Стоимость LLM за сутки
increase(travelagent_llm_cost_usd_total[24h])

# Error rate
rate(travelagent_errors_total[2m]) / rate(travelagent_request_duration_seconds_count[2m])
```

---

## 3. Бизнес-метрики

Считаются SQL-запросами к PostgreSQL (таблицы `sessions`, `leads`, `messages`).

| Метрика | Формула | Хранение |
|---|---|---|
| Конверсия в лид | `leads_created / sessions_started` | Агрегат в `leads` |
| Доля «подогретых» лидов | `leads with full_profile / total_leads` | `leads.profile_completeness` |
| Распределение intent | `COUNT(*) GROUP BY intent` | `messages.intent` |
| Распределение stage | `COUNT(*) GROUP BY stage` | `sessions.stage` |
| Соответствие high-end тону | Ручная оценка (сэмплинг 5%) | `evals` таблица |

---

## 4. Агентные метрики (Evals)

### SLO-таргеты

| Компонент | Метрика | Цель |
|---|---|---|
| Router (intent classification) | Точность | ≥ 85% |
| Decision Logic (stage transition) | Корректность | ≥ 80% |
| Tool-calls | Правильность параметров | ≥ 80% |
| High-end tone | Соответствие стилю | ≥ 75% |
| Конверсия в лид | leads/sessions | ≥ 15% |

### Методология

- **Router/Decision**: offline-eval на golden dataset (100+ размеченных сессий), запускается при деплое.
- **Tool-calls**: структурная валидация (параметры, типы), логируется в `travelagent_tool_calls_total{status="error"}`.
- **Tone**: LLM-as-judge (промпт с критериями high-end), сэмплинг 5% запросов, результат в таблицу `evals`.
- **Конверсия**: бизнес-метрика из PostgreSQL, считается ежедневно.

---

## 5. Структурированное логирование

### JSON-схема

```json
{
  "timestamp": "2026-02-01T14:30:00.123Z",
  "level": "INFO",
  "component": "orchestrator",
  "session_id": "uuid",
  "client_id_hash": "sha256_hash",
  "channel": "telegram",
  "intent": "discovery",
  "stage": "qualified",
  "tools_called": ["search_tours"],
  "latency_ms": 3200,
  "tokens_used": 1840,
  "cost_usd": 0.018,
  "agent_steps": 2
}
```

### Уровни логирования

| Level | Когда |
|---|---|
| `DEBUG` | Tool-вызовы, шаги агента (только dev) |
| `INFO` | Каждый обработанный запрос |
| `WARNING` | Превышение порогов latency/cost, fallback |
| `ERROR` | Исключения, недоступность внешних сервисов |
| `CRITICAL` | Redis/DB недоступны, бюджет исчерпан |

### Компоненты (поле `component`)

`orchestrator` | `router` | `decision_logic` | `llm_connector` | `tool_search_tours` | `tool_create_lead` | `telegram_adapter` | `web_adapter` | `memory`

---

## 6. PII-маскирование в логах

### Логируется

- `client_id_hash` (SHA-256 от telegram_id/user_id)
- `session_id` (UUID)
- `channel`, `timestamp`
- `intent`, `stage`
- Длина сообщения (`message_length_chars`)
- `tokens_used`, `latency_ms`, `cost_usd`
- Имена вызванных tools (без параметров с PII)

### НЕ логируется

- Полный текст сообщений (содержащих phone/email/паспорт)
- `telegram_id` в открытом виде
- `email`, `phone`, `passport_data` — нигде в логах
- Сессионные токены и API-ключи в plaintext
- Параметры tool-вызовов, если содержат контактные данные

### Маскирование в коде

```python
import re

PHONE_RE = re.compile(r'\+?\d[\d\s\-]{7,}\d')
EMAIL_RE = re.compile(r'[\w.+-]+@[\w-]+\.[a-z]{2,}')

def mask_pii(text: str) -> str:
    text = PHONE_RE.sub('[PHONE]', text)
    text = EMAIL_RE.sub('[EMAIL]', text)
    return text
```

---

## 7. Алерты

| Условие | Порог | Окно | Действие |
|---|---|---|---|
| p95 latency > 20s | Постоянно | 5 мин | Slack + email алерт |
| Дневные расходы LLM > $20 | Разово | — | Немедленный алерт, заморозка |
| Error rate > 5% | Постоянно | 2 мин | Алерт + ручная проверка |
| Redis недоступен | Любое событие | — | Критический алерт, fallback |
| Rate limit hits > 100/мин | — | 1 мин | Предупреждение |

**Конфигурация Alertmanager** (фрагмент):

```yaml
groups:
  - name: travelagent
    rules:
      - alert: HighLatency
        expr: histogram_quantile(0.95, rate(travelagent_request_duration_seconds_bucket[5m])) > 20
        for: 5m
        labels:
          severity: warning
      - alert: HighErrorRate
        expr: rate(travelagent_errors_total[2m]) / rate(travelagent_request_duration_seconds_count[2m]) > 0.05
        for: 2m
        labels:
          severity: critical
      - alert: DailyLLMBudget
        expr: increase(travelagent_llm_cost_usd_total[24h]) > 20
        labels:
          severity: critical
```

---

## 8. Distributed Tracing

Трейс одного запроса (OpenTelemetry):

```
[telegram_adapter] receive_message          span_id=A  → root
  [orchestrator] handle_message             span_id=B  parent=A
    [router] classify_intent                span_id=C  parent=B
    [decision_logic] get_stage              span_id=D  parent=B
    [memory] load_session (Redis)           span_id=E  parent=B
    [llm_connector] call_llm               span_id=F  parent=B
      [tool] search_tours                   span_id=G  parent=F
    [memory] save_session (Redis)           span_id=H  parent=B
    [memory] log_interaction (PostgreSQL)   span_id=I  parent=B
  [telegram_adapter] send_response          span_id=J  parent=A
```

**Обязательные атрибуты спана:** `session_id`, `channel`, `intent`, `stage`, `component`.

Экспорт: OTLP → Jaeger (dev) / managed tracing backend (prod).

---

## 9. Grafana-дашборды

### Dashboard: Overview

- RPS по каналам (telegram / web)
- p50/p95/p99 latency (time series)
- Error rate (%)
- Активные сессии (gauge)

### Dashboard: LLM & Costs

- Токены в/out по модели (stacked bar)
- Стоимость в час / за день (time series + stat)
- Вызовы tools (bar chart по `tool_name`)
- Шаги агента — histogram

### Dashboard: Business & Evals

- Конверсия в лид (stat, trend)
- Распределение intent (pie chart)
- Воронка stage (funnel)
- SLO-таблица: текущее vs. target

### Dashboard: Alerts & Errors

- Таблица активных алертов
- Ошибки по компоненту (heatmap)
- Rate limit hits (time series)

---

## 10. Сроки хранения

| Тип данных | Хранилище | Срок |
|---|---|---|
| Структурированные логи (JSON) | Loki / managed logs | 14 дней |
| Prometheus-метрики | Prometheus TSDB | 15 дней |
| Трейсы (spans) | Jaeger / managed | 7 дней |
| Eval-результаты | PostgreSQL (`evals`) | 90 дней |
| Агрегированные бизнес-метрики | PostgreSQL | Бессрочно |
