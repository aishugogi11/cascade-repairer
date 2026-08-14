"""Disruption injector — the demo's trigger.

POST /break_flight flips a trip's flight itinerary item to `broken` on cue,
via the repository layer (DML, stamps updated_at). Idempotent: calling it on
an already-broken flight just re-flips it. Curl-able from a phone or a
teammate's laptop during the demo.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.repositories import itinerary_items

disruption = APIRouter()


class BreakFlightRequest(BaseModel):
    trip_id: str


def _is_breakable(item) -> bool:
    if getattr(item, "type", None) == "flight":
        return True
    blob = " ".join([
        str(getattr(item, "location", "") or ""),
        str((getattr(item, "details", None) or {}).get("title") or ""),
        str(getattr(item, "type", "") or ""),
    ]).lower()
    return any(w in blob for w in (
        "airport", "sfo", "jfk", "lga", "ewr", "flight",
    ))


def breakable_item(items):
    return next((i for i in items if i.type == "flight"), None) or next(
        (i for i in items if _is_breakable(i)), None
    )


def break_trip_flight(trip_id: str) -> dict:
    """Find the trip's flight (or airport) item and flip it to `broken`.

    Blocking (BigQuery via the repository) — callers keep it off the event
    loop: the endpoint below is a sync handler (FastAPI threadpool), the
    Phase 12 demo orchestrator wraps it in asyncio.to_thread.

    Raises HTTPException — 404 when the trip has no flight/airport item (or
    the trip is unknown — same thing from this view); a failed or 0-row
    write is a 500, never reported as success.
    """
    success, items, error = itinerary_items.list_items_for_trip(trip_id)
    if not success:
        raise HTTPException(status_code=500, detail=f"could not list items: {error}")

    flight = breakable_item(items)
    if flight is None:
        raise HTTPException(
            status_code=404,
            detail=f"trip {trip_id} has no flight item to break",
        )

    write_ok, affected_rows, write_error = itinerary_items.update_status(
        flight.item_id, "broken"
    )
    if not write_ok:
        raise HTTPException(
            status_code=500,
            detail=f"status write failed for item {flight.item_id}: {write_error}",
        )
    if affected_rows == 0:
        raise HTTPException(
            status_code=500,
            detail=f"status write for item {flight.item_id} matched no rows",
        )

    return {
        "trip_id": trip_id,
        "item_id": flight.item_id,
        "previous_status": flight.status,
        "status": "broken",
        "affected_rows": affected_rows,
    }


@disruption.post("/break_flight")
def break_flight(req: BreakFlightRequest):
    """The standalone injector endpoint — curl-able from a phone or a
    teammate's laptop during the demo. Thin wrapper over break_trip_flight."""
    return break_trip_flight(req.trip_id)
