from __future__ import annotations

from uuid import UUID

from redis.asyncio import Redis

_TTL_RATELIMIT = 60  # 1 минута


def _key(client_id: UUID) -> str:
    return f"ratelimit:{client_id}"


async def increment(client: Redis, client_id: UUID) -> int:
    """
    Инкрементирует счётчик запросов для client_id.
    TTL 60s устанавливается только при создании ключа (NX), не сбрасывается на каждый запрос.
    Возвращает текущее значение счётчика после инкремента.
    """
    key = _key(client_id)
    pipe = client.pipeline()
    pipe.incr(key)
    pipe.expire(key, _TTL_RATELIMIT, nx=True)
    results = await pipe.execute()
    return int(results[0])


async def get_count(client: Redis, client_id: UUID) -> int:
    """Возвращает текущее значение счётчика без инкремента."""
    val = await client.get(_key(client_id))
    return int(val) if val else 0


async def reset(client: Redis, client_id: UUID) -> None:
    """Сбрасывает счётчик (для тестов и административных операций)."""
    await client.delete(_key(client_id))
