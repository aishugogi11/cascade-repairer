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


@disruption.post("/break_flight")
def break_flight(req: BreakFlightRequest):
    """Find the trip's flight item and flip it to `broken`.

    Sync handler on purpose: FastAPI runs it in the threadpool, keeping the
    blocking BigQuery calls off the event loop.

    404 when the trip has no flight item (or the trip is unknown — same
    thing from this endpoint's view). A failed or 0-row write is a 500,
    never reported as success.
    """
    success, items, error = itinerary_items.list_items_for_trip(req.trip_id)
    if not success:
        raise HTTPException(status_code=500, detail=f"could not list items: {error}")

    flight = next((i for i in items if i.type == "flight"), None)
    if flight is None:
        raise HTTPException(
            status_code=404,
            detail=f"trip {req.trip_id} has no flight item to break",
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
        "trip_id": req.trip_id,
        "item_id": flight.item_id,
        "previous_status": flight.status,
        "status": "broken",
        "affected_rows": affected_rows,
    }
