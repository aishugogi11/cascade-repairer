"""Pydantic models and status enums for the six BigQuery tables.

Schema source of truth: specs/tech-stack.md § Schema (BigQuery). Statuses are
validated here (Literal types) — BigQuery has no enum type, so the repository
boundary is where an invalid status fails fast.
"""
import json
from datetime import date, datetime
from typing import List, Literal, Optional, Type, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field, TypeAdapter, field_validator

TripStatus = Literal["draft", "booked", "active", "complete"]
ItemType = Literal["flight", "hotel", "ground", "dining", "experience"]
# The repair lifecycle — drives the cascade logic and the live itinerary UI.
ItemStatus = Literal["planned", "booked", "broken", "repairing", "fixed", "cancelled"]
Provider = Literal["sabre", "other"]
BookingState = Literal["pending", "confirmed", "cancelled"]
TurnRole = Literal["user", "agent"]
Architecture = Literal["cascaded", "realtime", "concierge"]

ITEM_STATUS_ADAPTER = TypeAdapter(ItemStatus)
TRIP_STATUS_ADAPTER = TypeAdapter(TripStatus)
BOOKING_STATE_ADAPTER = TypeAdapter(BookingState)


def _parse_json_column(value):
    """BigQuery JSON columns come back as parsed objects from the live client
    but as JSON strings from some paths/mocks — accept both."""
    if isinstance(value, str):
        return json.loads(value)
    return value


class Trip(BaseModel):
    trip_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    title: str
    status: TripStatus = "draft"
    origin: Optional[str] = None
    destinations: List[str] = Field(default_factory=list)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    created_at: Optional[datetime] = None  # stamped by BigQuery on insert


class ItineraryItem(BaseModel):
    item_id: str = Field(default_factory=lambda: str(uuid4()))
    trip_id: str
    type: ItemType
    status: ItemStatus = "planned"
    provider: Provider = "other"
    provider_ref: Optional[str] = None
    start_ts: Optional[datetime] = None
    end_ts: Optional[datetime] = None
    location: Optional[str] = None
    details: Optional[dict] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    updated_at: Optional[datetime] = None  # stamped by BigQuery on every write

    @field_validator("details", mode="before")
    @classmethod
    def _details_from_json(cls, v):
        return _parse_json_column(v)


class Booking(BaseModel):
    booking_id: str = Field(default_factory=lambda: str(uuid4()))
    item_id: str
    trip_id: str
    sabre_confirmation_ref: Optional[str] = None
    state: BookingState = "pending"
    booked_at: Optional[datetime] = None  # stamped by BigQuery on insert
    raw_response: Optional[dict] = None

    @field_validator("raw_response", mode="before")
    @classmethod
    def _raw_response_from_json(cls, v):
        return _parse_json_column(v)


class Session(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    trip_id: Optional[str] = None
    architecture: Architecture
    client: str = "vb_web"
    started_at: Optional[datetime] = None  # stamped by BigQuery on insert
    ended_at: Optional[datetime] = None


class Turn(BaseModel):
    turn_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    role: TurnRole
    transcript: Optional[str] = None
    audio_gcs_uri: Optional[str] = None
    started_at: Optional[datetime] = None  # defaults to insert time in SQL
    ttfb_ms: Optional[int] = None
    duration_ms: Optional[int] = None


class EvalRun(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    architecture: Architecture
    git_sha: Optional[str] = None
    scenario: Optional[str] = None
    ttfb_ms: Optional[float] = None
    e2e_latency_ms: Optional[float] = None
    wer: Optional[float] = None
    mos_estimate: Optional[float] = None
    notes: Optional[str] = None
    run_at: Optional[datetime] = None  # defaults to insert time in SQL


class TripWithItems(BaseModel):
    trip: Trip
    items: List[ItineraryItem] = Field(default_factory=list)


M = TypeVar("M", bound=BaseModel)


def rows_to_models(model_cls: Type[M], rows: list) -> List[M]:
    """Map BigQuery row dicts (from run_select) into models."""
    return [model_cls.model_validate(dict(row)) for row in rows]
