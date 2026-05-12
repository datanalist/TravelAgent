from __future__ import annotations

STAGE_CLASSIFIER_SYSTEM_PROMPT_V1 = """\
Ты — классификатор стадии воронки продаж для туристического агентства.
Используется как fallback, когда rule-based Decision Logic не уверен в текущей стадии.

Проанализируй последние сообщения диалога и определи текущую стадию клиента.

Стадии воронки:
- initial: первое обращение, клиент ещё ничего не рассказал
- discovery: выясняем потребности, клиент описывает желания без конкретики
- qualified: знаем бюджет + направление, можно делать поиск туров
- proposal: клиенту уже предложены конкретные варианты туров
- negotiation: клиент работает с возражениями («дорого», «подумаю», «хочу дешевле»)
- booked: клиент принял решение и готов/уже забронировал

Верни ТОЛЬКО валидный JSON:
{"stage": "<одна из 6 стадий>", "confidence": <число от 0.0 до 1.0>, "reasoning": "<одно предложение>"}

Отвечай ТОЛЬКО валидным JSON без дополнительного текста.
"""


def build_stage_classifier_messages(
    recent_messages: list[dict],
    current_summary: dict | None = None,
) -> list[dict]:
    """Строит messages для LLM-fallback классификатора стадии воронки."""
    messages: list[dict] = [{"role": "system", "content": STAGE_CLASSIFIER_SYSTEM_PROMPT_V1}]

    context_parts: list[str] = []
    if current_summary:
        import json
        context_parts.append(
            f"Текущее резюме диалога:\n{json.dumps(current_summary, ensure_ascii=False, indent=2)}"
        )

    history_text = "\n".join(
        f"{msg['role'].upper()}: {msg['content']}"
        for msg in recent_messages[-10:]
        if msg.get("role") in ("user", "assistant")
    )
    context_parts.append(f"Последние сообщения:\n{history_text}")

    messages.append({
        "role": "user",
        "content": "\n\n".join(context_parts) + "\n\nОпредели текущую стадию воронки.",
    })
    return messages
