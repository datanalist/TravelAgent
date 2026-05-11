from __future__ import annotations

"""Decision Logic — rule-based определение стадии воронки и набора доступных tools.

Реализует паттерн Guided Agent (ADR-004): Decision Logic определяет область
допустимых действий (available_tools), LLM самостоятельно решает — какие tools
вызывать и с какими параметрами.

Стадии воронки синхронизированы с redis_session.VALID_STAGES:
cold → discovery → qualified → proposal → objection → closing → follow_up
"""

from dataclasses import dataclass

# Порядок воронки (для сравнения приоритетов)
STAGES = ["cold", "discovery", "qualified", "proposal", "objection", "closing", "follow_up"]

# Матрица stage → available_tools (ADR-004, spec-orchestrator §4)
STAGE_TOOLS: dict[str, list[str]] = {
    "cold":        ["search_tours", "get_policy_info", "get_client_profile"],
    "discovery":   ["search_tours", "get_policy_info", "get_client_profile", "update_client_profile"],
    "qualified":   ["search_tours", "get_client_profile", "update_client_profile", "get_policy_info"],
    "proposal":    ["search_tours", "create_lead", "update_client_profile"],
    "objection":   ["search_tours", "update_lead_stage"],
    "closing":     ["create_lead", "update_lead_stage"],
    "follow_up":   ["search_tours", "get_policy_info", "get_client_profile"],
}

# Маппинг intent → целевая стадия воронки
INTENT_TO_STAGE: dict[str, str] = {
    "small_talk":       "cold",
    "discovery":        "discovery",
    "pricing_budget":   "qualified",
    "itinerary_search": "qualified",
    "policy_info":      "qualified",
    "objection":        "objection",
    "crm_event":        "closing",
}

# Стадии, при переходе в которые создаётся лид
_LEAD_STAGES = frozenset({"proposal", "objection", "closing"})


@dataclass
class DecisionResult:
    stage: str
    available_tools: list[str]
    should_create_lead: bool


def decide(current_stage: str, intent: str, confidence: float) -> DecisionResult:
    """Rule-based логика перехода стадии и выбора инструментов.

    Если confidence >= 0.7 — переходим в целевую стадию по intent.
    Если меньше — остаёмся в текущей стадии.
    Никогда не откатываемся назад по воронке (только вперёд или стоим).
    """
    # Определяем целевую стадию
    target_stage: str
    if confidence >= 0.7:
        intent_stage = INTENT_TO_STAGE.get(intent, current_stage)
        # Движение только вперёд по воронке
        try:
            current_idx = STAGES.index(current_stage)
        except ValueError:
            current_idx = 0

        try:
            intent_idx = STAGES.index(intent_stage)
        except ValueError:
            intent_idx = current_idx

        # Специальный случай: objection — переход возможен из proposal или closing
        if intent_stage == "objection" and current_stage in ("proposal", "closing"):
            target_stage = "objection"
        elif intent_idx >= current_idx:
            target_stage = intent_stage
        else:
            target_stage = current_stage
    else:
        target_stage = current_stage

    available_tools = STAGE_TOOLS.get(target_stage, STAGE_TOOLS["cold"])
    should_create_lead = target_stage in _LEAD_STAGES

    return DecisionResult(
        stage=target_stage,
        available_tools=list(available_tools),
        should_create_lead=should_create_lead,
    )
