from __future__ import annotations

"""Orchestrator — основной цикл обработки сообщения.

ADR-007: максимум MAX_STEPS=5 шагов tool-calling на одно сообщение.
Реализует ReAct-паттерн: LLM → tool_call → observation → LLM → ...

Инварианты:
- tools_executor принимается как параметр (не импортируется напрямую) — DI
- log_interaction — только программный вызов, не LLM-tool
- Все IO через async/await
"""

import json
import logging
from typing import Callable, Awaitable
from uuid import UUID

import asyncpg
import redis.asyncio as aioredis

from src.config import settings
from src.decision import decide
from src.llm.connector import LLMConnector
from src.llm.context_builder import build_messages
from src.llm.output_guard import validate_output, OutputGuardError
from src.llm.prompts.force_final import get_force_final_message
from src.llm.prompts.system_prompt import build_system_prompt
from src.llm.tools_schema import get_tools_for
from src.memory import redis_session
from src.memory.repositories import clients as clients_repo
from src.memory.repositories import messages as messages_repo
from src.memory.repositories import sessions as sessions_repo
from src.router import classify_intent

logger = logging.getLogger(__name__)

ToolsExecutor = Callable[[str, dict], Awaitable[dict]]

# Сообщение о недоступности сервиса (graceful degradation)
_SERVICE_UNAVAILABLE = (
    "К сожалению, в данный момент сервис временно недоступен. "
    "Пожалуйста, попробуйте позже или обратитесь к менеджеру."
)


def _make_assistant_tool_use_message(tool_calls: list[dict]) -> dict:
    """Формирует assistant-сообщение с блоками tool_use (Claude-compatible)."""
    return {
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": tc["input"],
            }
            for tc in tool_calls
        ],
    }


def _make_tool_results_message(tool_calls: list[dict], results: list[dict]) -> dict:
    """Формирует user-сообщение с результатами tool_result (Claude-compatible)."""
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tc["id"],
                "content": json.dumps(result, ensure_ascii=False),
            }
            for tc, result in zip(tool_calls, results)
        ],
    }


