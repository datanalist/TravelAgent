# Спецификация Tools / API — TravelAgent

> **Версия:** 1.0 · **Дата:** 2026-04-07  
> Источник истины: `docs/system-design.md` §7, §8, §9, §12

---

## 1. Обзор

Все инструменты расположены в `src/tools/`. LLM вызывает только разрешённые Decision Logic tools; `log_interaction` — исключительно программный вызов Orchestrator.

| Tool | Назначение | Backend |
|---|---|---|
| `search_tours` | Поиск туров по параметрам | Внутренняя БД / агрегатор |
| `get_client_profile` | Загрузка профиля клиента | PostgreSQL |
| `update_client_profile` | Обновление полей профиля | PostgreSQL |
| `create_lead` | Создание лида в CRM | PostgreSQL (таблица `leads`) |
| `update_lead_stage` | Смена стадии лида | PostgreSQL (таблица `leads`) |
| `get_policy_info` | Визовые требования и страховки | Внутренняя БД |
| `log_interaction` | Структурированное логирование (**НЕ LLM tool**) | PostgreSQL |

---

## 2. Детальные контракты

### 2.1 `search_tours`

```python
def search_tours(params: SearchParams) -> list[Tour]
```

**SearchParams:**

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `destination` | `str` | Нет | Страна, регион, курорт |
| `departure_city` | `str` | Нет | Город вылета |
| `date_from` | `date` | Нет | Начало диапазона дат |
| `date_to` | `date` | Нет | Конец диапазона дат |
| `duration_nights` | `int` | Нет | Количество ночей |
| `budget_max` | `int` | Нет | Максимальный бюджет, руб |
| `hotel_stars` | `int` | Нет | Категория отеля (1–5) |
| `travel_style` | `enum` | Нет | `relax` / `adventure` / `family` / `bleisure` |
| `adults` | `int` | Нет | Количество взрослых |
| `children` | `int` | Нет | Количество детей |

**Tour (элемент ответа):**

```json
{
  "tour_id": "string",
  "destination": "Мальдивы, Мале",
  "hotel": "Soneva Fushi 5*",
  "departure": "2026-02-10",
  "duration_nights": 10,
  "price_rub": 485000,
  "airline": "Emirates",
  "included": ["перелёт", "трансфер", "All Inclusive"],
  "available_seats": 4
}
```

**Side effects:** нет (read-only).  
**Ограничение:** результат усекается до top-N при > 10 совпадений.

---

### 2.2 `get_client_profile`

```python
def get_client_profile(client_id: str) -> ClientProfile
```

| Поле | Тип | Описание |
|---|---|---|
| `client_id` | `str` | **Обязательное.** Уникальный идентификатор клиента |

**ClientProfile** содержит: `name`, `contact`, `preferences`, `travel_history`, `budget_tier`, `vip_status`.

**Side effects:** нет (read-only).

---

### 2.3 `update_client_profile`

```python
def update_client_profile(client_id: str, fields: dict) -> None
```

| Поле | Тип | Описание |
|---|---|---|
| `client_id` | `str` | **Обязательное.** |
| `fields` | `dict` | Ключи и значения для обновления (partial update) |

**Side effects:** обновляет запись в таблице `client_profiles` (PostgreSQL).

---

### 2.4 `create_lead`

```python
def create_lead(data: LeadCreate) -> Lead
```

**LeadCreate:**

| Поле | Тип | Описание |
|---|---|---|
| `client_id` | `str` | **Обязательное.** |
| `session_id` | `str` | **Обязательное.** Для idempotency key |
| `contact` | `str` | Телефон или email |
| `preferences` | `dict` | Параметры интереса клиента |
| `stage` | `str` | Начальная стадия лида |

**Lead (ответ):**

```json
{
  "lead_id": "string",
  "client_id": "string",
  "created_at": "2026-02-10T12:00:00Z",
  "stage": "qualified"
}
```

**Side effects:** INSERT в таблицу `leads` (PostgreSQL).  
**Idempotency:** ключ = `hash(client_id + session_id + preferences)`. При дубликате возвращает существующий лид без повторной записи.

---

### 2.5 `update_lead_stage`

```python
def update_lead_stage(lead_id: str, stage: str) -> None
```

| Поле | Тип | Описание |
|---|---|---|
| `lead_id` | `str` | **Обязательное.** |
| `stage` | `str` | **Обязательное.** Новая стадия (`cold` / `qualified` / `proposal` / `objection` / `closing`) |

**Side effects:** UPDATE в таблице `leads` (PostgreSQL).

---

### 2.6 `get_policy_info`

```python
def get_policy_info(country: str, profile: ClientProfile) -> PolicyInfo
```

| Поле | Тип | Описание |
|---|---|---|
| `country` | `str` | **Обязательное.** Страна назначения |
| `profile` | `ClientProfile` | **Обязательное.** Профиль клиента (гражданство, статус) |

**PolicyInfo** содержит: `visa_required`, `visa_type`, `insurance_required`, `entry_restrictions`, `notes`.

**Side effects:** нет (read-only).

---

### 2.7 `log_interaction` ⚠️ НЕ LLM tool

```python
def log_interaction(event: InteractionEvent) -> None
```

**InteractionEvent:**

| Поле | Тип | Описание |
|---|---|---|
| `session_id` | `str` | Идентификатор сессии |
| `client_id` | `str` | Идентификатор клиента |
| `intent` | `str` | Распознанный интент |
| `stage` | `str` | Стадия воронки |
| `tools_called` | `list[str]` | Список вызванных tools |
| `tokens_used` | `int` | Потреблённые токены |
| `latency_ms` | `int` | Время обработки |

