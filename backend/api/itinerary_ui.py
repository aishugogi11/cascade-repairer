"""Live itinerary UI — the demo's second surface.

Serves the itinerary page and the JSON endpoints it polls: trip status
(all itinerary items with their repair-lifecycle statuses) and recent trips
for the selector. Read-only — disruption and repair are driven elsewhere
(/v1/disruption, /v1/sabre_tools, the concierge agent).

Handlers are async and wrap the blocking repository reads in
asyncio.to_thread, keeping BigQuery off the event loop (tech-stack rule).
The payload stays UI-agnostic so Phase 12 rehearsal scripting and eval
capture can reuse /status/{trip_id}.
"""
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, get_args

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from api import concierge
from api.repositories import bookings as bookings_repo
from api.repositories import trips
from api.repositories.models import Booking, ItemStatus, ItineraryItem

itinerary_ui = APIRouter()

# Read per request, not at import: uvicorn --reload only watches .py files,
# so an import-time read would serve stale HTML all through local dev.
_PAGE_PATH = Path(__file__).parent / "assets" / "itinerary" / "page.html"

_STATUSES = list(get_args(ItemStatus))
_ACTIVE_STATUSES = {"broken", "repairing"}


def _summarize(items) -> dict:
    counts = {status: 0 for status in _STATUSES}
    for item in items:
        counts[item.status] += 1
    all_clear = not any(item.status in _ACTIVE_STATUSES for item in items)
    return {"counts": counts, "all_clear": all_clear}


@itinerary_ui.get("/", response_class=HTMLResponse)
def itinerary_page():
    return _PAGE_PATH.read_text()


# --- per-item detail (Phase 17) — feeds the iOS recommendation sheet ----------
# Additive and deliberately shallow: one why-chosen sentence, a price-delta
# string, one downstream-impact sentence, in the mockup's glanceable register.
# The web page ignores the key entirely.

_IMPACT_BY_TYPE = {
    "flight": "The rest of the itinerary anchors to this flight's dates and "
              "arrival time.",
    "hotel": "Check-in and check-out line up with the flight days.",
    "ground": "Pickup is timed to the flight's arrival.",
    "dining": "The reservation fits the first evening's schedule.",
    "experience": "Scheduled around the trip's free morning.",
}

_REPAIR_WHY = {
    "flight": "Rebooked on the next departure with seats available, keeping "
              "arrival close to the original plan.",
    "hotel": "The stay was shifted to match the new flight dates at the same "
             "property.",
    "ground": "The pickup was rescheduled to meet the new arrival time.",
    "dining": "The reservation was moved to a time the new schedule can make.",
    "experience": "Tickets were reissued for a session the new dates allow.",
}

_REPAIR_IMPACT = {
    "flight": "Every downstream booking was re-checked against the new "
              "arrival time.",
    "hotel": "The nights still cover the full stay, so nothing downstream "
             "moves.",
    "ground": "No gap between landing and the ride into town.",
    "dining": "The evening plan survives the schedule change.",
    "experience": "The plan stays intact despite the flight change.",
}


def _voice_booking_detail(raw: dict) -> dict:
    """The rich case: the guided voice booking stored the chosen option and
    what it beat, so why-chosen and the price delta are real."""
    option = raw.get("option", {})
    offered = raw.get("options_offered", [])
    stops = option.get("stops", 0)
    legs = "nonstop" if stops == 0 else (
        "one stop" if stops == 1 else f"{stops} stops"
    )
    count = {2: "two", 3: "three"}.get(len(offered), str(len(offered)))
    prices = [o.get("price") for o in offered if o.get("price") is not None]
    delta = (option.get("price") or 0) - min(prices) if prices else 0
    return {
        "why_chosen": (
            f"Picked by voice from {count} options — {legs}, landing at "
            f"{option.get('arrive_time', 'the planned time')}."
        ),
        "price_delta": f"+${delta:,.0f}" if delta >= 0.5 else "$0",
        "impact": _IMPACT_BY_TYPE["flight"],
    }


