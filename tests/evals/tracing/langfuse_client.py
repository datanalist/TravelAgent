from __future__ import annotations

"""Обёртка над Langfuse Python SDK для eval-pipeline.

Graceful fallback: если LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY не заданы —
работает как no-op (только JSONL, без трейсов). Прогон не падает.

Документация SDK: https://langfuse.com/docs
"""

import logging
import os
from contextlib import contextmanager
from typing import Any, Generator

logger = logging.getLogger(__name__)


def _is_configured() -> bool:
    return bool(
        os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
    )


class _NoOpTrace:
    """Пустой трейс когда Langfuse не сконфигурирован."""

    def __init__(self, name: str) -> None:
        self.id = f"noop-{name}"

    def update(self, **kwargs: Any) -> None:
        pass


class _NoOpSpan:
    def __init__(self) -> None:
        self.id = "noop-span"

    def end(self, **kwargs: Any) -> None:
        pass

    def update(self, **kwargs: Any) -> None:
        pass


class LangfuseClient:
    """Тонкая обёртка над Langfuse SDK.

    Использование:
        client = LangfuseClient()
        trace = client.start_trace("high_end__happy_warm_destination")
        span = client.start_span(trace, "turn_1")
        span.end(output={"reply": "..."})
        client.score(trace.id, name="tone", value=0.9)
        client.end_trace(trace)
    """

    def __init__(self) -> None:
        self._enabled = _is_configured()
        self._lf = None

        if self._enabled:
            try:
                from langfuse import Langfuse
                self._lf = Langfuse(
                    public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
                    secret_key=os.environ["LANGFUSE_SECRET_KEY"],
                    host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
                )
                logger.info("LangfuseClient: подключение установлено")
            except Exception as exc:
                logger.warning("LangfuseClient: не удалось инициализировать Langfuse (%s) — fallback в JSONL", exc)
                self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    def start_trace(
        self,
        name: str,
        *,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
    ) -> Any:
        """Создаёт новый Langfuse trace (или no-op при fallback)."""
        if not self._enabled or self._lf is None:
            return _NoOpTrace(name)
        try:
            trace = self._lf.trace(
                name=name,
                metadata=metadata or {},
                tags=tags or [],
            )
            logger.debug("LangfuseClient: trace создан id=%s", trace.id)
            return trace
        except Exception as exc:
            logger.warning("LangfuseClient: start_trace ошибка: %s", exc)
            return _NoOpTrace(name)

    def start_span(
        self,
        trace: Any,
        name: str,
        *,
        input: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Any:
        """Создаёт span внутри trace."""
        if not self._enabled or isinstance(trace, _NoOpTrace):
            return _NoOpSpan()
        try:
            return trace.span(
                name=name,
                input=input or {},
                metadata=metadata or {},
            )
        except Exception as exc:
            logger.warning("LangfuseClient: start_span ошибка: %s", exc)
            return _NoOpSpan()

    def end_span(self, span: Any, *, output: dict[str, Any] | None = None) -> None:
        """Завершает span."""
        if isinstance(span, _NoOpSpan):
            return
        try:
            span.end(output=output or {})
        except Exception as exc:
            logger.warning("LangfuseClient: end_span ошибка: %s", exc)

    def score(
        self,
        trace_id: str,
        *,
        name: str,
        value: float,
        comment: str | None = None,
        data_type: str = "NUMERIC",
    ) -> None:
        """Добавляет score к trace (results judges)."""
        if not self._enabled or self._lf is None:
            return
        try:
            self._lf.score(
                trace_id=trace_id,
                name=name,
                value=value,
                comment=comment,
                data_type=data_type,
            )
        except Exception as exc:
            logger.warning("LangfuseClient: score ошибка (name=%s): %s", name, exc)

    def end_trace(self, trace: Any, *, output: dict[str, Any] | None = None) -> None:
        """Обновляет и финализирует trace."""
        if isinstance(trace, _NoOpTrace):
            return
        try:
            trace.update(output=output or {})
        except Exception as exc:
            logger.warning("LangfuseClient: end_trace ошибка: %s", exc)

    def flush(self) -> None:
        """Принудительно сбрасывает буфер SDK в Langfuse."""
        if self._enabled and self._lf:
            try:
                self._lf.flush()
            except Exception as exc:
                logger.warning("LangfuseClient: flush ошибка: %s", exc)
