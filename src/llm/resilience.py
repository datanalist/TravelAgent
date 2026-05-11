from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Awaitable, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}


def _is_retryable(exc: Exception) -> bool:
    """Определяет, стоит ли повторять запрос при данном исключении."""
    msg = str(exc).lower()
    # Проверяем HTTP-статус, встроенный в сообщение исключения или атрибут
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status is not None:
        return int(status) in _RETRYABLE_HTTP_CODES
    # 400/401/403 — не повторяем
    for no_retry in ("400", "401", "403", "invalid_api_key", "authentication"):
        if no_retry in msg:
            return False
    return True


async def with_retry(
    coro_factory: Callable[[], Awaitable[T]],
    max_attempts: int = 3,
    base_delay: float = 1.0,
) -> T:
    """Exponential backoff retry: 1s → 2s → 4s.

    Повторяет только при 429/5xx ошибках.
    При 400/401 — немедленно пробрасывает исключение.
    """
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return await coro_factory()
        except Exception as exc:
            last_exc = exc
            if not _is_retryable(exc):
                raise
            if attempt < max_attempts - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    "LLM request failed (attempt %d/%d), retrying in %.1fs: %s",
                    attempt + 1,
                    max_attempts,
                    delay,
                    exc,
                )
                await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


class CircuitBreaker:
    """Circuit Breaker для LLM-провайдера.

    Состояния: CLOSED → OPEN (cooldown) → HALF_OPEN → CLOSED
    Параметры: 5 ошибок за 60s → cooldown 30s
    """

    FAILURE_THRESHOLD = 5
    WINDOW_SECONDS = 60
    COOLDOWN_SECONDS = 30

    def __init__(self, provider_name: str) -> None:
        self._provider_name = provider_name
        self._failures: deque[float] = deque()
        self._open_until: float = 0.0

    @property
    def is_open(self) -> bool:
        now = time.monotonic()
        if now < self._open_until:
            return True
        # Переход OPEN → HALF_OPEN: сбрасываем состояние после cooldown
        if self._open_until > 0:
            self._open_until = 0.0
            self._failures.clear()
        return False

    def record_success(self) -> None:
        self._failures.clear()

    def record_failure(self) -> None:
        now = time.monotonic()
        self._failures.append(now)
        # Убираем ошибки вне окна
        cutoff = now - self.WINDOW_SECONDS
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

        if len(self._failures) >= self.FAILURE_THRESHOLD:
            self._open_until = now + self.COOLDOWN_SECONDS
            logger.error(
                "CircuitBreaker OPEN for provider=%s: %d failures in %ds, cooldown=%ds",
                self._provider_name,
                len(self._failures),
                self.WINDOW_SECONDS,
                self.COOLDOWN_SECONDS,
            )

    def check(self) -> None:
        """Выбрасывает исключение, если CB открыт."""
        if self.is_open:
            raise CircuitBreakerOpenError(
                f"Circuit Breaker открыт для {self._provider_name!r}, "
                f"повторите через {max(0, self._open_until - time.monotonic()):.0f}s"
            )


class CircuitBreakerOpenError(RuntimeError):
    """Поднимается, когда Circuit Breaker в состоянии OPEN."""


_circuit_breakers: dict[str, CircuitBreaker] = {}

_PROVIDER_FALLBACK_ORDER = ["claude", "openai", "mistral"]


def get_circuit_breaker(provider_name: str) -> CircuitBreaker:
    if provider_name not in _circuit_breakers:
        _circuit_breakers[provider_name] = CircuitBreaker(provider_name)
    return _circuit_breakers[provider_name]


async def call_with_resilience(
    provider_name: str,
    coro_factory: Callable[[], Awaitable[T]],
    max_attempts: int = 3,
    base_delay: float = 1.0,
) -> T:
    """Обёртка: Circuit Breaker + retry с exponential backoff."""
    cb = get_circuit_breaker(provider_name)
    cb.check()
    try:
        result = await with_retry(coro_factory, max_attempts=max_attempts, base_delay=base_delay)
        cb.record_success()
        return result
    except Exception as exc:
        cb.record_failure()
        raise
