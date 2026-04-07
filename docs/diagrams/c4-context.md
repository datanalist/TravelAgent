# C4 Context — TravelAgent

> Уровень: Context. Показывает TravelAgent как систему, её пользователей и внешние зависимости.

## Диаграмма

```mermaid
C4Context
title C4 Context — TravelAgent

UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="1")

System_Boundary(trusted, "Доверенная зона: стек Docker Compose") {
  System(ta, "TravelAgent", "Единая система-«чёрный ящик»: FastAPI, оркестратор агентов, Redis, PostgreSQL, интеграция с каналами.")
}

Enterprise_Boundary(untrusted, "Недоверенная зона: всё вне Docker Compose") {
  Person(client, "Клиент (турист)", "Высокий сегмент; каналы: Telegram-клиент или браузер (Web-чат).")
  Person_Ext(manager, "Менеджер турагентства", "Human-in-the-loop: коррекции и эскалации (планируется).")
  System_Ext(telegram, "Telegram Bot API", "Платформа; входящие апдейты доставляются на webhook.")
  System_Ext(llm, "LLM-провайдеры", "Claude API / OpenAI API / Mistral API.")
  System_Ext(crm, "CRM", "MVP: внутренняя модель лидов; далее HubSpot / amoCRM / Bitrix24.")
}

Rel(client, ta, "Инициирует диалог", "Web: HTTPS. Telegram: клиент → Bot API → webhook в TravelAgent.")
Rel(manager, ta, "Инициирует (будущее)", "Коррекции и эскалации в контуре турагентства.")
Rel(telegram, ta, "Инициирует доставку", "Webhook: push апдейтов в TravelAgent.")
Rel(ta, telegram, "Инициирует TravelAgent", "Исходящие вызовы Bot API (ответы в чат и т.д.).")
Rel(ta, llm, "Инициирует TravelAgent", "Запросы к модели (tool-calling, стриминг).")
Rel(ta, crm, "Инициирует TravelAgent", "Создание и обновление лидов.")

UpdateRelStyle(manager, ta, $offsetX="-1", $offsetY="-50")
UpdateRelStyle(telegram, ta, $offsetX="-300", $offsetY="200")
UpdateRelStyle(ta, telegram, $offsetX="-30", $offsetY="200")
UpdateRelStyle(ta, llm, $offsetX="120", $offsetY="200")
UpdateRelStyle(ta, crm, $offsetX="300", $offsetY="200")
UpdateRelStyle(client, ta, $offsetX="-423", $offsetY="50")
```

## Пояснения

| Элемент | Роль на уровне Context |
|--------|-------------------------|
| **TravelAgent** | Граница автоматизации турагентства: один логический контур доверия внутри Compose; детали сервисов и агентов — на уровнях Container / Component. |
| **Клиент (турист)** | Инициатор запроса в чат; для Web трафик идёт к backend TravelAgent, для Telegram — к инфраструктуре Telegram, а приложение получает события через webhook. |
| **Менеджер** | Внешний по отношению к автоматическому контуру человек; связи с TravelAgent появятся при внедрении HITL. |
| **Telegram Bot API** | Внешняя платформа: инициирует поток входящих через webhook; исходящие сообщения инициирует TravelAgent. |
| **LLM-провайдеры** | Внешние вычислительные API; каждый запрос к модели инициирует TravelAgent (ответ — обратно в систему). |
| **CRM** | Внешнее хранилище/контур лидов относительно «чёрного ящика»; запись лидов инициирует TravelAgent. |
| **Границы доверия** | Внутри **Docker Compose** — зона, где действуют политики деплоя, секретов и логирования проекта. Всё снаружи (пользователи, облачные API, будущие CRM) считается недоверенным: строгая валидация входа, TLS, ограничение доверия к данным извне. |

Диаграмма не детализирует внутренние компоненты (оркестратор, память, коннекторы к LLM) — они отражены в system-design на нижних уровнях C4.
