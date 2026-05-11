from __future__ import annotations

"""Базовый контракт для всех judges eval-pipeline."""

from abc import ABC, abstractmethod
from typing import Literal

from pydantic import BaseModel

from tests.evals.simulator.models import ConversationRecord


class JudgeVerdict(BaseModel):
    judge_name: str
    score: float          # 0.0–1.0 (нормализованный для Langfuse score API)
    verdict: Literal["pass", "fail"]
    reasons: list[str]
    flagged_items: list[str] = []  # конкретные фрагменты, вызвавшие fail
    metadata: dict = {}


class BaseJudge(ABC):
    """Абстрактный judge.

    Потребляет ConversationRecord, возвращает список вердиктов
    (обычно один per conversation, но может быть один per turn).
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def evaluate(self, record: ConversationRecord) -> list[JudgeVerdict]: ...
