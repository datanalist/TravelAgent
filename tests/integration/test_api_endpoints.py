from __future__ import annotations

"""Integration-тесты FastAPI endpoints: /health, /chat через httpx.AsyncClient."""

import pytest
import httpx
from httpx import ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone
from fastapi import FastAPI
from asyncpg import Pool
from redis.asyncio import Redis

from src.api.router import api_router, get_pool, get_redis, get_connector
from src.memory.models import Client, Session, Message


# ---------------------------------------------------------------------------
# Test app factory — переопределяет dependency_overrides async-функциями,
# чтобы избежать anyio/asyncio конфликта при run_in_threadpool.
# ---------------------------------------------------------------------------

def _build_test_app(pool, redis, connector) -> FastAPI:
    app = FastAPI()
    app.include_router(api_router)

    async def _get_pool() -> Pool:
        return pool

    async def _get_redis() -> Redis:
        return redis

    async def _get_connector():
        return connector

    app.dependency_overrides[get_pool] = _get_pool
    app.dependency_overrides[get_redis] = _get_redis
    app.dependency_overrides[get_connector] = _get_connector
    return app


# ---------------------------------------------------------------------------
# Хелперы для создания dataclass-заглушек
# ---------------------------------------------------------------------------

def _fake_client(telegram_id: int = 777) -> Client:
    now = datetime.now(timezone.utc)
    return Client(
        id=uuid4(),
        telegram_id=telegram_id,
        source="web",
        name=None, email=None, phone=None,
        segment=None, language=None, preferred_style=None,
        created_at=now, updated_at=now,
    )


def _fake_session(client_id=None, stage: str = "cold") -> Session:
    now = datetime.now(timezone.utc)
    return Session(
        id=uuid4(),
        client_id=client_id or uuid4(),
        channel="web",
        started_at=now,
        last_active_at=now,
        current_stage=stage,
        summary=None,
        message_count=0,
        status="active",
    )


def _fake_message(session_id=None) -> Message:
    now = datetime.now(timezone.utc)
    return Message(
        id=uuid4(),
        session_id=session_id or uuid4(),
        role="user",
        content="test",
        metadata=None,
        created_at=now,
    )


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

async def test_health_endpoint_ok(fake_redis):
    """GET /health → 200 {"status": "ok", "postgres": "ok", "redis": "ok"}."""
    pool = MagicMock()
    app = _build_test_app(pool=pool, redis=fake_redis, connector=MagicMock())

    with (
        patch("src.api.router.pg_healthcheck", new_callable=AsyncMock, return_value=True),
        patch("src.api.router.redis_healthcheck", new_callable=AsyncMock, return_value=True),
    ):
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["postgres"] == "ok"
    assert body["redis"] == "ok"


async def test_health_endpoint_degraded_on_pg_failure(fake_redis):
    """GET /health → 200 {"status": "degraded"} когда PostgreSQL недоступен."""
    app = _build_test_app(pool=MagicMock(), redis=fake_redis, connector=MagicMock())

    with (
        patch("src.api.router.pg_healthcheck", new_callable=AsyncMock, return_value=False),
        patch("src.api.router.redis_healthcheck", new_callable=AsyncMock, return_value=True),
    ):
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["postgres"] == "error"
    assert body["redis"] == "ok"


# ---------------------------------------------------------------------------
# /chat
# ---------------------------------------------------------------------------

async def test_chat_endpoint_returns_response(fake_redis):
    """POST /chat с telegram_id → 200 ChatResponse с reply и session_id."""
    client_obj = _fake_client(telegram_id=42)
    session_obj = _fake_session(client_id=client_obj.id)
    app = _build_test_app(pool=MagicMock(), redis=fake_redis, connector=MagicMock())

    with (
        patch("src.api.router.clients_repo.upsert", new_callable=AsyncMock, return_value=client_obj),
        patch("src.api.router.sessions_repo.get_active", new_callable=AsyncMock, return_value=session_obj),
        patch("src.api.router.messages_repo.append", new_callable=AsyncMock, return_value=_fake_message()),
        patch("src.api.router.sessions_repo.increment_message_count", new_callable=AsyncMock),
        patch("src.api.router.process_message", new_callable=AsyncMock, return_value="Добро пожаловать!"),
        patch("src.api.router.redis_session.get_stage", new_callable=AsyncMock, return_value="cold"),
    ):
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/chat",
                json={"message": "Привет", "telegram_id": 42, "channel": "web"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["reply"] == "Добро пожаловать!"
    assert "session_id" in body
    assert body["stage"] == "cold"


async def test_chat_endpoint_validation_error():
    """POST /chat без поля message → 422 Unprocessable Entity."""
    app = _build_test_app(pool=MagicMock(), redis=MagicMock(), connector=MagicMock())

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/chat", json={})

    assert resp.status_code == 422


async def test_chat_endpoint_missing_identifier():
    """POST /chat без telegram_id и web_session_id → 400 Bad Request."""
    app = _build_test_app(pool=MagicMock(), redis=MagicMock(), connector=MagicMock())

    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/chat", json={"message": "Привет", "channel": "web"})

    assert resp.status_code == 400


async def test_chat_endpoint_creates_new_session_when_none(fake_redis):
    """Если активной сессии нет — создаётся новая через sessions_repo.upsert."""
    client_obj = _fake_client(telegram_id=55)
    session_obj = _fake_session(client_id=client_obj.id)
    app = _build_test_app(pool=MagicMock(), redis=fake_redis, connector=MagicMock())

    with (
        patch("src.api.router.clients_repo.upsert", new_callable=AsyncMock, return_value=client_obj),
        # get_active возвращает None → должен вызваться upsert
        patch("src.api.router.sessions_repo.get_active", new_callable=AsyncMock, return_value=None),
        patch("src.api.router.sessions_repo.upsert", new_callable=AsyncMock, return_value=session_obj) as mock_upsert,
        patch("src.api.router.messages_repo.append", new_callable=AsyncMock, return_value=_fake_message()),
        patch("src.api.router.sessions_repo.increment_message_count", new_callable=AsyncMock),
        patch("src.api.router.process_message", new_callable=AsyncMock, return_value="Привет!"),
        patch("src.api.router.redis_session.get_stage", new_callable=AsyncMock, return_value="cold"),
    ):
        async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/chat",
                json={"message": "Привет", "telegram_id": 55, "channel": "telegram"},
            )

    assert resp.status_code == 200
    mock_upsert.assert_called_once()
