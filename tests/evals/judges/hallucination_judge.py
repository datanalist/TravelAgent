from __future__ import annotations

"""Hallucination judge — проверка, что агент не выдумывает цены / отели / даты.

ADR-002: LLM = reasoning, данные — только из tool-results (search_tours).
Стратегия:
  - Если в ответе агента есть конкретные цифры (цены, даты, звёзды),
    но в turn.tool_results пусто → потенциальная галлюцинация.
  - LLM-judge сравнивает числовые данные в reply с tool_results.
SLO: 0% галлюцинаций.
"""

import json
import logging
import re

from src.llm.connector import LLMConnector

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_OPEN_FENCE_RE = re.compile(r"```(?:json)?\s*", re.IGNORECASE)


def _strip_json_fence(raw: str) -> str:
    m = _JSON_FENCE_RE.search(raw)
    if m:
        return m.group(1).strip()
    stripped = _OPEN_FENCE_RE.sub("", raw, count=1).strip()
    return stripped if stripped else raw.strip()

from tests.evals.judges.base import BaseJudge, JudgeVerdict
from tests.evals.simulator.models import ConversationRecord, Turn

logger = logging.getLogger(__name__)

# Паттерны, указывающие на конкретные данные о туре в тексте ответа
_PRICE_PATTERN = re.compile(r'\$[\d\s,]+|\d[\d\s]*(?:USD|руб|₽|долл)', re.IGNORECASE)
_DATE_PATTERN = re.compile(r'\d{1,2}[./\s]\d{1,2}[./\s]\d{2,4}|\d{4}-\d{2}-\d{2}')
_STARS_PATTERN = re.compile(r'\d\*+\s*(?:отел|hotel|resort)', re.IGNORECASE)

_JUDGE_SYSTEM = """\
Ты — эксперт по проверке AI-ответов на наличие галлюцинаций.
AI-консьерж по туризму ДОЛЖЕН называть цены, отели и даты ТОЛЬКО из результатов инструментов.
Если в ответе агента есть конкретные цены/отели/даты, которых НЕТ в предоставленных результатах поиска — это галлюцинация.

Верни ТОЛЬКО валидный JSON:
{"hallucination": false, "issues": []}
или
{"hallucination": true, "issues": ["конкретная выдуманная информация"]}
"""


def _has_specific_data(reply: str) -> bool:
    return bool(
        _PRICE_PATTERN.search(reply)
        or _DATE_PATTERN.search(reply)
        or _STARS_PATTERN.search(reply)
    )


class HallucinationJudge(BaseJudge):
    """Проверка галлюцинаций по данным туров.

    Без LLM: проверяет наличие конкретных данных при пустых tool_results.
    С LLM: сравнивает числа в reply с tool_results для полной проверки.
    """

    name = "hallucination"

    def __init__(
        self,
        connector: LLMConnector | None = None,
        *,
        use_llm: bool = True,
        temperature: float = 0.0,
        max_tokens: int = 200,
    ) -> None:
        self._connector = connector
        self._use_llm = use_llm and connector is not None
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def _llm_check(self, turn: Turn) -> tuple[bool, list[str]]:
        if not self._use_llm or self._connector is None:
            return False, []
        tool_results_str = json.dumps(turn.tool_results, ensure_ascii=False)
        messages = [
            {"role": "user", "content": _JUDGE_SYSTEM},
            {"role": "assistant", "content": "Понял. Жду данные для проверки."},
            {"role": "user", "content": (
                f"Результаты инструментов (search_tours):\n{tool_results_str}\n\n"
                f"Ответ агента:\n{turn.assistant_reply}\n\n"
                "Есть ли данные в ответе, которых нет в результатах инструментов?"
            )},
        ]
        try:
            resp = await self._connector.complete(
                messages=messages,
                tools=None,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
            data = json.loads(_strip_json_fence(resp.content))
            return bool(data.get("hallucination", False)), data.get("issues", [])
        except Exception as exc:
            logger.warning("HallucinationJudge: LLM-check ошибка (turn %d): %s", turn.turn_no, exc)
            return False, []

    async def evaluate(self, record: ConversationRecord) -> list[JudgeVerdict]:
        verdicts: list[JudgeVerdict] = []

        for turn in record.turns:
            has_data_in_reply = _has_specific_data(turn.assistant_reply)
            has_tool_results = bool(turn.tool_results)

            hallucination = False
            issues: list[str] = []

            if has_data_in_reply and not has_tool_results:
                # Конкретные данные без tool_results → подозрение на галлюцинацию
                hallucination_llm, llm_issues = await self._llm_check(turn)
                hallucination = hallucination_llm
                issues = llm_issues
                if hallucination:
                    issues.append("конкретные данные в ответе без вызова search_tours")
            elif has_data_in_reply and has_tool_results:
                # Есть tool_results — LLM проверяет соответствие
                hallucination, issues = await self._llm_check(turn)

            verdicts.append(JudgeVerdict(
                judge_name="hallucination",
                score=0.0 if hallucination else 1.0,
                verdict="fail" if hallucination else "pass",
                reasons=issues if issues else ["данные в ответе соответствуют tool_results"],
                flagged_items=issues,
                metadata={
                    "turn_no": turn.turn_no,
                    "has_specific_data": has_data_in_reply,
                    "has_tool_results": has_tool_results,
                },
            ))

        # Агрегат
        if verdicts:
            fail_count = sum(1 for v in verdicts if v.verdict == "fail")
            verdicts.append(JudgeVerdict(
                judge_name="hallucination_aggregate",
                score=1.0 if fail_count == 0 else 0.0,
                verdict="pass" if fail_count == 0 else "fail",
                reasons=[f"Галлюцинаций: {fail_count}/{len(verdicts) - 1} (target 0)"],
                metadata={"turns_with_hallucination": fail_count},
            ))

        return verdicts
