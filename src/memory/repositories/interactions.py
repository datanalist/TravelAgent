from __future__ import annotations

from uuid import UUID

from asyncpg import Pool


async def log(
    pool: Pool,
    session_id: UUID,
    tool_name: str,
    input: dict,
    output: dict,
) -> None:
    """
    Записывает событие вызова tool. Вызывается программно Orchestrator'ом,
    не является LLM-tool.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO interactions (session_id, tool_name, input, output)
            VALUES ($1, $2, $3, $4)
            """,
            session_id,
            tool_name,
            input,
            output,
        )
