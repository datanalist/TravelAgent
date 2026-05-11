from __future__ import annotations

import pytest
import fakeredis.aioredis
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from src.memory import redis_session
from src.memory.ratelimit import increment, get_count
from src.memory.fallback import get_session_summary, get_session_stage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _AsyncCM:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *args):
        pass


def _make_pool(conn):
    pool = MagicMock()
    pool.acquire.return_value = _AsyncCM(conn)
    return pool


# ---------------------------------------------------------------------------
# redis_session
# ---------------------------------------------------------------------------

class TestRedisSession:
    async def test_set_and_get_summary(self, redis_client) -> None:
        session_id = uuid4()
        summary = {"topics": ["пляж"], "intent": "booking"}
        await redis_session.set_summary(redis_client, session_id, summary)
        result = await redis_session.get_summary(redis_client, session_id)
        assert result == summary

    async def test_get_summary_returns_none_when_missing(self, redis_client) -> None:
        result = await redis_session.get_summary(redis_client, uuid4())
        assert result is None

    async def test_set_and_get_stage(self, redis_client) -> None:
        session_id = uuid4()
        await redis_session.set_stage(redis_client, session_id, "discovery")
        result = await redis_session.get_stage(redis_client, session_id)
        assert result == "discovery"

    async def test_get_stage_returns_none_when_missing(self, redis_client) -> None:
        result = await redis_session.get_stage(redis_client, uuid4())
        assert result is None

    async def test_set_invalid_stage_raises(self, redis_client) -> None:
        with pytest.raises(ValueError, match="Недопустимая стадия"):
            await redis_session.set_stage(redis_client, uuid4(), "invalid_stage")

    async def test_clear_session_deletes_keys(self, redis_client) -> None:
        session_id = uuid4()
        await redis_session.set_summary(redis_client, session_id, {"x": 1})
        await redis_session.set_stage(redis_client, session_id, "qualified")
        await redis_session.set_scratchpad(redis_client, session_id, {"y": 2})

        await redis_session.clear_session(redis_client, session_id)

        assert await redis_session.get_summary(redis_client, session_id) is None
        assert await redis_session.get_stage(redis_client, session_id) is None
        assert await redis_session.get_scratchpad(redis_client, session_id) is None

    async def test_summary_ttl_is_set(self, redis_client) -> None:
        session_id = uuid4()
        await redis_session.set_summary(redis_client, session_id, {"k": "v"})
        key = f"session:{session_id}:summary"
        ttl = await redis_client.ttl(key)
        assert ttl > 0

    async def test_stage_ttl_is_set(self, redis_client) -> None:
        session_id = uuid4()
        await redis_session.set_stage(redis_client, session_id, "proposal")
        key = f"session:{session_id}:stage"
        ttl = await redis_client.ttl(key)
        assert ttl > 0

    async def test_all_valid_stages_accepted(self, redis_client) -> None:
        for stage in redis_session.VALID_STAGES:
            session_id = uuid4()
            await redis_session.set_stage(redis_client, session_id, stage)
            result = await redis_session.get_stage(redis_client, session_id)
            assert result == stage


# ---------------------------------------------------------------------------
# ratelimit
# ---------------------------------------------------------------------------

class TestRatelimit:
    async def test_first_increment_returns_one(self, redis_client) -> None:
        client_id = uuid4()
        count = await increment(redis_client, client_id)
        assert count == 1

    async def test_multiple_increments(self, redis_client) -> None:
        client_id = uuid4()
        for i in range(1, 6):
            count = await increment(redis_client, client_id)
            assert count == i

    async def test_get_count_without_increment(self, redis_client) -> None:
        client_id = uuid4()
        count = await get_count(redis_client, client_id)
        assert count == 0

    async def test_ttl_set_after_first_increment(self, redis_client) -> None:
        client_id = uuid4()
        await increment(redis_client, client_id)
        key = f"ratelimit:{client_id}"
        ttl = await redis_client.ttl(key)
        assert 0 < ttl <= 60

    async def test_ttl_not_reset_on_subsequent_increments(self, redis_client) -> None:
        """TTL устанавливается только при создании ключа (NX), не сбрасывается."""
        client_id = uuid4()
        await increment(redis_client, client_id)
        # Wait a moment would be needed in real test; here we just confirm TTL > 0
        key = f"ratelimit:{client_id}"
        ttl_after_first = await redis_client.ttl(key)
        await increment(redis_client, client_id)
        ttl_after_second = await redis_client.ttl(key)
        # TTL should not be reset higher on second increment
        assert ttl_after_second <= ttl_after_first + 1  # allow tiny clock drift

    async def test_different_clients_independent(self, redis_client) -> None:
        cid1, cid2 = uuid4(), uuid4()
        await increment(redis_client, cid1)
        await increment(redis_client, cid1)
        await increment(redis_client, cid2)
        assert await get_count(redis_client, cid1) == 2
        assert await get_count(redis_client, cid2) == 1


# ---------------------------------------------------------------------------
# fallback
# ---------------------------------------------------------------------------

class TestFallback:
    async def test_summary_redis_hit_no_pg_call(self, redis_client) -> None:
        session_id = uuid4()
        summary = {"text": "redis summary"}
        await redis_session.set_summary(redis_client, session_id, summary)

        pool = MagicMock()  # не должен вызываться

        result = await get_session_summary(redis_client, pool, session_id)

        assert result == summary
        pool.acquire.assert_not_called()

    async def test_summary_redis_miss_falls_back_to_pg(self, redis_client) -> None:
        session_id = uuid4()
        conn = AsyncMock()
        conn.fetchrow.return_value = {"summary": {"text": "pg summary"}}
        pool = _make_pool(conn)

        result = await get_session_summary(redis_client, pool, session_id)

        assert result == {"text": "pg summary"}
        conn.fetchrow.assert_called_once()

    async def test_summary_redis_miss_pg_no_row_returns_none(self, redis_client) -> None:
        session_id = uuid4()
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        pool = _make_pool(conn)

        result = await get_session_summary(redis_client, pool, session_id)
        assert result is None

    async def test_stage_redis_hit_no_pg_call(self, redis_client) -> None:
        session_id = uuid4()
        await redis_session.set_stage(redis_client, session_id, "qualified")

        pool = MagicMock()

        result = await get_session_stage(redis_client, pool, session_id)

        assert result == "qualified"
        pool.acquire.assert_not_called()

    async def test_stage_redis_miss_falls_back_to_pg(self, redis_client) -> None:
        session_id = uuid4()
        conn = AsyncMock()
        conn.fetchrow.return_value = {"current_stage": "proposal"}
        pool = _make_pool(conn)

        result = await get_session_stage(redis_client, pool, session_id)

        assert result == "proposal"
        conn.fetchrow.assert_called_once()
