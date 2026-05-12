from __future__ import annotations

from uuid import UUID

import asyncpg
from asyncpg import Pool

from src.memory.models import Lead

_LEAD_COLS = (
    "id, client_id, session_id, status, preferences, "
    "idempotency_key, created_at, updated_at"
)

# Маппинг stage воронки → leads.status согласно spec-memory-context §6.2
STAGE_TO_LEAD_STATUS: dict[str, str | None] = {
    "cold": None,
    "discovery": None,
    "qualified": "new",
    "proposal": "proposal",
    "objection": "contacted",
    "closing": "won",
    "follow_up": "contacted",
}


def map_stage_to_lead_status(stage: str) -> str | None:
    """Возвращает leads.status для заданной стадии воронки, или None если лид не создаётся."""
    return STAGE_TO_LEAD_STATUS.get(stage)


def _row_to_lead(row: asyncpg.Record) -> Lead:
    return Lead(
        id=row["id"],
        client_id=row["client_id"],
        session_id=row["session_id"],
        status=row["status"],
        preferences=row["preferences"],
        idempotency_key=row["idempotency_key"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


async def create_idempotent(
    pool: Pool,
    client_id: UUID,
    session_id: UUID,
    preferences: dict,
    idempotency_key: str,
) -> Lead:
    """
    Идемпотентное создание лида.
    При повторном вызове с тем же idempotency_key возвращает существующий лид без ошибки.
    Уникальность гарантируется UNIQUE-индексом на leads.idempotency_key.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            INSERT INTO leads (client_id, session_id, preferences, idempotency_key)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (idempotency_key) DO NOTHING
            RETURNING {_LEAD_COLS}
            """,
            client_id,
            session_id,
            preferences,
            idempotency_key,
        )
        if row is None:
            # ON CONFLICT DO NOTHING — лид уже существует, получаем его
            row = await conn.fetchrow(
                f"SELECT {_LEAD_COLS} FROM leads WHERE idempotency_key = $1",
                idempotency_key,
            )
        return _row_to_lead(row)


async def update_stage(pool: Pool, lead_id: UUID, status: str) -> Lead:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE leads
            SET status = $2,
                updated_at = now()
            WHERE id = $1
            RETURNING {_LEAD_COLS}
            """,
            lead_id,
            status,
        )
        if row is None:
            raise asyncpg.NoDataFoundError(f"Lead {lead_id} не найден")
        return _row_to_lead(row)


async def get_by_id(pool: Pool, lead_id: UUID) -> Lead | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {_LEAD_COLS} FROM leads WHERE id = $1",
            lead_id,
        )
        return _row_to_lead(row) if row else None
