from __future__ import annotations

"""Pydantic-модели для User-Behaviour Eval pipeline."""

from typing import Any, Literal
from pydantic import BaseModel, Field


class PersonaStyle(BaseModel):
    formality: Literal["high", "medium", "casual"] = "medium"
    patience: Literal["low", "medium", "high"] = "medium"
    expectations: Literal["budget", "mid", "premium"] = "mid"
    emoji_usage: Literal["never", "rare", "often"] = "rare"


class Persona(BaseModel):
    version: int = 1
    name: str
    display_name: str
    description: str
    style: PersonaStyle = Field(default_factory=PersonaStyle)
    constraints: list[str] = []
    voice_examples: list[str] = []
    forbidden_phrases: list[str] = []


class GroundTruthIntent(BaseModel):
    turn: int
    expected_intent: str


class ExpectedOutcome(BaseModel):
    injection_resistance: bool | None = None
    refusal_rate: float | None = None
    pii_leak: bool | None = None
    hallucination: bool | None = None
    goal_success: bool | None = None


class Scenario(BaseModel):
    version: int = 1
    name: str
    display_name: str
    category: str  # happy_path | edge_case_e1..e7 | red_team
    goal: str
    max_turns: int = 8
    expected_outcome: ExpectedOutcome = Field(default_factory=ExpectedOutcome)
    playbook_hints: list[str] = []
    attack_vectors_to_try: list[str] = []
    ground_truth_intents: list[GroundTruthIntent] = []


class Turn(BaseModel):
    turn_no: int
    user_message: str
    assistant_reply: str
    intent: str | None = None
    stage_before: str | None = None
    stage_after: str | None = None
    tool_calls: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    latency_ms: float = 0.0
    tokens_used: int | None = None
    agent_steps: int = 0
    metadata: dict[str, Any] = {}


class ConversationRecord(BaseModel):
    persona_name: str
    persona_version: int
    scenario_name: str
    scenario_version: int
    simulator_prompt_version: str = "SIMULATOR_PROMPT_V1"
    commit_hash: str = "unknown"
    turns: list[Turn] = []
    completed: bool = False   # True — цель достигнута / END_CONVERSATION; False — max_turns
    error: str | None = None  # текст исключения, если прогон упал


class AgentTurnResult(BaseModel):
    """Результат одного вызова process_message()."""

    reply: str
    intent: str | None = None
    stage_before: str | None = None
    stage_after: str | None = None
    tool_calls: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    latency_ms: float = 0.0
    tokens_used: int | None = None
    agent_steps: int = 0
