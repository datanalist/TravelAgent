from __future__ import annotations

import pytest
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4, UUID

from src.tools.base import ToolResult
from src.tools.search_tours import SearchToursTool
from src.tools.client_profile import GetClientProfileTool, UpdateClientProfileTool
from src.tools.leads import CreateLeadTool, UpdateLeadStageTool
from src.tools.policy import GetPolicyInfoTool
from src.tools.executor import ToolExecutor
from src.memory.models import ClientProfile, Lead


# ---------------------------------------------------------------------------
# Тестовые данные
# ---------------------------------------------------------------------------

_TOURS = [
    {"id": "1", "destination": "Таиланд Бангкок", "price_usd": 1200, "hotel_stars": 4, "meal_plan": "BB", "duration_nights": 7, "departure_date": "2026-07-01"},
    {"id": "2", "destination": "Таиланд Пхукет", "price_usd": 1500, "hotel_stars": 5, "meal_plan": "AI", "duration_nights": 10, "departure_date": "2026-07-10"},
    {"id": "3", "destination": "Дубай", "price_usd": 2000, "hotel_stars": 5, "meal_plan": "BB", "duration_nights": 7, "departure_date": "2026-08-01"},
    {"id": "4", "destination": "Мальдивы", "price_usd": 3500, "hotel_stars": 5, "meal_plan": "AI", "duration_nights": 10, "departure_date": "2026-09-01"},
    {"id": "5", "destination": "Греция Крит", "price_usd": 900, "hotel_stars": 3, "meal_plan": "HB", "duration_nights": 7, "departure_date": "2026-06-15"},
    {"id": "6", "destination": "Турция Анталья", "price_usd": 800, "hotel_stars": 4, "meal_plan": "AI", "duration_nights": 7, "departure_date": "2026-06-20"},
    {"id": "7", "destination": "Египет Хургада", "price_usd": 700, "hotel_stars": 4, "meal_plan": "AI", "duration_nights": 7, "departure_date": "2026-06-25"},
    {"id": "8", "destination": "Испания Барселона", "price_usd": 1100, "hotel_stars": 4, "meal_plan": "BB", "duration_nights": 6, "departure_date": "2026-07-05"},
    {"id": "9", "destination": "Италия Рим", "price_usd": 1300, "hotel_stars": 4, "meal_plan": "BB", "duration_nights": 5, "departure_date": "2026-07-12"},
    {"id": "10", "destination": "Мексика Канкун", "price_usd": 2500, "hotel_stars": 5, "meal_plan": "AI", "duration_nights": 14, "departure_date": "2026-12-01"},
]

_POLICIES = {
    "visa": {
        "default": "Для большинства направлений требуется виза.",
        "destinations": {
            "Таиланд": "Безвизовый въезд до 30 дней.",
        },
    },
    "insurance": {
        "default": "Страхование включено в стоимость тура.",
        "premium": "Расширенная страховка за доплату.",
    },
    "cancellation": {
        "default": "Более 30 дней — возврат 100%.",
        "flexible": "Гибкие условия для Flex-туров.",
    },
}


# ---------------------------------------------------------------------------
# SearchToursTool
# ---------------------------------------------------------------------------

class TestSearchToursTool:
    def setup_method(self) -> None:
        self.tool = SearchToursTool(tours_data=_TOURS)

    async def test_search_by_destination_partial_match(self) -> None:
        result = await self.tool.execute(destination="Таиланд")
        assert result.success
        assert len(result.data) == 2
        for tour in result.data:
            assert "таиланд" in tour["destination"].lower()

    async def test_search_by_destination_no_match(self) -> None:
        result = await self.tool.execute(destination="Антарктида")
        assert result.success
        assert result.data == []

    async def test_filter_by_budget_usd(self) -> None:
        result = await self.tool.execute(budget_usd=1000.0)
        assert result.success
        for tour in result.data:
            assert tour["price_usd"] <= 1000

    async def test_filter_by_hotel_stars(self) -> None:
        result = await self.tool.execute(hotel_stars=5)
        assert result.success
        for tour in result.data:
            assert tour["hotel_stars"] == 5

    async def test_max_5_results(self) -> None:
        result = await self.tool.execute()  # no filters → all 10 tours → capped at 5
        assert result.success
        assert len(result.data) <= 5

    async def test_results_sorted_by_price(self) -> None:
        result = await self.tool.execute()
        prices = [t["price_usd"] for t in result.data]
        assert prices == sorted(prices)

    async def test_filter_by_meal_plan(self) -> None:
        result = await self.tool.execute(meal_plan="AI")
        assert result.success
        for tour in result.data:
            assert tour["meal_plan"] == "AI"

    async def test_combined_filters(self) -> None:
        result = await self.tool.execute(destination="Таиланд", hotel_stars=5)
        assert result.success
        for tour in result.data:
            assert "таиланд" in tour["destination"].lower()
            assert tour["hotel_stars"] == 5

    async def test_filter_by_departure_date_range(self) -> None:
        result = await self.tool.execute(
            departure_date_from="2026-07-01",
            departure_date_to="2026-07-31",
        )
        assert result.success
        for tour in result.data:
            dep = date.fromisoformat(tour["departure_date"])
            assert date(2026, 7, 1) <= dep <= date(2026, 7, 31)

    async def test_duration_nights_with_tolerance(self) -> None:
        # 7 nights ± 2 tolerance → accept 5..9
        result = await self.tool.execute(duration_nights=7)
        assert result.success
        for tour in result.data:
            assert abs(tour["duration_nights"] - 7) <= 2


