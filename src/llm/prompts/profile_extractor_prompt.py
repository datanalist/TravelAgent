from __future__ import annotations

PROFILE_EXTRACTOR_SYSTEM_PROMPT_V1 = """\
Ты — экстрактор профиля клиента. Проанализируй диалог и извлеки структурированную информацию о клиенте.

Верни JSON строго в следующем формате:
{
  "budget_range": {"min": <int или null>, "max": <int или null>, "currency": "USD|RUB|EUR"},
  "preferred_destinations": ["направление1", "направление2"],
  "travel_style": "luxury|adventure|family|beach|cultural|null",
  "constraints": "<строка с ограничениями или пустая строка>",
  "travel_dates": {"from": "<YYYY-MM-DD или null>", "to": "<YYYY-MM-DD или null>"}
}

Правила:
- Если информация не упоминалась в диалоге — используй null (не придумывай)
- budget_range: извлекай из явно названных сумм («бюджет 150к», «до 200 тысяч», «$3000»)
- preferred_destinations: конкретные страны, регионы, курорты
- travel_style: выбирай наиболее подходящий из 5 вариантов или null
- constraints: аллергии, визовые ограничения, предпочтения по авиакомпаниям, дети и т.д.
- travel_dates: только явно названные даты

Отвечай ТОЛЬКО валидным JSON без дополнительного текста.
"""


def build_profile_extractor_messages(conversation_history: list[dict]) -> list[dict]:
    """Строит messages для Profile Updater."""
    messages: list[dict] = [{"role": "system", "content": PROFILE_EXTRACTOR_SYSTEM_PROMPT_V1}]

    history_text = "\n".join(
        f"{msg['role'].upper()}: {msg['content']}"
        for msg in conversation_history
        if msg.get("role") in ("user", "assistant")
    )

    messages.append({
        "role": "user",
        "content": f"Диалог:\n\n{history_text}\n\nИзвлеки профиль клиента в JSON.",
    })
    return messages
