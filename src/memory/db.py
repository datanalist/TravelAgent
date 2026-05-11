from __future__ import annotations

import json

import asyncpg
from asyncpg import Pool


async def _init_connection(conn: asyncpg.Connection) -> None:
    """Регистрирует кодеки для JSONB — asyncpg требует явной регистрации."""
    await conn.set_type_codec(
        "jsonb",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "json",
        encoder=json.dumps,
        decoder=json.loads,
        schema="pg_catalog",
    )


async def create_pool(
    dsn: str,
    min_size: int = 5,
    max_size: int = 20,
    command_timeout: float = 2.0,
) -> Pool:
    return await asyncpg.create_pool(
        dsn,
        min_size=min_size,
        max_size=max_size,
        command_timeout=command_timeout,
        statement_cache_size=100,
        init=_init_connection,
    )


async def healthcheck(pool: Pool) -> bool:
    try:
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except (asyncpg.PostgresError, OSError):
        return False
