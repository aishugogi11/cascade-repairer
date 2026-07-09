"""Walkthrough surface for the Phase 6 repair tools.

Two endpoints:
- POST /seed_trip — create a booked demo trip with all five item types
  (flight, hotel, ground, dining, experience) plus initial flight/hotel
  bookings, through the repository layer. The walkthrough's starting state.
- POST /repair_trip — run the six repair tools against a trip via
  concurrency_core.run_repairs. The curl surface for the validation
  walkthrough and the seam the voice phases will lift.
"""
import asyncio
import uuid
from datetime import date, datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api import concurrency_core as core
from api import repair_tools
from api.concurrency_core import RepairSpec
from api.repositories import bookings, itinerary_items, trips
from api.repositories.models import Booking, ItineraryItem, Trip

sabre_tools = APIRouter()


class SeedTripRequest(BaseModel):
    user_id: str = "demo-traveler"
    title: str = "The Complete Trip — hackathon demo"


# One itinerary item per required category. Dates match the demo story:
# fly in July 17, event July 18, fly out July 19.
_SEED_ITEMS = [
    {
        "type": "flight", "provider": "sabre", "location": "MSP-SFO",
        "start": datetime(2026, 7, 17, 8, 0, tzinfo=timezone.utc),
        "end": datetime(2026, 7, 17, 12, 5, tzinfo=timezone.utc),
        "price": 385.0,
    },
    {
        "type": "hotel", "provider": "sabre", "location": "Mountain View, CA",
        "start": datetime(2026, 7, 17, 22, 0, tzinfo=timezone.utc),
        "end": datetime(2026, 7, 19, 18, 0, tzinfo=timezone.utc),
        "price": 412.0,
    },
    {
        "type": "ground", "provider": "other", "location": "SFO -> Mountain View",
        "start": datetime(2026, 7, 17, 12, 30, tzinfo=timezone.utc),
        "end": datetime(2026, 7, 17, 13, 15, tzinfo=timezone.utc),
        "price": 58.0,
    },
    {
        "type": "dining", "provider": "other", "location": "Castro St, Mountain View",
        "start": datetime(2026, 7, 17, 19, 0, tzinfo=timezone.utc),
        "end": datetime(2026, 7, 17, 21, 0, tzinfo=timezone.utc),
        "price": 120.0,
    },
    {
        "type": "experience", "provider": "other", "location": "Computer History Museum",
        "start": datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc),
        "end": datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc),
        "price": 37.5,
    },
]


@sabre_tools.post("/seed_trip")
def seed_trip(req: SeedTripRequest):
    """Create a booked demo trip with all five item types.

    Sync handler on purpose: FastAPI runs it in the threadpool, keeping the
    blocking BigQuery calls off the event loop. Every write goes through the
    repositories; the first failure aborts with its error.
    """
    trip = Trip(
        user_id=req.user_id,
        title=req.title,
        status="booked",
        origin="MSP",
        destinations=["SFO", "Mountain View"],
        start_date=date(2026, 7, 17),
        end_date=date(2026, 7, 19),
    )
    success, _, error = trips.create_trip(trip)
    if not success:
        raise HTTPException(status_code=500, detail=f"trip insert failed: {error}")

    items = []
    for seed in _SEED_ITEMS:
        item = ItineraryItem(
            trip_id=trip.trip_id,
            type=seed["type"],
            status="booked",
            provider=seed["provider"],
            provider_ref=f"SEED-{seed['type'].upper()}-{uuid.uuid4().hex[:6].upper()}",
            start_ts=seed["start"],
            end_ts=seed["end"],
            location=seed["location"],
            price=seed["price"],
            currency="USD",
        )
        success, _, error = itinerary_items.create_item(item)
        if not success:
            raise HTTPException(
                status_code=500, detail=f"{seed['type']} item insert failed: {error}"
            )
        items.append(item)

    # Initial flight/hotel bookings — the rows the repair tools later cancel
    # or supersede.
    booking_rows = []
    for item in items:
        if item.type not in ("flight", "hotel"):
            continue
        booking = Booking(
            item_id=item.item_id,
            trip_id=trip.trip_id,
            sabre_confirmation_ref=item.provider_ref,
            state="confirmed",
            raw_response={"seeded": True, "type": item.type},
        )
        success, _, error = bookings.create_booking(booking)
        if not success:
            raise HTTPException(
                status_code=500, detail=f"{item.type} booking insert failed: {error}"
            )
        booking_rows.append(booking)

    return {
        "trip_id": trip.trip_id,
        "items": [
            {"item_id": i.item_id, "type": i.type, "status": i.status} for i in items
        ],
        "bookings": [
            {"booking_id": b.booking_id, "item_id": b.item_id} for b in booking_rows
        ],
    }


