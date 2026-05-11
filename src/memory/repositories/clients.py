from __future__ import annotations

from uuid import UUID

import asyncpg
from asyncpg import Pool

from src.memory.models import Client, ClientProfile

_CLIENT_COLS = (
    "id, telegram_id, source, name, email, phone, "
    "segment, language, preferred_style, created_at, updated_at"
)

_PROFILE_COLS = (
    "id, client_id, budget_range, preferred_destinations, "
    "travel_style, constraints, raw_preferences, updated_at"
)


def _row_to_client(row: asyncpg.Record) -> Client:
    return Client(
        id=row["id"],
        telegram_id=row["telegram_id"],
        source=row["source"],
        name=row["name"],
        email=row["email"],
        phone=row["phone"],
        segment=row["segment"],
        language=row["language"],
        preferred_style=row["preferred_style"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_profile(row: asyncpg.Record) -> ClientProfile:
    return ClientProfile(
        id=row["id"],
        client_id=row["client_id"],
        budget_range=row["budget_range"],
        preferred_destinations=row["preferred_destinations"],
        travel_style=row["travel_style"],
        constraints=row["constraints"],
        raw_preferences=row["raw_preferences"],
        updated_at=row["updated_at"],
    )


async def get_by_id(pool: Pool, client_id: UUID) -> Client | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {_CLIENT_COLS} FROM clients WHERE id = $1",
            client_id,
        )
        return _row_to_client(row) if row else None


async def get_by_telegram_id(pool: Pool, telegram_id: int) -> Client | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {_CLIENT_COLS} FROM clients WHERE telegram_id = $1",
            telegram_id,
        )
        return _row_to_client(row) if row else None


async def upsert(pool: Pool, telegram_id: int, source: str) -> Client:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            INSERT INTO clients (telegram_id, source)
            VALUES ($1, $2)
            ON CONFLICT (telegram_id) DO UPDATE
                SET source = EXCLUDED.source,
                    updated_at = now()
            RETURNING {_CLIENT_COLS}
            """,
            telegram_id,
            source,
        )
        return _row_to_client(row)


async def get_profile(pool: Pool, client_id: UUID) -> ClientProfile | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {_PROFILE_COLS} FROM client_profile WHERE client_id = $1",
            client_id,
        )
        return _row_to_profile(row) if row else None


# Разрешённые поля для UPSERT — только они попадают в динамический запрос
_PROFILE_UPDATABLE = frozenset(
    {"budget_range", "preferred_destinations", "travel_style", "constraints", "raw_preferences"}
)


async def upsert_profile(pool: Pool, client_id: UUID, **fields: object) -> ClientProfile:
    """
    Partial UPSERT профиля клиента.
    Обновляет только переданные поля; не затрагивает остальные колонки.
    """
    update_fields = {k: v for k, v in fields.items() if k in _PROFILE_UPDATABLE}
    if not update_fields:
        raise ValueError(f"Нет допустимых полей для обновления. Разрешено: {_PROFILE_UPDATABLE}")

    col_names = list(update_fields.keys())
    col_values = list(update_fields.values())

    col_list = ", ".join(col_names)
    insert_placeholders = ", ".join(f"${i + 2}" for i in range(len(col_names)))
    excluded_set = ", ".join(f"{k} = EXCLUDED.{k}" for k in col_names)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""
            INSERT INTO client_profile (client_id, {col_list})
            VALUES ($1, {insert_placeholders})
            ON CONFLICT (client_id) DO UPDATE
                SET {excluded_set}, updated_at = now()
            RETURNING {_PROFILE_COLS}
            """,
            client_id,
            *col_values,
        )
        return _row_to_profile(row)
