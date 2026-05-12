from __future__ import annotations

from uuid import UUID

import asyncpg
from asyncpg import Pool

from src.memory.models import Message

_MSG_COLS = "id, session_id, role, content, metadata, created_at"


def _row_to_message(row: asyncpg.Record) -> Message:
    return Message(
        id=row["id"],
        session_id=row["session_id"],
        role=row["role"],
        content=row["content"],
        metadata=row["metadata"],
        created_at=row["created_at"],
    )


async def append(
    pool: Pool,
    session_id: UUID,
    role: str,
    content: str,
    metadata: dict | None = None,
) -> Message:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            INSERT INTO messages (session_id, role, content, metadata)
            VALUES ($1, $2, $3, $4)
            RETURNING {_MSG_COLS}
            """,
            session_id,
            role,
            content,
            metadata,
        )
        return _row_to_message(row)


async def load_recent(
    pool: Pool,
    session_id: UUID,
    limit: int = 10,
) -> list[Message]:
    """Загружает последние N сообщений сессии в хронологическом порядке."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT {_MSG_COLS}
            FROM (
                SELECT {_MSG_COLS}
                FROM messages
                WHERE session_id = $1
                ORDER BY created_at DESC
                LIMIT $2
            ) sub
            ORDER BY created_at ASC
            """,
            session_id,
            limit,
        )
        return [_row_to_message(r) for r in rows]
