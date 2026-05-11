from __future__ import annotations

import logging
from uuid import UUID

from asyncpg import Pool
from redis.asyncio import Redis
from redis.exceptions import ConnectionError, TimeoutError

from src.memory import redis_session

logger = logging.getLogger(__name__)


async def get_session_summary(
    redis_client: Redis,
    pool: Pool,
    session_id: UUID,
) -> dict | None:
    """
    Возвращает summary сессии.
    Приоритет: Redis → PostgreSQL (при недоступности Redis или истёкшем TTL).
    """
    try:
        raw = await redis_session.get_summary(redis_client, session_id)
        if raw is not None:
            return raw
    except (ConnectionError, TimeoutError) as exc:
        logger.warning("Redis недоступен при чтении summary сессии %s: %s", session_id, exc)

    # Fallback на PostgreSQL
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT summary FROM sessions WHERE id = $1",
            session_id,
        )
        return row["summary"] if row and row["summary"] else None


async def get_session_stage(
    redis_client: Redis,
    pool: Pool,
    session_id: UUID,
) -> str | None:
    """
    Возвращает стадию воронки.
    Приоритет: Redis → PostgreSQL.
    При расхождении источник истины — PostgreSQL (ADR-003).
    """
    try:
        stage = await redis_session.get_stage(redis_client, session_id)
        if stage is not None:
            return stage
    except (ConnectionError, TimeoutError) as exc:
        logger.warning("Redis недоступен при чтении stage сессии %s: %s", session_id, exc)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT current_stage FROM sessions WHERE id = $1",
            session_id,
        )
        return row["current_stage"] if row else None


async def rehydrate_session(
    redis_client: Redis,
    pool: Pool,
    session_id: UUID,
) -> None:
    """
    Восстанавливает Redis-ключи сессии из PostgreSQL.
    Вызывается при обнаружении отсутствия ключей (истёкший TTL) или после рестарта Redis.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT summary, current_stage FROM sessions WHERE id = $1",
            session_id,
        )

    if row is None:
        logger.warning("Сессия %s не найдена в PostgreSQL при регидратации", session_id)
        return

    try:
        if row["summary"] is not None:
            await redis_session.set_summary(redis_client, session_id, row["summary"])

        if row["current_stage"] is not None:
            await redis_session.set_stage(redis_client, session_id, row["current_stage"])

        logger.info("Redis-ключи сессии %s успешно восстановлены из PostgreSQL", session_id)
    except (ConnectionError, TimeoutError) as exc:
        logger.error("Не удалось записать в Redis при регидратации сессии %s: %s", session_id, exc)
