from __future__ import annotations

"""
Telegram Bot webhook handler для TravelAgent.
Нормализует Update → ChatRequest → вызывает Orchestrator → отправляет ответ.
"""

import logging

from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters

from src.memory.repositories import clients as clients_repo
from src.memory.repositories import messages as messages_repo
from src.memory.repositories import sessions as sessions_repo
from src.models.chat import ChatRequest
from src.orchestrator import process_message

logger = logging.getLogger(__name__)

_ERROR_MESSAGE = "Произошла техническая ошибка. Пожалуйста, попробуйте ещё раз."


def normalize_update(update: Update) -> ChatRequest | None:
    """Извлекает текстовое сообщение из Update и возвращает ChatRequest.

    Возвращает None для нетекстовых сообщений (фото, стикеры, голосовые и т.д.).
    """
    if (
        update.effective_user is None
        or update.message is None
        or update.message.text is None
    ):
        return None

    return ChatRequest(
        message=update.message.text,
        telegram_id=update.effective_user.id,
        channel="telegram",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """PTB MessageHandler: нормализует → Orchestrator → отправляет ответ."""
    chat_request = normalize_update(update)
    if chat_request is None:
        return

    pool = context.bot_data["pool"]
    redis = context.bot_data["redis"]
    connector = context.bot_data["connector"]

    assert update.effective_chat is not None
    chat_id = update.effective_chat.id

    try:
        # Резолв/создание клиента по telegram_id
        assert chat_request.telegram_id is not None
        client = await clients_repo.upsert(pool, chat_request.telegram_id, "telegram")

        # Получение или создание активной сессии
        session = await sessions_repo.get_active(pool, client.id, "telegram")
        if session is None:
            session = await sessions_repo.upsert(pool, client.id, "telegram")

        # Сохранение user-сообщения
        await messages_repo.append(
            pool, session.id, role="user", content=chat_request.message
        )
        await sessions_repo.increment_message_count(pool, session.id)

        async def _stub_executor(tool_name: str, tool_input: dict) -> dict:
            logger.warning("telegram: tool=%r вызван, но src/tools/ не реализован", tool_name)
            return {"error": f"Tool '{tool_name}' is not yet implemented"}

        reply = await process_message(
            message=chat_request.message,
            client_id=client.id,
            session_id=session.id,
            channel="telegram",
            pool=pool,
            redis_client=redis,
            connector=connector,
            tools_executor=_stub_executor,
        )
    except Exception as exc:
        logger.error("telegram handle_message: ошибка обработки: %s", exc)
        reply = _ERROR_MESSAGE

    try:
        await context.bot.send_message(chat_id=chat_id, text=reply, parse_mode="Markdown")
    except Exception as exc:
        logger.error("telegram handle_message: ошибка отправки ответа: %s", exc)


def build_application(bot_token: str) -> Application:
    """Создаёт и конфигурирует PTB Application для webhook-режима."""
    application = Application.builder().token(bot_token).build()
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return application
