from __future__ import annotations

TOOLS: list[dict] = [
    {
        "name": "search_tours",
        "description": (
            "Поиск туров по параметрам клиента. "
            "Используй когда клиент готов к конкретному предложению."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "destination": {
                    "type": "string",
                    "description": "Направление (страна, регион, курорт)",
                },
                "departure_date_from": {
                    "type": "string",
                    "description": "Дата отъезда от (ISO 8601, например 2026-02-01)",
                },
                "departure_date_to": {
                    "type": "string",
                    "description": "Дата отъезда до (ISO 8601)",
                },
                "duration_nights": {
                    "type": "integer",
                    "description": "Продолжительность в ночах",
                },
                "budget_usd": {
                    "type": "number",
                    "description": "Бюджет в USD",
                },
                "travelers": {
                    "type": "integer",
                    "description": "Количество путешественников",
                },
                "hotel_stars": {
                    "type": "integer",
                    "enum": [3, 4, 5],
                    "description": "Категория отеля (звёзды)",
                },
                "meal_plan": {
                    "type": "string",
                    "enum": ["BB", "HB", "FB", "AI"],
                    "description": "Тип питания: BB-завтрак, HB-полупансион, FB-полный пансион, AI-всё включено",
                },
            },
            "required": ["destination"],
        },
    },
    {
        "name": "get_client_profile",
        "description": (
            "Получить сохранённый профиль клиента: предпочтения, бюджет, стиль путешествий. "
            "Используй в начале диалога для персонализации."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "update_client_profile",
        "description": (
            "Обновить профиль клиента на основе новой информации из диалога. "
            "Вызывай после уточнения бюджета, направлений или стиля путешествий."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "budget_range": {
                    "type": "object",
                    "description": "Бюджетный диапазон: {\"min\": int, \"max\": int, \"currency\": str}",
                },
                "preferred_destinations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Список предпочтительных направлений",
                },
                "travel_style": {
                    "type": "string",
                    "description": "Стиль путешествий: luxury, adventure, family, beach, cultural",
                },
                "constraints": {
                    "type": "string",
                    "description": "Ограничения и пожелания: аллергии, визовые вопросы, даты, авиакомпании",
                },
            },
            "required": [],
        },
    },
    {
        "name": "create_lead",
        "description": (
            "Создать лид в CRM когда клиент проявил конкретный интерес к туру или готов к бронированию."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "preferences": {
                    "type": "object",
                    "description": "Предпочтения клиента: направление, даты, бюджет, количество человек",
                },
                "idempotency_key": {
                    "type": "string",
                    "description": "Уникальный ключ для предотвращения дублирования лида",
                },
            },
            "required": ["preferences", "idempotency_key"],
        },
    },
    {
        "name": "update_lead_stage",
        "description": "Обновить стадию лида в воронке продаж при смене статуса клиента.",
        "input_schema": {
            "type": "object",
            "properties": {
                "lead_id": {
                    "type": "string",
                    "description": "Идентификатор лида",
                },
                "status": {
                    "type": "string",
                    "enum": ["new", "qualified", "proposal_sent", "negotiation", "booked", "lost"],
                    "description": "Новый статус лида",
                },
            },
            "required": ["lead_id", "status"],
        },
    },
    {
        "name": "get_policy_info",
        "description": (
            "Получить информацию о политиках агентства: визовые требования, страховки, "
            "условия отмены и оплаты."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "policy_type": {
                    "type": "string",
                    "enum": ["visa", "insurance", "cancellation", "payment"],
                    "description": "Тип политики",
                },
                "destination": {
                    "type": "string",
                    "description": "Направление для уточнения визовых требований",
                },
            },
            "required": ["policy_type"],
        },
    },
]

_TOOLS_BY_NAME: dict[str, dict] = {t["name"]: t for t in TOOLS}


def get_tools_for(tool_names: list[str]) -> list[dict]:
    """Возвращает схемы только для указанных tools (фильтр по available_tools от Decision Logic)."""
    return [_TOOLS_BY_NAME[name] for name in tool_names if name in _TOOLS_BY_NAME]
