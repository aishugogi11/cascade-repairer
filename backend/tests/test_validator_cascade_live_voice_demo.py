"""Independent-validator checks for Phase 23 acceptance criteria."""

import asyncio
from datetime import date

from api import concierge, consent
from api import demo as demo_module
from api.repositories.models import ItineraryItem, Trip


def teardown_function():
    concierge._SESSION_TRIPS.clear()
    consent.reset()


def test_validator_trip_status_does_not_call_a_cancelled_trip_on_track(monkeypatch):
    """A current cancelled status must not be followed by an all-clear claim."""
    trip = Trip(
        trip_id="t-cancelled",
        user_id="demo-traveler",
        title="Trip to LAX",
        status="booked",
        origin="JFK",
        destinations=["LAX"],
        start_date=date(2026, 7, 17),
        end_date=date(2026, 7, 19),
    )
    cached_items = [
        ItineraryItem(
            item_id="i-flight",
            trip_id=trip.trip_id,
            type="flight",
            status="booked",
        )
    ]
    concierge._SESSION_TRIPS["voice-session"] = concierge.TripContext(
        trip=trip,
        items=cached_items,
        summary="TRIP CONTEXT (authoritative): test. ",
    )
    live_items = [
        ItineraryItem(
            item_id="i-flight",
            trip_id=trip.trip_id,
            type="flight",
            status="cancelled",
        )
    ]
    monkeypatch.setattr(
        concierge.itinerary_items,
        "list_items_for_trip",
        lambda trip_id: (True, live_items, None),
    )

    reply = asyncio.run(concierge.trip_status_impl("voice-session"))

    assert "your flight is cancelled" in reply
    assert "Everything is on track" not in reply


def test_validator_retrigger_during_classification_stops_the_old_watcher(monkeypatch):
    """A fresh Cancel must supersede a watcher already classifying Call 1."""
    launched = []
    callbacks = []

    async def transcript(_call_id):
        return "USER: yes"

    async def classify(_transcript):
        # The second Cancel lands while the first watcher's LLM call is in flight.
        consent.register_awaiting("t-race", "call-new")
        return "yes"

    def list_items(_trip_id):
        return True, [object()], None

    def launch(_session_id, _items):
        launched.append(True)
        return ["repair"], []

    async def callback(_trip_id, _tasks):
        callbacks.append(True)

    monkeypatch.setattr(demo_module, "_await_call_transcript", transcript)
    monkeypatch.setattr(demo_module.consent, "classify_consent", classify)
    monkeypatch.setattr(
        demo_module.itinerary_items, "list_items_for_trip", list_items
    )
    monkeypatch.setattr(demo_module, "launch_trip_repairs", launch)
    monkeypatch.setattr(demo_module, "_call_back_with_results", callback)

    stale = consent.register_awaiting("t-race", "call-old")
    asyncio.run(
        demo_module._watch_consent_then_repair("t-race", "call-old", stale)
    )

    assert consent.current("t-race").call_id == "call-new"
    assert launched == []
    assert callbacks == []
