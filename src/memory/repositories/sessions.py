from __future__ import annotations

from uuid import UUID

import asyncpg
from asyncpg import Pool

from src.memory.models import Session

_SESSION_COLS = (
    "id, client_id, channel, started_at, last_active_at, "
    "current_stage, summary, message_count, status"
)


def _row_to_session(row: asyncpg.Record) -> Session:
    return Session(
        id=row["id"],
        client_id=row["client_id"],
        channel=row["channel"],
        started_at=row["started_at"],
        last_active_at=row["last_active_at"],
        current_stage=row["current_stage"],
        summary=row["summary"],
        message_count=row["message_count"],
        status=row["status"],
    )


async def upsert(pool: Pool, client_id: UUID, channel: str) -> Session:
    """Создаёт новую активную сессию для клиента и канала."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            INSERT INTO sessions (client_id, channel)
            VALUES ($1, $2)
            RETURNING {_SESSION_COLS}
            """,
            client_id,
            channel,
        )
        return _row_to_session(row)


async def get_active(pool: Pool, client_id: UUID, channel: str) -> Session | None:
    """Возвращает последнюю активную сессию клиента в заданном канале."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            SELECT {_SESSION_COLS}
            FROM sessions
            WHERE client_id = $1
              AND channel = $2
              AND status = 'active'
            ORDER BY started_at DESC
            LIMIT 1
            """,
            client_id,
            channel,
        )
        return _row_to_session(row) if row else None


async def append_summary(pool: Pool, session_id: UUID, summary: dict) -> None:
    """
    Записывает результат Conversation Summarizer в sessions.summary (PostgreSQL).
    Зеркальная запись в Redis выполняется через redis_session.set_summary().
    """
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE sessions
            SET summary = $2,
                last_active_at = now()
            WHERE id = $1
            """,
            session_id,
            summary,
        )


async def update_stage(pool: Pool, session_id: UUID, stage: str) -> None:
    """
    Атомарно обновляет стадию воронки в PostgreSQL.
    Stage Tracker также пишет в Redis через redis_session.set_stage().
    """
    async with pool.acquire() as conn:
        await conn.execute(
            """
            UPDATE sessions
            SET current_stage = $2,
                last_active_at = now()
            WHERE id = $1
            """,
            session_id,
            stage,
        )


async def increment_message_count(pool: Pool, session_id: UUID) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE sessions SET message_count = message_count + 1 WHERE id = $1",
            session_id,
        )
