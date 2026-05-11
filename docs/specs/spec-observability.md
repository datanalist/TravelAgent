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

---

## 11. Prompt / Eval Management

### 11.1 Prompt Registry

Все промпты, используемые в системе, версионируются и хранятся централизованно. Это позволяет откатиться, сравнивать версии и запускать CI-eval при изменениях.

#### Таблица `prompts` (PostgreSQL)

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID PK | Идентификатор записи |
| `name` | VARCHAR | Логическое имя (`router_intent`, `summarizer`, `tone_judge`, ...) |
| `version` | VARCHAR | Семантическая версия (`1.0.0`, `1.1.0`) |
| `content_hash` | CHAR(64) | SHA-256 от текста промпта (детектор изменений) |
| `system_prompt` | TEXT | Системный промпт |
| `user_template` | TEXT | Шаблон user-части (Jinja2 / f-string) |
| `provider` | VARCHAR | Целевой провайдер (`claude`, `openai`, `mistral`, `any`) |
| `tags` | JSONB | `["router", "few-shot"]` |
| `author` | VARCHAR | Кто создал / изменил |
| `created_at` | TIMESTAMPTZ | Время создания |
| `is_active` | BOOLEAN | Используется ли прямо сейчас |

#### Реестр активных промптов

| Имя (`name`) | Версия | Компонент | Описание |
|---|---|---|---|
| `router_intent` | 1.0.0 | Router | Few-shot классификация intent (JSON output) |
| `summarizer` | 1.0.0 | Conversation Summarizer | Сжатие диалога в 3–5 фактов |
| `main_agent` | 1.0.0 | LLM Connector | Системный промпт агента (тон, роль, правила) |
| `profile_extractor` | 1.0.0 | Profile Updater | Извлечение фактов о клиенте |
| `stage_classifier` | 1.0.0 | Stage Tracker | Классификация стадии воронки |
| `tone_judge` | 1.0.0 | LLM-as-Judge | Оценка соответствия high-end тону |

#### Хранение файлов промптов

```
prompts/
├── router_intent/
│   ├── v1.0.0.md          # Промпт в markdown-формате
│   └── v1.1.0.md
├── summarizer/
│   └── v1.0.0.md
├── main_agent/
│   └── v1.0.0.md
└── ...
```

При деплое `content_hash` пересчитывается и сверяется с БД. Расхождение → предупреждение в логах.

---

### 11.2 Golden Dataset

Золотой датасет — аннотированные примеры для offline-eval агентных компонентов. Хранится в `data/golden/`.

#### Структура датасета

```
data/golden/
├── router/             # Примеры для intent classification
│   └── examples.jsonl
├── decision/           # Примеры для stage transition
│   └── examples.jsonl
├── tone/               # Примеры для оценки high-end тона
│   └── examples.jsonl
└── tool_calls/         # Примеры корректных tool-вызовов
    └── examples.jsonl
```

#### Схема одного примера (JSONL)

```json
{
  "id": "router_001",
  "component": "router",
  "input": {
    "message": "Хочу слетать на Мальдивы в феврале, бюджет до 200к",
    "context": {"stage": "cold", "prior_messages": []}
  },
  "expected_output": {
    "intent": "itinerary_search"
  },
  "metadata": {
    "difficulty": "easy",
    "annotator": "human",
    "created_at": "2026-02-01"
  }
}
```

#### Распределение датасета (минимум)

| Компонент | Количество | Категории |
|---|---|---|
| Router (intent) | 40+ | по 5–7 на каждый intent |
| Decision Logic | 30+ | по 4–5 на каждую стадию |
| High-end Tone | 20+ | passing / failing примеры |
| Tool-calls | 20+ | корректные / некорректные параметры |
| **Итого** | **110+** | — |

Датасет пополняется из:
1. Ручной разметки (новые edge-cases, найденные в продакшне)
2. Экспорта реальных сессий с исправленными метками (раз в 2 недели)

---

### 11.3 CI-eval Pipeline

Eval-пайплайн запускается автоматически при каждом деплое и при изменении промптов.