# ---------------------------------------------------------------------------
# GetClientProfileTool
# ---------------------------------------------------------------------------

def _make_pool_with_conn() -> tuple[MagicMock, AsyncMock]:
    from tests.conftest import _AsyncCM
    pool = MagicMock()
    conn = AsyncMock()
    pool.acquire.return_value = _AsyncCM(conn)
    return pool, conn


def _make_profile(client_id: UUID) -> ClientProfile:
    return ClientProfile(
        id=uuid4(),
        client_id=client_id,
        budget_range={"min": 1000, "max": 3000},
        preferred_destinations=["Таиланд"],
        travel_style="beach",
        constraints={},
        raw_preferences={},
        updated_at=datetime(2026, 1, 1),
    )


class TestGetClientProfileTool:
    async def test_returns_profile_when_exists(self) -> None:
        client_id = uuid4()
        profile = _make_profile(client_id)
        pool, _ = _make_pool_with_conn()

        with pytest.MonkeyPatch().context() as mp:
            import src.tools.client_profile as mod
            mp.setattr(
                mod.clients_repo,
                "get_profile",
                AsyncMock(return_value=profile),
            )
            tool = GetClientProfileTool(pool)
            result = await tool.execute(client_id=str(client_id))

        assert result.success
        assert result.data["client_id"] == str(client_id)
        assert result.data["budget_range"] == {"min": 1000, "max": 3000}
        assert result.data["preferred_destinations"] == ["Таиланд"]

    async def test_returns_empty_dict_when_no_profile(self) -> None:
        client_id = uuid4()
        pool, _ = _make_pool_with_conn()

        with pytest.MonkeyPatch().context() as mp:
            import src.tools.client_profile as mod
            mp.setattr(mod.clients_repo, "get_profile", AsyncMock(return_value=None))
            tool = GetClientProfileTool(pool)
            result = await tool.execute(client_id=str(client_id))

        assert result.success
        assert result.data["client_id"] == str(client_id)
        assert result.data["budget_range"] is None
        assert result.data["preferred_destinations"] == []

    async def test_returns_error_on_exception(self) -> None:
        client_id = uuid4()
        pool, _ = _make_pool_with_conn()

        with pytest.MonkeyPatch().context() as mp:
            import src.tools.client_profile as mod
            mp.setattr(
                mod.clients_repo,
                "get_profile",
                AsyncMock(side_effect=RuntimeError("DB error")),
            )
            tool = GetClientProfileTool(pool)
            result = await tool.execute(client_id=str(client_id))

        assert not result.success
        assert "DB error" in result.error


class TestUpdateClientProfileTool:
    async def test_update_calls_upsert_with_fields(self) -> None:
        client_id = uuid4()
        updated_profile = _make_profile(client_id)
        pool, _ = _make_pool_with_conn()

        with pytest.MonkeyPatch().context() as mp:
            import src.tools.client_profile as mod
            mock_upsert = AsyncMock(return_value=updated_profile)
            mp.setattr(mod.clients_repo, "upsert_profile", mock_upsert)
            tool = UpdateClientProfileTool(pool)
            result = await tool.execute(
                client_id=str(client_id),
                travel_style="luxury",
                preferred_destinations=["Дубай"],
            )

        assert result.success
        mock_upsert.assert_called_once()
        call_kwargs = mock_upsert.call_args
        assert call_kwargs.kwargs.get("travel_style") == "luxury"
        assert call_kwargs.kwargs.get("preferred_destinations") == ["Дубай"]

    async def test_no_fields_returns_error(self) -> None:
        pool, _ = _make_pool_with_conn()
        tool = UpdateClientProfileTool(pool)
        result = await tool.execute(client_id=str(uuid4()))
        assert not result.success
        assert "поля" in result.error.lower() or "field" in result.error.lower()


# ---------------------------------------------------------------------------
# CreateLeadTool
# ---------------------------------------------------------------------------

def _make_lead(client_id: UUID, session_id: UUID, ikey: str) -> Lead:
    return Lead(
        id=uuid4(),
        client_id=client_id,
        session_id=session_id,
        status="new",
        preferences={"destination": "Таиланд"},
        idempotency_key=ikey,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )


