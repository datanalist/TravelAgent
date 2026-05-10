# Skill: idempotency-key

Генерация и проверка идемпотентного ключа для защиты `create_lead` (и других write-tools при необходимости) от дубликатов.

## Когда использовать

- При реализации `src/tools/leads.py` → `create_lead`
- При любом другом write-tool, где повторный вызов с теми же параметрами не должен порождать дубль
- Когда LLM может повторно вызвать tool из-за reasoning-петли или retry

## Что делает

1. Принимает входные параметры tool (`client_id`, `session_id`, нормализованные `preferences`).
2. Считает SHA-256 от канонической строки → `idempotency_key`.
3. Перед INSERT проверяет, существует ли запись с таким ключом.
4. Если **есть** → возвращает существующую запись (без новой записи в БД).
5. Если **нет** → INSERT с сохранением ключа.

## Контракт (input → output)

```python
def make_idempotency_key(
    client_id: str,
    session_id: str,
    preferences: dict,
) -> str:
    """SHA256(client_id + session_id + canonical_json(sorted(preferences)))"""

async def create_lead(data: LeadCreate) -> Lead:
    key = make_idempotency_key(data.client_id, data.session_id, data.preferences)
    existing = await leads_repo.find_by_idempotency_key(key)
    if existing:
        return existing  # дедупликация без ошибки
    return await leads_repo.insert(data, idempotency_key=key)
```

## Правила и инварианты

- Алгоритм: **SHA-256** (`spec-tools-api.md` §5)
- Канонизация `preferences` обязательна: сортировка ключей + `json.dumps(..., sort_keys=True, ensure_ascii=False)`
- Ключ хранится **в БД** в колонке таблицы `leads` (с `UNIQUE`-индексом — задача `agent-travel-dba`)
- Дубль возвращает **существующую запись**, а не ошибку (код `LEAD_DUPLICATE` логируется, но клиенту не видно)
- Ключ нечувствителен к порядку полей в `preferences` (благодаря канонизации)
- Ключ **зависит** от `session_id` — лиды из разных сессий не считаются дубликатами
- При изменении набора полей `preferences` — обратная совместимость не гарантируется (новый ключ для тех же данных)

## Ограничения / SLA

| Параметр | Значение |
|---|---|
| Latency генерации ключа | < 1 мс |
| Latency проверки в БД | ≤ 100 мс (с UNIQUE-индексом) |
| Длина ключа | 64 hex-символа |

## Используется агентами

- `agent-travel-backend` — формирование ключа `SHA256(client_id+session_id+sorted(prefs))` в `src/tools/leads.py`
- `agent-travel-dba` — гарантирует уникальность на уровне БД через `UNIQUE INDEX ON leads(idempotency_key)` + `ON CONFLICT DO NOTHING RETURNING` в репозитории

## Связанные документы

- `docs/specs/spec-tools-api.md` §2.4 (`create_lead`)
- `docs/specs/spec-tools-api.md` §5 (Idempotency)
- `docs/specs/spec-tools-api.md` §3 (код `LEAD_DUPLICATE`)

## Статус

Backlog — реализация навыка предстоит при разработке `src/tools/leads.py` (после создания таблицы `leads` агентом `agent-travel-dba`).
