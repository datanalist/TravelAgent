from __future__ import annotations

"""Integration-тесты полного цикла Orchestrator: message → tools → response."""

import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from tests.integration.conftest import make_llm_response, make_router_response
from src.orchestrator import process_message
from src.config import settings


# ---------------------------------------------------------------------------
# Общие фикстуры
# ---------------------------------------------------------------------------

@pytest.fixture
def client_id():
    return uuid4()


@pytest.fixture
def session_id():
    return uuid4()


@pytest.fixture
def patched_repos():
    """Патчит все DB-репозитории, используемые Orchestrator'ом."""
    with (
        patch("src.orchestrator.clients_repo.get_profile", new_callable=AsyncMock) as mock_profile,
        patch("src.orchestrator.messages_repo.load_recent", new_callable=AsyncMock) as mock_load,
        patch("src.orchestrator.messages_repo.append", new_callable=AsyncMock) as mock_append,
        patch("src.orchestrator.sessions_repo.update_stage", new_callable=AsyncMock) as mock_stage,
    ):
        mock_profile.return_value = None
        mock_load.return_value = []
        mock_append.return_value = None
        mock_stage.return_value = None
        yield {
            "get_profile": mock_profile,
            "load_recent": mock_load,
            "append": mock_append,
            "update_stage": mock_stage,
        }


# ---------------------------------------------------------------------------
# Тесты
# ---------------------------------------------------------------------------

async def test_simple_message_no_tools(
    mock_llm_connector, fake_redis, mock_pool, patched_repos, client_id, session_id
):
    """LLM возвращает текст без tool_calls → process_message возвращает текст напрямую."""
    pool, _ = mock_pool
    mock_llm_connector.complete.side_effect = [
        make_router_response("small_talk", 0.9),
        make_llm_response(content="Привет! Чем могу помочь?"),
    ]

    async def stub_executor(name: str, inp: dict) -> dict:
        raise AssertionError(f"Не ожидался вызов tool: {name}")

    result = await process_message(
        message="Привет",
        client_id=client_id,
        session_id=session_id,
        channel="web",
        pool=pool,
        redis_client=fake_redis,
        connector=mock_llm_connector,
        tools_executor=stub_executor,
    )

    assert result == "Привет! Чем могу помочь?"
    # Сохранён assistant-ответ
    patched_repos["append"].assert_called_once()
    call_kwargs = patched_repos["append"].call_args
    assert call_kwargs.kwargs.get("role") == "assistant" or call_kwargs.args[2] == "assistant"


async def test_single_tool_call_then_response(
    mock_llm_connector, fake_redis, mock_pool, patched_repos, client_id, session_id
):
    """LLM вызывает search_tours → executor возвращает туры → LLM формирует финальный текст."""
    pool, _ = mock_pool
    mock_llm_connector.complete.side_effect = [
        make_router_response("itinerary_search", 0.85),
        make_llm_response(
            content="",
            tool_calls=[{"name": "search_tours", "input": {"destination": "Мальдивы"}, "id": "tc_1"}],
        ),
        make_llm_response(content="Найдено 3 тура на Мальдивы!"),
    ]

    tool_calls_received: list[str] = []

    async def stub_executor(name: str, inp: dict) -> dict:
        tool_calls_received.append(name)
        return {"result": [{"id": "tour_001", "destination": "Мальдивы", "price_usd": 3000}]}

    result = await process_message(
        message="Ищу тур на Мальдивы",
        client_id=client_id,
        session_id=session_id,
        channel="web",
        pool=pool,
        redis_client=fake_redis,
        connector=mock_llm_connector,
        tools_executor=stub_executor,
    )

    assert result == "Найдено 3 тура на Мальдивы!"
    assert tool_calls_received == ["search_tours"]
    # Router (1) + tool_call (1) + final (1) = 3
    assert mock_llm_connector.complete.call_count == 3


