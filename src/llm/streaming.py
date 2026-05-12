from __future__ import annotations

import json
from typing import AsyncIterator


async def token_stream(provider_stream: AsyncIterator[str]) -> AsyncIterator[dict]:
    """Оборачивает поток токенов провайдера в SSE-совместимые чанки.

    Формат чанков:
        {"token": "текст", "done": false}
        {"token": "", "done": true}   # финальный маркер
    """
    try:
        async for token in provider_stream:
            if token:
                yield {"token": token, "done": False}
    finally:
        yield {"token": "", "done": True}


async def to_sse_lines(provider_stream: AsyncIterator[str]) -> AsyncIterator[str]:
    """Преобразует поток токенов в строки формата SSE (data: ...\\n\\n).

    Для использования в FastAPI StreamingResponse / EventSourceResponse.
    """
    async for chunk in token_stream(provider_stream):
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


async def buffer_full_response(provider_stream: AsyncIterator[str]) -> str:
    """Буферизует весь стрим в строку — для Telegram-канала."""
    parts: list[str] = []
    async for token in provider_stream:
        parts.append(token)
    return "".join(parts)
