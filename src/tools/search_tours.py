from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from src.tools.base import BaseTool, ToolResult

_TOURS_PATH = Path(__file__).parent.parent.parent / "data" / "tours.json"

_MAX_RESULTS = 5
_DURATION_TOLERANCE = 2


def _load_tours(path: Path = _TOURS_PATH) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _parse_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


class SearchToursTool(BaseTool):
    name = "search_tours"

    def __init__(self, tours_data: list[dict[str, Any]] | None = None) -> None:
        self._tours: list[dict[str, Any]] = tours_data if tours_data is not None else _load_tours()

    async def execute(  # type: ignore[override]
        self,
        destination: str | None = None,
        budget_usd: float | None = None,
        hotel_stars: int | None = None,
        meal_plan: str | None = None,
        duration_nights: int | None = None,
        departure_date_from: str | date | None = None,
        departure_date_to: str | date | None = None,
        travelers: int | None = None,
        **_: Any,
    ) -> ToolResult:
        date_from = _parse_date(departure_date_from)
        date_to = _parse_date(departure_date_to)

        results: list[dict[str, Any]] = []
        for tour in self._tours:
            if destination is not None:
                if destination.lower() not in tour.get("destination", "").lower():
                    continue

            if budget_usd is not None:
                if tour.get("price_usd", 0) > budget_usd:
                    continue

            if hotel_stars is not None:
                if tour.get("hotel_stars") != hotel_stars:
                    continue

            if meal_plan is not None:
                if tour.get("meal_plan") != meal_plan:
                    continue

            if duration_nights is not None:
                tour_nights = tour.get("duration_nights", 0)
                if abs(tour_nights - duration_nights) > _DURATION_TOLERANCE:
                    continue

            if date_from is not None or date_to is not None:
                dep_raw = tour.get("departure_date")
                if dep_raw is None:
                    continue
                dep = date.fromisoformat(str(dep_raw))
                if date_from is not None and dep < date_from:
                    continue
                if date_to is not None and dep > date_to:
                    continue

            results.append(tour)

        results.sort(key=lambda t: t.get("price_usd", 0))
        return ToolResult(success=True, data=results[:_MAX_RESULTS])