def _item_detail(item: ItineraryItem, booking: Optional[Booking]) -> Optional[dict]:
    """Why this item is what it is, derived from its latest booking's
    raw_response — None (key omitted) when there is no booking to speak from."""
    if booking is None:
        return None
    raw = booking.raw_response or {}
    if raw.get("source") == "voice_guided_booking":
        return _voice_booking_detail(raw)
    if raw.get("seeded"):
        return {
            "why_chosen": "Booked as part of the original trip plan.",
            "price_delta": "$0",
            "impact": _IMPACT_BY_TYPE.get(item.type, "Part of the trip plan."),
        }
    return {
        "why_chosen": _REPAIR_WHY.get(
            item.type, "Rebooked automatically to keep the trip on track."
        ),
        "price_delta": "$0",
        "impact": _REPAIR_IMPACT.get(
            item.type, "The rest of the trip stays as planned."
        ),
    }


async def _details_for(trip_id: str, items) -> dict:
    """item_id -> detail, best-effort: the poll the demo depends on must
    never fail because the bookings read did. list_bookings_for_trip orders
    by booked_at, so the last row per item is its latest booking."""
    try:
        success, rows, _error = await asyncio.to_thread(
            bookings_repo.list_bookings_for_trip, trip_id
        )
        if not success:
            return {}
        latest = {b.item_id: b for b in rows}
    except Exception:  # noqa: BLE001 — detail is additive, never load-bearing
        return {}
    details = {}
    for item in items:
        detail = _item_detail(item, latest.get(item.item_id))
        if detail:
            details[item.item_id] = detail
    return details


def _pending_options(trip_id: str) -> Optional[dict]:
    """The Concierge's in-flight flight options for the booking page's
    candidates panel (Phase 21) — best-effort like `detail`: any failure
    omits the block, never breaks the poll."""
    try:
        return concierge.pending_options_for_trip(trip_id)
    except Exception:  # noqa: BLE001 — additive, never load-bearing
        return None


@itinerary_ui.get("/status/{trip_id}")
async def trip_status(trip_id: str):
    """The poll target: trip header + items (sorted by start_ts) + summary.

    404 for an unknown trip; a repository failure is a 500, never an empty
    200 the page would render as a healthy trip. Items with a booking carry
    an additive `detail` object (why chosen / price delta / impact) for the
    iOS recommendation sheet; while a guided booking conversation has live
    flight options the payload carries an additive `pending_options` block
    (Phase 21, the booking page's candidates panel); everything else in the
    payload is unchanged.
    """
    success, view, error = await asyncio.to_thread(trips.get_trip_with_items, trip_id)
    if not success:
        raise HTTPException(status_code=500, detail=f"could not load trip: {error}")
    if view is None:
        raise HTTPException(status_code=404, detail=f"trip {trip_id} not found")

    details = await _details_for(trip_id, view.items)
    items = []
    for item in view.items:
        payload = item.model_dump()
        if item.item_id in details:
            payload["detail"] = details[item.item_id]
        items.append(payload)

    body = {
        "trip": view.trip,
        "items": items,
        "summary": _summarize(view.items),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    pending = _pending_options(trip_id)
    if pending:
        body["pending_options"] = pending
    return body


@itinerary_ui.get("/trips")
async def recent_trips(limit: int = 10):
    """Recent trips, newest first — backs the page's trip selector."""
    success, result, error = await asyncio.to_thread(trips.list_recent_trips, limit)
    if not success:
        raise HTTPException(status_code=500, detail=f"could not list trips: {error}")
    return {
        "trips": [
            {
                "trip_id": t.trip_id,
                "title": t.title,
                "status": t.status,
                "start_date": t.start_date,
                "end_date": t.end_date,
                "created_at": t.created_at,
            }
            for t in result
        ]
    }
