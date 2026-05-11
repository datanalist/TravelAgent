from __future__ import annotations

"""Integration-тесты Telegram-канала: normalize_update + handle_message E2E."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from src.channels.telegram import normalize_update, handle_message
from src.models.chat import ChatRequest
from src.memory.models import Client, Session


# ---------------------------------------------------------------------------
# Хелперы
# ---------------------------------------------------------------------------

def _make_update(text: str | None = "Привет", user_id: int = 12345, chat_id: int = 12345):
    """Создаёт mock Telegram Update с нужными полями."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = user_id
    update.effective_chat = MagicMock()
    update.effective_chat.id = chat_id
    update.message = MagicMock()
    update.message.text = text
    return update


def _make_client(telegram_id: int = 12345) -> Client:
    now = datetime.now(timezone.utc)
    return Client(
        id=uuid4(),
        telegram_id=telegram_id,
        source="telegram",
        name=None,
        email=None,
        phone=None,
        segment=None,
        language=None,
        preferred_style=None,
        created_at=now,
        updated_at=now,
    )


def _make_session(client_id=None) -> Session:
    now = datetime.now(timezone.utc)
    return Session(
        id=uuid4(),
        client_id=client_id or uuid4(),
        channel="telegram",
        started_at=now,
        last_active_at=now,
        current_stage="cold",
        summary=None,
        message_count=0,
        status="active",
    )


# ---------------------------------------------------------------------------
# normalize_update
# ---------------------------------------------------------------------------

def test_normalize_text_message():
    """Update с text → ChatRequest с правильными полями."""
    update = _make_update(text="Хочу на Мальдивы", user_id=99999)
    result = normalize_update(update)

    assert result is not None
    assert isinstance(result, ChatRequest)
    assert result.message == "Хочу на Мальдивы"
    assert result.telegram_id == 99999
    assert result.channel == "telegram"


def test_normalize_non_text_returns_none():
    """Update без текста (фото, стикер) → None."""
    update = _make_update(text=None)
    result = normalize_update(update)
    assert result is None


def test_normalize_missing_user_returns_none():
    """Update без effective_user → None."""
    update = MagicMock()
    update.effective_user = None
    update.message = MagicMock()
    update.message.text = "Привет"
    result = normalize_update(update)
    assert result is None


def test_normalize_missing_message_returns_none():
    """Update без message → None."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.message = None
    result = normalize_update(update)
    assert result is None


# ---------------------------------------------------------------------------
# handle_message
# ---------------------------------------------------------------------------

async def test_handle_message_success(fake_redis):
    """handle_message вызывает process_message и отправляет ответ через bot."""
    client = _make_client()
    session = _make_session(client_id=client.id)

    update = _make_update(text="Ищу тур на море", user_id=client.telegram_id)
    context = MagicMock()
    context.bot_data = {
        "pool": MagicMock(),
        "redis": fake_redis,
        "connector": MagicMock(),
    }
    context.bot.send_message = AsyncMock()

    with (
        patch("src.channels.telegram.clients_repo.upsert", new_callable=AsyncMock, return_value=client),
        patch("src.channels.telegram.sessions_repo.get_active", new_callable=AsyncMock, return_value=session),
        patch("src.channels.telegram.sessions_repo.upsert", new_callable=AsyncMock, return_value=session),
        patch("src.channels.telegram.messages_repo.append", new_callable=AsyncMock, return_value=None),
        patch("src.channels.telegram.sessions_repo.increment_message_count", new_callable=AsyncMock),
        patch("src.channels.telegram.process_message", new_callable=AsyncMock, return_value="Вот подборка туров!"),
    ):
        await handle_message(update, context)

    context.bot.send_message.assert_called_once()
    call_kwargs = context.bot.send_message.call_args
    assert call_kwargs.kwargs.get("text") == "Вот подборка туров!" or call_kwargs.args[1] == "Вот подборка туров!"
    assert call_kwargs.kwargs.get("chat_id") == update.effective_chat.id


async def test_handle_message_orchestrator_error(fake_redis):
    """process_message бросает исключение → bot.send_message вызван с graceful fallback."""
    client = _make_client()
    session = _make_session(client_id=client.id)

    update = _make_update(text="Привет", user_id=client.telegram_id)
    context = MagicMock()
    context.bot_data = {
        "pool": MagicMock(),
        "redis": fake_redis,
        "connector": MagicMock(),
    }
    context.bot.send_message = AsyncMock()

    with (
        patch("src.channels.telegram.clients_repo.upsert", new_callable=AsyncMock, return_value=client),
        patch("src.channels.telegram.sessions_repo.get_active", new_callable=AsyncMock, return_value=session),
        patch("src.channels.telegram.sessions_repo.upsert", new_callable=AsyncMock, return_value=session),
        patch("src.channels.telegram.messages_repo.append", new_callable=AsyncMock, return_value=None),
        patch("src.channels.telegram.sessions_repo.increment_message_count", new_callable=AsyncMock),
        patch(
            "src.channels.telegram.process_message",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB connection lost"),
        ),
    ):
        await handle_message(update, context)

    context.bot.send_message.assert_called_once()
    sent_text = context.bot.send_message.call_args.kwargs.get("text", "")
    # Клиент не видит traceback, получает понятное сообщение
    assert "RuntimeError" not in sent_text
    assert "DB connection lost" not in sent_text
    assert len(sent_text) > 0


async def test_handle_message_non_text_ignored(fake_redis):
    """Нетекстовые сообщения (фото) игнорируются; bot.send_message не вызывается."""
    update = _make_update(text=None)
    context = MagicMock()
    context.bot.send_message = AsyncMock()

    await handle_message(update, context)

    context.bot.send_message.assert_not_called()
