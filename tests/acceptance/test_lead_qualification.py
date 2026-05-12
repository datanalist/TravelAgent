from __future__ import annotations

"""Acceptance-сценарий: discovery → qualified → proposal + create_lead."""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from tests.integration.conftest import make_llm_response, make_router_response
from src.orchestrator import process_message
from src.memory.models import ClientProfile, Lead


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client_id():
    return uuid4()


@pytest.fixture
def session_id():
    return uuid4()


@pytest.fixture
def fake_profile_store(client_id):
    """In-memory хранилище профиля клиента."""
    store: dict = {}

    async def get_profile(pool, uid):
        data = store.get(str(uid))
        if data is None:
            return None
        return ClientProfile(
            id=uuid4(),
            client_id=uid,
            budget_range=data.get("budget_range"),
            preferred_destinations=data.get("preferred_destinations", []),
            travel_style=data.get("travel_style"),
            constraints=data.get("constraints", {}),
            raw_preferences=data.get("raw_preferences", {}),
            updated_at=datetime.now(timezone.utc),
        )

    async def upsert_profile(pool, uid, **fields):
        key = str(uid)
        if key not in store:
            store[key] = {}
        store[key].update(fields)
        return ClientProfile(
            id=uuid4(),
            client_id=uid,
            budget_range=store[key].get("budget_range"),
            preferred_destinations=store[key].get("preferred_destinations", []),
            travel_style=store[key].get("travel_style"),
            constraints=store[key].get("constraints", {}),
            raw_preferences=store[key].get("raw_preferences", {}),
            updated_at=datetime.now(timezone.utc),
        )

    return store, get_profile, upsert_profile