# --- repair_trip ----------------------------------------------------------------

def _iso_date(ts: Optional[datetime], fallback: str) -> str:
    return ts.date().isoformat() if ts else fallback


def _repair_call(item: ItineraryItem):
    """The repair tool coroutine for one itinerary item, args derived from
    the item's own data. One entry per required category; the tool writes
    the bookings row and the item's `fixed` transition."""
    trip_id, item_id = item.trip_id, item.item_id
    if item.type == "flight":
        origin, _, dest = (item.location or "MSP-SFO").partition("-")
        return repair_tools._rebook_flight(
            trip_id, item_id, origin or "MSP", dest or "SFO",
            _iso_date(item.start_ts, "2026-07-17"),
        )
    if item.type == "hotel":
        return repair_tools._shift_hotel_dates(
            trip_id, item_id,
            _iso_date(item.start_ts, "2026-07-17"),
            _iso_date(item.end_ts, "2026-07-19"),
        )
    if item.type == "ground":
        return repair_tools._reschedule_ground(
            trip_id, item_id,
            item.start_ts.isoformat() if item.start_ts else "2026-07-17T13:00",
        )
    if item.type == "dining":
        return repair_tools._move_dining(
            trip_id, item_id,
            item.start_ts.isoformat() if item.start_ts else "2026-07-17T20:00",
        )
    return repair_tools._rebook_experience(
        trip_id, item_id, _iso_date(item.start_ts, "2026-07-19")
    )


_REPAIR_NAMES = {
    "flight": "rebook_flight",
    "hotel": "shift_hotel_dates",
    "ground": "reschedule_ground",
    "dining": "move_dining",
    "experience": "rebook_experience",
}


def launch_trip_repairs(session_id, items):
    """Launch one background repair per itinerary item through
    concurrency_core — the shared seam between the /repair_trip walkthrough
    endpoint and the Phase 9 concierge's fix_trip tool. Returns
    (launched_names, tasks); the caller decides whether to await the tasks.
    """
    calls = {item.item_id: _repair_call(item) for item in items}
    specs = [
        RepairSpec(
            item_id=item.item_id,
            name=_REPAIR_NAMES.get(item.type, f"repair_{item.type}"),
            duration_seconds=0.0,  # real duration comes from the tool itself
        )
        for item in items
    ]

    async def do_repair(spec: RepairSpec):
        return await calls[spec.item_id]

    tasks = core.run_repairs(session_id, specs, do_repair)
    return [s.name for s in specs], tasks


class RepairTripRequest(BaseModel):
    trip_id: str
    session_id: Optional[str] = None
    wait: bool = True  # false: return immediately, poll the session later


@sabre_tools.post("/repair_trip")
async def repair_trip(req: RepairTripRequest):
    """Run the repair tools against every item of a trip, all concurrent,
    through launch_trip_repairs — the walkthrough surface for the cascade
    and the same seam the Phase 9 concierge fires.

    Each tool writes its bookings row; the cascade unit (`_repair_one`) is
    the single writer of the item's `repairing` -> `fixed` transitions. A
    failed write surfaces as a status="error" completion event, never a
    false ok.
    """
    success, items, error = await asyncio.to_thread(
        itinerary_items.list_items_for_trip, req.trip_id
    )
    if not success:
        raise HTTPException(status_code=500, detail=f"could not list items: {error}")
    if not items:
        raise HTTPException(
            status_code=404, detail=f"trip {req.trip_id} has no itinerary items"
        )

    session_id = req.session_id or f"repair-{uuid.uuid4().hex[:12]}"
    launched, tasks = launch_trip_repairs(session_id, items)
    if req.wait:
        await asyncio.gather(*tasks)

    session = core.get_session(session_id)
    return {
        "trip_id": req.trip_id,
        "session_id": session_id,
        "launched": launched,
        "item_ids": [item.item_id for item in items],
        "waited_for_completion": req.wait,
        "pending_tasks": session.pending(),
        "completed_events": [e.model_dump() for e in session.events],
    }

@sabre_tools.get("/latest_trip_id")
def latest_trip_id():
    """Return the most recently created trip_id, for the walkthrough's
    convenience (feeds the <TRIP_ID> in the validation queries). Trips carry
    created_at (stamped on insert); only itinerary_items has updated_at."""
    query = f"""
        SELECT trip_id, created_at
        FROM `{trips._table()}`
        ORDER BY created_at DESC
        LIMIT 1
    """
    success, rows, error = trips.bq_helper.run_select(query)
    if not success:
        raise HTTPException(status_code=500, detail=f"could not fetch latest trip: {error}")
    if not rows:
        raise HTTPException(status_code=404, detail="no trips found")
    return {"trip_id": rows[0]["trip_id"], "created_at": rows[0]["created_at"].isoformat()}