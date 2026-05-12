from __future__ import annotations

"""Tone judge — оценка high-end тона ответов агента (LLM-as-Judge).

Использует существующий TONE_JUDGE_SYSTEM_PROMPT_V1 из src/llm/prompts/.
SLO: ≥ 75% turn'ов получают verdict="pass" (score ≥ 4/5 → 0.8).
"""

import json
import logging
import re

from src.llm.connector import LLMConnector

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_OPEN_FENCE_RE = re.compile(r"```(?:json)?\s*", re.IGNORECASE)


def _strip_json_fence(raw: str) -> str:
    """Убирает markdown-обёртку ```json ... ``` если она есть.

    Обрабатывает случай без закрывающего fence (truncated response).
    """
    m = _JSON_FENCE_RE.search(raw)
    if m:
        return m.group(1).strip()
    # Открывающий fence без закрывающего (обрезан max_tokens)
    stripped = _OPEN_FENCE_RE.sub("", raw, count=1).strip()
    return stripped if stripped else raw.strip()
from src.llm.prompts.tone_judge_prompt import build_tone_judge_messages

from tests.evals.judges.base import BaseJudge, JudgeVerdict
from tests.evals.simulator.models import ConversationRecord, Turn

logger = logging.getLogger(__name__)

PASS_THRESHOLD = 4  # score ≥ 4 из 5 → pass


def _parse_verdict(raw: str, turn: Turn) -> JudgeVerdict:
    try:
        data = json.loads(_strip_json_fence(raw))
        score_raw = int(data.get("score", 0))
        compliant = bool(data.get("compliant", score_raw >= PASS_THRESHOLD))
        issues = data.get("issues", [])
        return JudgeVerdict(
            judge_name="tone",
            score=round(score_raw / 5, 2),
            verdict="pass" if compliant else "fail",
            reasons=issues if issues else ["ответ соответствует high-end тону"],
            metadata={"turn_no": turn.turn_no, "raw_score": score_raw},
        )
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        logger.warning("ToneJudge: не удалось разобрать ответ LLM: %s | raw=%r", exc, raw[:200])
        return JudgeVerdict(
            judge_name="tone",
            score=0.0,
            verdict="fail",
            reasons=[f"Не удалось разобрать ответ judge: {exc}"],
            metadata={"turn_no": turn.turn_no, "parse_error": str(exc)},
        )


class ToneJudge(BaseJudge):
    """LLM-as-Judge для оценки high-end тона.

    Args:
        connector: LLMConnector (желательно другая модель/промпт чем у агента).
        temperature: 0.0 для воспроизводимости.
        max_tokens: короткий JSON-ответ.
    """

    name = "tone"

    def __init__(
        self,
        connector: LLMConnector,
        *,
        temperature: float = 0.0,
        max_tokens: int = 400,
    ) -> None:
        self._connector = connector
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def evaluate(self, record: ConversationRecord) -> list[JudgeVerdict]:
        verdicts: list[JudgeVerdict] = []

        for turn in record.turns:
            messages = build_tone_judge_messages(
                agent_response=turn.assistant_reply,
                user_message=turn.user_message,
            )
            try:
                response = await self._connector.complete(
                    messages=messages,
                    tools=None,
                    temperature=self._temperature,
                    max_tokens=self._max_tokens,
                )
                verdict = _parse_verdict(response.content, turn)
            except Exception as exc:
                logger.error("ToneJudge: ошибка LLM-вызова (turn %d): %s", turn.turn_no, exc)
                verdict = JudgeVerdict(
                    judge_name="tone",
                    score=0.0,
                    verdict="fail",
                    reasons=[f"Ошибка вызова judge: {exc}"],
                    metadata={"turn_no": turn.turn_no},
                )
            verdicts.append(verdict)

        # Суммарный verdict для всей conversation (агрегат)
        if verdicts:
            pass_rate = sum(1 for v in verdicts if v.verdict == "pass") / len(verdicts)
            verdicts.append(JudgeVerdict(
                judge_name="tone_aggregate",
                score=round(pass_rate, 2),
                verdict="pass" if pass_rate >= 0.75 else "fail",
                reasons=[f"Pass rate: {pass_rate:.0%} (target ≥ 75%)"],
                metadata={
                    "turns_total": len(verdicts) - 1,
                    "turns_pass": sum(1 for v in verdicts[:-1] if v.verdict == "pass"),
                },
            ))

        return verdicts
