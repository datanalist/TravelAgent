from __future__ import annotations

from typing import Any
from uuid import UUID

from asyncpg import Pool

from src.memory.models import ClientProfile
from src.memory.repositories import clients as clients_repo
from src.tools.base import BaseTool, ToolResult


class GetClientProfileTool(BaseTool):
    name = "get_client_profile"

    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def execute(self, client_id: str | UUID, **_: Any) -> ToolResult:  # type: ignore[override]
        try:
            uid = UUID(str(client_id))
            profile: ClientProfile | None = await clients_repo.get_profile(self._pool, uid)
            if profile is None:
                empty: dict[str, Any] = {
                    "client_id": str(client_id),
                    "budget_range": None,
                    "preferred_destinations": [],
                    "travel_style": None,
                    "constraints": {},
                    "raw_preferences": {},
                }
                return ToolResult(success=True, data=empty)
            return ToolResult(
                success=True,
                data={
                    "id": str(profile.id),
                    "client_id": str(profile.client_id),
                    "budget_range": profile.budget_range,
                    "preferred_destinations": profile.preferred_destinations or [],
                    "travel_style": profile.travel_style,
                    "constraints": profile.constraints or {},
                    "raw_preferences": profile.raw_preferences or {},
                    "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
                },
            )
        except Exception as exc:
            return ToolResult(success=False, data=None, error=str(exc))


class UpdateClientProfileTool(BaseTool):
    name = "update_client_profile"

    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def execute(  # type: ignore[override]
        self,
        client_id: str | UUID,
        budget_range: dict | None = None,
        preferred_destinations: list | None = None,
        travel_style: str | None = None,
        constraints: dict | None = None,
        raw_preferences: dict | None = None,
        **_: Any,
    ) -> ToolResult:
        try:
            uid = UUID(str(client_id))
            fields: dict[str, Any] = {}
            if budget_range is not None:
                fields["budget_range"] = budget_range
            if preferred_destinations is not None:
                fields["preferred_destinations"] = preferred_destinations
            if travel_style is not None:
                fields["travel_style"] = travel_style
            if constraints is not None:
                fields["constraints"] = constraints
            if raw_preferences is not None:
                fields["raw_preferences"] = raw_preferences

            if not fields:
                return ToolResult(success=False, data=None, error="Не передано ни одного поля для обновления")

            profile = await clients_repo.upsert_profile(self._pool, uid, **fields)
            return ToolResult(
                success=True,
                data={
                    "id": str(profile.id),
                    "client_id": str(profile.client_id),
                    "updated_at": profile.updated_at.isoformat() if profile.updated_at else None,
                },
            )
        except Exception as exc:
            return ToolResult(success=False, data=None, error=str(exc))
