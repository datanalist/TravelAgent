"""Initial schema: clients, client_profile, sessions, messages, leads, itineraries

Revision ID: 0001
Revises:
Create Date: 2026-05-11

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("segment", sa.String(), nullable=True),
        sa.Column("language", sa.String(5), nullable=True),
        sa.Column("preferred_style", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("source IN ('telegram', 'web')", name="clients_source_check"),
        sa.CheckConstraint(
            "segment IS NULL OR segment IN ('high_end', 'mid', 'mass')",
            name="clients_segment_check",
        ),
        sa.CheckConstraint(
            "preferred_style IS NULL OR preferred_style IN ('formal', 'friendly', 'casual')",
            name="clients_preferred_style_check",
        ),
    )

    op.create_table(
        "client_profile",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("budget_range", postgresql.JSONB(), nullable=True),
        sa.Column("preferred_destinations", postgresql.JSONB(), nullable=True),
        sa.Column("travel_style", sa.String(), nullable=True),
        sa.Column("constraints", postgresql.JSONB(), nullable=True),
        sa.Column("raw_preferences", postgresql.JSONB(), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # 1:1 с clients — один профиль на клиента
        sa.UniqueConstraint("client_id", name="uq_client_profile_client_id"),
    )

    op.create_table(
        "sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", sa.String(), nullable=False),
        sa.Column(
            "started_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_active_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("current_stage", sa.String(), nullable=False, server_default="cold"),
        sa.Column("summary", postgresql.JSONB(), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(), nullable=False, server_default="active"),
        sa.CheckConstraint("channel IN ('telegram', 'web')", name="sessions_channel_check"),
        sa.CheckConstraint(
            "status IN ('active', 'closed', 'expired', 'follow_up')",
            name="sessions_status_check",
        ),
        sa.CheckConstraint(
            "current_stage IN ('cold', 'discovery', 'qualified', 'proposal', 'objection', 'closing', 'follow_up')",
            name="sessions_stage_check",
        ),
    )

    op.create_table(
        "messages",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "role IN ('user', 'assistant', 'tool')",
            name="messages_role_check",
        ),
    )

    op.create_table(
        "leads",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "client_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("clients.id"),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False, server_default="new"),
        sa.Column("preferences", postgresql.JSONB(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('new', 'proposal', 'contacted', 'won', 'lost')",
            name="leads_status_check",
        ),
        sa.UniqueConstraint("idempotency_key", name="uq_leads_idempotency_key"),
    )

    op.create_table(
        "itineraries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "lead_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("leads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("options", postgresql.JSONB(), nullable=False, server_default="'[]'::jsonb"),
        sa.Column("chosen_option", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("itineraries")
    op.drop_table("leads")
    op.drop_table("messages")
    op.drop_table("sessions")
    op.drop_table("client_profile")
    op.drop_table("clients")
