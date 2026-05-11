from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.tools.base import BaseTool, ToolResult

_POLICIES_PATH = Path(__file__).parent.parent.parent / "data" / "policies.json"


def _load_policies(path: Path = _POLICIES_PATH) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


class GetPolicyInfoTool(BaseTool):
    name = "get_policy_info"

    def __init__(self, policies_data: dict[str, Any] | None = None) -> None:
        self._policies: dict[str, Any] = policies_data if policies_data is not None else _load_policies()

    async def execute(  # type: ignore[override]
        self,
        policy_type: str,
        destination: str | None = None,
        **_: Any,
    ) -> ToolResult:
        section = self._policies.get(policy_type)
        if section is None:
            available = list(self._policies.keys())
            return ToolResult(
                success=False,
                data=None,
                error=f"Неизвестный тип политики '{policy_type}'. Доступные: {available}",
            )

        result: dict[str, Any] = {"policy_type": policy_type}

        if destination is not None:
            destinations_map: dict[str, str] = section.get("destinations", {})
            destination_info = _find_destination(destinations_map, destination)
            if destination_info is not None:
                result["destination"] = destination
                result["info"] = destination_info
            else:
                result["destination"] = destination
                result["info"] = section.get("default", "")
                result["note"] = "Специфической информации по данному направлению нет, применяется общее правило."
        else:
            result["info"] = section.get("default", "")
            if "premium" in section:
                result["premium"] = section["premium"]
            if "flexible" in section:
                result["flexible"] = section["flexible"]
            if "installment" in section:
                result["installment"] = section["installment"]

        return ToolResult(success=True, data=result)


def _find_destination(destinations: dict[str, str], query: str) -> str | None:
    query_lower = query.lower()
    for key, value in destinations.items():
        if query_lower in key.lower() or key.lower() in query_lower:
            return value
    return None
