from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class Client:
    id: UUID
    telegram_id: int | None
    source: str
    name: str | None
    email: str | None
    phone: str | None
    segment: str | None
    language: str | None
    preferred_style: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ClientProfile:
    id: UUID
    client_id: UUID
    budget_range: dict | None
    preferred_destinations: list | None
    travel_style: str | None
    constraints: dict | None
    raw_preferences: dict | None
    updated_at: datetime


@dataclass(frozen=True)
class Session:
    id: UUID
    client_id: UUID
    channel: str
    started_at: datetime
    last_active_at: datetime
    current_stage: str
    summary: dict | None
    message_count: int
    status: str


@dataclass(frozen=True)
class Message:
    id: UUID
    session_id: UUID
    role: str
    content: str
    metadata: dict | None
    created_at: datetime


@dataclass(frozen=True)
class Lead:
    id: UUID
    client_id: UUID
    session_id: UUID
    status: str
    preferences: dict | None
    idempotency_key: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class Itinerary:
    id: UUID
    lead_id: UUID
    options: list
    chosen_option: dict | None
    created_at: datetime


@dataclass(frozen=True)
class Interaction:
    id: UUID
    session_id: UUID
    tool_name: str
    input: dict
    output: dict
    created_at: datetime
