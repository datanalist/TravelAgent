from __future__ import annotations

"""FastAPI API router: POST /chat, GET /health, POST /webhook/telegram.

Ответственность:
- Нормализация запроса → резолв/создание client + session
- Сохранение user-сообщения
- Вызов Orchestrator.process_message()
- tools_executor — стаб, который будет заменён реальной реализацией из src/tools/
"""

import asyncio
import logging
import uuid
from typing import Annotated

import asyncpg
from asyncpg import Pool
from fastapi import APIRouter, Depends, HTTPException, Request
from redis.asyncio import Redis
from telegram import Update

from src.config import settings
from src.llm.connector import LLMConnector
from src.memory import redis_session
from src.memory.db import healthcheck as pg_healthcheck
from src.memory.redis_client import healthcheck as redis_healthcheck
from src.memory.repositories import clients as clients_repo
from src.memory.repositories import messages as messages_repo
from src.memory.repositories import sessions as sessions_repo
from src.models.chat import ChatRequest, ChatResponse
from src.orchestrator import process_message

# Глобальный lock для однократной инициализации PTB Application
_tg_init_lock = asyncio.Lock()

logger = logging.getLogger(__name__)

api_router = APIRouter()


# --- Dependencies ---

def get_pool(request: Request) -> Pool:
    return request.app.state.pool


def get_redis(request: Request) -> Redis:
    return request.app.state.redis


def get_connector(request: Request) -> LLMConnector:
    return request.app.state.llm_connector


PoolDep = Annotated[Pool, Depends(get_pool)]
RedisDep = Annotated[Redis, Depends(get_redis)]
ConnectorDep = Annotated[LLMConnector, Depends(get_connector)]


# --- Web client helpers ---

_WEB_CLIENT_NS = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")  # uuid.NAMESPACE_URL


async def _resolve_web_client(pool: Pool, web_session_id: str) -> asyncpg.Record:
    """Возвращает или создаёт клиента для web-сессии.

    Использует детерминированный UUID на основе web_session_id.
    TODO: перенести в src/memory/repositories/clients.py (upsert_by_external_id).
    """
    client_id = uuid.uuid5(_WEB_CLIENT_NS, f"web:{web_session_id}")
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO clients (id, source)
            VALUES ($1, 'web')
            ON CONFLICT (id) DO UPDATE SET source = EXCLUDED.source
            RETURNING id, telegram_id, source, name, email, phone,
                      segment, language, preferred_style, created_at, updated_at
            """,
            client_id,
        )
    return row


# --- Stub tools executor ---

async def _stub_tools_executor(tool_name: str, tool_input: dict) -> dict:
    """Заглушка tools_executor до реализации src/tools/ (другой агент).

    Возвращает error-payload — Orchestrator обработает это как graceful degradation.
    """
    logger.warning("tools_executor: tool=%r вызван, но src/tools/ не реализован", tool_name)
    return {"error": f"Tool '{tool_name}' is not yet implemented"}


# --- Endpoints ---

@api_router.post("/chat", response_model=ChatResponse)
async def chat(
    request_body: ChatRequest,
    pool: PoolDep,
    redis: RedisDep,
    connector: ConnectorDep,
) -> ChatResponse:
    """Обработка сообщения чата.

    1. Резолв или создание client
    2. Получение или создание активной session
    3. Сохранение user-сообщения
    4. Вызов Orchestrator.process_message()
    5. Возврат ChatResponse
    """
    # Валидация: нужен хотя бы один идентификатор
    if request_body.telegram_id is None and not request_body.web_session_id:
        raise HTTPException(
            status_code=400,
            detail="Необходимо указать telegram_id или web_session_id",
        )

    # --- Резолв client ---
    try:
        if request_body.telegram_id is not None:
            client = await clients_repo.upsert(
                pool, request_body.telegram_id, request_body.channel
            )
        else:
            # web_session_id guaranteed non-None by check above
            row = await _resolve_web_client(pool, request_body.web_session_id)  # type: ignore[arg-type]
            from src.memory.models import Client
            from datetime import datetime, timezone
            client = Client(
                id=row["id"],
                telegram_id=row["telegram_id"],
                source=row["source"],
                name=row["name"],
                email=row["email"],
                phone=row["phone"],
                segment=row["segment"],
                language=row["language"],
                preferred_style=row["preferred_style"],
                created_at=row["created_at"] or datetime.now(timezone.utc),
                updated_at=row["updated_at"] or datetime.now(timezone.utc),
            )
    except Exception as exc:
        logger.error("chat: ошибка резолва клиента: %s", exc)
        raise HTTPException(status_code=503, detail="Ошибка сервиса, попробуйте позже")

    # --- Резолв session ---
    try:
        session = await sessions_repo.get_active(pool, client.id, request_body.channel)
        if session is None:
            session = await sessions_repo.upsert(pool, client.id, request_body.channel)
    except Exception as exc:
        logger.error("chat: ошибка резолва сессии: %s", exc)
        raise HTTPException(status_code=503, detail="Ошибка сервиса, попробуйте позже")

    # --- Сохранить user-сообщение ---
    try:
        await messages_repo.append(
            pool,
            session.id,
            role="user",
            content=request_body.message,
        )
        await sessions_repo.increment_message_count(pool, session.id)
    except Exception as exc:
        logger.warning("chat: не удалось сохранить user-сообщение: %s", exc)

    # --- Вызов Orchestrator ---
    try:
        reply = await process_message(
            message=request_body.message,
            client_id=client.id,
            session_id=session.id,
            channel=request_body.channel,
            pool=pool,
            redis_client=redis,
            connector=connector,
            tools_executor=_stub_tools_executor,
        )
    except Exception as exc:
        logger.error("chat: критическая ошибка orchestrator: %s", exc)
        reply = "К сожалению, произошла ошибка. Попробуйте позже или обратитесь к менеджеру."

    # --- Получить актуальную стадию ---
    try:
        current_stage = await redis_session.get_stage(redis, session.id) or session.current_stage
    except Exception:
        current_stage = session.current_stage

    return ChatResponse(
        reply=reply,
        session_id=session.id,
        stage=current_stage,
        lead_id=None,
    )


@api_router.post("/webhook/telegram")
async def telegram_webhook(request: Request) -> dict:
    """Принимает Telegram Update и передаёт в PTB Application."""
    async with _tg_init_lock:
        if not hasattr(request.app.state, "telegram_app"):
            from src.channels.telegram import build_application

            tg_app = build_application(settings.TELEGRAM_BOT_TOKEN)
            tg_app.bot_data.update(
                {
                    "pool": request.app.state.pool,
                    "redis": request.app.state.redis,
                    "connector": request.app.state.llm_connector,
                }
            )
            await tg_app.initialize()
            request.app.state.telegram_app = tg_app

    tg_app = request.app.state.telegram_app
    data = await request.json()
    update = Update.de_json(data, tg_app.bot)
    if update is not None:
        await tg_app.process_update(update)
    return {"ok": True}


@api_router.get("/health")
async def health(
    pool: PoolDep,
    redis: RedisDep,
) -> dict:
    """Проверяет соединение с PostgreSQL и Redis."""
    pg_ok = await pg_healthcheck(pool)
    redis_ok = await redis_healthcheck(redis)

    status = "ok" if (pg_ok and redis_ok) else "degraded"
    return {
        "status": status,
        "postgres": "ok" if pg_ok else "error",
        "redis": "ok" if redis_ok else "error",
    }
