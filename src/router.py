from __future__ import annotations

"""Intent Router — классифицирует входящее сообщение через LLM.

7 интентов: small_talk, discovery, pricing_budget, itinerary_search,
policy_info, objection, crm_event
"""

import json
import logging

from src.llm.connector import LLMConnector
from src.llm.prompts.router_prompt import build_router_messages

logger = logging.getLogger(__name__)

_VALID_INTENTS = frozenset(
    {
        "small_talk",
        "discovery",
        "pricing_budget",
        "itinerary_search",
        "policy_info",
        "objection",
        "crm_event",
    }
)

_DEFAULT_INTENT = "discovery"
_TEMPERATURE_ROUTING = 0.1  # LLM_TEMPERATURE_TOOLCALL


async def classify_intent(
    connector: LLMConnector,
    message: str,
    history: list[dict],
) -> tuple[str, float]:
    """Классифицирует intent входящего сообщения.

    Возвращает (intent, confidence).
    При ошибке парсинга или неизвестном интенте — fallback на "discovery".
    """
    messages = build_router_messages(message)

    try:
        response = await connector.complete(
            messages=messages,
            tools=None,
            temperature=_TEMPERATURE_ROUTING,
        )
        raw = response.content.strip()

        # Извлекаем JSON — ищем первый JSON-объект в тексте
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"JSON не найден в ответе: {raw!r}")

        data = json.loads(raw[start:end])
        intent: str = data.get("intent", _DEFAULT_INTENT)
        confidence: float = float(data.get("confidence", 0.5))

        if intent not in _VALID_INTENTS:
            logger.warning(
                "Router: неизвестный intent=%r, fallback на %r",
                intent,
                _DEFAULT_INTENT,
            )
            return _DEFAULT_INTENT, 0.5

        return intent, confidence

    except Exception as exc:
        logger.warning(
            "Router: ошибка классификации intent (%s), fallback на %r",
            exc,
            _DEFAULT_INTENT,
        )
        return _DEFAULT_INTENT, 0.5
