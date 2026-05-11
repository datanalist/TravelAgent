from __future__ import annotations

import logging
from typing import Any

from src.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ToolExecutor:
    """Диспетчер — вызывает нужный tool по имени."""

    def __init__(self, tools: list[BaseTool]) -> None:
        self._tools: dict[str, BaseTool] = {t.name: t for t in tools}

    @property
    def available_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    async def execute(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        """
        Вызывается из Orchestrator'а.
        Возвращает dict с результатом для добавления в messages как tool-результат.
        При ошибке — {"error": "..."}.
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            error_msg = f"Tool '{tool_name}' не найден. Доступные: {self.available_tool_names}"
            logger.warning(error_msg)
            return {"error": error_msg}

        try:
            result: ToolResult = await tool.execute(**tool_input)
        except Exception as exc:
            error_msg = f"Ошибка выполнения tool '{tool_name}': {exc}"
            logger.exception(error_msg)
            return {"error": error_msg}

        if not result.success:
            return {"error": result.error or f"Tool '{tool_name}' завершился с ошибкой"}

        return {"result": result.data}