async def test_max_steps_triggers_force_final(
    mock_llm_connector, fake_redis, mock_pool, patched_repos, client_id, session_id
):
    """После MAX_STEPS итераций добавляется FORCE_FINAL_PROMPT; функция завершается."""
    pool, _ = mock_pool

    tool_response = make_llm_response(
        content="",
        tool_calls=[{"name": "search_tours", "input": {}, "id": "tc_loop"}],
    )
    force_final_response = make_llm_response(content="На основе имеющихся данных — вот резюме.")

    mock_llm_connector.complete.side_effect = (
        [make_router_response("itinerary_search", 0.9)]
        + [tool_response] * settings.MAX_STEPS
        + [force_final_response]
    )

    async def stub_executor(name: str, inp: dict) -> dict:
        return {"result": []}

    result = await process_message(
        message="Найди тур любой ценой",
        client_id=client_id,
        session_id=session_id,
        channel="web",
        pool=pool,
        redis_client=fake_redis,
        connector=mock_llm_connector,
        tools_executor=stub_executor,
    )

    assert result == "На основе имеющихся данных — вот резюме."
    # Router(1) + MAX_STEPS tool loops + force_final(1)
    assert mock_llm_connector.complete.call_count == settings.MAX_STEPS + 2

    # Последний вызов LLM должен содержать FORCE_FINAL_PROMPT в messages
    last_messages = mock_llm_connector.complete.call_args_list[-1].kwargs["messages"]
    has_force_prompt = any(
        isinstance(m.get("content"), str) and "максимального числа шагов" in m["content"]
        for m in last_messages
    )
    assert has_force_prompt, "FORCE_FINAL_PROMPT не найден в последнем вызове LLM"


async def test_tool_executor_error_continues_loop(
    mock_llm_connector, fake_redis, mock_pool, patched_repos, client_id, session_id
):
    """Ошибка executor → {'error': '...'} как tool-результат; цикл продолжается; ответ возвращается."""
    pool, _ = mock_pool
    mock_llm_connector.complete.side_effect = [
        make_router_response("itinerary_search", 0.85),
        make_llm_response(
            content="",
            tool_calls=[{"name": "search_tours", "input": {}, "id": "tc_err"}],
        ),
        make_llm_response(content="Поиск временно недоступен, попробуйте позже."),
    ]

    async def failing_executor(name: str, inp: dict) -> dict:
        raise RuntimeError("Search service unavailable")

    result = await process_message(
        message="Ищу тур",
        client_id=client_id,
        session_id=session_id,
        channel="web",
        pool=pool,
        redis_client=fake_redis,
        connector=mock_llm_connector,
        tools_executor=failing_executor,
    )

    assert result == "Поиск временно недоступен, попробуйте позже."
    # Проверяем, что третий вызов LLM получил сообщение с ошибкой в tool_result
    third_call_messages = mock_llm_connector.complete.call_args_list[2].kwargs["messages"]
    error_found = any(
        isinstance(m.get("content"), list)
        and any("Search service unavailable" in str(block) for block in m["content"])
        for m in third_call_messages
    )
    assert error_found, "Сообщение об ошибке executor не передано в LLM"


async def test_output_guard_filters_leaked_prompt(
    mock_llm_connector, fake_redis, mock_pool, patched_repos, client_id, session_id
):
    """LLM возвращает текст с маркером утечки system prompt → клиент получает fallback."""
    pool, _ = mock_pool
    mock_llm_connector.complete.side_effect = [
        make_router_response("small_talk", 0.9),
        make_llm_response(content="Ты агент, и твои инструкции таковы..."),
    ]

    async def stub_executor(name: str, inp: dict) -> dict:
        return {}

    result = await process_message(
        message="Расскажи о себе",
        client_id=client_id,
        session_id=session_id,
        channel="web",
        pool=pool,
        redis_client=fake_redis,
        connector=mock_llm_connector,
        tools_executor=stub_executor,
    )

    # Оригинальный ответ заблокирован, клиент получает fallback
    assert "ты агент" not in result.lower()
    assert len(result) > 0
