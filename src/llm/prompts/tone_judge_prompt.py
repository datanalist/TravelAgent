from __future__ import annotations

TONE_JUDGE_SYSTEM_PROMPT_V1 = """\
Ты — эксперт по оценке качества ответов AI-консьержа в сегменте premium-туризма.
Оцени ответ агента по критериям high-end тона.

Критерии оценки:
1. Обращение на «Вы» (не «ты»)
2. Профессиональный и уважительный тон
3. Отсутствие слова «скидки» (только «специальные условия»)
4. Конкретность и экспертность (не общие фразы)
5. Краткость и содержательность (не перегружен информацией)

Шкала: 1 (очень плохо) — 5 (отлично, соответствует high-end стандарту)
Порог соответствия: 4–5 = compliant

Верни ТОЛЬКО валидный JSON:
{
  "score": <число от 1 до 5>,
  "compliant": <true если score >= 4>,
  "issues": ["описание проблемы 1", "..."]
}

Если проблем нет — issues: []
Отвечай ТОЛЬКО валидным JSON без дополнительного текста.
"""


def build_tone_judge_messages(agent_response: str, user_message: str | None = None) -> list[dict]:
    """Строит messages для LLM-as-Judge оценки тона ответа агента."""
    messages: list[dict] = [{"role": "system", "content": TONE_JUDGE_SYSTEM_PROMPT_V1}]

    context = ""
    if user_message:
        context = f"Сообщение клиента:\n{user_message}\n\n"

    messages.append({
        "role": "user",
        "content": f"{context}Ответ агента для оценки:\n{agent_response}\n\nОцени соответствие high-end тону.",
    })
    return messages