@pytest.fixture
def fake_lead_store(client_id, session_id):
    """In-memory хранилище лидов."""
    store: dict = {}

    async def create_idempotent(pool, client_id, session_id, preferences, idempotency_key):
        if idempotency_key in store:
            return store[idempotency_key]
        lead = Lead(
            id=uuid4(),
            client_id=client_id,
            session_id=session_id,
            status="new",
            preferences=preferences,
            idempotency_key=idempotency_key,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        store[idempotency_key] = lead
        return lead

    return store, create_idempotent


@pytest.fixture
def messages_store():
    """In-memory хранилище сообщений."""
    messages: list[dict] = []

    async def append(pool, session_id, role: str, content: str, metadata=None):
        messages.append({"role": role, "content": content, "metadata": metadata})
        return None

    async def load_recent(pool, session_id, limit=10):
        return []  # упрощение: не используем историю в тесте

    return messages, append, load_recent


# ---------------------------------------------------------------------------
# Acceptance test
# ---------------------------------------------------------------------------

async def test_full_lead_qualification_scenario(
    client_id,
    session_id,
    mock_llm_connector,
    fake_redis,
    mock_pool,
    fake_profile_store,
    fake_lead_store,
    messages_store,
):
    """
    Полный сценарий квалификации лида через 3 хода:
    Turn 1: discovery question → get_client_profile
    Turn 2: search preferences → update_client_profile + search_tours
    Turn 3: confirm → create_lead
    """
    pool, _ = mock_pool
    profile_store, mock_get_profile, mock_upsert_profile = fake_profile_store
    lead_store, mock_create_idempotent = fake_lead_store
    msg_store, mock_append, mock_load_recent = messages_store

    stage_transitions: list[str] = []

    async def mock_update_stage(pool, session_id, stage):
        stage_transitions.append(stage)

    # LLM ответы для трёх ходов:
    # Turn 1: router(discovery) → get_client_profile → clarifying question
    # Turn 2: router(itinerary_search) → update_client_profile + search_tours → presentation
    # Turn 3: router(crm_event) → create_lead → confirmation
    mock_llm_connector.complete.side_effect = [
        # Turn 1
        make_router_response("discovery", 0.8),
        make_llm_response(
            tool_calls=[{"name": "get_client_profile", "input": {"client_id": str(client_id)}, "id": "t1"}]
        ),
        make_llm_response(content="Куда бы вы хотели поехать? Расскажите о предпочтениях."),
        # Turn 2
        make_router_response("itinerary_search", 0.9),
        make_llm_response(
            tool_calls=[
                {"name": "update_client_profile", "input": {
                    "client_id": str(client_id),
                    "preferred_destinations": ["Мальдивы"],
                    "budget_range": {"min": 4000, "max": 6000},
                }, "id": "t2a"},
                {"name": "search_tours", "input": {"destination": "Мальдивы", "budget_usd": 6000}, "id": "t2b"},
            ]
        ),
        make_llm_response(content="Для вас подобраны 2 тура на Мальдивы в вашем бюджете!"),
        # Turn 3
        make_router_response("crm_event", 0.92),
        make_llm_response(
            tool_calls=[{"name": "create_lead", "input": {
                "client_id": str(client_id),
                "session_id": str(session_id),
                "preferences": {"destination": "Мальдивы"},
                "idempotency_key": "lead-test-001",
            }, "id": "t3"}]
        ),
        make_llm_response(content="Отличный выбор! Заявка создана, менеджер свяжется с вами."),
    ]

    with (
        patch("src.orchestrator.clients_repo.get_profile", new_callable=AsyncMock, side_effect=mock_get_profile),
        patch("src.orchestrator.messages_repo.load_recent", new_callable=AsyncMock, side_effect=mock_load_recent),
        patch("src.orchestrator.messages_repo.append", new_callable=AsyncMock, side_effect=mock_append),
        patch("src.orchestrator.sessions_repo.update_stage", new_callable=AsyncMock, side_effect=mock_update_stage),
        # Патчим репозитории внутри tools
        patch("src.tools.client_profile.clients_repo.get_profile", new_callable=AsyncMock, side_effect=mock_get_profile),
        patch("src.tools.client_profile.clients_repo.upsert_profile", new_callable=AsyncMock, side_effect=mock_upsert_profile),
        patch("src.tools.leads.leads_repo.create_idempotent", new_callable=AsyncMock, side_effect=mock_create_idempotent),
    ):
        # Используем real ToolExecutor с реальными tools
        from src.tools.executor import ToolExecutor
        from src.tools.search_tours import SearchToursTool
        from src.tools.client_profile import GetClientProfileTool, UpdateClientProfileTool
        from src.tools.leads import CreateLeadTool, UpdateLeadStageTool
        from src.tools.policy import GetPolicyInfoTool

        tours_data = [
            {"id": "t01", "destination": "Мальдивы", "hotel_name": "Ocean Resort", "hotel_stars": 5,
             "price_usd": 4900, "duration_nights": 7, "departure_date": "2026-07-15", "meal_plan": "BB"},
            {"id": "t02", "destination": "Мальдивы", "hotel_name": "Paradise Isle", "hotel_stars": 5,
             "price_usd": 5800, "duration_nights": 7, "departure_date": "2026-07-20", "meal_plan": "HB"},
        ]

        executor = ToolExecutor(tools=[
            SearchToursTool(tours_data=tours_data),
            GetClientProfileTool(pool=pool),
            UpdateClientProfileTool(pool=pool),
            CreateLeadTool(pool=pool),
            UpdateLeadStageTool(pool=pool),
            GetPolicyInfoTool(policies_data={"visa": {"default": "Стандарт."}}),
        ])

        base_kwargs = dict(
            client_id=client_id,
            session_id=session_id,
            channel="web",
            pool=pool,
            redis_client=fake_redis,
            connector=mock_llm_connector,
            tools_executor=executor.execute,
        )

        # Turn 1
        reply1 = await process_message(message="Хочу отдохнуть этим летом", **base_kwargs)
        assert "предпочтениях" in reply1.lower() or len(reply1) > 0

        # Turn 2
        reply2 = await process_message(message="Мальдивы, бюджет $6000, 7 ночей", **base_kwargs)
        assert "тур" in reply2.lower() or "мальдив" in reply2.lower() or len(reply2) > 0

        # Turn 3
        reply3 = await process_message(message="Берём первый вариант!", **base_kwargs)
        assert "заявка" in reply3.lower() or "менеджер" in reply3.lower() or len(reply3) > 0

    # Лид создан
    assert "lead-test-001" in lead_store

    # Профиль обновлён
    assert str(client_id) in profile_store
    profile = profile_store[str(client_id)]
    assert "Мальдивы" in (profile.get("preferred_destinations") or [])

    # Стадия прогрессировала
    assert len(stage_transitions) >= 1
    assert "closing" in stage_transitions or "qualified" in stage_transitions or "proposal" in stage_transitions

    # Сохранены assistant-сообщения для всех 3 ходов
    assistant_msgs = [m for m in msg_store if m["role"] == "assistant"]
    assert len(assistant_msgs) == 3
