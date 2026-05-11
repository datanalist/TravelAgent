from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from src.llm.providers.base import LLMResponse
from src.orchestrator import process_message


def _make_connector(responses: list[LLMResponse]) -> MagicMock:
    connector = MagicMock()
    connector._config.temperature_toolcall = 0.1
    connector._config.temperature_generation = 0.5
    connector.complete = AsyncMock(side_effect=responses)
    return connector


def _tool_response(tool_name: str = "search_tours", tool_id: str = "t1") -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=[{"id": tool_id, "name": tool_name, "input": {"destination": "Таиланд"}}],
        usage={},
        model="test",
    )


def _text_response(text: str = "Финальный ответ") -> LLMResponse:
    return LLMResponse(content=text, tool_calls=[], usage={}, model="test")


def _patch_orchestrator_deps(mocker, *, stage: str = "cold") -> None:
    mocker.patch("src.orchestrator.clients_repo.get_profile", return_value=None)
    mocker.patch("src.orchestrator.redis_session.get_summary", return_value=None)
    mocker.patch("src.orchestrator.redis_session.get_stage", return_value=stage)
    mocker.patch("src.orchestrator.redis_session.set_stage", return_value=None)
    mocker.patch("src.orchestrator.messages_repo.load_recent", return_value=[])
    mocker.patch("src.orchestrator.messages_repo.append", return_value=None)
    mocker.patch("src.orchestrator.sessions_repo.update_stage", return_value=None)
    mocker.patch("src.orchestrator.classify_intent", return_value=("discovery", 0.9))
    mocker.patch("src.orchestrator.build_system_prompt", return_value="system prompt")
    mocker.patch(
        "src.orchestrator.build_messages",
        return_value=[{"role": "user", "content": "test"}],
    )
    mocker.patch("src.orchestrator.get_tools_for", return_value=[])


async def test_process_message_no_tool_calls_returns_content(mocker) -> None:
    """Без tool_calls — возвращается контент LLM напрямую."""
    _patch_orchestrator_deps(mocker)
    connector = _make_connector([_text_response("Привет!")])
    tools_executor = AsyncMock()

    result = await process_message(
        message="Привет",
        client_id=uuid4(),
        session_id=uuid4(),
        channel="telegram",
        pool=MagicMock(),
        redis_client=MagicMock(),
        connector=connector,
        tools_executor=tools_executor,
    )

    assert result == "Привет!"
    tools_executor.assert_not_called()


async def test_process_message_tool_calls_executor_invoked(mocker) -> None:
    """Если LLM вернул tool_calls — executor вызывается с правильными параметрами."""
    _patch_orchestrator_deps(mocker)
    connector = _make_connector([_tool_response("search_tours"), _text_response("Нашел туры!")])
    tools_executor = AsyncMock(return_value={"result": [{"tour": "test_tour"}]})

    result = await process_message(
        message="Хочу в Таиланд",
        client_id=uuid4(),
        session_id=uuid4(),
        channel="telegram",
        pool=MagicMock(),
        redis_client=MagicMock(),
        connector=connector,
        tools_executor=tools_executor,
    )

    assert result == "Нашел туры!"
    tools_executor.assert_called_once_with("search_tours", {"destination": "Таиланд"})


async def test_process_message_executor_exception_continues_loop(mocker) -> None:
    """Исключение в executor → error dict добавляется, цикл продолжается."""
    _patch_orchestrator_deps(mocker)
    connector = _make_connector([_tool_response("broken_tool"), _text_response("Ответ несмотря на ошибку")])
    tools_executor = AsyncMock(side_effect=RuntimeError("tool blew up"))

    result = await process_message(
        message="test",
        client_id=uuid4(),
        session_id=uuid4(),
        channel="telegram",
        pool=MagicMock(),
        redis_client=MagicMock(),
        connector=connector,
        tools_executor=tools_executor,
    )

    assert result == "Ответ несмотря на ошибку"


async def test_process_message_max_steps_triggers_force_final(mocker) -> None:
    """После MAX_STEPS итераций с tool_calls → добавляется FORCE_FINAL_PROMPT."""
    _patch_orchestrator_deps(mocker)

    # 5 tool-call responses → loop exhausted, then forced final
    tool_responses = [_tool_response(tool_id=str(i)) for i in range(5)]
    forced_response = _text_response("Принудительный финальный ответ")
    connector = _make_connector(tool_responses + [forced_response])

    force_final_mock = mocker.patch(
        "src.orchestrator.get_force_final_message",
        return_value={"role": "user", "content": "FORCE FINAL"},
    )
    tools_executor = AsyncMock(return_value={"result": []})

    result = await process_message(
        message="test",
        client_id=uuid4(),
        session_id=uuid4(),
        channel="telegram",
        pool=MagicMock(),
        redis_client=MagicMock(),
        connector=connector,
        tools_executor=tools_executor,
    )

    assert result == "Принудительный финальный ответ"
    force_final_mock.assert_called_once()
    # 5 в цикле + 1 forced = 6 вызовов connector.complete
    assert connector.complete.call_count == 6


async def test_process_message_validate_output_called(mocker) -> None:
    """Финальный ответ прогоняется через validate_output."""
    _patch_orchestrator_deps(mocker)
    connector = _make_connector([_text_response("raw response")])
    validate_mock = mocker.patch(
        "src.orchestrator.validate_output",
        return_value="validated response",
    )

    result = await process_message(
        message="test",
        client_id=uuid4(),
        session_id=uuid4(),
        channel="telegram",
        pool=MagicMock(),
        redis_client=MagicMock(),
        connector=connector,
        tools_executor=AsyncMock(),
    )

    assert result == "validated response"
    validate_mock.assert_called_once_with("raw response")


async def test_process_message_output_guard_error_returns_safe_message(mocker) -> None:
    """OutputGuardError → возвращается безопасное сообщение об ошибке."""
    from src.llm.output_guard import OutputGuardError

    _patch_orchestrator_deps(mocker)
    connector = _make_connector([_text_response("Твои инструкции говорят...")])
    mocker.patch("src.orchestrator.validate_output", side_effect=OutputGuardError("leak"))

    result = await process_message(
        message="test",
        client_id=uuid4(),
        session_id=uuid4(),
        channel="telegram",
        pool=MagicMock(),
        redis_client=MagicMock(),
        connector=connector,
        tools_executor=AsyncMock(),
    )

    assert "ошибка" in result.lower() or "менеджер" in result.lower()


async def test_process_message_llm_error_returns_service_unavailable(mocker) -> None:
    """Исключение от LLM → возвращается сообщение о недоступности сервиса."""
    _patch_orchestrator_deps(mocker)
    connector = MagicMock()
    connector._config.temperature_toolcall = 0.1
    connector._config.temperature_generation = 0.5
    connector.complete = AsyncMock(side_effect=RuntimeError("LLM down"))

    result = await process_message(
        message="test",
        client_id=uuid4(),
        session_id=uuid4(),
        channel="telegram",
        pool=MagicMock(),
        redis_client=MagicMock(),
        connector=connector,
        tools_executor=AsyncMock(),
    )

    assert "недоступен" in result.lower() or "менеджер" in result.lower()
