from __future__ import annotations

import json
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import ConnectionError, TimeoutError

_TTL_SESSION = 86400  # 24 часа

# Допустимые значения стадии воронки согласно system-design §3
VALID_STAGES = frozenset(
    {"cold", "discovery", "qualified", "proposal", "objection", "closing", "follow_up"}
)


def _summary_key(session_id: UUID) -> str:
    return f"session:{session_id}:summary"


def _stage_key(session_id: UUID) -> str:
    return f"session:{session_id}:stage"


def _scratchpad_key(session_id: UUID) -> str:
    return f"session:{session_id}:scratchpad"


async def get_summary(client: Redis, session_id: UUID) -> dict | None:
    try:
        raw = await client.get(_summary_key(session_id))
        return json.loads(raw) if raw else None
    except (ConnectionError, TimeoutError):
        return None


async def set_summary(client: Redis, session_id: UUID, summary: dict) -> None:
    await client.set(_summary_key(session_id), json.dumps(summary), ex=_TTL_SESSION)


async def get_stage(client: Redis, session_id: UUID) -> str | None:
    try:
        return await client.get(_stage_key(session_id))
    except (ConnectionError, TimeoutError):
        return None


async def set_stage(client: Redis, session_id: UUID, stage: str) -> None:
    if stage not in VALID_STAGES:
        raise ValueError(f"Недопустимая стадия воронки: {stage!r}. Допустимые: {VALID_STAGES}")
    await client.set(_stage_key(session_id), stage, ex=_TTL_SESSION)


async def get_scratchpad(client: Redis, session_id: UUID) -> dict | None:
    try:
        raw = await client.get(_scratchpad_key(session_id))
        return json.loads(raw) if raw else None
    except (ConnectionError, TimeoutError):
        return None


async def set_scratchpad(client: Redis, session_id: UUID, data: dict) -> None:
    await client.set(_scratchpad_key(session_id), json.dumps(data), ex=_TTL_SESSION)


async def clear_session(client: Redis, session_id: UUID) -> None:
    """Удаляет все ключи сессии из Redis (например, при явном завершении сессии)."""
    await client.delete(
        _summary_key(session_id),
        _stage_key(session_id),
        _scratchpad_key(session_id),
    )
