"""In-memory trips when BigQuery is unavailable (WhatsApp PDF ingest).

The dict is the live store. On the demo server it is also mirrored to a JSON
file under backend/.data so uvicorn --reload does not wipe a WhatsApp trip
the traveler still has open. Tests never read or write that file.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from api.repositories.models import (
    ITEM_STATUS_ADAPTER,
    Booking,
    ItineraryItem,
    Trip,
    TripWithItems,
)

logger = logging.getLogger(__name__)

_STORE: Dict[str, TripWithItems] = {}
_BOOKINGS: Dict[str, List[Booking]] = {}


def _should_persist() -> bool:
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    if "pytest" in sys.modules:
        return False
    return True


def _store_path() -> Path:
    override = os.environ.get("MEMORY_TRIPS_PATH", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent.parent / ".data" / "memory_trips.json"


def _save() -> None:
    if not _should_persist():
        return
    path = _store_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "trips": [
                {
                    "trip": view.trip.model_dump(mode="json"),
                    "items": [item.model_dump(mode="json") for item in view.items],
                }
                for view in _STORE.values()
            ],
            "bookings": {
                trip_id: [booking.model_dump(mode="json") for booking in rows]
                for trip_id, rows in _BOOKINGS.items()
            },
        }
        path.write_text(json.dumps(payload), encoding="utf-8")
    except Exception:  # noqa: BLE001 — never block a booking on disk
        logger.exception("memory_trips save failed")


def _load() -> None:
    if not _should_persist():
        return
    path = _store_path()
    if not path.is_file():
        return
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        logger.exception("memory_trips load failed")
        return
    _STORE.clear()
    _BOOKINGS.clear()
    for row in payload.get("trips") or []:
        try:
            trip = Trip.model_validate(row.get("trip") or {})
            items = [
                ItineraryItem.model_validate(item) for item in (row.get("items") or [])
            ]
            _STORE[trip.trip_id] = TripWithItems(trip=trip, items=items)
        except Exception:  # noqa: BLE001 — skip a bad row, keep the rest
            logger.exception("memory_trips skipped a corrupt trip row")
    for trip_id, rows in (payload.get("bookings") or {}).items():
        try:
            _BOOKINGS[trip_id] = [Booking.model_validate(row) for row in rows]
        except Exception:  # noqa: BLE001
            logger.exception("memory_trips skipped corrupt bookings for %s", trip_id)


def clear() -> None:
    _STORE.clear()
    _BOOKINGS.clear()


def get(trip_id: str) -> Optional[TripWithItems]:
    return _STORE.get(trip_id)


def list_recent() -> List[Trip]:
    rows = [view.trip for view in _STORE.values()]
    rows.sort(
        key=lambda t: t.created_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return rows


def put(trip: Trip, items: List[ItineraryItem]) -> dict:
    now = datetime.now(timezone.utc)
    if trip.created_at is None:
        trip.created_at = now
    for item in items:
        item.trip_id = trip.trip_id
        if item.updated_at is None:
            item.updated_at = now
    _STORE[trip.trip_id] = TripWithItems(trip=trip, items=list(items))
    _BOOKINGS.setdefault(trip.trip_id, [])
    _save()
    return {
        "trip_id": trip.trip_id,
        "items": [
            {"item_id": i.item_id, "type": i.type, "status": i.status} for i in items
        ],
        "source": "memory",
    }


def ensure_trip(trip: Trip) -> None:
    """Keep a trip row in the store without wiping items already on it."""
    view = _STORE.get(trip.trip_id)
    put(trip, list(view.items) if view else [])


def seed(user_id: str, title: str) -> dict:
    from api.sabre_tools import _SEED_ITEMS

    now = datetime.now(timezone.utc)
    trip = Trip(
        user_id=user_id,
        title=title,
        status="booked",
        origin="MSP",
        destinations=["SFO", "Mountain View"],
        start_date=_SEED_ITEMS[0]["start"].date(),
        end_date=_SEED_ITEMS[-1]["end"].date(),
        created_at=now,
    )
    items: List[ItineraryItem] = []
    for seed_row in _SEED_ITEMS:
        items.append(ItineraryItem(
            trip_id=trip.trip_id,
            type=seed_row["type"],
            status="booked",
            provider=seed_row["provider"],
            provider_ref=f"MEM-{seed_row['type'].upper()}-{uuid.uuid4().hex[:6].upper()}",
            start_ts=seed_row["start"],
            end_ts=seed_row["end"],
            location=seed_row["location"],
            price=seed_row["price"],
            currency="USD",
            updated_at=now,
        ))
    return put(trip, items)


def _find_item(item_id: str) -> Optional[Tuple[str, ItineraryItem]]:
    for trip_id, view in _STORE.items():
        for item in view.items:
            if item.item_id == item_id:
                return trip_id, item
    return None


def update_status(item_id: str, status: str) -> Optional[Tuple[bool, int, Optional[str]]]:
    found = _find_item(item_id)
    if found is None:
        return None
    status = ITEM_STATUS_ADAPTER.validate_python(status)
    trip_id, item = found
    item.status = status
    item.updated_at = datetime.now(timezone.utc)
    _save()
    return True, 1, None


def update_item_fields(
    item_id: str,
    *,
    start_ts=None,
    end_ts=None,
    location=None,
    details=None,
) -> Optional[Tuple[bool, int, Optional[str]]]:
    found = _find_item(item_id)
    if found is None:
        return None
    _, item = found
    if start_ts is not None:
        item.start_ts = start_ts
    if end_ts is not None:
        item.end_ts = end_ts
    if location is not None:
        item.location = location
    if details is not None:
        item.details = details
    item.updated_at = datetime.now(timezone.utc)
    _save()
    return True, 1, None


def update_flight_fields(
    item_id: str,
    *,
    start_ts,
    end_ts,
    price: float,
    currency: str,
    details: Optional[dict],
) -> Optional[Tuple[bool, int, Optional[str]]]:
    found = _find_item(item_id)
    if found is None:
        return None
    _, item = found
    item.start_ts = start_ts
    item.end_ts = end_ts
    item.price = price
    item.currency = currency
    item.details = details
    item.updated_at = datetime.now(timezone.utc)
    _save()
    return True, 1, None


def add_item(item: ItineraryItem) -> Optional[Tuple[bool, Optional[ItineraryItem], Optional[str]]]:
    view = _STORE.get(item.trip_id)
    if view is None:
        return None
    item.updated_at = datetime.now(timezone.utc)
    view.items.append(item)
    _save()
    return True, item, None


def add_booking(booking: Booking) -> Optional[Tuple[bool, Optional[Booking], Optional[str]]]:
    if booking.trip_id not in _STORE:
        return None
    if booking.booked_at is None:
        booking.booked_at = datetime.now(timezone.utc)
    _BOOKINGS.setdefault(booking.trip_id, []).append(booking)
    _save()
    return True, booking, None


def list_bookings(trip_id: str) -> Optional[List[Booking]]:
    if trip_id not in _STORE:
        return None
    return list(_BOOKINGS.get(trip_id) or [])


def patch_trip_route(trip_id: str, origin: str, destination: str, start_date) -> None:
    view = _STORE.get(trip_id)
    if view is None:
        return
    view.trip.origin = origin
    if destination:
        view.trip.destinations = [destination]
    if start_date is not None:
        view.trip.start_date = start_date
    _save()


_load()
