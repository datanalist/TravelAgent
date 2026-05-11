from __future__ import annotations

from uuid import UUID

import asyncpg
from asyncpg import Pool

from src.memory.models import Itinerary

_ITIN_COLS = "id, lead_id, options, chosen_option, created_at"


def _row_to_itinerary(row: asyncpg.Record) -> Itinerary:
    return Itinerary(
        id=row["id"],
        lead_id=row["lead_id"],
        options=row["options"] or [],
        chosen_option=row["chosen_option"],
        created_at=row["created_at"],
    )


async def create(pool: Pool, lead_id: UUID, options: list[dict]) -> Itinerary:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            INSERT INTO itineraries (lead_id, options)
            VALUES ($1, $2)
            RETURNING {_ITIN_COLS}
            """,
            lead_id,
            options,
        )
        return _row_to_itinerary(row)


async def set_chosen_option(
    pool: Pool,
    itinerary_id: UUID,
    chosen_option: dict,
) -> Itinerary:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            UPDATE itineraries
            SET chosen_option = $2
            WHERE id = $1
            RETURNING {_ITIN_COLS}
            """,
            itinerary_id,
            chosen_option,
        )
        if row is None:
            raise asyncpg.NoDataFoundError(f"Itinerary {itinerary_id} не найден")
        return _row_to_itinerary(row)


async def get_by_lead_id(pool: Pool, lead_id: UUID) -> Itinerary | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            SELECT {_ITIN_COLS}
            FROM itineraries
            WHERE lead_id = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            lead_id,
        )
        return _row_to_itinerary(row) if row else None
