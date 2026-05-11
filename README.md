# TravelAgent — AI-консьерж для туроператора

> Мультиагентная система, которая увеличивает выручку и конверсию туроператора/турагентства за счёт AI-консьержа, берущего на себя значимую часть первичных продаж и сервиса в digital-каналах.

**Статус:** PoC | Milestone 1

---

## Какую задачу решает и для кого

### Целевая аудитория

Туроператоры и турагентства, которые хотят повысить конверсию из трафика, снизить нагрузку на менеджеров и улучшить сервис для клиентов (включая high-end сегмент).

### Проблема сейчас

- **Низкая конверсия из входящего трафика.** Большая часть лидов «холодные»: менеджеры тратят время на квалификацию, базовые вопросы, не успевают реагировать быстро.
- **Падает средний чек.** Без экспертного диалога и персонализации клиенты выбирают «популярное», а не оптимальное по соотношению цена/качество/маржинальность.
- **Перегруз менеджеров.** Типовые вопросы (визы, документы, базовые сценарии) отнимают львиную долю времени, менеджеры не фокусируются на сделках.
- **Сервис 24/7 недоступен.** High-end клиенты ожидают быстрый отклик и премиальный тон; круглосуточный персонал дорог.
- **Слабая аналитика воронки.** История диалогов, причины отказов, предпочтения клиентов теряются или не структурированы.

---

## Что делает PoC на демо

1. Клиент общается в **Telegram-боте** или **Web-чате** — единый backend, общая сессия по `client_id`
2. Агент **квалифицирует запрос** — собирает бюджет, даты, направление, стиль отдыха, отсекает «шумиху»
3. Агент ведёт **экспертный диалог** — уточняет предпочтения, работает с возражениями, адаптирует тон (в т.ч. high-end)
4. Агент **подбирает туры** — вызов `search_tours` (заглушка или простая БД), ранжирование и объяснение выбора
5. Агент **создаёт лид в CRM** (таблица `leads` вместо реальной CRM в MVP)
6. Агент **обновляет профиль клиента** — бюджет, города вылета, предпочтения
7. Ответы **стримятся** в реальном времени (SSE для Web)

**Интерфейс:** Telegram Bot API + Web-чат (SPA) с REST/SSE

---

## Что НЕ делает PoC (Out of Scope)

- Реальная интеграция с CRM (HubSpot, amoCRM, Bitrix) — только заглушка/внутренняя таблица
- Реальная интеграция с агрегаторами туров и API авиакомпаний/отелей
- Оплата и бронирование через агента
- Голосовой ввод и распознавание речи
- Мультиязычность (только русский)
- Авторизация и полноценные профили с историей между сессиями (только базовая сессия)
- Мобильное приложение (отдельное от Web)
- A/B-тестирование и продвинутая аналитика воронки

---

## Стек технологий

| Компонент | Технология |
|---|---|
| Backend | FastAPI (Python 3.11+) |
| LLM | Claude / OpenAI / Mistral (через единый connector) |
| Память | Redis (session) + PostgreSQL |
| Каналы | Telegram Bot API, Web SSE |
| Деплой | Docker, ngrok (dev), Ingress/LB (prod) |
| Мониторинг | Логи + метрики (Prometheus/Grafana или аналог) |

---

## Структура проекта

```
TravelAgent/
├── README.md
├── docs/
│   ├── system-design.md          # Источник истины по архитектуре
│   ├── product-proposal.md
│   ├── governance.md
│   ├── specs/
│   │   ├── spec-orchestrator.md
│   │   ├── spec-memory-context.md
│   │   ├── spec-observability.md
│   │   ├── spec-tools-api.md
│   │   ├── spec-retriever.md
│   │   └── spec-serving-config.md
│   └── diagrams/
│       ├── c4-context.md
│       ├── c4-container.md
│       ├── c4-component.md
│       ├── data-flow.md
│       ├── workflow-request.md
│       └── state-machine-funnel.md
├── src/                          # Backend (FastAPI, агент, tools, memory)
├── data/                         # Каталог туров, seed-данные
└── tests/                        # Тесты
```

---

## Документация

### Архитектура

- [**System Design**](docs/system-design.md) — источник истины: ADR, модули, workflow, memory, tools, деплой
- [Продуктовое предложение](docs/product-proposal.md) — обоснование идеи, метрики, data flow
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
