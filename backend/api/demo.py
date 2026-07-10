"""Demo orchestrator — Phase 12's "one button, one beat" surface.

Two endpoints compose the Cascade Repairer demo from seams built in earlier
phases; a third serves the operator-facing demo page:

- POST /book — Beat 1: the traveler receives a phone call while the booked
  trip lands. The outbound call (vb_cli, Phase 7) carries the booking
  narrative; the trip itself is seeded server-side (create_seed_trip,
  Phase 6). The hosted Vocal Bridge caller agent cannot invoke our tools
  mid-call, so the call is the narrative and the backend does the booking —
  accepted stagecraft; the purpose carries the trip details so voice and
  screen tell the same story.
- POST /disrupt — Beat 2: the flight cancels and the agent reaches out
  first ("your flight was just cancelled; I'm already rebooking"). Places
  the call, breaks the flight (break_trip_flight), and launches all-item
  repairs in the background without waiting (launch_trip_repairs, the
  Phase 5 pattern) so the page timer and the phone call run while repairs
  land.
- GET / — the demo page (assets/demo/page.html), the projector surface.

In each beat the call fires before the data writes — the phone should ring
while the screen changes, not after. Failure of any leg is an error status,
never a silent partial success. Same invariants as outbound_call.py: nothing
returned ever contains the callee phone number or the API key; blocking work
runs via asyncio.to_thread.
"""
import asyncio
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from api import vb_cli
from api.disruption import break_trip_flight
from api.outbound_call import _missing_env, _scrub
from api.repositories import itinerary_items
from api.sabre_tools import create_seed_trip, launch_trip_repairs

demo = APIRouter()

# Read per request, not at import: uvicorn --reload only watches .py files,
# so an import-time read would serve stale HTML all through local dev.
_PAGE_PATH = Path(__file__).parent / "assets" / "demo" / "page.html"

_REQUIRED_ENV = (
    "VOCAL_BRIDGE_API_KEY",
    "VOCAL_BRIDGE_CALLER_AGENT_ID",
    "VOCAL_BRIDGE_CALLEE_PHONE",
)


def _book_purpose(title: str) -> str:
    """Beat 1 call script — agent-voiced, matching what the seeded trip puts
    on screen (sabre_tools._SEED_ITEMS): what's booked, where to see it."""
    return (
        "You are the traveler's AI travel agent calling with good news about "
        f'their trip "{title}". Their complete trip is now booked: a flight '
        "from Minneapolis to San Francisco on the morning of July 17, a hotel "
        "in Mountain View through July 19, a ride from the airport, dinner on "
        "Castro Street that evening, and a Computer History Museum tour on "
        "July 19. Walk them through it briefly and warmly, tell them every "
        "detail is on their live itinerary screen, and wish them a great trip. "
        "Keep the call short."
    )


# Beat 2 call script — calm and concrete: what happened, what's being done,
# a time promise.
_DISRUPT_PURPOSE = (
    "You are the traveler's AI travel agent, calling them proactively — they "
    "do not know yet. Their flight from Minneapolis to San Francisco was just "
    "cancelled by the airline. Tell them right away, then reassure them: you "
    "are already rebooking the flight and rechecking every other part of the "
    "trip — the hotel, the airport ride, the dinner reservation, and the "
    "museum tour. Ask them to give you about thirty seconds while the repairs "
    "finish, and tell them they can watch each piece flip to fixed on their "
    "live itinerary screen. Stay calm, concrete, and brief."
)


class BookRequest(BaseModel):
    user_id: str = "demo-traveler"
    title: str = "The Complete Trip — hackathon demo"


class DisruptRequest(BaseModel):
    trip_id: str


@demo.get("/", response_class=HTMLResponse)
def demo_page():
    return _PAGE_PATH.read_text()


@demo.post(
    "/book",
    summary="[Phase 12] Beat 1 — call the traveler while their trip books",
)
async def book(request: BookRequest):
    missing = _missing_env(*_REQUIRED_ENV)
    if missing:
        return JSONResponse(status_code=503, content={"error": f"{missing} not set"})

    # Call first: place_call returns as soon as the call is queued, so the
    # phone rings while the trip writes land.
    ok, call, error = await asyncio.to_thread(
        vb_cli.place_call, _book_purpose(request.title), "demo-beat1-booking"
    )
    if not ok:
        return JSONResponse(status_code=502, content={"error": _scrub(error)})

    seeded = await asyncio.to_thread(
        create_seed_trip, request.user_id, request.title
    )
    return {
        "trip_id": seeded["trip_id"],
        "call_id": call["call_id"],
        "call_status": call["status"],
    }


@demo.post(
    "/disrupt",
    summary="[Phase 12] Beat 2 — cancellation call, broken flight, "
    "background repairs",
)
async def disrupt(request: DisruptRequest):
    missing = _missing_env(*_REQUIRED_ENV)
    if missing:
        return JSONResponse(status_code=503, content={"error": f"{missing} not set"})

    ok, call, error = await asyncio.to_thread(
        vb_cli.place_call, _DISRUPT_PURPOSE, "demo-beat2-disruption"
    )
    if not ok:
        return JSONResponse(status_code=502, content={"error": _scrub(error)})

    # break_trip_flight's 404 (no flight item / unknown trip) and 500
    # (failed or 0-row write) pass through untouched.
    broken = await asyncio.to_thread(break_trip_flight, request.trip_id)

    success, items, error = await asyncio.to_thread(
        itinerary_items.list_items_for_trip, request.trip_id
    )
    if not success:
        raise HTTPException(status_code=500, detail=f"could not list items: {error}")

    # Launched, not awaited: /disrupt returns immediately so the page timer
    # and the live phone call run while repairs land.
    repair_session_id = f"demo-{uuid.uuid4().hex[:12]}"
    launched, _tasks = launch_trip_repairs(repair_session_id, items)

    return {
        "trip_id": request.trip_id,
        "item_id": broken["item_id"],
        "call_id": call["call_id"],
        "call_status": call["status"],
        "repair_session_id": repair_session_id,
        "launched": launched,
    }
