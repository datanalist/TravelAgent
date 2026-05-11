# Спецификация: Memory / Context Layer

**Версия:** 1.0  
**Статус:** Draft  
**Домен:** agent-travel-dba  
**Источник истины:** [System Design, ADR-003](../system-design.md)

---

## 1. Обзор архитектуры памяти

Двухуровневая память (ADR-003):

| Уровень | Хранилище | Назначение | Срок хранения |
|---|---|---|---|
| Краткосрочный | Redis | Контекст активной сессии | TTL 24h |
| Долгосрочный | PostgreSQL | Профиль клиента, история сессий | 90 дней / по решению оператора |

**Источник истины — PostgreSQL.** Redis — кэш для быстрого доступа во время диалога. При недоступности Redis или истёкшем TTL — fallback на PostgreSQL.

---

## 2. Redis — структура ключей

### 2.1 Таблица ключей

| Ключ | Тип Redis | TTL | Содержимое |
|---|---|---|---|
| `session:{id}:summary` | String (JSON) | 24h | Сжатая история диалога |
| `session:{id}:stage` | String | 24h | Текущая стадия воронки |
| `session:{id}:scratchpad` | String (JSON) | 24h | Временные данные между шагами |
| `ratelimit:{client_id}` | Counter | 1 min | Счётчик сообщений в минуту |

### 2.2 Формат `session:{id}:summary`

```json
{
  "client_facts": ["бюджет до 150к руб", "хочет море в феврале", "2 взрослых"],
  "current_request": "подбор тура Мальдивы/ОАЭ",
  "stage": "proposal",
  "last_shown_tours": ["tour_id_abc", "tour_id_def"],
  "updated_at": "2026-02-01T14:30:00Z"
}
```

### 2.3 Формат `session:{id}:scratchpad`

```json
{
  "search_results": ["tour_id_1", "tour_id_2", "tour_id_3"],
  "draft_proposal": "Предлагаю рассмотреть...",
  "pending_clarifications": ["дата вылета?", "нужен ли трансфер?"]
}
```

### 2.4 Значения `session:{id}:stage`

`cold` | `discovery` | `qualified` | `proposal` | `objection` | `closing` | `follow_up`

---

## 3. PostgreSQL — таблицы Memory Layer

### 3.1 `clients`

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID PK | Внутренний ID |
| `telegram_id` | BIGINT UNIQUE | Telegram user ID |
| `name` | VARCHAR | Имя клиента |
| `email` | VARCHAR | Email |
| `phone` | VARCHAR | Телефон |
| `segment` | VARCHAR | Сегмент (vip, standard, ...) |
| `language` | VARCHAR(5) | Язык общения (ru, en, ...) |
| `preferred_style` | VARCHAR | Предпочитаемый стиль коммуникации |

### 3.2 `client_profile`

| Поле | Тип | Описание |
|---|---|---|
| `client_id` | UUID FK → clients | Клиент |
| `budget_range` | JSONB | `{"min": 50000, "max": 150000, "currency": "RUB"}` |
| `preferred_destinations` | JSONB | `["Мальдивы", "ОАЭ", "Таиланд"]` |
| `travel_style` | VARCHAR | beach / city / adventure / luxury |
| `constraints` | JSONB | `{"children": true, "visa_issues": ["USA"], "diet": "halal", "airlines_excluded": ["UT"]}` |

### 3.3 `sessions`

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID PK | ID сессии |
| `client_id` | UUID FK → clients | Клиент |
| `channel` | VARCHAR | telegram / web |
| `status` | VARCHAR | active / closed / expired |
| `current_stage` | VARCHAR | Текущая стадия воронки |
| `summary` | JSONB | Персистентная копия Redis summary |
| `started_at` | TIMESTAMPTZ | Время начала |
| `updated_at` | TIMESTAMPTZ | Время последнего обновления |

### 3.4 `messages`

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID PK | ID сообщения |
| `session_id` | UUID FK → sessions | Сессия |
| `sender` | VARCHAR | user / assistant / system |
| `role` | VARCHAR | user / assistant / tool |
| `content` | TEXT | Текст сообщения |
| `metadata` | JSONB | tool_calls, tokens, latency и т.д. |
| `created_at` | TIMESTAMPTZ | Время создания |

### 3.5 `leads`

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID PK | ID лида |
| `client_id` | UUID FK → clients | Клиент |
| `status` | VARCHAR | new / proposal / contacted / won / lost |
| `budget` | NUMERIC | Бюджет лида |
| `destination` | VARCHAR | Направление |
| `travel_dates` | JSONB | `{"from": "2026-02-10", "to": "2026-02-20"}` |
| `probability` | NUMERIC(3,2) | Вероятность закрытия 0.00–1.00 |
| `created_at` | TIMESTAMPTZ | Создание |
| `updated_at` | TIMESTAMPTZ | Обновление |

