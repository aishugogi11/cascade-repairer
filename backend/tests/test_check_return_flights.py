"""Phase 34 tests — the check_return_flights Tavily tool, hermetic.

Tavily is mocked at the search boundary (`_tavily_search`); no TAVILY_API_KEY,
no network. The load-bearing contracts: the reverse route derives from the
pinned trip (primary destination back to the origin) with the return date
human-formatted into the query, the successful result carries the baked-in
honesty framing, an unpinned session gets the no-trip line without a search,
every failure path returns the route-aware soft fallback (no invented
specifics) instead of raising, and — the phase's core invariant — the call
leaves session/booking state exactly untouched: nothing bookable can enter
the session from a return question.
"""
import asyncio
import time
from datetime import date
from unittest.mock import MagicMock

import pytest

from api import concierge
from api.helpers.bigquery_helper import bq_helper
from api.repositories.models import ItineraryItem, Trip


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(concierge, "_SESSION_TRIPS", {})


def _pin_trip(session_id="room-1", origin="JFK", destinations=("LAX",)):
    trip = Trip(
        trip_id="t-1", user_id="demo-traveler",
        title="The Complete Trip — hackathon demo", status="booked",
        origin=origin, destinations=list(destinations),
        start_date=date(2026, 7, 21), end_date=date(2026, 7, 23),
    )
    items = [ItineraryItem(trip_id="t-1", type="flight", status="booked")]
    concierge._SESSION_TRIPS[session_id] = concierge.TripContext(
        trip=trip, items=items, summary="summary"
    )


_INDICATION = (
    "Three airlines operate nonstop flights from LAX to JFK: "
    "JetBlue, American Airlines, and Delta Air Lines."
)


def _capture_search(monkeypatch, reply=_INDICATION):
    queries = []

    def fake_search(query):
        queries.append(query)
        return reply

    monkeypatch.setattr(concierge, "_tavily_search", fake_search)
    return queries


# --- query construction (reverse route, human-formatted date) ----------------


def test_pinned_trip_with_date_queries_reverse_route_and_query_date(monkeypatch):
    queries = _capture_search(monkeypatch)
    _pin_trip()

    reply = asyncio.run(
        concierge.check_return_flights_impl("room-1", "2026-07-26")
    )

    assert reply == concierge._RETURN_FRAMING + _INDICATION
    assert queries == ["flights from LAX to JFK on July 26, 2026"]


def test_pinned_trip_dateless_queries_route_only(monkeypatch):
    queries = _capture_search(monkeypatch)
    _pin_trip()

    reply = asyncio.run(concierge.check_return_flights_impl("room-1"))

    assert reply == concierge._RETURN_FRAMING + _INDICATION
    assert queries == ["flights from LAX to JFK"]


def test_malformed_date_passes_through_verbatim(monkeypatch):
    # The tool never raises on input shape — Tavily copes with odd dates.
    queries = _capture_search(monkeypatch)
    _pin_trip()

    asyncio.run(concierge.check_return_flights_impl("room-1", "next Sunday"))

    assert queries == ["flights from LAX to JFK on next Sunday"]


def test_multi_destination_trip_uses_primary_destination(monkeypatch):
    queries = _capture_search(monkeypatch)
    _pin_trip(origin="MSP", destinations=("SFO", "Mountain View"))

    asyncio.run(concierge.check_return_flights_impl("room-1", "2026-07-19"))

    assert queries == ["flights from SFO to MSP on July 19, 2026"]


# --- no trip / no route: never a search, never a raise -----------------------


def test_unpinned_session_gets_no_trip_line_without_searching(monkeypatch):
    queries = _capture_search(monkeypatch)

    reply = asyncio.run(
        concierge.check_return_flights_impl("room-1", "2026-07-26")
    )

    assert reply == concierge._NO_TRIP_SPOKEN
    assert queries == []


def test_trip_missing_route_ends_gets_fallback_without_searching(monkeypatch):
    queries = _capture_search(monkeypatch)
    _pin_trip(origin=None, destinations=())

    reply = asyncio.run(concierge.check_return_flights_impl("room-1"))

    assert reply == concierge._return_fallback()
    assert queries == []


