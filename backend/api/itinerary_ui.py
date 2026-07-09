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
from typing import get_args

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from api.repositories import trips
from api.repositories.models import ItemStatus

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


@itinerary_ui.get("/status/{trip_id}")
async def trip_status(trip_id: str):
    """The poll target: trip header + items (sorted by start_ts) + summary.

    404 for an unknown trip; a repository failure is a 500, never an empty
    200 the page would render as a healthy trip.
    """
    success, view, error = await asyncio.to_thread(trips.get_trip_with_items, trip_id)
    if not success:
        raise HTTPException(status_code=500, detail=f"could not load trip: {error}")
    if view is None:
        raise HTTPException(status_code=404, detail=f"trip {trip_id} not found")

    return {
        "trip": view.trip,
        "items": view.items,
        "summary": _summarize(view.items),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


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
            }
            for t in result
        ]
    }