---

## 4. Conversation Summarizer

### 4.1 Триггеры

- Число новых сообщений без пересчёта summary > N (настраивается, default: 10)
- Суммарный размер контекста > K токенов (default: 12 000)
- Явный запрос на пересчёт (например, при смене stage)

### 4.2 Алгоритм

```
1. Взять последние N сообщений из messages (PostgreSQL)
2. Передать LLM prompt: «Сожми диалог в 3-5 фактов о клиенте и его запросе»
3. Получить структуру: client_facts, current_request, stage, last_shown_tours
4. Записать в Redis: SET session:{id}:summary <json> EX 86400
5. Записать в PostgreSQL: UPDATE sessions SET summary = <json>, updated_at = NOW()
```

### 4.3 Выходной формат

```json
{
  "client_facts": ["<факт 1>", "<факт 2>", "..."],
  "current_request": "<текущий запрос одной фразой>",
  "stage": "<стадия>",
  "last_shown_tours": ["<tour_id>", "..."],
  "updated_at": "<ISO8601>"
}
```

---

## 5. Profile Updater

### 5.1 Что извлекается

Каждое извлечённое значение сопровождается **confidence score** (0.0–1.0), отражающим уверенность в правильности извлечения. Поле записывается в `client_profile` только если `confidence >= 0.70`.

| Факт | Метод извлечения | Confidence | Куда пишется |
|---|---|---|---|
| Бюджет (мин/макс) | `regex_currency` — точное число + единица | 0.95 | `client_profile.budget_range` |
| Бюджет (приблизительный) | LLM-extraction («около 150к», «не дороже...») | 0.75 | `client_profile.budget_range` |
| Город вылета (явный) | regex / справочник городов РФ | 0.90 | `client_profile.constraints.departure_city` |
| Город вылета (косвенный) | LLM-extraction | 0.65 → не пишется | — |
| Даты (dd.mm.yyyy) | regex точный | 0.95 | `leads.travel_dates` |
| Даты (месяц словом) | regex нормализация | 0.85 | `leads.travel_dates` |
| Даты (приблизительные) | LLM-extraction («в феврале», «на НГ») | 0.70 | `leads.travel_dates` |
| Стиль отдыха | LLM-классификация (4 класса) | 0.80 | `client_profile.travel_style` |
| Дети (явное упоминание) | regex / LLM | 0.90 | `client_profile.constraints.children` |
| Дети (косвенное) | LLM-inference | 0.60 → не пишется | — |
| Визовые ограничения | LLM-extraction | 0.75 | `client_profile.constraints.visa_issues` |
| Питание / авиакомпании | LLM-extraction | 0.75 | `client_profile.constraints` |
| Предпочитаемые направления | LLM-extraction | 0.80 | `client_profile.preferred_destinations` |

### 5.2 Шкала confidence

| Диапазон | Метод | Поведение |
|---|---|---|
| 0.90–1.00 | Точный regex, справочник | Записать, не перезаписывать более высоким |
| 0.75–0.89 | LLM с высокой уверенностью | Записать |
| 0.60–0.74 | LLM с неопределённостью | Не записывать, логировать как `candidate` |
| < 0.60 | Нет явных сигналов | Игнорировать |

### 5.3 Хранение confidence

Поле `profile_confidence` в `client_profile` хранит score по каждому извлечённому факту:

```json
{
  "budget_range": {
    "value": {"min": 100000, "max": 200000, "currency": "RUB"},
    "confidence": 0.95,
    "method": "regex_currency",
    "updated_at": "2026-02-01T14:30:00Z"
  },
  "travel_style": {
    "value": "beach",
    "confidence": 0.80,
    "method": "llm_classification",
    "updated_at": "2026-02-01T14:31:00Z"
  },
  "departure_city": {
    "value": "Москва",
    "confidence": 0.90,
    "method": "city_dictionary",
    "updated_at": "2026-02-01T14:30:00Z"
  }
}
```

Схема в PostgreSQL: поле `profile_confidence JSONB` в таблице `client_profile`.

### 5.4 Алгоритм обновления с confidence

```python
def update_profile_field(client_id: str, field: str, value: Any, confidence: float, method: str):
    existing = get_profile_confidence(client_id, field)
    if existing and existing["confidence"] >= confidence:
        # Не перезаписываем более уверенное значение менее уверенным
        return
    if confidence < 0.70:
        log_candidate(client_id, field, value, confidence)
        return
    upsert_profile(client_id, field, value)
    upsert_confidence(client_id, field, confidence, method)
```