#### Шаги пайплайна

```
1. [trigger]    PR merge в main / изменение файла в prompts/
2. [load]       Загрузить golden dataset из data/golden/
3. [run]        Прогнать каждый пример через актуальный компонент
4. [score]      Сравнить вывод с expected_output (exact match / LLM-judge)
5. [report]     Записать результаты в PostgreSQL (таблица evals)
6. [gate]       Если score < SLO-порога → fail деплой / алерт
```

#### Конфигурация CI (GitHub Actions фрагмент)

```yaml
name: eval-pipeline

on:
  push:
    branches: [main]
    paths:
      - "prompts/**"
      - "src/router.py"
      - "src/decision.py"

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run evals
        run: uv run python -m evals.run --dataset data/golden/ --report evals/report.json
      - name: Check SLO gates
        run: uv run python -m evals.gate --report evals/report.json --config evals/slo.yaml
```

#### Конфигурация порогов (`evals/slo.yaml`)

```yaml
gates:
  router_accuracy:
    metric: accuracy
    threshold: 0.85
    action: fail_deploy

  decision_accuracy:
    metric: accuracy
    threshold: 0.80
    action: fail_deploy

  tool_call_correctness:
    metric: param_accuracy
    threshold: 0.80
    action: fail_deploy

  tone_score:
    metric: llm_judge_pass_rate
    threshold: 0.75
    action: warn_only
```

#### Таблица `evals` (PostgreSQL)

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID PK | ID записи |
| `run_id` | UUID | Идентификатор запуска пайплайна |
| `component` | VARCHAR | `router`, `decision`, `tone`, `tool_calls` |
| `prompt_name` | VARCHAR | Имя промпта из реестра |
| `prompt_version` | VARCHAR | Версия промпта |
| `example_id` | VARCHAR | ID примера из golden dataset |
| `input` | JSONB | Входные данные |
| `expected` | JSONB | Ожидаемый вывод |
| `actual` | JSONB | Фактический вывод LLM |
| `score` | NUMERIC(4,3) | 0.000–1.000 |
| `passed` | BOOLEAN | Прошёл ли порог |
| `latency_ms` | INT | Время выполнения |
| `tokens_used` | INT | Токены |
| `created_at` | TIMESTAMPTZ | Время запуска |

---

### 11.4 A/B-тесты промптов

A/B-тесты позволяют сравнивать версии промптов на реальном трафике без полного переключения.

#### Схема разделения трафика

```python
def get_prompt_variant(client_id: str, prompt_name: str) -> str:
    """Детерминированное назначение варианта по client_id."""
    bucket = int(hashlib.md5(f"{client_id}:{prompt_name}".encode()).hexdigest(), 16) % 100
    config = ab_config[prompt_name]  # из env / БД
    if bucket < config["control_pct"]:
        return config["control_version"]   # напр. "1.0.0"
    else:
        return config["treatment_version"] # напр. "1.1.0"
```

**Принципы:**
- Разделение по `client_id` (не по сессии) — клиент всегда видит один вариант
- Минимальная длительность теста: 7 дней или 200+ сессий на вариант
- Метрики успеха: конверсия в лид, tone score (LLM-judge), latency

#### Конфигурация A/B теста

```json
{
  "prompt_name": "summarizer",
  "control_version": "1.0.0",
  "treatment_version": "1.1.0",
  "control_pct": 50,
  "start_date": "2026-03-01",
  "end_date": "2026-03-15",
  "primary_metric": "lead_conversion_rate",
  "secondary_metrics": ["latency_ms", "tokens_used"]
}
```

#### Оценка результатов

| Метрика | Метод сравнения | Порог значимости |
|---|---|---|
| Конверсия в лид | Z-test по долям | p < 0.05 |
| Tone score | Mann-Whitney U | p < 0.05 |
| Latency | Сравнение p95 | Δ > 500ms считается регрессией |
| Стоимость токенов | Среднее ± std | Δ > 20% считается регрессией |

Результаты сохраняются в таблицу `evals` с тегом `ab_test_run_id`.
