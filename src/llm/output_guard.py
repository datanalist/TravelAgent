from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)

# Паттерны, сигнализирующие об утечке system prompt в ответе
_LEAK_PATTERNS: list[re.Pattern] = [
    re.compile(r"ты\s+агент", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"твои\s+инструкции", re.IGNORECASE),
    re.compile(r"не\s+раскрывай", re.IGNORECASE),
    re.compile(r"ignore\s+previous", re.IGNORECASE),
    re.compile(r"моя\s+роль", re.IGNORECASE),
    re.compile(r"я\s+настроен\s+(как|быть)", re.IGNORECASE),
]

# Паттерны признаков jailbreak / prompt-injection в ответе LLM
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+all\s+(previous|prior)\s+instructions", re.IGNORECASE),
    re.compile(r"disregard\s+(your|the)\s+(instructions|rules)", re.IGNORECASE),
    re.compile(r"pretend\s+you\s+are", re.IGNORECASE),
    re.compile(r"act\s+as\s+if\s+you\s+(have\s+no|don)", re.IGNORECASE),
]

_CHARS_PER_TOKEN_APPROX = 3.5


class OutputGuardError(ValueError):
    """Ответ LLM заблокирован из-за критической утечки system prompt."""


def validate_output(text: str, max_tokens: int = 2000) -> str:
    """Проверяет и очищает ответ LLM.

    1. Проверяет на признаки утечки system prompt — если найдено, поднимает OutputGuardError.
    2. Проверяет на признаки jailbreak/prompt-injection — логирует предупреждение.
    3. Обрезает до max_tokens (приближённо по символам).
    """
    # Проверка утечки system prompt
    for pattern in _LEAK_PATTERNS:
        if pattern.search(text):
            logger.error(
                "OutputGuard: обнаружена потенциальная утечка system prompt, паттерн=%s",
                pattern.pattern,
            )
            raise OutputGuardError(
                "Ответ заблокирован: обнаружена утечка содержимого системного промпта."
            )

    # Проверка признаков injection в ответе
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            logger.warning(
                "OutputGuard: признаки prompt-injection в ответе LLM, паттерн=%s",
                pattern.pattern,
            )

    # Обрезка по приближённому числу символов
    max_chars = int(max_tokens * _CHARS_PER_TOKEN_APPROX)
    if len(text) > max_chars:
        logger.warning(
            "OutputGuard: ответ обрезан с %d до %d символов (~%d токенов)",
            len(text),
            max_chars,
            max_tokens,
        )
        text = text[:max_chars]

    return text
