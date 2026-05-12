from __future__ import annotations

"""Фикстуры для integration-тестов."""

import pytest
from unittest.mock import MagicMock
from uuid import uuid4

from src.llm.providers.base import LLMResponse
from src.tools.executor import ToolExecutor
from src.tools.search_tours import SearchToursTool
from src.tools.client_profile import GetClientProfileTool, UpdateClientProfileTool
from src.tools.leads import CreateLeadTool, UpdateLeadStageTool
from src.tools.policy import GetPolicyInfoTool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_llm_response(
    content: str = "",
    tool_calls: list[dict] | None = None,
) -> LLMResponse:
    """Создаёт LLMResponse для подстановки в mock connector."""
    calls = tool_calls or []
    return LLMResponse(
        content=content,
        tool_calls=calls,
        usage={"input_tokens": 10, "output_tokens": 20},
        model="test-model",
        finish_reason="tool_use" if calls else "end_turn",
    )


def make_router_response(intent: str = "discovery", confidence: float = 0.8) -> LLMResponse:
    """LLMResponse имитирующий ответ роутера с заданным intent/confidence."""
    return make_llm_response(
        content=f'{{"intent": "{intent}", "confidence": {confidence}}}'
    )


# ---------------------------------------------------------------------------
# Фикстуры (mock_pool, fake_redis, mock_llm_connector определены в tests/conftest.py)
# ---------------------------------------------------------------------------


_SAMPLE_TOURS = [
    {
        "id": "tour_t001",
        "destination": "Мальдивы",
        "hotel_name": "Test Resort Alpha",
        "hotel_stars": 5,
        "price_usd": 3000,
        "duration_nights": 7,
        "departure_date": "2026-07-01",
        "meal_plan": "BB",
        "description": "Тур на Мальдивы (тестовый).",
    },
    {
        "id": "tour_t002",
        "destination": "Мальдивы",
        "hotel_name": "Test Resort Beta",
        "hotel_stars": 5,
        "price_usd": 4500,
        "duration_nights": 7,
        "departure_date": "2026-07-10",
        "meal_plan": "HB",
        "description": "Премиум-тур на Мальдивы (тестовый).",
    },
    {
        "id": "tour_t003",
        "destination": "Таиланд",
        "hotel_name": "Thai Test Resort",
        "hotel_stars": 4,
        "price_usd": 1500,
        "duration_nights": 7,
        "departure_date": "2026-08-01",
        "meal_plan": "BB",
        "description": "Тур в Таиланд (тестовый).",
    },
]

_SAMPLE_POLICIES = {
    "visa": {
        "default": "Стандартные визовые требования.",
        "destinations": {
            "Таиланд": "Безвизовый въезд до 30 дней.",
        },
    },
    "cancellation": {
        "default": "Отмена за 30 дней — полный возврат.",
        "premium": "Гибкие условия для премиум-клиентов.",
    },
}


@pytest.fixture
def full_tool_executor(mock_pool):
    """ToolExecutor с реальными tools и mock pool.

    SearchToursTool и GetPolicyInfoTool работают из in-memory данных.
    GetClientProfileTool / UpdateClientProfileTool / CreateLeadTool / UpdateLeadStageTool
    используют mock pool: в тестах, где нужны реальные записи, дополнительно
    патчатся соответствующие repo-функции.
    """
    pool, _ = mock_pool
    tools = [
        SearchToursTool(tours_data=_SAMPLE_TOURS),
        GetClientProfileTool(pool=pool),
        UpdateClientProfileTool(pool=pool),
        CreateLeadTool(pool=pool),
        UpdateLeadStageTool(pool=pool),
        GetPolicyInfoTool(policies_data=_SAMPLE_POLICIES),
    ]
    return ToolExecutor(tools=tools)
