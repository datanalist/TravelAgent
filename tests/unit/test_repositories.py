from __future__ import annotations

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4, UUID

from src.memory.repositories import clients as clients_repo
from src.memory.repositories import leads as leads_repo
from src.memory.repositories.leads import STAGE_TO_LEAD_STATUS, map_stage_to_lead_status


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


def _make_pool(conn: AsyncMock) -> MagicMock:
    pool = MagicMock()
    pool.acquire.return_value = _AsyncCM(conn)
    return pool


def _client_row(client_id: UUID | None = None) -> dict:
    uid = client_id or uuid4()
    return {
        "id": uid,
        "telegram_id": 12345,
        "source": "telegram",
        "name": "Test User",
        "email": "test@example.com",
        "phone": "+79001234567",
        "segment": "premium",
        "language": "ru",
        "preferred_style": "luxury",
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 1),
    }


def _profile_row(client_id: UUID | None = None) -> dict:
    return {
        "id": uuid4(),
        "client_id": client_id or uuid4(),
        "budget_range": {"min": 1000, "max": 5000},
        "preferred_destinations": ["Таиланд"],
        "travel_style": "beach",
        "constraints": {},
        "raw_preferences": {},
        "updated_at": datetime(2026, 1, 1),
    }


def _lead_row(
    client_id: UUID | None = None,
    session_id: UUID | None = None,
    ikey: str = "key-1",
) -> dict:
    return {
        "id": uuid4(),
        "client_id": client_id or uuid4(),
        "session_id": session_id or uuid4(),
        "status": "new",
        "preferences": {"destination": "Таиланд"},
        "idempotency_key": ikey,
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 1),
    }


# ---------------------------------------------------------------------------
# clients repository
# ---------------------------------------------------------------------------

class TestClientsRepository:
    async def test_get_by_id_returns_client(self) -> None:
        client_id = uuid4()
        row = _client_row(client_id)
        conn = AsyncMock()
        conn.fetchrow.return_value = row
        pool = _make_pool(conn)

        result = await clients_repo.get_by_id(pool, client_id)

        assert result is not None
        assert result.id == client_id
        assert result.telegram_id == 12345

    async def test_get_by_id_returns_none_when_missing(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        pool = _make_pool(conn)

        result = await clients_repo.get_by_id(pool, uuid4())
        assert result is None

    async def test_upsert_executes_correct_sql(self) -> None:
        row = _client_row()
        conn = AsyncMock()
        conn.fetchrow.return_value = row
        pool = _make_pool(conn)

        await clients_repo.upsert(pool, telegram_id=12345, source="telegram")

        sql: str = conn.fetchrow.call_args[0][0]
        assert "ON CONFLICT" in sql
        assert "telegram_id" in sql

    async def test_get_profile_returns_profile(self) -> None:
        client_id = uuid4()
        row = _profile_row(client_id)
        conn = AsyncMock()
        conn.fetchrow.return_value = row
        pool = _make_pool(conn)

        result = await clients_repo.get_profile(pool, client_id)

        assert result is not None
        assert result.client_id == client_id
        assert result.travel_style == "beach"

    async def test_get_profile_returns_none_when_missing(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        pool = _make_pool(conn)

        result = await clients_repo.get_profile(pool, uuid4())
        assert result is None

    async def test_upsert_profile_executes_on_conflict_sql(self) -> None:
        client_id = uuid4()
        row = _profile_row(client_id)
        conn = AsyncMock()
        conn.fetchrow.return_value = row
        pool = _make_pool(conn)

        await clients_repo.upsert_profile(pool, client_id, travel_style="luxury")

        sql: str = conn.fetchrow.call_args[0][0]
        assert "ON CONFLICT" in sql
        assert "travel_style" in sql

    async def test_upsert_profile_no_valid_fields_raises(self) -> None:
        conn = AsyncMock()
        pool = _make_pool(conn)

        with pytest.raises(ValueError, match="Нет допустимых полей"):
            await clients_repo.upsert_profile(pool, uuid4(), invalid_field="value")

    async def test_get_by_telegram_id_returns_client(self) -> None:
        row = _client_row()
        conn = AsyncMock()
        conn.fetchrow.return_value = row
        pool = _make_pool(conn)

        result = await clients_repo.get_by_telegram_id(pool, 12345)
        assert result is not None
        assert result.telegram_id == 12345


# ---------------------------------------------------------------------------
# leads repository
# ---------------------------------------------------------------------------

class TestLeadsRepository:
    async def test_create_idempotent_inserts_new_lead(self) -> None:
        client_id = uuid4()
        session_id = uuid4()
        ikey = "unique-key-1"
        row = _lead_row(client_id, session_id, ikey)

        conn = AsyncMock()
        conn.fetchrow.return_value = row  # First INSERT returns row
        pool = _make_pool(conn)

        result = await leads_repo.create_idempotent(
            pool=pool,
            client_id=client_id,
            session_id=session_id,
            preferences={"destination": "Таиланд"},
            idempotency_key=ikey,
        )

        assert result.idempotency_key == ikey
        assert result.client_id == client_id
        sql: str = conn.fetchrow.call_args_list[0][0][0]
        assert "ON CONFLICT" in sql
        assert "idempotency_key" in sql

    async def test_create_idempotent_returns_existing_on_conflict(self) -> None:
        """ON CONFLICT DO NOTHING → INSERT возвращает None → делается SELECT."""
        client_id = uuid4()
        session_id = uuid4()
        ikey = "duplicate-key"
        row = _lead_row(client_id, session_id, ikey)

        conn = AsyncMock()
        # First fetchrow (INSERT) returns None (conflict), second (SELECT) returns row
        conn.fetchrow.side_effect = [None, row]
        pool = _make_pool(conn)

        result = await leads_repo.create_idempotent(
            pool=pool,
            client_id=client_id,
            session_id=session_id,
            preferences={},
            idempotency_key=ikey,
        )

        assert result.idempotency_key == ikey
        assert conn.fetchrow.call_count == 2

    async def test_update_stage_executes_update_sql(self) -> None:
        lead_id = uuid4()
        row = _lead_row()
        row["id"] = lead_id
        row["status"] = "contacted"
        conn = AsyncMock()
        conn.fetchrow.return_value = row
        pool = _make_pool(conn)

        result = await leads_repo.update_stage(pool, lead_id, "contacted")

        assert result.status == "contacted"
        sql: str = conn.fetchrow.call_args[0][0]
        assert "UPDATE leads" in sql

    async def test_update_stage_raises_when_not_found(self) -> None:
        import asyncpg
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        pool = _make_pool(conn)

        with pytest.raises(asyncpg.NoDataFoundError):
            await leads_repo.update_stage(pool, uuid4(), "won")


# ---------------------------------------------------------------------------
# map_stage_to_lead_status
# ---------------------------------------------------------------------------

class TestMapStageToLeadStatus:
    @pytest.mark.parametrize("stage,expected", [
        ("cold", None),
        ("discovery", None),
        ("qualified", "new"),
        ("proposal", "proposal"),
        ("objection", "contacted"),
        ("closing", "won"),
        ("follow_up", "contacted"),
    ])
    def test_mapping(self, stage: str, expected) -> None:
        assert map_stage_to_lead_status(stage) == expected

    def test_all_stages_in_mapping(self) -> None:
        from src.decision import STAGES
        for stage in STAGES:
            assert stage in STAGE_TO_LEAD_STATUS, f"Stage {stage!r} not in STAGE_TO_LEAD_STATUS"

    def test_unknown_stage_returns_none(self) -> None:
        result = map_stage_to_lead_status("nonexistent")
        assert result is None
