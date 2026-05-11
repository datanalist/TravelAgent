from __future__ import annotations

import redis.asyncio as aioredis
from redis.asyncio import Redis
from redis.exceptions import ConnectionError, TimeoutError


def create_client(
    url: str,
    socket_timeout: float = 0.5,
    socket_connect_timeout: float = 1.0,
    decode_responses: bool = True,
) -> Redis:
    return aioredis.from_url(
        url,
        socket_timeout=socket_timeout,
        socket_connect_timeout=socket_connect_timeout,
        decode_responses=decode_responses,
    )


async def healthcheck(client: Redis) -> bool:
    try:
        await client.ping()
        return True
    except (ConnectionError, TimeoutError, OSError):
        return False
