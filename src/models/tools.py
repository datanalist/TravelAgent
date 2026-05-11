from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class SearchParams(BaseModel):
    destination: str
    departure_date_from: str | None = None
    departure_date_to: str | None = None
    duration_nights: int | None = None
    budget_usd: float | None = None
    travelers: int = 2
    hotel_stars: int | None = None
    meal_plan: str | None = None


class Tour(BaseModel):
    id: str
    destination: str
    hotel_name: str
    hotel_stars: int
    price_usd: float
    duration_nights: int
    departure_date: str
    meal_plan: str
    description: str


class ClientProfileUpdate(BaseModel):
    budget_range: dict | None = None
    preferred_destinations: list[str] | None = None
    travel_style: str | None = None
    constraints: str | None = None


class LeadCreate(BaseModel):
    preferences: dict
    idempotency_key: str


class Lead(BaseModel):
    id: UUID
    status: str


class PolicyInfoRequest(BaseModel):
    policy_type: str  # "visa" | "insurance" | "cancellation" | "payment"
    destination: str | None = None