class TestCreateLeadTool:
    async def test_create_lead_returns_lead_data(self) -> None:
        client_id = uuid4()
        session_id = uuid4()
        ikey = "key-123"
        lead = _make_lead(client_id, session_id, ikey)
        pool, _ = _make_pool_with_conn()

        with pytest.MonkeyPatch().context() as mp:
            import src.tools.leads as mod
            mp.setattr(mod.leads_repo, "create_idempotent", AsyncMock(return_value=lead))
            tool = CreateLeadTool(pool)
            result = await tool.execute(
                client_id=str(client_id),
                session_id=str(session_id),
                preferences={"destination": "Таиланд"},
                idempotency_key=ikey,
            )

        assert result.success
        assert result.data["lead_id"] == str(lead.id)
        assert result.data["status"] == "new"

    async def test_idempotency_same_key_same_lead(self) -> None:
        """Повторный вызов с тем же ключом → тот же lead_id."""
        client_id = uuid4()
        session_id = uuid4()
        ikey = "idempotent-key"
        lead = _make_lead(client_id, session_id, ikey)
        pool, _ = _make_pool_with_conn()

        with pytest.MonkeyPatch().context() as mp:
            import src.tools.leads as mod
            # Оба вызова возвращают один и тот же lead
            mp.setattr(mod.leads_repo, "create_idempotent", AsyncMock(return_value=lead))
            tool = CreateLeadTool(pool)
            r1 = await tool.execute(
                client_id=str(client_id),
                session_id=str(session_id),
                preferences={},
                idempotency_key=ikey,
            )
            r2 = await tool.execute(
                client_id=str(client_id),
                session_id=str(session_id),
                preferences={},
                idempotency_key=ikey,
            )

        assert r1.data["lead_id"] == r2.data["lead_id"]


class TestUpdateLeadStageTool:
    async def test_update_valid_status(self) -> None:
        lead_id = uuid4()
        lead = Lead(
            id=lead_id,
            client_id=uuid4(),
            session_id=uuid4(),
            status="contacted",
            preferences={},
            idempotency_key="k",
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 1),
        )
        pool, _ = _make_pool_with_conn()

        with pytest.MonkeyPatch().context() as mp:
            import src.tools.leads as mod
            mp.setattr(mod.leads_repo, "update_stage", AsyncMock(return_value=lead))
            tool = UpdateLeadStageTool(pool)
            result = await tool.execute(lead_id=str(lead_id), status="contacted")

        assert result.success
        assert result.data["status"] == "contacted"

    async def test_update_invalid_status_returns_error(self) -> None:
        pool, _ = _make_pool_with_conn()
        tool = UpdateLeadStageTool(pool)
        result = await tool.execute(lead_id=str(uuid4()), status="invalid_status")
        assert not result.success
        assert "invalid_status" in result.error


# ---------------------------------------------------------------------------
# GetPolicyInfoTool
# ---------------------------------------------------------------------------

class TestGetPolicyInfoTool:
    def setup_method(self) -> None:
        self.tool = GetPolicyInfoTool(policies_data=_POLICIES)

    async def test_visa_policy_no_destination(self) -> None:
        result = await self.tool.execute(policy_type="visa")
        assert result.success
        assert result.data["policy_type"] == "visa"
        assert "info" in result.data

    async def test_visa_policy_with_destination_thailand(self) -> None:
        result = await self.tool.execute(policy_type="visa", destination="Таиланд")
        assert result.success
        assert "безвизовый" in result.data["info"].lower()

    async def test_visa_policy_unknown_destination_returns_default(self) -> None:
        result = await self.tool.execute(policy_type="visa", destination="Антарктида")
        assert result.success
        assert result.data["info"] == _POLICIES["visa"]["default"]
        assert "note" in result.data

    async def test_insurance_policy(self) -> None:
        result = await self.tool.execute(policy_type="insurance")
        assert result.success
        assert "premium" in result.data

    async def test_unknown_policy_type_returns_error(self) -> None:
        result = await self.tool.execute(policy_type="unicorn")
        assert not result.success
        assert "unicorn" in result.error

    async def test_cancellation_policy_has_flexible(self) -> None:
        result = await self.tool.execute(policy_type="cancellation")
        assert result.success
        assert "flexible" in result.data


# ---------------------------------------------------------------------------
# ToolExecutor
# ---------------------------------------------------------------------------

class TestToolExecutor:
    async def test_executes_known_tool(self) -> None:
        tool = SearchToursTool(tours_data=_TOURS)
        executor = ToolExecutor([tool])
        result = await executor.execute("search_tours", {"destination": "Таиланд"})
        assert "result" in result

    async def test_unknown_tool_returns_error(self) -> None:
        executor = ToolExecutor([])
        result = await executor.execute("nonexistent_tool", {})
        assert "error" in result
        assert "nonexistent_tool" in result["error"]

    async def test_tool_failure_returns_error(self) -> None:
        tool = GetPolicyInfoTool(policies_data=_POLICIES)
        executor = ToolExecutor([tool])
        result = await executor.execute("get_policy_info", {"policy_type": "invalid"})
        assert "error" in result

    def test_available_tool_names(self) -> None:
        tool = SearchToursTool(tours_data=_TOURS)
        executor = ToolExecutor([tool])
        assert "search_tours" in executor.available_tool_names
