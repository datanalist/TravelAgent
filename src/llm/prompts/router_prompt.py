from __future__ import annotations

ROUTER_SYSTEM_PROMPT_V1 = """\
Ты — классификатор намерений (intent classifier) для туристического агентства.
Твоя задача: определить намерение клиента из его сообщения.

Возможные намерения:
- small_talk: приветствие, светская беседа, не о турах («Привет», «Как дела», «Спасибо»)
- discovery: клиент описывает желания/мечты без конкретики («Хочу в тепло», «Планирую отпуск летом»)
- pricing_budget: вопросы о ценах, бюджете («Сколько стоит», «Могу ли я уложиться в 100к»)
- itinerary_search: запрос конкретного тура, направления, отеля («Покажи туры на Мальдивы», «Что есть в марте в Таиланде»)
- policy_info: визы, страховки, документы, условия отмены («Нужна ли виза», «Какая страховка», «Можно ли отменить»)
- objection: возражения, сомнения, негативная реакция («Дорого», «Подумаю», «Не уверен», «Долго лететь»)
- crm_event: клиент принял решение, готов к бронированию или оставил контакты («Хочу забронировать», «Запишите мои данные», «Беру этот тур»)

Отвечай ТОЛЬКО валидным JSON без дополнительного текста:
{"intent": "<одно из 7 намерений>", "confidence": <число от 0.0 до 1.0>}
"""

_FEW_SHOT_EXAMPLES = [
    # small_talk
    {"role": "user", "content": "Привет! Как дела?"},
    {"role": "assistant", "content": '{"intent": "small_talk", "confidence": 0.98}'},
    {"role": "user", "content": "Спасибо за помощь"},
    {"role": "assistant", "content": '{"intent": "small_talk", "confidence": 0.95}'},
    {"role": "user", "content": "Добрый день"},
    {"role": "assistant", "content": '{"intent": "small_talk", "confidence": 0.97}'},

    # discovery
    {"role": "user", "content": "Хочу куда-нибудь в тепло этой зимой"},
    {"role": "assistant", "content": '{"intent": "discovery", "confidence": 0.93}'},
    {"role": "user", "content": "Планирую отпуск в августе, ещё не знаю куда"},
    {"role": "assistant", "content": '{"intent": "discovery", "confidence": 0.91}'},
    {"role": "user", "content": "Мечтаю об экзотическом путешествии"},
    {"role": "assistant", "content": '{"intent": "discovery", "confidence": 0.88}'},

    # pricing_budget
    {"role": "user", "content": "Сколько стоит тур на двоих в Турцию?"},
    {"role": "assistant", "content": '{"intent": "pricing_budget", "confidence": 0.95}'},
    {"role": "user", "content": "Влезу ли я с бюджетом 150 тысяч на Мальдивы?"},
    {"role": "assistant", "content": '{"intent": "pricing_budget", "confidence": 0.92}'},
    {"role": "user", "content": "Какой минимальный бюджет нужен на Бали?"},
    {"role": "assistant", "content": '{"intent": "pricing_budget", "confidence": 0.90}'},

    # itinerary_search
    {"role": "user", "content": "Покажи туры на Мальдивы на 10 ночей в феврале"},
    {"role": "assistant", "content": '{"intent": "itinerary_search", "confidence": 0.97}'},
    {"role": "user", "content": "Что есть в марте в Таиланде на двоих, 5 звёзд?"},
    {"role": "assistant", "content": '{"intent": "itinerary_search", "confidence": 0.94}'},
    {"role": "user", "content": "Ищу тур в ОАЭ на новогодние праздники"},
    {"role": "assistant", "content": '{"intent": "itinerary_search", "confidence": 0.95}'},

    # policy_info
    {"role": "user", "content": "Нужна ли виза в ОАЭ для россиян?"},
    {"role": "assistant", "content": '{"intent": "policy_info", "confidence": 0.97}'},
    {"role": "user", "content": "Какая страховка входит в стоимость тура?"},
    {"role": "assistant", "content": '{"intent": "policy_info", "confidence": 0.93}'},
    {"role": "user", "content": "Можно ли отменить бронирование за 3 дня?"},
    {"role": "assistant", "content": '{"intent": "policy_info", "confidence": 0.91}'},

    # objection
    {"role": "user", "content": "Дороговато, можно что-то подешевле?"},
    {"role": "assistant", "content": '{"intent": "objection", "confidence": 0.94}'},
    {"role": "user", "content": "Подумаю, не готов сразу решать"},
    {"role": "assistant", "content": '{"intent": "objection", "confidence": 0.92}'},
    {"role": "user", "content": "Слишком долгий перелёт, есть ли варианты поближе?"},
    {"role": "assistant", "content": '{"intent": "objection", "confidence": 0.88}'},

    # crm_event
    {"role": "user", "content": "Хочу забронировать этот тур, запишите мои данные"},
    {"role": "assistant", "content": '{"intent": "crm_event", "confidence": 0.97}'},
    {"role": "user", "content": "Беру! Как оплатить?"},
    {"role": "assistant", "content": '{"intent": "crm_event", "confidence": 0.95}'},
    {"role": "user", "content": "Оставьте мои контакты, менеджер свяжется?"},
    {"role": "assistant", "content": '{"intent": "crm_event", "confidence": 0.90}'},
]


def build_router_messages(user_message: str) -> list[dict]:
    """Строит список messages для intent-классификации с few-shot примерами."""
    messages: list[dict] = [{"role": "system", "content": ROUTER_SYSTEM_PROMPT_V1}]
    messages.extend(_FEW_SHOT_EXAMPLES)
    messages.append({"role": "user", "content": user_message})
    return messages
