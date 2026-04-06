# Диаграммы архитектуры — TravelAgent

Набор Mermaid-диаграмм визуализирует архитектуру TravelAgent на уровнях C4 (context / container / component), основной сценарий обработки запроса и поток данных относительно [System Design Document](../system-design.md). Используйте их как быстрый вход в SDD и для ревью границ системы.

## Содержание

| Файл | Тип диаграммы | Назначение | Разделы SDD |
|------|---------------|------------|-------------|
| [`c4-context.md`](c4-context.md) | C4 Context | TravelAgent как система, пользователи, внешние сервисы, границы доверия | §1 (Обзор системы), §11 (Деплой) |
| [`c4-container.md`](c4-container.md) | C4 Container | Docker-контейнеры, каналы, хранилища, observability, внешние LLM-провайдеры | §3 (Список модулей), §11 (Деплой) |
| [`c4-component.md`](c4-component.md) | C4 Component | Внутреннее устройство FastAPI App: API Gateway, Core, Memory, LLM, Tools | §3 (Список модулей), §12 (LLM vs программная логика) |
| [`workflow-request.md`](workflow-request.md) | Workflow | Пошаговое выполнение запроса от клиента до ответа, ветки ошибок, ReAct loop | §4 (Основной workflow), §8 (Failure Modes) |
| [`data-flow.md`](data-flow.md) | Data Flow | Путь данных: что пишется в Redis/PostgreSQL, что уходит в LLM, что логируется и попадает в метрики | §5 (Memory), §10 (Модель данных), §13 (Безопасность), §14 (Метрики) |

## Просмотр

Диаграммы описаны в Markdown с блоками **Mermaid** (` ```mermaid `). Они рендерятся во встроенном просмотрщике **GitHub** и **GitLab**, а также на [mermaid.live](https://mermaid.live) — можно вставить содержимое блока для правки и экспорта.
