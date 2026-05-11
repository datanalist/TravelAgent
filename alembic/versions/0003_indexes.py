"""Add performance and uniqueness indexes

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-11

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # clients: быстрый поиск по telegram_id (уникальность уже задана через UniqueConstraint в 0001)
    op.create_index(
        "ix_clients_telegram_id",
        "clients",
        ["telegram_id"],
        unique=True,
        postgresql_where="telegram_id IS NOT NULL",
    )

    # client_profile: FK-индекс (PostgreSQL не создаёт автоматически)
    op.create_index("ix_client_profile_client_id", "client_profile", ["client_id"])

    # GIN-индекс на JSONB-поля client_profile для поиска по бюджету и направлениям
    op.create_index(
        "ix_client_profile_budget_range_gin",
        "client_profile",
        ["budget_range"],
        postgresql_using="gin",
    )
    op.create_index(
        "ix_client_profile_preferred_destinations_gin",
        "client_profile",
        ["preferred_destinations"],
        postgresql_using="gin",
    )

    # sessions: сортировка по убыванию для get_active()
    op.create_index(
        "ix_sessions_client_id_started_at",
        "sessions",
        ["client_id", "started_at"],
        postgresql_ops={"started_at": "DESC"},
    )
    # Partial-индекс для фильтрации активных сессий
    op.create_index(
        "ix_sessions_active",
        "sessions",
        ["client_id", "channel", "started_at"],
        postgresql_where="status = 'active'",
    )
    # Retention: быстрый поиск устаревших сессий
    op.create_index("ix_sessions_last_active_at", "sessions", ["last_active_at"])

    # messages: хронологическая выборка по сессии
    op.create_index("ix_messages_session_id_created_at", "messages", ["session_id", "created_at"])

    # leads: FK-индексы и уникальность idempotency_key
    op.create_index("ix_leads_client_id", "leads", ["client_id"])
    op.create_index("ix_leads_session_id", "leads", ["session_id"])
    # idempotency_key уже покрыт UniqueConstraint из 0001, дополнительный индекс не нужен

    # GIN-индекс на leads.preferences для JSONB-поиска
    op.create_index(
        "ix_leads_preferences_gin",
        "leads",
        ["preferences"],
        postgresql_using="gin",
    )

    # itineraries: FK-индекс
    op.create_index("ix_itineraries_lead_id", "itineraries", ["lead_id"])

    # interactions: FK-индекс + retention
    op.create_index("ix_interactions_session_id", "interactions", ["session_id"])
    op.create_index("ix_interactions_created_at", "interactions", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_interactions_created_at", table_name="interactions")
    op.drop_index("ix_interactions_session_id", table_name="interactions")
    op.drop_index("ix_itineraries_lead_id", table_name="itineraries")
    op.drop_index("ix_leads_preferences_gin", table_name="leads")
    op.drop_index("ix_leads_session_id", table_name="leads")
    op.drop_index("ix_leads_client_id", table_name="leads")
    op.drop_index("ix_messages_session_id_created_at", table_name="messages")
    op.drop_index("ix_sessions_last_active_at", table_name="sessions")
    op.drop_index("ix_sessions_active", table_name="sessions")
    op.drop_index("ix_sessions_client_id_started_at", table_name="sessions")
    op.drop_index("ix_client_profile_preferred_destinations_gin", table_name="client_profile")
    op.drop_index("ix_client_profile_budget_range_gin", table_name="client_profile")
    op.drop_index("ix_client_profile_client_id", table_name="client_profile")
    op.drop_index("ix_clients_telegram_id", table_name="clients")
