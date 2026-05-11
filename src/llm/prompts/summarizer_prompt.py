from __future__ import annotations

SUMMARIZER_SYSTEM_PROMPT_V1 = """\
Ты — ассистент по сжатию диалогов. Проанализируй предоставленный диалог между клиентом и AI-консьержем \
туристического агентства.

Извлеки и верни структурированное JSON-резюме строго в следующем формате:
{
  "client_facts": ["факт о клиенте 1", "факт 2", ...],
  "current_request": "краткое описание текущего запроса клиента",
  "stage": "discovery|qualified|proposal|negotiation",
  "last_shown_tours": ["tour_id_1", "tour_id_2"]
}

Требования:
- client_facts: 3–5 ключевых факта о клиенте (бюджет, направления, стиль, ограничения, даты)
- current_request: одно предложение, описывающее актуальный запрос
- stage: текущая стадия ('discovery' — выясняем потребности, 'qualified' — знаем бюджет и направление, \
'proposal' — предложили варианты, 'negotiation' — работаем с возражениями)
- last_shown_tours: идентификаторы туров, если они были показаны клиенту (иначе пустой массив)

Отвечай ТОЛЬКО валидным JSON без дополнительного текста.
"""


def build_summarizer_messages(conversation_history: list[dict]) -> list[dict]:
    """Строит messages для Conversation Summarizer.

    conversation_history: список сообщений [{role: user|assistant, content: str}]
    """
    messages: list[dict] = [{"role": "system", "content": SUMMARIZER_SYSTEM_PROMPT_V1}]

    history_text = "\n".join(
        f"{msg['role'].upper()}: {msg['content']}"
        for msg in conversation_history
        if msg.get("role") in ("user", "assistant")
    )

    messages.append({
        "role": "user",
        "content": f"Диалог для анализа:\n\n{history_text}\n\nСожми в структурированное JSON-резюме.",
    })
    return messages