**Side effects:** INSERT в таблицу `interactions` (PostgreSQL).  
**Вызывается:** только Orchestrator после каждого цикла. LLM не имеет доступа к этому tool.

---

## 3. Коды ошибок и timeout-политики

| Код | Ситуация | Поведение |
|---|---|---|
| `TOURS_NOT_FOUND` | `search_tours` вернул пустой список | Сообщение: «По вашим параметрам вариантов не найдено. Попробуйте изменить даты или бюджет.» |
| `PROFILE_NOT_FOUND` | `get_client_profile` не нашёл запись | Создаётся пустой профиль, обработка продолжается |
| `LEAD_DUPLICATE` | `create_lead` с совпадающим idempotency key | Возврат существующего лида, без ошибки |
| `DB_ERROR` | Ошибка PostgreSQL на любом tool | Аварийный режим: ответ без данных профиля, запись в лог ошибок |
| `VALIDATION_ERROR` | Некорректные параметры | 422 Unprocessable Entity, детали в `detail` |
| `RATE_LIMIT` | Превышен лимит сообщений | 429 Too Many Requests |

**Timeouts:**

| Tool | Timeout |
|---|---|
| `search_tours` | 3 сек |
| `get_client_profile` | 1 сек |
| `update_client_profile` | 1 сек |
| `create_lead` | 2 сек |
| `update_lead_stage` | 1 сек |
| `get_policy_info` | 2 сек |

При превышении timeout — исключение, Orchestrator логирует и применяет fallback.

---

## 4. Side Effects — сводная таблица

| Tool | READ | WRITE | Таблица |
|---|---|---|---|
| `search_tours` | ✓ | — | tours (internal DB) |
| `get_client_profile` | ✓ | — | `client_profiles` |
| `update_client_profile` | — | ✓ | `client_profiles` |
| `create_lead` | — | ✓ | `leads` |
| `update_lead_stage` | — | ✓ | `leads` |
| `get_policy_info` | ✓ | — | policy (internal DB) |
| `log_interaction` | — | ✓ | `interactions` |

---

## 5. Защита от злоупотреблений

### Rate Limiting
- **20 сообщений/мин** на `client_id` (ADR-007)
- При превышении: HTTP 429, клиент уведомляется

### Max Tool-Calls per Turn
- **Не более 5 tool-calls** на одно входящее сообщение (ADR-007)
- При достижении лимита: Orchestrator принудительно завершает цикл и возвращает промежуточный ответ

### Idempotency
- `create_lead`: idempotency key = `SHA256(client_id + session_id + sorted(preferences))`
- Повторный вызов с тем же ключом → дедупликация, без дублирования в БД

### Валидация входных параметров
- Все поля проходят Pydantic-валидацию перед выполнением
- `hotel_stars`: диапазон 1–5
- `travel_style`: строго enum (`relax` / `adventure` / `family` / `bleisure`)
- `budget_max`: положительное целое
- `stage` в `update_lead_stage`: строго из допустимого набора

### Усечение результатов
- `search_tours` при > 10 результатах усекает до top-N по релевантности/цене
- LLM видит только усечённый список, не полный датасет

---

## 6. Матрица доступности tools по стадиям воронки

| Tool | `cold` | `discovery` | `qualified` | `proposal` | `objection` | `closing` |
|---|---|---|---|---|---|---|
| `search_tours` | ✓ | ✓ | ✓ | ✓ | ✓ | — |
| `get_client_profile` | ✓ | ✓ | ✓ | — | — | — |
| `update_client_profile` | — | — | ✓ | ✓ | — | — |
| `get_policy_info` | ✓ | ✓ | ✓ | — | — | — |
| `create_lead` | — | — | — | ✓ | — | ✓ |
| `update_lead_stage` | — | — | — | — | ✓ | ✓ |
| `log_interaction` | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

> Decision Logic передаёт LLM только `available_tools` текущей стадии. LLM физически не может вызвать tool вне разрешённого набора.

---

## 7. Примеры вызовов и ответов

### `search_tours` — запрос

```python
search_tours(SearchParams(
    destination="Мальдивы",
    departure_city="Москва",
    date_from="2026-02-01",
    date_to="2026-02-28",
    duration_nights=10,
    budget_max=600000,
    hotel_stars=5,
    travel_style="relax",
    adults=2,
    children=0
))
```

### `search_tours` — ответ

```json
[
  {
    "tour_id": "TUR-00451",
    "destination": "Мальдивы, Мале",
    "hotel": "Soneva Fushi 5*",
    "departure": "2026-02-10",
    "duration_nights": 10,
    "price_rub": 485000,
    "airline": "Emirates",
    "included": ["перелёт", "трансфер", "All Inclusive"],
    "available_seats": 4
  }
]
```

### `create_lead` — запрос

```python
create_lead(LeadCreate(
    client_id="tg_123456789",
    session_id="sess_abc123",
    contact="+7 999 123-45-67",
    preferences={"destination": "Мальдивы", "budget_max": 600000},
    stage="qualified"
))
```

### `create_lead` — ответ

```json
{
  "lead_id": "lead_987xyz",
  "client_id": "tg_123456789",
  "created_at": "2026-02-07T14:30:00Z",
  "stage": "qualified"
}
```

### `get_policy_info` — запрос

```python
get_policy_info(
    country="Мальдивы",
    profile=ClientProfile(citizenship="RU", vip_status=True)
)
```

### `get_policy_info` — ответ

```json
{
  "visa_required": false,
  "visa_type": null,
  "insurance_required": true,
  "entry_restrictions": [],
  "notes": "Безвизовый въезд для граждан РФ до 30 дней. Страховка обязательна."
}
```