### 5.5 Запись

```sql
INSERT INTO client_profile (client_id, budget_range, profile_confidence, updated_at)
VALUES (:client_id, :value, :confidence_json, NOW())
ON CONFLICT (client_id)
DO UPDATE SET
  budget_range = EXCLUDED.budget_range,
  profile_confidence = client_profile.profile_confidence || EXCLUDED.profile_confidence,
  updated_at = NOW()
WHERE (EXCLUDED.profile_confidence->>'confidence')::float
    > COALESCE((client_profile.profile_confidence->>'confidence')::float, 0);
```

Profile Updater срабатывает после каждого сообщения от пользователя (асинхронно, не блокирует ответ).

---

## 6. Stage Tracker

### 6.1 Хранение стадии

| Слой | Ключ / Поле | Тип | Когда обновляется |
|---|---|---|---|
| Redis | `session:{id}:stage` | String | При каждом переходе |
| PostgreSQL | `sessions.current_stage` | VARCHAR | При каждом переходе |
| CRM | `leads.status` | VARCHAR | При переходах квалификация→выше |

### 6.2 Маппинг stage → leads.status

| Stage | leads.status | Действие |
|---|---|---|
| `cold` | — | Лид не создаётся |
| `discovery` | — | Лид не создаётся |
| `qualified` | `new` | Создать лид |
| `proposal` | `proposal` | Обновить лид |
| `objection` | `contacted` | Обновить лид |
| `closing` | `won` / `lost` | Финализировать |
| `follow_up` | `contacted` | Обновить |

### 6.3 Алгоритм переключения

```
1. Определить новую стадию (Orchestrator / Stage Classifier LLM)
2. SET session:{id}:stage <new_stage> EX 86400  (Redis)
3. UPDATE sessions SET current_stage = <new_stage>  (PostgreSQL)
4. Если stage в маппинге → UPSERT leads SET status = <mapped_status>
5. Записать событие в metadata сообщения
```

---

## 7. Context Window Management

### 7.1 Порядок контекста для LLM

```
1. [system_prompt]           — инструкции агента
2. [client_profile]          — профиль клиента из PostgreSQL
3. [conversation_summary]    — summary из Redis / PostgreSQL
4. [recent_messages]         — последние 3–5 сообщений из messages
5. [current_message]         — входящее сообщение
```

### 7.2 Лимиты

| Параметр | Значение |
|---|---|
| Максимум токенов на запрос | 16 000 |
| Триггер сжатия | > 12 000 токенов |
| Recent messages при нормальном режиме | 5 сообщений |
| Recent messages при высокой нагрузке | 3 сообщения |
| Максимум результатов search_tours | top-5 (усечение из 10+) |

### 7.3 Стратегия усечения

```
если total_tokens > 12_000:
    заменить [recent_messages] на [conversation_summary]
    уменьшить recent_messages до 3
    усечь search_results до top-5
если total_tokens > 15_500:
    убрать [client_profile] (оставить только ключевые факты из summary)
```

---

## 8. Fallback стратегии

### 8.1 Redis недоступен

```
1. Загрузить sessions.summary из PostgreSQL
2. Загрузить sessions.current_stage из PostgreSQL
3. Работать только с PostgreSQL до восстановления Redis
4. При восстановлении Redis — синхронизировать из PostgreSQL
```

### 8.2 TTL истёк (`session:{id}:summary` отсутствует)

```
1. Запросить sessions.summary (PostgreSQL) по session_id
2. Восстановить Redis-ключи: SET session:{id}:summary <json> EX 86400
3. Продолжить работу штатно
```

### 8.3 PostgreSQL недоступен

- Работать только из Redis (деградированный режим)
- Новые сообщения не персистировать до восстановления
- Алертинг / circuit breaker на уровне инфраструктуры

---

## 9. Политика сроков хранения

| Данные | Хранилище | Срок | Примечание |
|---|---|---|---|
| Redis сессия (summary, stage, scratchpad) | Redis | 24 часа TTL | Автоудаление |
| Rate limit counter | Redis | 1 минута TTL | Автоудаление |
| Сессии + сообщения | PostgreSQL | 90 дней | Cron-удаление |
| Профили клиентов | PostgreSQL | По решению оператора | Ручное/регуляторное |
| Логи (audit, errors) | PostgreSQL / файлы | 14 дней | Ротация |
| Leads | PostgreSQL | По решению оператора | CRM-данные |
