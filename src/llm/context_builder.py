from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN_APPROX = 3.5
_COMPRESS_THRESHOLD_TOKENS = 12_000
_EMERGENCY_THRESHOLD_TOKENS = 15_500
_MAX_RECENT_MESSAGES = 5
_MIN_RECENT_MESSAGES = 1


def _estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / _CHARS_PER_TOKEN_APPROX))


def _messages_tokens(messages: list[dict]) -> int:
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += _estimate_tokens(content)
        elif isinstance(content, (dict, list)):
            total += _estimate_tokens(json.dumps(content, ensure_ascii=False))
    return total


def build_messages(
    system_prompt: str,
    client_profile: dict | None,
    conversation_summary: dict | None,
    recent_messages: list[dict],
    current_message: str,
) -> list[dict]:
    """Собирает список messages для LLM в правильном порядке.

    Порядок: [system] → [profile] → [summary] → [recent 3-5] → [current]

    Стратегия усечения:
    - > 12K токенов: убираем старые recent_messages (оставляем минимум 1)
    - > 15.5K токенов: убираем conversation_summary
    """
    messages: list[dict] = []

    # 1. System prompt
    messages.append({"role": "system", "content": system_prompt})

    # 2. Профиль клиента (как system-контекст)
    if client_profile:
        profile_text = "Профиль клиента:\n" + json.dumps(client_profile, ensure_ascii=False, indent=2)
        messages.append({"role": "system", "content": profile_text})

    # 3. Сводка диалога
    summary_msg: dict | None = None
    if conversation_summary:
        summary_text = "Сводка предыдущего диалога:\n" + json.dumps(
            conversation_summary, ensure_ascii=False, indent=2
        )
        summary_msg = {"role": "system", "content": summary_text}
        messages.append(summary_msg)

    # 4. Последние сообщения (усечение при необходимости)
    capped_recent = recent_messages[-_MAX_RECENT_MESSAGES:]

    for msg in capped_recent:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # 5. Текущее сообщение пользователя
    messages.append({"role": "user", "content": current_message})

    # Проверяем общий объём
    total_tokens = _messages_tokens(messages)

    if total_tokens > _COMPRESS_THRESHOLD_TOKENS:
        logger.warning(
            "Context window: %d tokens > 12K, начинаем сжатие recent_messages",
            total_tokens,
        )
        # Убираем старые recent по одному
        base_msgs_count = len(messages) - len(capped_recent) - 1  # без recent и current
        while len(capped_recent) > _MIN_RECENT_MESSAGES:
            capped_recent = capped_recent[1:]
            rebuilt = list(messages[:base_msgs_count])
            for msg in capped_recent:
                rebuilt.append({"role": msg["role"], "content": msg["content"]})
            rebuilt.append({"role": "user", "content": current_message})
            total_tokens = _messages_tokens(rebuilt)
            messages = rebuilt
            if total_tokens <= _COMPRESS_THRESHOLD_TOKENS:
                break

    total_tokens = _messages_tokens(messages)
    if total_tokens > _EMERGENCY_THRESHOLD_TOKENS and summary_msg is not None:
        logger.warning(
            "Context window: %d tokens > 15.5K, убираем conversation_summary",
            total_tokens,
        )
        messages = [m for m in messages if m is not summary_msg]

    return messages
