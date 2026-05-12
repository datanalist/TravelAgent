from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.llm.providers.base import LLMResponse
from src.router import classify_intent


def _make_connector(content: str) -> MagicMock:
    connector = MagicMock()
    connector.complete = AsyncMock(
        return_value=LLMResponse(
            content=content,
            tool_calls=[],
            usage={},
            model="test",
        )
    )
    return connector


_INTENTS = [
    "small_talk",
    "discovery",
    "pricing_budget",
    "itinerary_search",
    "policy_info",
    "objection",
    "crm_event",
]


@pytest.mark.parametrize("intent", _INTENTS)
async def test_classify_intent_valid(intent: str) -> None:
    connector = _make_connector(f'{{"intent": "{intent}", "confidence": 0.9}}')
    result_intent, confidence = await classify_intent(connector, "test message", [])
    assert result_intent == intent
    assert confidence == pytest.approx(0.9)


async def test_classify_intent_fallback_on_invalid_json() -> None:
    connector = _make_connector("not a json response at all")
    intent, confidence = await classify_intent(connector, "hello", [])
    assert intent == "discovery"
    assert confidence == pytest.approx(0.5)


async def test_classify_intent_fallback_on_unknown_intent() -> None:
    connector = _make_connector('{"intent": "unknown_intent", "confidence": 0.8}')
    intent, confidence = await classify_intent(connector, "hello", [])
    assert intent == "discovery"
    assert confidence == pytest.approx(0.5)


async def test_classify_intent_low_confidence_returned() -> None:
    """При confidence < 0.5 — значение всё равно возвращается (решение о переходе в decision)."""
    connector = _make_connector('{"intent": "small_talk", "confidence": 0.3}')
    intent, confidence = await classify_intent(connector, "hello", [])
    assert intent == "small_talk"
    assert confidence == pytest.approx(0.3)


async def test_classify_intent_json_embedded_in_text() -> None:
    """Router умеет извлечь JSON из текста с мусором до/после."""
    connector = _make_connector(
        'Sure! Here is my answer: {"intent": "pricing_budget", "confidence": 0.85} — done.'
    )
    intent, confidence = await classify_intent(connector, "сколько стоит?", [])
    assert intent == "pricing_budget"
    assert confidence == pytest.approx(0.85)


async def test_classify_intent_connector_exception() -> None:
    """При исключении в connector → fallback."""
    connector = MagicMock()
    connector.complete = AsyncMock(side_effect=RuntimeError("API down"))
    intent, confidence = await classify_intent(connector, "test", [])
    assert intent == "discovery"
    assert confidence == pytest.approx(0.5)


async def test_classify_intent_missing_confidence_defaults_to_half() -> None:
    connector = _make_connector('{"intent": "objection"}')
    intent, confidence = await classify_intent(connector, "test", [])
    assert intent == "objection"
    assert confidence == pytest.approx(0.5)
