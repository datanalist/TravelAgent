# Skill: circuit-breaker

Обёртка над внешним LLM-вызовом: exponential backoff retry + Circuit Breaker для предотвращения каскадных сбоев при недоступности провайдера.

## Когда использовать

- В `src/orchestrator.py` / `src/router.py` — при каждом вызове `LLM Connector`
- При интеграции с внешними сервисами, чьи сбои не должны валить весь request
- Любой I/O-вызов с риском прерывистой недоступности

## Что делает

**Retry-слой:**
1. Делает вызов.
2. При исключении (`TimeoutError`, `5xx`, transient network error) — повтор с задержкой.
3. Задержки: `1s → 2s → 4s` (exponential, до 3 попыток).
4. После 3 неудач — пробрасывает `LLMUnavailableError`.

**Circuit Breaker:**
- Состояния: `closed` → `open` → `half_open` → `closed`
- Если **5 ошибок за 60 секунд** → переход в `open`, новые вызовы немедленно падают (без обращения к LLM)
- Через **30 секунд cooldown** → `half_open`: пропускается **один** пробный вызов
- Успех → `closed`; неудача → снова `open` на 30 с

## Контракт (input → output)

```python
class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,     # ошибок
        window_seconds: int = 60,       # за какое окно считаем
        cooldown_seconds: int = 30,
    ): ...

    async def call(self, fn: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        """Поднимает CircuitOpenError, если breaker open."""

async def with_retry(
    fn: Callable[..., Awaitable[T]],
    *args,
    attempts: int = 3,
    base_delay: float = 1.0,
    **kwargs,
) -> T:
    """Exponential backoff: 1s → 2s → 4s."""
```

Использование в orchestrator:

```python
result = await breaker.call(
    with_retry, llm_connector.complete, messages=..., tools=...,
)
```

## Правила и инварианты

- Параметры по умолчанию: **3 попытки**, окно **60 с**, threshold **5 ошибок**, cooldown **30 с** (`spec-orchestrator.md` §7, ADR-006)
- Retry **только** для transient ошибок (timeout, 5xx, network); для `400/401/422` — не повторять
- Circuit Breaker — **на каждый LLM-провайдер** отдельно (если несколько провайдеров через `LLM Connector`)
- При `CircuitOpenError` или `LLMUnavailableError` → graceful fallback в Orchestrator: вежливое сообщение клиенту, `log_interaction` с `error_type`
- Метрики breaker (`state`, `failures_in_window`) — экспортируются для Prometheus (`agent-travel-devops`)
- Не оборачивать вызовы tools (только LLM API) — для DB-ошибок другая стратегия (`spec-orchestrator.md` §7)
- Circuit Breaker — **stateful** компонент, живёт всё время процесса (singleton через DI)
- **Владение реализацией:** код живёт в `src/llm/resilience.py` (`agent-travel-llm`); встроен внутрь `LLM Connector`. `agent-travel-backend` использует уже-обёрнутый интерфейс — повторная обёртка не нужна
- При появлении нового провайдера в `src/llm/providers/*` — новый экземпляр CB регистрируется автоматически (per-provider state)

## Ограничения / SLA

| Параметр | Значение | Источник |
|---|---|---|
| Retry attempts | 3 | spec-orchestrator §7 |
| Backoff sequence | 1s → 2s → 4s | spec-orchestrator §7 |
| CB threshold | 5 ошибок / 60 с | systemPatterns + ADR-006 |
| CB cooldown | 30 с | systemPatterns |
| Total retry latency (worst case) | ~7 с | сумма задержек |

## Используется агентами

- `agent-travel-llm` — **владелец реализации** (`src/llm/resilience.py`); CB+retry встроены внутрь `LLM Connector`
- `agent-travel-backend` — потребитель через готовый интерфейс `LLM Connector` (повторно не оборачивает)

## Связанные документы

- `docs/specs/spec-orchestrator.md` §7 (Retry / Fallback стратегии)
- `memory-bank/systemPatterns.md` (Guardrails — LLM API)
- `.cursor/skills/llm-provider-adapter/SKILL.md` (обёртываемый объект — сам адаптер не делает retry/CB)
- `.cursor/skills/tool-calling-loop/SKILL.md` (потребитель: каждый LLM-вызов цикла идёт через CB)
- ADR-006 — Абстракция LLM Connector (включая отказоустойчивость)

## Статус

Backlog — реализация навыка предстоит при разработке `src/orchestrator.py` (после контракта `LLM Connector` от `agent-travel-llm`).
