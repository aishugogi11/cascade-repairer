"""Phase 40 tests — the email_itinerary Concierge tool, hermetic.

The send module is mocked at the concierge boundary (`send_email`); no
RESEND_API_KEY, no network. The load-bearing contracts: an unpinned session
gets the no-trip line without storing or sending, a malformed address gets
the spoken re-ask and stores nothing (the code backstop behind the
read-back-confirm instructions), a valid address stores BEFORE the send so
the repair callback can reuse it even when the send fails, the send status
is spoken honestly (never "sent" on disabled/error), no failure path
raises, and the email path touches nothing bookable.
"""
import asyncio
from datetime import date
from unittest.mock import MagicMock

import pytest

from api import concierge, trip_emails
from api.helpers.bigquery_helper import bq_helper
from api.repositories.models import ItineraryItem, Trip


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(concierge, "_SESSION_TRIPS", {})
    trip_emails._reset()
    yield
    trip_emails._reset()


def _items():
    return [
        ItineraryItem(
            item_id="i-flight", trip_id="t-1", type="flight", status="booked",
            location="JFK-LAX",
            details={"airline": "DL", "flight_number": 439,
                     "airline_name": "Delta", "cabin": "Economy",
                     "duration_minutes": 349, "layover_airports": [],
                     "arrives_next_day": False, "stops": 0},
            price=214.0, currency="USD",
        )
    ]


def _pin_trip(monkeypatch, session_id="room-1"):
    trip = Trip(
        trip_id="t-1", user_id="demo-traveler", title="Trip to LAX",
        status="booked", origin="JFK", destinations=["LAX"],
        start_date=date(2026, 7, 21), end_date=date(2026, 7, 23),
    )
    items = _items()
    concierge._SESSION_TRIPS[session_id] = concierge.TripContext(
        trip=trip, items=items, summary="summary"
    )
    # The impl re-reads items fresh (build-out legs land after the pin) —
    # keep that read hermetic and successful unless a test overrides it.
    monkeypatch.setattr(
        concierge.itinerary_items, "list_items_for_trip",
        lambda trip_id: (True, items, None),
    )
    return trip


def _capture_send(monkeypatch, status="sent"):
    sends = []

    async def fake_send(**kwargs):
        sends.append(kwargs)
        return {"status": status, "id": "email-1"}

    monkeypatch.setattr(concierge, "send_email", fake_send)
    return sends


# --- no trip / bad address: nothing stored, nothing sent ----------------------


def test_unpinned_session_gets_no_trip_line_without_storing(monkeypatch):
    sends = _capture_send(monkeypatch)

    reply = asyncio.run(
        concierge.email_itinerary_impl("room-1", "josh@example.com")
    )

    assert reply == concierge._NO_TRIP_SPOKEN
    assert trip_emails.get("t-1") is None
    assert sends == []


@pytest.mark.parametrize("bad", [
    "", "   ", "josh at gmail dot com", "josh@", "@example.com",
    "josh@example", "jo sh@example.com", None,
])
def test_malformed_address_gets_reask_and_stores_nothing(monkeypatch, bad):
    sends = _capture_send(monkeypatch)
    _pin_trip(monkeypatch)

    reply = asyncio.run(concierge.email_itinerary_impl("room-1", bad))

    assert reply == concierge._EMAIL_REASK_LINE
    assert trip_emails.get("t-1") is None
    assert sends == []


# --- the confirmed-address happy path ------------------------------------------


def test_confirmed_address_stores_and_sends_the_itinerary(monkeypatch):
    sends = _capture_send(monkeypatch)
    _pin_trip(monkeypatch)

    reply = asyncio.run(
        concierge.email_itinerary_impl("room-1", " Josh@Example.COM ")
    )

    assert reply == concierge._EMAIL_SENT_LINE
    assert trip_emails.get("t-1") == "josh@example.com"
    assert len(sends) == 1
    assert sends[0]["to"] == "josh@example.com"
    assert sends[0]["subject"] == "Your trip to Los Angeles — July 21"
    assert sends[0]["html"].strip() and sends[0]["text"].strip()
    assert "Delta 439" in sends[0]["text"]


