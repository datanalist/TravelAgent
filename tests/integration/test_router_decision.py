from __future__ import annotations

"""Integration-тесты Router → Decision → tools selection."""

import pytest
from tests.integration.conftest import make_llm_response, make_router_response
from src.router import classify_intent
from src.decision import decide, STAGE_TOOLS


# ---------------------------------------------------------------------------
# Decision Logic (pure function — не требует async)
# ---------------------------------------------------------------------------

def test_intent_small_talk_keeps_cold_stage():
    """intent=small_talk, confidence=0.9, stage=cold → остаётся cold."""
    result = decide("cold", "small_talk", 0.9)
    assert result.stage == "cold"
    assert "get_client_profile" in result.available_tools


def test_intent_itinerary_search_upgrades_to_qualified():
    """intent=itinerary_search, confidence=0.85, stage=discovery → qualified."""
    result = decide("discovery", "itinerary_search", 0.85)
    assert result.stage == "qualified"
    assert "search_tours" in result.available_tools


def test_low_confidence_keeps_current_stage():
    """confidence=0.4 < 0.7 → stage не меняется независимо от intent."""
    result = decide("discovery", "crm_event", 0.4)
    assert result.stage == "discovery"


def test_funnel_never_goes_backwards():
    """Из proposal нельзя откатиться в discovery даже при discovery intent."""
    result = decide("proposal", "discovery", 0.95)
    assert result.stage == "proposal"


def test_objection_from_proposal_allowed():
    """Переход proposal → objection допускается при objection intent."""
    result = decide("proposal", "objection", 0.9)
    assert result.stage == "objection"


def test_should_create_lead_for_proposal_stage():
    """should_create_lead=True когда целевая стадия в _LEAD_STAGES."""
    result = decide("qualified", "crm_event", 0.95)
    assert result.stage == "closing"
    assert result.should_create_lead is True


def test_should_not_create_lead_for_cold_stage():
    """should_create_lead=False для холодной стадии."""
    result = decide("cold", "small_talk", 0.9)
    assert result.should_create_lead is False


# ---------------------------------------------------------------------------
# Router (async, требует mock LLM)
# ---------------------------------------------------------------------------

async def test_classify_intent_valid_response(mock_llm_connector):
    """Router корректно парсит JSON-ответ LLM и возвращает (intent, confidence)."""
    mock_llm_connector.complete.return_value = make_router_response("itinerary_search", 0.9)

    intent, confidence = await classify_intent(
        mock_llm_connector,
        message="Хочу тур на Мальдивы",
        history=[],
    )

    assert intent == "itinerary_search"
    assert confidence == pytest.approx(0.9)


async def test_router_fallback_on_invalid_json(mock_llm_connector):
    """LLM возвращает невалидный JSON → fallback ('discovery', 0.5); исключение не бросается."""
    mock_llm_connector.complete.return_value = make_llm_response(
        content="это точно не json!!!"
    )

    intent, confidence = await classify_intent(
        mock_llm_connector,
        message="Привет",
        history=[],
    )

    assert intent == "discovery"
    assert confidence == pytest.approx(0.5)


async def test_router_fallback_on_unknown_intent(mock_llm_connector):
    """LLM возвращает неизвестный intent → fallback на 'discovery'."""
    mock_llm_connector.complete.return_value = make_llm_response(
        content='{"intent": "unknown_intent_xyz", "confidence": 0.99}'
    )

    intent, confidence = await classify_intent(
        mock_llm_connector,
        message="Что угодно",
        history=[],
    )

    assert intent == "discovery"
    assert confidence == pytest.approx(0.5)


async def test_router_parses_json_with_surrounding_text(mock_llm_connector):
    """JSON внутри текста корректно извлекается роутером."""
    mock_llm_connector.complete.return_value = make_llm_response(
        content='Sure! {"intent": "policy_info", "confidence": 0.75} Done.'
    )

    intent, confidence = await classify_intent(
        mock_llm_connector,
        message="Какие документы нужны?",
        history=[],
    )

    assert intent == "policy_info"
    assert confidence == pytest.approx(0.75)


async def test_full_router_to_decision_pipeline(mock_llm_connector):
    """E2E: classify_intent → decide → search_tours в available_tools."""
    mock_llm_connector.complete.return_value = make_router_response("itinerary_search", 0.85)

    intent, confidence = await classify_intent(
        mock_llm_connector,
        message="Ищу тур",
        history=[],
    )
    result = decide("discovery", intent, confidence)

    assert "search_tours" in result.available_tools
    assert result.stage == "qualified"
