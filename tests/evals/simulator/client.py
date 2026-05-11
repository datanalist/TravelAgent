from __future__ import annotations

"""In-process клиент к TravelAgent — тонкая обёртка над process_message().

Запускает Orchestrator напрямую с моками pool / redis (как в acceptance-тестах),
собирает AgentTurnResult из ответа и метаданных сессии.
"""

import time
import logging
from uuid import UUID

import fakeredis.aioredis
from unittest.mock import AsyncMock, MagicMock

from src.orchestrator import process_message
from src.memory import redis_session
from src.tools.executor import ToolExecutor
from src.tools.search_tours import SearchToursTool
from src.tools.policy import GetPolicyInfoTool
from src.tools.leads import CreateLeadTool, UpdateLeadStageTool
from src.tools.client_profile import GetClientProfileTool, UpdateClientProfileTool

from tests.evals.simulator.models import AgentTurnResult


class _ClientIdInjector:
    """Обёртка — инжектирует client_id в tool-вызовы, где LLM его не передаёт."""

    def __init__(self, wrapped: object, client_id: UUID) -> None:
        self._wrapped = wrapped
        self._client_id = client_id

    @property
    def name(self) -> str:
        return self._wrapped.name  # type: ignore[attr-defined]

    async def execute(self, **kwargs: object) -> object:
        kwargs.setdefault("client_id", str(self._client_id))
        return await self._wrapped.execute(**kwargs)  # type: ignore[union-attr]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Тестовые данные (seed)
# ---------------------------------------------------------------------------

_TOURS_DATA = [
    {
        "id": "eval_t001",
        "destination": "Мальдивы",
        "hotel_name": "Soneva Fushi",
        "hotel_stars": 5,
        "price_usd": 6500,
        "duration_nights": 7,
        "departure_date": "2026-12-01",
        "meal_plan": "FB",
        "description": "Эксклюзивный частный остров, вилла с бассейном.",
    },
    {
        "id": "eval_t002",
        "destination": "Мальдивы",
        "hotel_name": "One&Only Reethi Rah",
        "hotel_stars": 5,
        "price_usd": 9800,
        "duration_nights": 7,
        "departure_date": "2026-12-15",
        "meal_plan": "HB",
        "description": "Ультра-премиум, дайвинг, spa.",
    },
    {
        "id": "eval_t003",
        "destination": "Бали",
        "hotel_name": "Four Seasons Jimbaran",
        "hotel_stars": 5,
        "price_usd": 3800,
        "duration_nights": 7,
        "departure_date": "2026-11-20",
        "meal_plan": "BB",
        "description": "Виллы на берегу океана, персональный батлер.",
    },
    {
        "id": "eval_t004",
        "destination": "Таиланд",
        "hotel_name": "Amanpuri Phuket",
        "hotel_stars": 5,
        "price_usd": 4200,
        "duration_nights": 7,
        "departure_date": "2026-12-05",
        "meal_plan": "BB",
        "description": "Культовый Aman-resort на Пхукете.",
    },
]

_POLICIES_DATA = {
    "visa": {
        "default": "Для большинства направлений требуется виза, оформляемая заранее.",
        "destinations": {
            "Мальдивы": "Безвизовый въезд для граждан РФ до 90 дней.",
            "Таиланд": "Безвизовый въезд до 30 дней, при необходимости виза по прилёту.",
            "Бали": "Безвизовый въезд до 30 дней (Индонезия).",
        },
    },
    "cancellation": {
        "default": "Отмена за 30+ дней — полный возврат за вычетом сервисного сбора.",
        "premium": "Для VIP-клиентов — гибкие условия отмены до 7 дней до вылета.",
    },
}


class _AsyncCM:
    def __init__(self, conn: AsyncMock) -> None:
        self._conn = conn

    async def __aenter__(self) -> AsyncMock:
        return self._conn

    async def __aexit__(self, *args: object) -> None:
        pass


def _make_mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    conn.fetch.return_value = []
    conn.execute.return_value = None
    pool.acquire.return_value = _AsyncCM(conn)
    return pool


def _make_tool_executor(pool, client_id: UUID) -> ToolExecutor:
    return ToolExecutor(tools=[
        SearchToursTool(tours_data=_TOURS_DATA),
        GetPolicyInfoTool(policies_data=_POLICIES_DATA),
        _ClientIdInjector(GetClientProfileTool(pool=pool), client_id),
        _ClientIdInjector(UpdateClientProfileTool(pool=pool), client_id),
        CreateLeadTool(pool=pool),
        UpdateLeadStageTool(pool=pool),
    ])


class InProcessClient:
    """Вызывает process_message() in-process с изолированным состоянием.

    Один экземпляр = одна сессия (client_id + session_id фиксированы).
    Pool и redis пересоздаются при каждом вызове (stateless для unit-тестов)
    или переиспользуются (stateful — через конструктор).
    """

    def __init__(
        self,
        connector,
        client_id: UUID,
        session_id: UUID,
        channel: str = "web",
    ) -> None:
        self._connector = connector
        self._client_id = client_id
        self._session_id = session_id
        self._channel = channel
        self._pool = _make_mock_pool()
        self._redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        self._tool_executor = _make_tool_executor(self._pool, client_id)

    async def chat_turn(self, message: str) -> AgentTurnResult:
        """Отправляет одно сообщение в систему, возвращает AgentTurnResult."""
        stage_before = await redis_session.get_stage(self._redis, self._session_id)

        t0 = time.perf_counter()
        try:
            reply = await process_message(
                message=message,
                client_id=self._client_id,
                session_id=self._session_id,
                channel=self._channel,
                pool=self._pool,
                redis_client=self._redis,
                connector=self._connector,
                tools_executor=self._tool_executor.execute,
            )
        except Exception as exc:
            logger.error("InProcessClient: ошибка process_message: %s", exc)
            raise
        finally:
            latency_ms = (time.perf_counter() - t0) * 1000

        stage_after = await redis_session.get_stage(self._redis, self._session_id)

        return AgentTurnResult(
            reply=reply,
            stage_before=stage_before,
            stage_after=stage_after,
            latency_ms=latency_ms,
        )
