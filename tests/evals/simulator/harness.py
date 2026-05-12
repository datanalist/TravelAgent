from __future__ import annotations

"""Conversation harness — оркестратор одного диалога persona × scenario.

Алгоритм:
1. Открыть Langfuse trace (или no-op).
2. Loop max_turns:
   a. UserBehaviourAgent.next_turn(history) → user_message (или None = завершение)
   b. InProcessClient.chat_turn(user_message) → AgentTurnResult
   c. Собрать Turn, дописать в JSONL (append), добавить Langfuse span.
3. Закрыть trace, вернуть ConversationRecord.
"""

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

from tests.evals.simulator.models import (
    AgentTurnResult,
    ConversationRecord,
    Persona,
    Scenario,
    Turn,
)
from tests.evals.simulator.client import InProcessClient
from tests.evals.simulator.user_agent import UserBehaviourAgent
from tests.evals.tracing.langfuse_client import LangfuseClient

logger = logging.getLogger(__name__)

_RECORDINGS_DIR = Path(__file__).parent.parent / "recordings"


def _get_commit_hash() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=3,
        )
        return result.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _jsonl_path(persona: Persona, scenario: Scenario, commit: str) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{ts}__{commit}__{persona.name}__{scenario.name}.jsonl"
    _RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    return _RECORDINGS_DIR / filename


def _append_turn(path: Path, turn: Turn) -> None:
    """Атомарный append одного turn в JSONL-файл."""
    with path.open("a", encoding="utf-8") as f:
        f.write(turn.model_dump_json() + "\n")


async def run_conversation(
    persona: Persona,
    scenario: Scenario,
    connector,
    client_id: UUID,
    session_id: UUID,
    langfuse: LangfuseClient | None = None,
    *,
    recording_path: Path | None = None,
) -> ConversationRecord:
    """Прогоняет один диалог persona × scenario.

    Args:
        persona: описание персонажа.
        scenario: описание сценария.
        connector: LLMConnector (для симулятора и агента-под-тестом — один).
        client_id: UUID клиента для InProcessClient.
        session_id: UUID сессии.
        langfuse: клиент трейсинга (no-op если None).
        recording_path: куда писать JSONL (авто-генерируется если None).

    Returns:
        ConversationRecord с полной историей.
    """
    if langfuse is None:
        langfuse = LangfuseClient()

    commit = _get_commit_hash()
    path = recording_path or _jsonl_path(persona, scenario, commit)

    record = ConversationRecord(
        persona_name=persona.name,
        persona_version=persona.version,
        scenario_name=scenario.name,
        scenario_version=scenario.version,
        commit_hash=commit,
    )

    trace_name = f"{persona.name}__{scenario.name}"
    trace = langfuse.start_trace(
        trace_name,
        metadata={
            "persona": persona.name,
            "scenario": scenario.name,
            "commit": commit,
        },
        tags=[persona.name, scenario.category],
    )

    agent_client = InProcessClient(
        connector=connector,
        client_id=client_id,
        session_id=session_id,
    )
    simulator = UserBehaviourAgent(connector=connector, persona=persona, scenario=scenario)

    history: list[Turn] = []
    completed = False

    try:
        for turn_no in range(1, scenario.max_turns + 1):
            # --- Симулятор генерирует сообщение ---
            sim_span = langfuse.start_span(
                trace, f"simulator_turn_{turn_no}",
                input={"history_len": len(history)},
            )
            user_message = await simulator.next_turn(history)
            langfuse.end_span(sim_span, output={"user_message": user_message or "<END>"})

            if user_message is None:
                completed = True
                logger.info("Harness: симулятор завершил диалог на turn %d", turn_no)
                break

            # --- Вызов агента ---
            agent_span = langfuse.start_span(
                trace, f"agent_turn_{turn_no}",
                input={"message": user_message[:200]},
            )
            try:
                result: AgentTurnResult = await agent_client.chat_turn(user_message)
            except Exception as exc:
                logger.error("Harness: ошибка agent_client.chat_turn на turn %d: %s", turn_no, exc)
                langfuse.end_span(agent_span, output={"error": str(exc)})
                record.error = str(exc)
                break

            langfuse.end_span(agent_span, output={
                "reply": result.reply[:200],
                "stage_after": result.stage_after,
                "latency_ms": result.latency_ms,
            })

            # --- Запись turn ---
            turn = Turn(
                turn_no=turn_no,
                user_message=user_message,
                assistant_reply=result.reply,
                intent=result.intent,
                stage_before=result.stage_before,
                stage_after=result.stage_after,
                tool_calls=result.tool_calls,
                tool_results=result.tool_results,
                latency_ms=result.latency_ms,
                tokens_used=result.tokens_used,
                agent_steps=result.agent_steps,
            )
            history.append(turn)
            record.turns.append(turn)
            _append_turn(path, turn)

            logger.info(
                "Harness: turn %d/%d | latency=%.0fms | stage=%s→%s",
                turn_no, scenario.max_turns,
                result.latency_ms,
                result.stage_before, result.stage_after,
            )

        else:
            # max_turns исчерпан без явного завершения
            logger.info(
                "Harness: max_turns=%d достигнут (persona=%s, scenario=%s)",
                scenario.max_turns, persona.name, scenario.name,
            )

        record.completed = completed

    except Exception as exc:
        logger.error("Harness: критическая ошибка: %s", exc)
        record.error = str(exc)
    finally:
        langfuse.end_trace(trace, output={
            "turns": len(record.turns),
            "completed": record.completed,
            "error": record.error,
        })
        langfuse.flush()

    logger.info(
        "Harness: диалог завершён — turns=%d completed=%s recording=%s",
        len(record.turns), record.completed, path,
    )
    return record
