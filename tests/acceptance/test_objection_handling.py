from __future__ import annotations

"""Acceptance-сценарий: возражение → поиск альтернатив с меньшим бюджетом."""

import pytest
from unittest.mock import AsyncMock, patch, call
from uuid import uuid4

from tests.integration.conftest import make_llm_response, make_router_response
from src.orchestrator import process_message


@pytest.fixture
def client_id():
    return uuid4()


@pytest.fixture
def session_id():
    return uuid4()


async def test_objection_to_alternative_scenario(
    client_id,
    session_id,
    mock_llm_connector,
    fake_redis,
    mock_pool,
):
    """
    Turn 1: LLM предлагает туры (search_tours с budget_usd=8000)
    Turn 2: клиент говорит "дороговато" → search_tours с меньшим budget_usd
    Проверяем: search_tours вызван дважды, второй вызов с меньшим бюджетом.
    """
    pool, _ = mock_pool

    # Запись реальных вызовов search_tours
    search_calls: list[dict] = []

    original_search = None  # будет установлен после импорта

    mock_llm_connector.complete.side_effect = [
        # Turn 1: initial search
        make_router_response("itinerary_search", 0.9),
        make_llm_response(
            tool_calls=[{"name": "search_tours", "input": {"destination": "Мальдивы", "budget_usd": 8000}, "id": "s1"}]
        ),
        make_llm_response(content="Для вас есть отличные туры на Мальдивы от $5000!"),
        # Turn 2: objection → cheaper search
        make_router_response("objection", 0.88),
        make_llm_response(
            tool_calls=[{"name": "search_tours", "input": {"destination": "Мальдивы", "budget_usd": 4000}, "id": "s2"}]
        ),
        make_llm_response(content="Нашёл более бюджетные варианты на Мальдивы до $4000."),
    ]

    tours_data = [
        {"id": "t01", "destination": "Мальдивы", "hotel_name": "Standard Resort", "hotel_stars": 4,
         "price_usd": 3500, "duration_nights": 7, "departure_date": "2026-07-01", "meal_plan": "BB"},
        {"id": "t02", "destination": "Мальдивы", "hotel_name": "Luxury Resort", "hotel_stars": 5,
         "price_usd": 7000, "duration_nights": 7, "departure_date": "2026-07-10", "meal_plan": "HB"},
    ]

    with (
        patch("src.orchestrator.clients_repo.get_profile", new_callable=AsyncMock, return_value=None),
        patch("src.orchestrator.messages_repo.load_recent", new_callable=AsyncMock, return_value=[]),
        patch("src.orchestrator.messages_repo.append", new_callable=AsyncMock, return_value=None),
        patch("src.orchestrator.sessions_repo.update_stage", new_callable=AsyncMock, return_value=None),
    ):
        from src.tools.executor import ToolExecutor
        from src.tools.search_tours import SearchToursTool
        from src.tools.policy import GetPolicyInfoTool

        # Оборачиваем SearchToursTool для отслеживания вызовов
        real_search = SearchToursTool(tours_data=tours_data)

        class TrackingSearchTool(SearchToursTool):
            name = "search_tours"

            async def execute(self, **kwargs):
                search_calls.append(dict(kwargs))
                return await real_search.execute(**kwargs)

        executor = ToolExecutor(tools=[
            TrackingSearchTool(tours_data=tours_data),
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

        # Turn 1: первоначальный поиск
        reply1 = await process_message(message="Ищу тур на Мальдивы", **base_kwargs)
        assert len(reply1) > 0

        # Turn 2: возражение по цене
        reply2 = await process_message(message="Это дороговато, есть что-то дешевле?", **base_kwargs)
        assert len(reply2) > 0

    # search_tours вызван дважды
    assert len(search_calls) == 2, f"Ожидалось 2 вызова search_tours, получено: {len(search_calls)}"

    # Второй вызов имеет меньший budget_usd
    first_budget = search_calls[0].get("budget_usd")
    second_budget = search_calls[1].get("budget_usd")

    assert first_budget is not None, "Первый вызов не содержит budget_usd"
    assert second_budget is not None, "Второй вызов не содержит budget_usd"
    assert second_budget < first_budget, (
        f"Ожидалось: второй budget_usd ({second_budget}) < первый ({first_budget})"
    )


async def test_objection_stage_transition(
    client_id,
    session_id,
    mock_llm_connector,
    fake_redis,
    mock_pool,
):
    """Из stage=proposal при intent=objection происходит переход в objection."""
    pool, _ = mock_pool

    # Устанавливаем начальную стадию через Redis
    from src.memory import redis_session
    await redis_session.set_stage(fake_redis, session_id, "proposal")

    stage_after: list[str] = []

    async def capture_stage(pool, session_id, stage):
        stage_after.append(stage)

    mock_llm_connector.complete.side_effect = [
        make_router_response("objection", 0.9),
        make_llm_response(
            tool_calls=[{"name": "search_tours", "input": {"budget_usd": 3000}, "id": "obj1"}]
        ),
        make_llm_response(content="Вот альтернативы по более низкой цене."),
    ]

    with (
        patch("src.orchestrator.clients_repo.get_profile", new_callable=AsyncMock, return_value=None),
        patch("src.orchestrator.messages_repo.load_recent", new_callable=AsyncMock, return_value=[]),
        patch("src.orchestrator.messages_repo.append", new_callable=AsyncMock, return_value=None),
        patch("src.orchestrator.sessions_repo.update_stage", new_callable=AsyncMock, side_effect=capture_stage),
    ):
        from src.tools.executor import ToolExecutor
        from src.tools.search_tours import SearchToursTool

        executor = ToolExecutor(tools=[
            SearchToursTool(tours_data=[
                {"id": "t1", "destination": "Бюджет", "hotel_name": "Budget Hotel", "hotel_stars": 3,
                 "price_usd": 2500, "duration_nights": 7, "departure_date": "2026-08-01", "meal_plan": "BB"},
            ]),
        ])

        await process_message(
            message="Слишком дорого!",
            client_id=client_id,
            session_id=session_id,
            channel="web",
            pool=pool,
            redis_client=fake_redis,
            connector=mock_llm_connector,
            tools_executor=executor.execute,
        )

    assert "objection" in stage_after, f"Переход в objection не произошёл: {stage_after}"