@pytest.mark.parametrize("status", ["disabled", "error"])
def test_failed_send_is_honest_and_keeps_the_address(monkeypatch, status):
    # Decision 3: store first — the repair callback can still use the
    # address — and never claim the email arrived when it didn't.
    sends = _capture_send(monkeypatch, status=status)
    _pin_trip(monkeypatch)

    reply = asyncio.run(
        concierge.email_itinerary_impl("room-1", "josh@example.com")
    )

    assert reply == concierge._EMAIL_SEND_FAILED_LINE
    assert reply != concierge._EMAIL_SENT_LINE
    assert trip_emails.get("t-1") == "josh@example.com"
    assert len(sends) == 1


# --- failure paths never raise (the voice turn must survive anything) ----------


def test_items_read_failure_falls_back_to_pinned_items(monkeypatch):
    sends = _capture_send(monkeypatch)
    _pin_trip(monkeypatch)

    def boom(trip_id):
        raise RuntimeError("bigquery fell over")

    monkeypatch.setattr(concierge.itinerary_items, "list_items_for_trip", boom)

    reply = asyncio.run(
        concierge.email_itinerary_impl("room-1", "josh@example.com")
    )

    assert reply == concierge._EMAIL_SENT_LINE
    assert len(sends) == 1
    assert "Delta 439" in sends[0]["text"]  # the pinned items made the email


def test_send_raising_returns_speakable_error(monkeypatch):
    # send_email never raises by contract — but the tool survives even a
    # broken contract, and the address (confirmed) stays stored.
    async def broken_send(**kwargs):
        raise RuntimeError("transport contract broken")

    monkeypatch.setattr(concierge, "send_email", broken_send)
    _pin_trip(monkeypatch)

    reply = asyncio.run(
        concierge.email_itinerary_impl("room-1", "josh@example.com")
    )

    assert reply == concierge._EMAIL_ERROR_LINE
    assert trip_emails.get("t-1") == "josh@example.com"


# --- email-path purity: nothing bookable enters or leaves ----------------------


def test_email_path_touches_nothing_bookable(monkeypatch):
    """The Phase 34 purity precedent: no _SESSION_FLIGHT_OPTIONS entry, no
    _LATEST_SEARCH touch, no DML, no pinned-context drift — an email
    question can never make anything bookable."""
    _capture_send(monkeypatch)
    _pin_trip(monkeypatch)
    options_sentinel = {"room-1": ["option-sentinel"]}
    monkeypatch.setattr(
        concierge, "_SESSION_FLIGHT_OPTIONS", {"room-1": ["option-sentinel"]}
    )
    latest_sentinel = ("room-1", ["option-sentinel"], "recorded-at")
    monkeypatch.setattr(concierge, "_LATEST_SEARCH", latest_sentinel)
    dml = MagicMock()
    monkeypatch.setattr(bq_helper, "run_dml", dml)
    context_before = concierge._SESSION_TRIPS["room-1"].model_dump_json()

    reply = asyncio.run(
        concierge.email_itinerary_impl("room-1", "josh@example.com")
    )

    assert reply == concierge._EMAIL_SENT_LINE
    assert concierge._SESSION_TRIPS["room-1"].model_dump_json() == context_before
    assert concierge._SESSION_FLIGHT_OPTIONS == options_sentinel
    assert concierge._LATEST_SEARCH is latest_sentinel
    dml.assert_not_called()


# --- registration & instruction routing ----------------------------------------


def test_tool_is_registered():
    agent = concierge.build_agent("room-1")
    assert "email_itinerary" in {t.name for t in agent.tools}


def test_instructions_carry_the_offer_and_confirm_contract():
    assert "email_itinerary" in concierge.BASE_INSTRUCTIONS
    assert (
        "Would you like me to send this to your email?"
        in concierge.BASE_INSTRUCTIONS
    )
    # The confirm-before-store contract and the never-guess rule.
    assert "read it back" in concierge.BASE_INSTRUCTIONS
    assert "never guess or invent an address" in concierge.BASE_INSTRUCTIONS
    assert "don't offer again" in concierge.BASE_INSTRUCTIONS
    # The spell-back rule (live-QA finding 2026-07-18: a doubled letter
    # passed a plainly spoken read-back and the email bounced) and the
    # what's-on-file / correction flow.
    assert "spelling the part" in concierge.BASE_INSTRUCTIONS
    assert "what email is on file" in concierge.BASE_INSTRUCTIONS
    assert "newest confirmed address replaces" in concierge.BASE_INSTRUCTIONS
