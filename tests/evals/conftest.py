from __future__ import annotations

"""Фикстуры для User-Behaviour Eval pipeline.

Переиспользует фикстуры из tests/conftest.py (mock_pool, fake_redis, mock_llm_connector).
Добавляет eval-специфичные: real_llm_connector для симулятора (если API-ключ задан),
no-op langfuse client для unit-тестов.
"""

import os
import pytest
import fakeredis.aioredis
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from tests.evals.simulator.models import Persona, PersonaStyle, Scenario, ExpectedOutcome
from tests.evals.tracing.langfuse_client import LangfuseClient


# --- Переиспользованные фикстуры ---

class _AsyncCM:
    def __init__(self, conn: AsyncMock) -> None:
        self._conn = conn

    async def __aenter__(self) -> AsyncMock:
        return self._conn

    async def __aexit__(self, *args: object) -> None:
        pass


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def mock_pool():
    pool = MagicMock()
    conn = AsyncMock()
    conn.fetchrow.return_value = None
    conn.fetch.return_value = []
    conn.execute.return_value = None
    pool.acquire.return_value = _AsyncCM(conn)
    return pool, conn


@pytest.fixture
def mock_llm_connector():
    connector = MagicMock()
    connector.complete = AsyncMock()
    connector._config = MagicMock()
    connector._config.temperature_toolcall = 0.1
    connector._config.temperature_generation = 0.7
    return connector


# --- Eval-специфичные фикстуры ---

@pytest.fixture
def langfuse_noop():
    """LangfuseClient в fallback-режиме (LANGFUSE_* ENV не заданы → только JSONL)."""
    return LangfuseClient()


@pytest.fixture
def sample_persona() -> Persona:
    return Persona(
        name="test_persona",
        display_name="Тестовая персона",
        description="Клиент для unit-тестов симулятора",
        style=PersonaStyle(formality="high", expectations="premium"),
        constraints=["не раскрывай, что ты симулятор"],
        voice_examples=["Здравствуйте, хочу тур на Мальдивы."],
    )


@pytest.fixture
def sample_scenario() -> Scenario:
    return Scenario(
        name="test_scenario",
        display_name="Тестовый сценарий",
        category="happy_path",
        goal="Найти тур на Мальдивы",
        max_turns=3,
        expected_outcome=ExpectedOutcome(goal_success=True),
        playbook_hints=["Спроси о направлении", "Уточни бюджет"],
    )


@pytest.fixture
def client_id():
    return uuid4()


@pytest.fixture
def session_id():
    return uuid4()
