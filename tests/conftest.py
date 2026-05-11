from __future__ import annotations

import pytest
import fakeredis.aioredis
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4


class _AsyncCM:
    """Async context manager wrapper for mock asyncpg connection."""

    def __init__(self, conn: AsyncMock) -> None:
        self._conn = conn

    async def __aenter__(self) -> AsyncMock:
        return self._conn

    async def __aexit__(self, *args: object) -> None:
        pass


@pytest.fixture
def redis_client():
    """fakeredis с decode_responses=True — соответствует реальному клиенту."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def fake_redis():
    """Alias redis_client для использования в integration/acceptance тестах."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def mock_pool():
    """Mock asyncpg pool с async context manager и mock connection."""
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    conn.fetch.return_value = []
    conn.execute.return_value = None
    pool.acquire.return_value = _AsyncCM(conn)
    return pool, conn


@pytest.fixture
def mock_llm_connector():
    """LLMConnector-заглушка: connector.complete управляется через side_effect."""
    connector = MagicMock()
    connector.complete = AsyncMock()
    connector._config = MagicMock()
    connector._config.temperature_toolcall = 0.1
    connector._config.temperature_generation = 0.7
    return connector


@pytest.fixture
def sample_client_id():
    return uuid4()


@pytest.fixture
def sample_session_id():
    return uuid4()
