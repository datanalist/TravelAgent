from __future__ import annotations

from typing import Any
from uuid import UUID

from asyncpg import Pool

from src.memory.repositories import leads as leads_repo
from src.tools.base import BaseTool, ToolResult

_VALID_STATUSES = frozenset({"new", "contacted", "qualified", "proposal", "won", "lost"})


class CreateLeadTool(BaseTool):
    name = "create_lead"

    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def execute(  # type: ignore[override]
        self,
        client_id: str | UUID,
        session_id: str | UUID,
        preferences: dict,
        idempotency_key: str,
        **_: Any,
    ) -> ToolResult:
        try:
            lead = await leads_repo.create_idempotent(
                pool=self._pool,
                client_id=UUID(str(client_id)),
                session_id=UUID(str(session_id)),
                preferences=preferences,
                idempotency_key=idempotency_key,
            )
            return ToolResult(
                success=True,
                data={
                    "lead_id": str(lead.id),
                    "client_id": str(lead.client_id),
                    "session_id": str(lead.session_id),
                    "status": lead.status,
                    "created_at": lead.created_at.isoformat() if lead.created_at else None,
                },
            )
        except Exception as exc:
            return ToolResult(success=False, data=None, error=str(exc))


class UpdateLeadStageTool(BaseTool):
    name = "update_lead_stage"

    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def execute(  # type: ignore[override]
        self,
        lead_id: str | UUID,
        status: str,
        **_: Any,
    ) -> ToolResult:
        if status not in _VALID_STATUSES:
            return ToolResult(
                success=False,
                data=None,
                error=f"Недопустимый статус '{status}'. Допустимые: {sorted(_VALID_STATUSES)}",
            )
        try:
            lead = await leads_repo.update_stage(
                pool=self._pool,
                lead_id=UUID(str(lead_id)),
                status=status,
            )
            return ToolResult(
                success=True,
                data={
                    "lead_id": str(lead.id),
                    "status": lead.status,
                    "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
                },
            )
        except Exception as exc:
            return ToolResult(success=False, data=None, error=str(exc))
