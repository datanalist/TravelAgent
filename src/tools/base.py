from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    success: bool
    data: Any
    error: str | None = None


class BaseTool:
    name: str

    async def execute(self, **kwargs: Any) -> ToolResult:
        raise NotImplementedError
