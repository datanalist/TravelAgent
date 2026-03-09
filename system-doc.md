Ниже набросок System Design документа для Travel-Agent‑консьержа, ориентированного на продажи и high‑end сегмент. [docs.langdb](https://docs.langdb.ai/guides/building-agents/building-travel-concierge-with-google-adk)

***

## 1. Цели и сценарии

- Экспертный диалог о путешествиях (открытые вопросы, уточнение предпочтений, работа с возражениями) с адаптивной **персонализацией** по истории и профилю клиента. [dev](https://dev.to/aws-builders/building-a-proactive-ai-travel-agent-on-aws-my-journey-with-bedrock-agentcore-part-2-199i)
- Квалификация лида (определение бюджета, сроков, уровня гибкости, вероятности покупки) и фиксация статуса в CRM.  
- Подбор туров: поиск по внешним API/внутренним продуктовым витринам, сбор и ранжирование вариантов, объяснение логики выбора.  
- High‑end tone: стилистическая адаптация ответов (лексика, формат, степень формальности) в зависимости от выбранного стиля бренда.  
- Продажная логика: стадии воронки (discovery → квалификация → презентация → работа с возражениями → закрытие → follow‑up). [vivun](https://www.vivun.com/blog/inside-the-ai-sales-agent-memory-reasoning-real-work)
- Каналы: Telegram Bot API и Web‑чат, оба работают поверх одного backend‑API.

***

## 2. Высокоуровневая архитектура

Компоненты (backend‑зона):

- API Gateway / FastAPI backend  
  - REST/SSE endpoint для Web‑чата (`/chat/stream`).  
  - Webhook для Telegram (`/telegram/webhook`).  
  - Auth/Rate limiting (по токену/чат‑id).  
- Orchestrator / Conversation Controller  
  - Обрабатывает входящие сообщения, нормализует их в единый internal request.  
  - Вызывает Router (intent/тип запроса) и Decision Logic.  
- LLM Connector Layer  
  - Абстракция над Claude / OpenAI / Mistral (единый интерфейс `llm.generate()`, `llm.tools_call()`). [cloud.google](https://cloud.google.com/discover/what-are-ai-agents)
  - Поддержка streaming (SSE) и tool‑calling.  
- Memory Layer  
  - Session memory (краткосрочная, Redis).  
  - Long‑term profile (PostgreSQL +, опционально, векторная БД для эмбеддингов предпочтений).  
- Tools Layer  
  - Инструменты для поиска туров (`search_tours`), проверки доступности, расчёта цены, работы с CRM (`create_lead`, `update_stage`, `log_interaction`). [anadea](https://anadea.info/blog/how-to-build-ai-travel-agent/)
- CRM Integration  
  - Адаптер к CRM (REST/gRPC, например HubSpot/amoCRM/Bitrix).  
- Logging & Monitoring  
  - Логи запросов/ответов (с анонимизацией PII).  
  - Метрики (Prometheus/Grafana или аналог).

Деплой:

- Docker‑контейнер с FastAPI backend.  
- PostgreSQL (persistent storage) + Redis (in‑memory).  
- Публичный endpoint (ngrok на dev, нормальный Ingress/Load Balancer на prod). [dev](https://dev.to/permit_io/building-a-secure-flight-booking-system-with-llm-agent-in-langflow-3ml)

***

## 3. Модель данных

### 3.1 PostgreSQL

Таблицы (приблизительно):

- `clients`  
  - `id`, `telegram_id`/`external_id`, `name`, `email`, `phone`, `crm_contact_id`.  
  - `segment` (high‑end, mid, mass), `language`, `preferred_style` (формальный, дружелюбный и т.п.).  
- `client_profile`  
  - `client_id` FK, `budget_range`, `preferred_destinations` (JSONB), `travel_style` (relax, adventure, family, bleisure), `constraints` (дети, визы, питание, авиакомпании).  
- `sessions`  
  - `id`, `client_id`, `channel` (tg/web), `started_at`, `status`, `current_stage` (lead_stage).  
- `messages`  
  - `id`, `session_id`, `sender` (user/agent/system), `content`, `role`, `created_at`, `metadata` (JSONB – intents, tools, latency).  
- `leads`  
  - `id`, `client_id`, `crm_lead_id`, `status`, `probability`, `budget`, `destination`, `travel_dates`, `created_at`, `updated_at`.  
- `itineraries`  
  - `id`, `lead_id`, `options` (JSONB: список туров/перелётов/отелей), `chosen_option_id`.

### 3.2 Redis

- Краткосрочный контекст диалога:  
  - `session:{id}:summary` – актуальное summary общения (для LLM).  
  - `session:{id}:stage` – текущая стадия продажи.  
  - `session:{id}:scratchpad` – временные планы/варианты.

Опционально:

- Векторная БД (Qdrant/pgvector) для хранения эмбеддингов предпочтений клиента и FAQ/knowledge‑base (правила компании, типовые туры, USP бренда). [anadea](https://anadea.info/blog/how-to-build-ai-travel-agent/)

***

## 4. Memory Layer

Цели:

- Сохранить непрерывность диалога между сообщениями и каналами.  
- Хранить профиль клиента и его предпочтения независимо от сессии.  
- Давать LLM компактный, но информативный контекст. [vivun](https://www.vivun.com/blog/inside-the-ai-sales-agent-memory-reasoning-real-work)

Компоненты:

- **Conversation Summarizer**  
  - Периодически сворачивает длинную историю в summary (через отдельный LLM‑prompt).  
  - Пишет summary в Redis и PostgreSQL(`sessions.summary`).  
- **Profile Updater**  
  - Извлекает из сообщений факты: бюджет, города вылета, даты, любимые бренды отелей.  
  - Обновляет `client_profile` и при необходимости CRM контакт.  
- **Stage Tracker**  
  - Определяет текущее состояние сделки (cold, discovery, qualified, proposal, closing, follow‑up).  
  - Сохраняет в `sessions.current_stage` и синхронизирует с CRM (lead.stage). [vivun](https://www.vivun.com/blog/inside-the-ai-sales-agent-memory-reasoning-real-work)

***

## 5. Decision Logic

Есть отдельный модуль (или под‑агент), который решает «что делать дальше» до вызова LLM для финального текста.

Вход:

- Parsed user message (текст + возможный intent от Router).  
- Session state (stage, summary, profile).  
- CRM state (существующий lead/сделка).  

Выход:

- Target stage (оставить/сменить).  
- High‑level действие:  
  - задать уточняющий вопрос,  
  - перейти к квалификации,  
  - перейти к подбору туров,  
  - презентовать 1–3 варианта,  
  - работать с возражениями,  
  - закрывать сделку / бронировать,  
  - делать мягкий follow‑up. [vivun](https://www.vivun.com/blog/inside-the-ai-sales-agent-memory-reasoning-real-work)
- Набор tools, которые нужно вызвать (поисковые, CRM, вспомогательные).

Простая реализация:

- Небольшой rule‑based слой (if/else по intents + stage).  
- Или LLM‑агент‑решатель: prompt с описанием стадий и политик, который возвращает JSON c `next_stage`, `action`, `tools_to_call`. [linkedin](https://www.linkedin.com/posts/alexxubyte_systemdesign-coding-interviewtips-activity-7422681249774845952--j_d)

***

## 6. Router (Intent & Module Router)

Задача: определить тип запроса и маршрутизировать его на нужную подсистему. [cloud.google](https://cloud.google.com/discover/what-are-ai-agents)

Типы:

- Small talk / rapport (поддержание общения, стиль, тон).  
- Discovery / сбор требований.  
- Pricing / budget.  
- Itinerary / подбор туров.  
- Policy / визы / ограничения.  
- CRM‑события (изменить контакты, напомнить, отправить email).  

Реализация:

- Intent classifier (LLM с few‑shot+JSON schema).  
- Возможен гибрид: легковесная модель + эвристики по ключевым словам.  
- Router передаёт управление в нужный модуль (например, `TravelSearchModule`, `SalesModule`, `ProfileModule`).

***

## 7. Tools Layer

Примеры инструментов (LLM‑tools / функции):

- `search_tours(params)` – обращение к агрегатору/внутренней БД туров; возвращает список вариантов (цена, даты, авиакомпания, отель, ограничения). [anadea](https://anadea.info/blog/how-to-build-ai-travel-agent/)
- `get_client_profile(client_id)` / `update_client_profile(fields)` – работа с профилем (PostgreSQL).  
- `get_lead(client_id)` / `create_lead(data)` / `update_lead_stage(...)` – CRM.  
- `log_interaction(event)` – запись структурированной активности (для последующей аналитики).  
- `get_policy_info(country, client_profile)` – проверки виз/страховок и внутренних ограничений.  

Оркестрация:

- Orchestrator вызывает LLM с описанием доступных tools.  
- LLM возвращает план (Thought → Action → Observation loop) и tool‑calls, backend выполняет их и подставляет результаты обратно. [reddit](https://www.reddit.com/r/AI_Agents/comments/1ov7x6k/built_a_production_langgraph_travel_agent_with/)

***

## 8. Стиль, high‑end сегмент и персонализация

Механизмы:

- System prompt включает:  
  - бренд‑гайд (тон, обращения, табу‑темы),  
  - требования к формату (структурированные ответы, аккуратные формулировки),  
  - особенности high‑end сегмента (деликатность, уважение времени, premium‑словари). [learn.microsoft](https://learn.microsoft.com/en-us/power-platform/architecture/solution-ideas/agent-travel-customer)
- Персонализация на основе `client_profile` и сегмента:  
  - выбор register (ты/вы, уровень формальности),  
  - рекомендации, ориентированные на комфорт и уникальность, а не на «скидки».  
- LLM получает отдельное поле `style_profile`, сформированное из настроек клиента и бренда.

***

## 9. Интеграция с каналами (Telegram / Web)

### Telegram

- Bot API → webhook → FastAPI `/telegram/webhook`.  
- Нормализатор переводит сообщения Telegram (текст/кнопки) в внутренний формат `ChatMessage`.  
- Ответы от backend мапятся в сообщения Telegram (текст + inline‑кнопки, например «Показать ещё варианты», «Записать контакты»).

### Web

- Web‑клиент (SPA) → REST/SSE `/chat/stream`.  
- SSE/WS для стриминга токенов ответа от LLM.  

Оба канала используют общий `session_id`/`client_id` и общий Memory/Decision слой.

***

## 10. Поток обработки запроса (MVP)

1. Клиент пишет в Telegram/Web.  
2. FastAPI получает сообщение, резолвит/создаёт `client` и `session`.  
3. Router определяет intent и передаёт управление Orchestrator.  
4. Orchestrator запрашивает Memory (summary, profile, stage).  
5. Decision Logic решает: к какой стадии/действию переходить, какие tools потенциально могут понадобиться.  
6. LLM вызывается с:  
   - system prompt (роль, стиль, продажная логика),  
   - memory (summary + profile),  
   - текущим запросом,  
   - описанием tools.  
7. LLM при необходимости делает tool‑calls (поиск туров, CRM и т.п.), backend выполняет их, возвращает наблюдения.  
8. LLM формирует финальный ответ в нужном стиле и, при необходимости, JSON‑payload (например, для CRM).  
9. Ответ стримится в Web/Telegram, структурированные данные пишутся в PostgreSQL/CRM.  
10. Conversation Summarizer и Profile Updater обновляют память и профиль после сообщения. [reddit](https://www.reddit.com/r/AI_Agents/comments/1ov7x6k/built_a_production_langgraph_travel_agent_with/)

***

## 11. MVP‑объём

Минимум, который стоит реализовать в первой итерации:

- FastAPI backend с:  
  - `/chat/stream` (SSE) и `/telegram/webhook`.  
  - Обёртка над 1 выбранным LLM API.  
- Простая Session memory (Redis) + сохранение сообщений в PostgreSQL.  
- Базовый профиль клиента (страна, город вылета, примерный бюджет, тип отдыха).  
- Router с 3–4 intent‑ами: small talk, discovery, tour search, objections.  
- Decision Logic с простой rule‑based логикой по стадиям.  
- Один tool: `search_tours` (заглушка или простая БД туров) + простой `create_lead` (запись в таблицу `leads` вместо реальной CRM).  
- Конфигурируемый high‑end стиль через system prompt.

Если нужно, могу следующим шагом набросать структуру папок/модулей проекта и пример схемы FastAPI эндпоинтов с Pydantic‑моделями.