async def process_message(
    message: str,
    client_id: UUID,
    session_id: UUID,
    channel: str,
    pool: asyncpg.Pool,
    redis_client: aioredis.Redis,
    connector: LLMConnector,
    tools_executor: ToolsExecutor,
) -> str:
    """Основной цикл обработки одного пользовательского сообщения.

    Шаги:
    1. Загрузить контекст (profile, summary, recent messages, stage)
    2. Classify intent → Decision → available_tools
    3. Tool-calling loop (max MAX_STEPS):
       a. LLM.complete() с available_tools
       b. Если tool_calls → выполнить через tools_executor, добавить результаты
       c. Если нет tool_calls → финальный ответ
    4. При step == MAX_STEPS без финального ответа → добавить FORCE_FINAL_PROMPT
    5. validate_output(response)
    6. Сохранить assistant-сообщение в messages
    7. Обновить stage в Redis и DB
    8. Вернуть финальный текст
    """
    # --- 1. Загрузка контекста ---
    client_profile: dict | None = None
    try:
        profile = await clients_repo.get_profile(pool, client_id)
        if profile:
            client_profile = {
                "budget_range": profile.budget_range,
                "preferred_destinations": profile.preferred_destinations,
                "travel_style": profile.travel_style,
                "constraints": profile.constraints,
            }
    except Exception as exc:
        logger.warning("Orchestrator: не удалось загрузить профиль клиента: %s", exc)

    conversation_summary: dict | None = None
    try:
        conversation_summary = await redis_session.get_summary(redis_client, session_id)
    except Exception as exc:
        logger.warning("Orchestrator: не удалось загрузить summary из Redis: %s", exc)

    current_stage: str = "cold"
    try:
        stage_from_redis = await redis_session.get_stage(redis_client, session_id)
        if stage_from_redis:
            current_stage = stage_from_redis
    except Exception as exc:
        logger.warning("Orchestrator: не удалось загрузить stage из Redis: %s", exc)

    recent_messages: list[dict] = []
    try:
        msgs = await messages_repo.load_recent(pool, session_id, limit=settings.MAX_RECENT_MESSAGES)
        recent_messages = [{"role": m.role, "content": m.content} for m in msgs]
    except Exception as exc:
        logger.warning("Orchestrator: не удалось загрузить recent messages: %s", exc)

    # --- 2. Intent classification + Decision Logic ---
    intent, confidence = await classify_intent(connector, message, recent_messages)
    decision = decide(current_stage, intent, confidence)

    logger.info(
        "Orchestrator: intent=%r confidence=%.2f stage=%r→%r tools=%r",
        intent,
        confidence,
        current_stage,
        decision.stage,
        decision.available_tools,
    )

    # --- 3. Подготовка messages для LLM ---
    system_prompt = build_system_prompt()
    llm_messages = build_messages(
        system_prompt=system_prompt,
        client_profile=client_profile,
        conversation_summary=conversation_summary,
        recent_messages=recent_messages,
        current_message=message,
    )

    available_tool_schemas = get_tools_for(decision.available_tools)

    # --- 4. Tool-calling loop (ReAct, ADR-007) ---
    final_reply: str | None = None
    step = 0

    while step < settings.MAX_STEPS:
        try:
            response = await connector.complete(
                messages=llm_messages,
                tools=available_tool_schemas if available_tool_schemas else None,
                temperature=connector._config.temperature_toolcall,
            )
        except Exception as exc:
            logger.error("Orchestrator: LLM ошибка на шаге %d: %s", step, exc)
            return _SERVICE_UNAVAILABLE

        if not response.tool_calls:
            # LLM сформировал финальный ответ
            final_reply = response.content
            break

        # LLM хочет вызвать tools
        llm_messages.append(_make_assistant_tool_use_message(response.tool_calls))

        results: list[dict] = []
        for tc in response.tool_calls:
            tool_name = tc.get("name", "")
            tool_input = tc.get("input", {})
            try:
                result = await tools_executor(tool_name, tool_input)
            except Exception as exc:
                logger.warning(
                    "Orchestrator: ошибка выполнения tool=%r: %s", tool_name, exc
                )
                result = {"error": str(exc)}
            results.append(result)

        llm_messages.append(_make_tool_results_message(response.tool_calls, results))
        step += 1

    # --- 5. Принудительный финальный ответ при превышении MAX_STEPS ---
    if final_reply is None:
        llm_messages.append(get_force_final_message())
        try:
            forced = await connector.complete(
                messages=llm_messages,
                tools=None,
                temperature=connector._config.temperature_generation,
            )
            final_reply = forced.content
        except Exception as exc:
            logger.error("Orchestrator: ошибка при forced final response: %s", exc)
            final_reply = _SERVICE_UNAVAILABLE

    # --- 6. Output guard ---
    try:
        final_reply = validate_output(final_reply or "")
    except OutputGuardError as exc:
        logger.error("Orchestrator: OutputGuard заблокировал ответ: %s", exc)
        final_reply = "Извините, произошла ошибка при формировании ответа. Пожалуйста, свяжитесь с менеджером."

    # --- 7. Сохранить assistant-сообщение ---
    metadata: dict = {
        "intent": intent,
        "stage_before": current_stage,
        "stage_after": decision.stage,
        "agent_steps": step,
    }
    try:
        await messages_repo.append(
            pool,
            session_id,
            role="assistant",
            content=final_reply,
            metadata=metadata,
        )
    except Exception as exc:
        logger.warning("Orchestrator: не удалось сохранить assistant-сообщение: %s", exc)

    # --- 8. Обновить stage (Redis + DB) ---
    if decision.stage != current_stage:
        try:
            await redis_session.set_stage(redis_client, session_id, decision.stage)
        except Exception as exc:
            logger.warning("Orchestrator: не удалось обновить stage в Redis: %s", exc)
        try:
            await sessions_repo.update_stage(pool, session_id, decision.stage)
        except Exception as exc:
            logger.warning("Orchestrator: не удалось обновить stage в PostgreSQL: %s", exc)

    return final_reply
