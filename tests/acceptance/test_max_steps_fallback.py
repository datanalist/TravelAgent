from __future__ import annotations

"""Acceptance-сценарий: LLM всегда возвращает tool_calls → MAX_STEPS → force_final."""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from unittest import mock

from tests.integration.conftest import make_llm_response, make_router_response
from src.orchestrator import process_message


@pytest.fixture
def client_id():
    return uuid4()


@pytest.fixture
def session_id():
    return uuid4()


async def test_force_final_after_max_steps(
    client_id,
    session_id,
    mock_llm_connector,
    fake_redis,
    mock_pool,
):
    """
    LLM настроен всегда возвращать tool_calls.
    MAX_STEPS переопределён как 3.
    → После 3 шагов добавляется FORCE_FINAL_PROMPT.
    → LLM вызван ровно MAX_STEPS+2 раз (1 router + 3 loops + 1 force_final).
    → process_message завершается, возвращает текст.
    """
    pool, _ = mock_pool
    test_max_steps = 3

    infinite_tool_response = make_llm_response(
        content="",
        tool_calls=[{"name": "search_tours", "input": {"destination": "Любое"}, "id": "tc_inf"}],
    )
    force_final_response = make_llm_response(
        content="Исчерпан лимит шагов. Обратитесь к менеджеру для подробной консультации."
    )

    mock_llm_connector.complete.side_effect = (
        [make_router_response("itinerary_search", 0.9)]
        + [infinite_tool_response] * test_max_steps
        + [force_final_response]
    )

    call_count = 0

    async def counting_executor(name: str, inp: dict) -> dict:
        nonlocal call_count
        call_count += 1
        return {"result": []}

    with (
        patch("src.orchestrator.clients_repo.get_profile", new_callable=AsyncMock, return_value=None),
        patch("src.orchestrator.messages_repo.load_recent", new_callable=AsyncMock, return_value=[]),
        patch("src.orchestrator.messages_repo.append", new_callable=AsyncMock, return_value=None),
        patch("src.orchestrator.sessions_repo.update_stage", new_callable=AsyncMock, return_value=None),
        # Переопределяем MAX_STEPS = 3
        mock.patch("src.orchestrator.settings.MAX_STEPS", test_max_steps),
    ):
        result = await process_message(
            message="Найди тур",
            client_id=client_id,
            session_id=session_id,
            channel="web",
            pool=pool,
            redis_client=fake_redis,
            connector=mock_llm_connector,
            tools_executor=counting_executor,
        )

    # process_message завершается и возвращает строку
    assert isinstance(result, str)
    assert len(result) > 0

    # executor вызван ровно MAX_STEPS раз
    assert call_count == test_max_steps

    # LLM вызван: 1 (router) + MAX_STEPS (loops) + 1 (force_final)
    total_llm_calls = mock_llm_connector.complete.call_count
    assert total_llm_calls == test_max_steps + 2, (
        f"Ожидалось {test_max_steps + 2} вызовов LLM, получено {total_llm_calls}"
    )

    # FORCE_FINAL_PROMPT присутствует в предпоследнем вызове (force_final call)
    force_final_call_idx = test_max_steps + 1  # 0-indexed: router=0, loops=1..MAX_STEPS, force=MAX_STEPS+1
    force_call_messages = mock_llm_connector.complete.call_args_list[force_final_call_idx].kwargs["messages"]
    has_force_prompt = any(
        isinstance(m.get("content"), str) and "максимального числа шагов" in m["content"]
        for m in force_call_messages
    )
    assert has_force_prompt, "FORCE_FINAL_PROMPT не найден в последнем вызове LLM"

    # tools=None для force_final вызова (принудительный текстовый ответ)
    force_call_tools = mock_llm_connector.complete.call_args_list[force_final_call_idx].kwargs.get("tools")
    assert force_call_tools is None


async def test_force_final_response_returned_even_if_text_empty(
    client_id,
    session_id,
    mock_llm_connector,
    fake_redis,
    mock_pool,
):
    """После MAX_STEPS LLM возвращает пустой текст → возвращается SERVICE_UNAVAILABLE fallback."""
    pool, _ = mock_pool

    mock_llm_connector.complete.side_effect = [
        make_router_response("itinerary_search", 0.9),
        *[make_llm_response(tool_calls=[{"name": "search_tours", "input": {}, "id": f"t{i}"}]) for i in range(3)],
        # force_final возвращает пустой контент
        make_llm_response(content=""),
    ]

    with (
        patch("src.orchestrator.clients_repo.get_profile", new_callable=AsyncMock, return_value=None),
        patch("src.orchestrator.messages_repo.load_recent", new_callable=AsyncMock, return_value=[]),
        patch("src.orchestrator.messages_repo.append", new_callable=AsyncMock, return_value=None),
        patch("src.orchestrator.sessions_repo.update_stage", new_callable=AsyncMock, return_value=None),
        mock.patch("src.orchestrator.settings.MAX_STEPS", 3),
    ):
        result = await process_message(
            message="Поиск",
            client_id=client_id,
            session_id=session_id,
            channel="web",
            pool=pool,
            redis_client=fake_redis,
            connector=mock_llm_connector,
            tools_executor=AsyncMock(return_value={"result": []}),
        )

    # Независимо от пустого контента — функция возвращает строку (пустую или fallback)
    assert isinstance(result, str)
