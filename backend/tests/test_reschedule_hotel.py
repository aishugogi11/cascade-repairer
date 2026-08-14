"""Voice-initiated hotel date change — hermetic.

The traveler can ask Cascade to reschedule the hotel without a flight
cancel. The Sabre modify is mock (same path as cascade repair); the
itinerary card must show the new stay.
"""
import asyncio
from datetime import datetime, timezone

import pytest

from api import concierge
from api import memory_trips
from api.sabre import client as sabre_client


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.delenv("SABRE_MODE", raising=False)
    monkeypatch.setattr(sabre_client._mock, "latency_seconds", 0)
    monkeypatch.setattr(concierge, "_SESSION_TRIPS", {})
    memory_trips.clear()
    yield
    memory_trips.clear()


def _pin_seeded(session_id="room-1"):
    seeded = memory_trips.seed("whatsapp-demo", "PDF trip")
    view = memory_trips.get(seeded["trip_id"])
    concierge._SESSION_TRIPS[session_id] = concierge.TripContext(
        trip=view.trip, items=list(view.items), summary="pdf",
    )
    return view


def test_reschedule_hotel_moves_stay_and_updates_card():
    view = _pin_seeded()
    hotel = next(i for i in view.items if i.type == "hotel")
    assert concierge._pacific_day(hotel.start_ts).isoformat() == "2026-07-17"

    msg = asyncio.run(concierge.reschedule_hotel_impl(
        "room-1", "2026-07-18", "2026-07-21"
    ))

    assert "July 18th" in msg and "July 21st" in msg
    assert "moved your hotel" in msg
    refreshed = memory_trips.get(view.trip.trip_id)
    hotel = next(i for i in refreshed.items if i.type == "hotel")
    assert concierge._pacific_day(hotel.start_ts).isoformat() == "2026-07-18"
    assert concierge._pacific_day(hotel.end_ts).isoformat() == "2026-07-21"
    assert hotel.start_ts.astimezone(timezone.utc) == datetime(
        2026, 7, 19, 5, 0, tzinfo=timezone.utc
    )
    assert hotel.details["check_in"] == "2026-07-18"
    assert hotel.details["check_out"] == "2026-07-21"
    pinned = concierge._SESSION_TRIPS["room-1"]
    assert "check-in 2026-07-18" in pinned.summary


def test_reschedule_hotel_keeps_stay_length_when_checkout_omitted():
    _pin_seeded()

    msg = asyncio.run(concierge.reschedule_hotel_impl("room-1", "2026-07-18", ""))

    assert "July 18th" in msg and "July 20th" in msg
    view = memory_trips.get(concierge._SESSION_TRIPS["room-1"].trip.trip_id)
    hotel = next(i for i in view.items if i.type == "hotel")
    assert concierge._pacific_day(hotel.end_ts).isoformat() == "2026-07-20"


def test_reschedule_hotel_already_those_dates():
    _pin_seeded()

    msg = asyncio.run(concierge.reschedule_hotel_impl(
        "room-1", "2026-07-17", "2026-07-19"
    ))

    assert "already set" in msg
    assert "July 17th" in msg and "July 19th" in msg


def test_reschedule_hotel_rejects_checkout_before_checkin():
    _pin_seeded()

    msg = asyncio.run(concierge.reschedule_hotel_impl(
        "room-1", "2026-07-20", "2026-07-18"
    ))

    assert "check-in date that comes before check-out" in msg


def test_reschedule_hotel_asks_for_a_date():
    _pin_seeded()

    msg = asyncio.run(concierge.reschedule_hotel_impl("room-1", "", ""))

    assert "new check-in date" in msg


def test_reschedule_hotel_without_a_trip():
    msg = asyncio.run(concierge.reschedule_hotel_impl(
        "room-1", "2026-07-18", "2026-07-20"
    ))

    assert "don't see a hotel" in msg


def test_reschedule_hotel_without_a_hotel_item():
    view = _pin_seeded()
    view.items[:] = [i for i in view.items if i.type != "hotel"]
    concierge._SESSION_TRIPS["room-1"].items = list(view.items)

    msg = asyncio.run(concierge.reschedule_hotel_impl(
        "room-1", "2026-07-18", "2026-07-20"
    ))

    assert "no hotel reservation" in msg


def test_agent_registers_reschedule_hotel(monkeypatch):
    monkeypatch.delenv("CONCIERGE_LLM_MODEL", raising=False)
    monkeypatch.delenv("FEATHERLESS_API_KEY", raising=False)
    agent = concierge.build_agent("room-1")
    assert "reschedule_hotel" in {t.name for t in agent.tools}
    assert "reschedule_hotel" in concierge.BASE_INSTRUCTIONS
    assert "do not call fix_trip or offer_rebook" in concierge.BASE_INSTRUCTIONS
