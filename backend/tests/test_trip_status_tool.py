"""Phase 23 tests — the trip_status Concierge tool.

Hermetic (the test_concierge patterns): repositories monkeypatched at the
module boundary, no GCP, no OPENAI_API_KEY. Load-bearing invariant: the
tool reads the repository fresh on every call — never the pinned cache or
the session snapshot — so it answers honestly even when repairs ran under
a different session id.
"""
import asyncio
from datetime import date

from api import concierge
from api.repositories.models import ItineraryItem, Trip


def _pin(session_id, trip_id="t-1"):
    trip = Trip(
        trip_id=trip_id, user_id="demo-traveler", title="Trip to LAX",
        status="booked", origin="JFK", destinations=["LAX"],
        start_date=date(2026, 7, 17), end_date=date(2026, 7, 19),
    )
    items = [
        ItineraryItem(item_id=f"i-{t}", trip_id=trip_id, type=t, status="booked")
        for t in ("flight", "hotel", "ground", "dining", "experience")
    ]
    concierge._SESSION_TRIPS[session_id] = concierge.TripContext(
        trip=trip, items=items, summary="TRIP CONTEXT (authoritative): test. "
    )
    return trip, items


def teardown_function():
    concierge._SESSION_TRIPS.clear()


def test_unpinned_session_gets_the_no_trip_line():
    concierge._SESSION_TRIPS.clear()
    reply = asyncio.run(concierge.trip_status_impl("fresh-session"))
    assert reply == concierge._NO_TRIP_SPOKEN


def test_reads_fresh_statuses_not_the_pinned_cache(monkeypatch):
    """The pinned context still says booked; the repository says the flight
    is repairing (a disrupt ran under another session) — the tool speaks
    the repository's truth."""
    _pin("room-1", "t-1")
    live = [
        ItineraryItem(item_id="i-flight", trip_id="t-1", type="flight",
                      status="repairing"),
        ItineraryItem(item_id="i-hotel", trip_id="t-1", type="hotel",
                      status="fixed"),
        ItineraryItem(item_id="i-ground", trip_id="t-1", type="ground",
                      status="booked"),
    ]
    reads = []

    def fake_list(trip_id):
        reads.append(trip_id)
        return True, live, None

    monkeypatch.setattr(
        concierge.itinerary_items, "list_items_for_trip", fake_list
    )

    reply = asyncio.run(concierge.trip_status_impl("room-1"))
    assert reads == ["t-1"]  # a fresh read, for the pinned trip
    assert "your flight is being repaired right now" in reply
    assert "your hotel is repaired and confirmed" in reply
    assert "your ride is booked and confirmed" in reply
    # Mid-repair: no premature all-clear.
    assert "Everything is on track" not in reply


def test_broken_trip_suppresses_all_clear(monkeypatch):
    """Phase 31 validation gap: `broken` had no dedicated assertion — a live
    broken leg must be spoken as disrupted with no all-clear claim (the
    cancelled and repairing cases have their own tests)."""
    _pin("room-4", "t-4")
    live = [
        ItineraryItem(item_id="i-flight", trip_id="t-4", type="flight",
                      status="broken"),
        ItineraryItem(item_id="i-hotel", trip_id="t-4", type="hotel",
                      status="booked"),
    ]
    monkeypatch.setattr(
        concierge.itinerary_items, "list_items_for_trip",
        lambda trip_id: (True, live, None),
    )
    reply = asyncio.run(concierge.trip_status_impl("room-4"))
    assert "your flight is disrupted" in reply
    assert "your hotel is booked and confirmed" in reply
    assert "Everything is on track" not in reply


def test_all_clear_trip_reads_on_track_with_grouped_legs(monkeypatch):
    _pin("room-2", "t-2")
    live = [
        ItineraryItem(item_id=f"i-{t}", trip_id="t-2", type=t, status="booked")
        for t in ("flight", "hotel", "ground", "dining", "experience")
    ]
    monkeypatch.setattr(
        concierge.itinerary_items, "list_items_for_trip",
        lambda trip_id: (True, live, None),
    )
    reply = asyncio.run(concierge.trip_status_impl("room-2"))
    assert (
        "your flight, hotel, ride, dinner reservation, and tour are booked "
        "and confirmed" in reply
    )
    assert "Everything is on track" in reply
    # Spoken copy: no ids, no raw status enums beyond the spoken forms.
    assert "t-2" not in reply and "i-flight" not in reply


def test_failed_read_returns_a_speakable_retry_line(monkeypatch):
    _pin("room-3", "t-3")
    monkeypatch.setattr(
        concierge.itinerary_items, "list_items_for_trip",
        lambda trip_id: (False, None, "boom"),
    )
    reply = asyncio.run(concierge.trip_status_impl("room-3"))
    assert "ask me again" in reply


def test_tool_is_registered_and_instructed():
    agent = concierge.build_agent("some-session")
    names = [tool.name for tool in agent.tools]
    assert "trip_status" in names
    assert "trip_status" in concierge.BASE_INSTRUCTIONS