# --- failure paths never raise (the voice turn must survive anything) --------


def _assert_honest_fallback(reply):
    """Route-aware but no invented specifics — no airline names, flight
    counts, or clock times may appear in a fallback (the honesty rule)."""
    assert reply == concierge._return_fallback("LAX to JFK")
    for invented in ("Delta", "American", "JetBlue", "nonstop", ":"):
        assert invented not in reply


def test_search_exception_returns_route_aware_fallback(monkeypatch):
    def boom(query):
        raise ValueError("tavily fell over")

    monkeypatch.setattr(concierge, "_tavily_search", boom)
    _pin_trip()

    reply = asyncio.run(
        concierge.check_return_flights_impl("room-1", "2026-07-26")
    )

    _assert_honest_fallback(reply)


def test_timeout_returns_route_aware_fallback(monkeypatch):
    monkeypatch.setattr(concierge, "_TAVILY_TIMEOUT_S", 0.05)

    def slow(query):
        time.sleep(0.5)
        return "too late"

    monkeypatch.setattr(concierge, "_tavily_search", slow)
    _pin_trip()

    reply = asyncio.run(concierge.check_return_flights_impl("room-1"))

    _assert_honest_fallback(reply)


def test_missing_key_returns_route_aware_fallback():
    # fresh_state deleted TAVILY_API_KEY; the real _tavily_search raises.
    _pin_trip()

    reply = asyncio.run(concierge.check_return_flights_impl("room-1"))

    _assert_honest_fallback(reply)


def test_empty_answer_returns_route_aware_fallback(monkeypatch):
    # An unusable Tavily response raises inside _tavily_search (Phase 35
    # contract) — this tool turns it into the route-aware fallback.
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    client = MagicMock()
    client.search.return_value = {"answer": "", "results": []}
    monkeypatch.setattr(concierge, "_tavily_client", lambda: client)
    _pin_trip()

    reply = asyncio.run(concierge.check_return_flights_impl("room-1"))

    _assert_honest_fallback(reply)


# --- session-state purity: the phase's core invariant -------------------------


def test_return_check_stores_nothing_bookable(monkeypatch):
    """The point of the Tavily path: no _SESSION_FLIGHT_OPTIONS entry, no
    _LATEST_SEARCH touch, no repository write, no pinned-context drift —
    a return question can never make anything bookable."""
    _capture_search(monkeypatch)
    _pin_trip()
    options_sentinel = {"room-1": ["option-sentinel"]}
    monkeypatch.setattr(
        concierge, "_SESSION_FLIGHT_OPTIONS", {"room-1": ["option-sentinel"]}
    )
    latest_sentinel = ("room-1", ["option-sentinel"], "recorded-at")
    monkeypatch.setattr(concierge, "_LATEST_SEARCH", latest_sentinel)
    dml, select = MagicMock(), MagicMock()
    monkeypatch.setattr(bq_helper, "run_dml", dml)
    monkeypatch.setattr(bq_helper, "run_select", select)
    context_before = concierge._SESSION_TRIPS["room-1"].model_dump_json()

    reply = asyncio.run(
        concierge.check_return_flights_impl("room-1", "2026-07-26")
    )

    assert reply.startswith(concierge._RETURN_FRAMING)
    assert concierge._SESSION_TRIPS["room-1"].model_dump_json() == context_before
    assert concierge._SESSION_FLIGHT_OPTIONS == options_sentinel
    assert concierge._LATEST_SEARCH is latest_sentinel
    dml.assert_not_called()
    select.assert_not_called()


# --- registration & instruction routing ---------------------------------------


def test_tool_always_registered_without_key():
    agent = concierge.build_agent("room-1")
    assert "check_return_flights" in {t.name for t in agent.tools}


def test_instructions_route_return_questions_to_the_tool():
    assert "check_return_flights" in concierge.BASE_INSTRUCTIONS
    assert "is there a way to get home" in concierge.BASE_INSTRUCTIONS
    # The elicitation rule: ask for the date first, dateless on a decline.
    assert "ask for it in one short turn first" in concierge.BASE_INSTRUCTIONS
    assert "call the tool without a date" in concierge.BASE_INSTRUCTIONS
