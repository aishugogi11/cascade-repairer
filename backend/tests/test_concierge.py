"""Phase 9 tests — the Concierge hybrid, hermetic.

BigQuery mocked at the bq_helper boundary, the agent at the Runner boundary,
Sabre through its mock client (no OPENAI_API_KEY, no GCP, no network). The
load-bearing contracts: fix_trip launches and returns while repairs are still
in flight (the inversion), the per-turn instructions carry the authoritative
session snapshot, failures come back speakable, and the acceptance shape —
a turn is answered while five real repair coroutines run — holds end to end.
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from api import concierge
from api import concurrency_core as core
from api.helpers.bigquery_helper import bq_helper
from api.sabre import client as sabre_client


class _FakeResult:
    def __init__(self, input_items, reply):
        self._items = list(input_items) + [{"role": "assistant", "content": reply}]
        self.final_output = reply

    def to_input_list(self):
        return self._items


def _mock_runner(monkeypatch, reply="Right away.", captured=None):
    calls = []

    class _FakeRunner:
        @classmethod
        async def run(cls, agent, input, max_turns=None):
            calls.append(input)
            if captured is not None:
                captured["agent"] = agent
            return _FakeResult(input, reply)

    monkeypatch.setattr(concierge, "Runner", _FakeRunner)
    return calls


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.delenv("SABRE_MODE", raising=False)
    monkeypatch.setattr(sabre_client._mock, "latency_seconds", 0)
    monkeypatch.setattr(concierge, "_HISTORY", {})
    monkeypatch.setattr(concierge, "_SESSION_TRIPS", {})
    monkeypatch.setattr(concierge, "_SESSION_FLIGHT_OPTIONS", {})
    core._SESSIONS.clear()
    yield
    core._SESSIONS.clear()


def trip_row():
    return {
        "trip_id": "t-1", "user_id": "demo-traveler",
        "title": "The Complete Trip — hackathon demo", "status": "booked",
        "origin": "MSP", "destinations": ["SFO", "Mountain View"],
        "start_date": "2026-07-17", "end_date": "2026-07-19",
    }


def five_item_rows():
    return [
        {
            "item_id": f"i-{t}", "trip_id": "t-1", "type": t, "status": "broken"
            if t == "flight" else "booked",
            "location": "MSP-SFO" if t == "flight" else "Mountain View",
        }
        for t in ("flight", "hotel", "ground", "dining", "experience")
    ]


@pytest.fixture
def bq(monkeypatch):
    """run_select routed by table: latest trip, the trip's items, bookings."""
    def route_select(query, params=None):
        if "itinerary_items" in query:
            return True, five_item_rows(), None
        if "bookings" in query:
            return True, [], None
        return True, [trip_row()], None

    dml = MagicMock(return_value=(True, 1, None))
    select = MagicMock(side_effect=route_select)
    monkeypatch.setattr(bq_helper, "run_dml", dml)
    monkeypatch.setattr(bq_helper, "run_select", select)
    return SimpleNamespace(dml=dml, select=select)


def _trip_selects(select):
    """The select calls that hit the trips table (the pin's read)."""
    return [
        c for c in select.call_args_list
        if "itinerary_items" not in c.args[0] and "bookings" not in c.args[0]
    ]


# --- answer_query (module-level seam) -----------------------------------------


def test_answer_query_replays_and_stores_history(monkeypatch, bq):
    calls = _mock_runner(monkeypatch, reply="Hello there.")

    async def scenario():
        await concierge.answer_query("room-1", "first")
        await concierge.answer_query("room-1", "second")

    asyncio.run(scenario())
    assert len(calls) == 2
    contents = [item.get("content") for item in calls[1]]
    assert "first" in contents and "second" in contents
    assert any(i.get("role") == "assistant" for i in calls[1])
    # A different session starts clean.
    assert "room-2" not in concierge._HISTORY


def test_agent_instructions_carry_authoritative_snapshot(monkeypatch, bq):
    captured = {}
    _mock_runner(monkeypatch, captured=captured)

    async def scenario():
        async def done_work():
            return {"status": "done"}

        finished = core.start_background_call("room-9", "move_dining", done_work())
        await finished
        pending = core.start_background_call(
            "room-9", "rebook_flight", asyncio.sleep(30)
        )
        try:
            await concierge.answer_query("room-9", "how are the repairs coming?")
        finally:
            pending.cancel()

    asyncio.run(scenario())
    instructions = captured["agent"].instructions
    assert "authoritative" in instructions
    assert "rebook_flight" in instructions          # pending, by name
    assert "move_dining: done" in instructions       # finished, by name
    assert instructions.startswith(concierge.BASE_INSTRUCTIONS)


def test_agent_uses_fast_model_and_exposes_guided_toolset(monkeypatch):
    monkeypatch.delenv("CONCIERGE_LLM_MODEL", raising=False)
    agent = concierge.build_agent("room-1")
    assert agent.model == "gpt-5.4-mini"
    # The Phase 17 guided flow replaces the Phase 16 magic utterance.
    assert {t.name for t in agent.tools} == {
        "fix_trip", "search_flights", "book_flight", "complete_trip",
    }
    # Without a pinned trip, the agent is told so instead of guessing.
    assert concierge._NO_TRIP_LINE in agent.instructions


# --- trip context (QA addendum) ---------------------------------------------


def test_trip_summary_injected_into_instructions(monkeypatch, bq):
    captured = {}
    _mock_runner(monkeypatch, captured=captured)

    asyncio.run(concierge.answer_query("room-1", "where do I fly into?"))

    instructions = captured["agent"].instructions
    assert "TRIP CONTEXT" in instructions and "authoritative" in instructions
    assert "MSP" in instructions and "SFO, Mountain View" in instructions
    assert "2026-07-17 to 2026-07-19" in instructions
    assert "flight (MSP-SFO)" in instructions and "hotel" in instructions
    # Statuses stay out of the static summary — live progress is the snapshot's.
    assert "broken" not in concierge._SESSION_TRIPS["room-1"].summary


def test_trip_is_pinned_once_per_session(monkeypatch, bq):
    _mock_runner(monkeypatch)

    async def scenario():
        await concierge.answer_query("room-1", "hi")
        await concierge.answer_query("room-1", "where am I staying?")

    asyncio.run(scenario())
    # One trips read + one items read for the whole session, not per turn.
    assert len(_trip_selects(bq.select)) == 1
    assert len([
        c for c in bq.select.call_args_list if "itinerary_items" in c.args[0]
    ]) == 1


def test_failed_pin_never_blocks_the_turn_and_retries(monkeypatch, bq):
    captured = {}
    _mock_runner(monkeypatch, reply="Still here.", captured=captured)
    healthy_route = bq.select.side_effect
    bq.select.side_effect = lambda query, params=None: (False, [], "bq down")

    reply = asyncio.run(concierge.answer_query("room-1", "hello?"))
    assert reply == "Still here."  # the turn survived the failed pin
    assert concierge._NO_TRIP_LINE in captured["agent"].instructions
    assert "room-1" not in concierge._SESSION_TRIPS  # failure not cached

    bq.select.side_effect = healthy_route
    asyncio.run(concierge.answer_query("room-1", "and now?"))
    assert "TRIP CONTEXT" in captured["agent"].instructions  # retry pinned it


def test_ensure_trip_context_explicit_trip_id_is_the_phase_12_seam(monkeypatch, bq):
    def route_with_lookup(query, params=None):
        if "itinerary_items" in query:
            return True, five_item_rows(), None
        if "WHERE trip_id" in query:
            row = dict(trip_row(), trip_id="t-explicit")
            return True, [row], None
        raise AssertionError("latest-trip query must not run when trip_id is given")

    bq.select.side_effect = route_with_lookup

    async def scenario():
        return await concierge.ensure_trip_context("room-1", trip_id="t-explicit")

    context, error = asyncio.run(scenario())
    assert error is None
    assert context.trip.trip_id == "t-explicit"
    assert concierge._SESSION_TRIPS["room-1"] is context


# --- fix_trip -------------------------------------------------------------------


def test_fix_trip_no_trip_is_speakable(monkeypatch, bq):
    bq.select.side_effect = lambda query, params=None: (True, [], None)
    msg = asyncio.run(concierge.fix_trip_impl("room-1"))
    assert "don't see a booked trip" in msg


def test_fix_trip_lookup_failure_is_speakable_never_raises(monkeypatch, bq):
    bq.select.side_effect = lambda query, params=None: (False, [], "bq down")
    msg = asyncio.run(concierge.fix_trip_impl("room-1"))
    assert "trouble reaching the booking system" in msg


def test_fix_trip_launches_all_items_and_returns_before_completion(monkeypatch, bq):
    seen = {}

    def fake_launch(session_id, items):
        seen["session_id"] = session_id
        seen["items"] = items
        seen["task"] = asyncio.ensure_future(asyncio.sleep(30))
        return ["rebook_flight", "shift_hotel_dates"], [seen["task"]]

    monkeypatch.setattr(concierge, "launch_trip_repairs", fake_launch)

    async def scenario():
        # wait_for is the await-guard: if fix_trip awaited the repair task,
        # this would time out instead of returning.
        msg = await asyncio.wait_for(concierge.fix_trip_impl("room-1"), 2.0)
        assert not seen["task"].done()
        seen["task"].cancel()
        return msg

    msg = asyncio.run(scenario())
    assert seen["session_id"] == "room-1"
    assert len(seen["items"]) == 5
    assert "rebook flight" in msg and "shift hotel dates" in msg


# --- guided booking (Phase 17): search → options → book → complete -----------


def _mock_repos(monkeypatch):
    """The repository boundary for the booking writes: every call recorded,
    all succeed. ensure_trip_context's reads come back canned so the pin
    replacement lands on the freshly created trip."""
    import threading

    seen = {"writes": [], "threads": []}

    def create_trip(trip):
        seen["writes"].append(("trip", trip))
        seen["threads"].append(threading.current_thread())
        return True, trip, None

    def create_item(item):
        seen["writes"].append(("item", item))
        return True, item, None

    def create_booking(booking):
        seen["writes"].append(("booking", booking))
        return True, booking, None

    def update_status(item_id, status):
        seen["writes"].append(("status", item_id, status))
        return True, 1, None

    def get_trip(trip_id):
        return True, concierge.Trip(**dict(trip_row(), trip_id=trip_id)), None

    def list_items(trip_id):
        items = [
            concierge.ItineraryItem(**dict(row, trip_id=trip_id))
            for row in five_item_rows()
        ]
        return True, items, None

    monkeypatch.setattr(concierge.trips, "create_trip", create_trip)
    monkeypatch.setattr(concierge.itinerary_items, "create_item", create_item)
    monkeypatch.setattr(concierge.bookings, "create_booking", create_booking)
    monkeypatch.setattr(concierge.itinerary_items, "update_status", update_status)
    monkeypatch.setattr(concierge.trips, "get_trip", get_trip)
    monkeypatch.setattr(
        concierge.itinerary_items, "list_items_for_trip", list_items
    )
    return seen


def _search(session="room-1"):
    return asyncio.run(
        concierge.search_flights_impl(session, "MSP", "SFO", "2026-07-17")
    )


def test_search_flights_stores_options_and_speaks_them(bq):
    msg = _search()

    options = concierge._SESSION_FLIGHT_OPTIONS["room-1"]
    assert 2 <= len(options) <= 3
    assert [o.option_number for o in options] == list(range(1, len(options) + 1))
    # Listenable, not readable: numbered words, rounded dollars, and none of
    # the airline/fare codes or markdown the spoken-copy rule bans.
    assert "Option one" in msg and "Option two" in msg
    assert "dollars" in msg
    assert "AA" not in msg and "USD" not in msg and "*" not in msg


def test_search_flights_failure_is_speakable_never_raises(monkeypatch, bq):
    async def broken_search(request):
        raise RuntimeError("sabre down")

    monkeypatch.setattr(concierge.sabre_client, "flight_search", broken_search)

    msg = _search()

    assert "trouble searching flights" in msg
    assert "room-1" not in concierge._SESSION_FLIGHT_OPTIONS


def test_search_flights_blank_args_ask_instead_of_searching(bq):
    msg = asyncio.run(concierge.search_flights_impl("room-1", "MSP", " ", ""))

    assert "where" in msg.lower()
    assert "room-1" not in concierge._SESSION_FLIGHT_OPTIONS


def test_book_flight_without_search_is_speakable_and_writes_nothing(monkeypatch, bq):
    seen = _mock_repos(monkeypatch)

    msg = asyncio.run(concierge.book_flight_impl("room-1", 1))

    assert "search" in msg
    assert seen["writes"] == []


def test_book_flight_bad_option_number_is_speakable_and_writes_nothing(
    monkeypatch, bq
):
    seen = _mock_repos(monkeypatch)
    _search()

    msg = asyncio.run(concierge.book_flight_impl("room-1", 4))

    assert "three options" in msg
    assert seen["writes"] == []
    # The options survive so the traveler can just say a valid number next.
    assert "room-1" in concierge._SESSION_FLIGHT_OPTIONS


def test_book_flight_creates_rows_replaces_pin_and_clears_options(monkeypatch, bq):
    import threading

    seen = _mock_repos(monkeypatch)
    _search()
    # A stale pin from earlier in the session — booking must replace it.
    stale = concierge.TripContext(
        trip=concierge.Trip(**dict(trip_row(), trip_id="t-old")),
        items=[],
        summary="old",
    )
    concierge._SESSION_TRIPS["room-1"] = stale

    msg = asyncio.run(concierge.book_flight_impl("room-1", 1))

    kinds = [w[0] for w in seen["writes"]]
    assert kinds == ["trip", "item", "booking", "status"]
    trip = seen["writes"][0][1]
    item = seen["writes"][1][1]
    booking = seen["writes"][2][1]
    assert trip.destinations == ["SFO"] and trip.origin == "MSP"
    assert item.type == "flight" and item.status == "planned"
    assert seen["writes"][3][1:] == (item.item_id, "booked")
    assert booking.raw_response["source"] == "voice_guided_booking"
    assert booking.raw_response["option"]["option_number"] == 1
    assert len(booking.raw_response["options_offered"]) >= 2
    # Blocking writes ran off the event loop's thread (the to_thread rule).
    assert seen["threads"][0] is not threading.main_thread()
    # Pin replaced with the new trip; the spent options are gone.
    assert concierge._SESSION_TRIPS["room-1"].trip.trip_id == trip.trip_id
    assert "room-1" not in concierge._SESSION_FLIGHT_OPTIONS
    # Spoken copy: confirmation with the spoken date, no ids or markdown.
    assert "booked" in msg and "July 17th" in msg
    assert trip.trip_id not in msg and "*" not in msg


def test_book_flight_write_failure_is_speakable(monkeypatch, bq):
    _mock_repos(monkeypatch)
    _search()
    monkeypatch.setattr(
        concierge.trips, "create_trip",
        lambda trip: (False, None, "bq down"),
    )

    msg = asyncio.run(concierge.book_flight_impl("room-1", 1))

    assert "couldn't get that flight booked" in msg


def test_complete_trip_without_pin_is_speakable(bq):
    msg = asyncio.run(concierge.complete_trip_impl("room-1"))

    assert "flight" in msg and "booked first" in msg


def test_complete_trip_spaces_items_and_returns_immediately(monkeypatch, bq):
    seen = _mock_repos(monkeypatch)
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(concierge, "_sleep", fake_sleep)
    concierge._SESSION_TRIPS["room-1"] = concierge.TripContext(
        trip=concierge.Trip(**trip_row()), items=[], summary="pinned",
    )

    async def scenario():
        msg = await asyncio.wait_for(concierge.complete_trip_impl("room-1"), 2.0)
        # The reply came back before the build-out ran its course.
        assert "building the rest of your trip" in msg
        await asyncio.gather(*concierge._BUILD_TASKS)

    asyncio.run(scenario())

    # Four items, spaced by a sleep each (asserted on calls, not wall clock),
    # each created planned then flipped to booked.
    assert sleeps == [1.5, 1.5, 1.5, 1.5]
    created = [w[1] for w in seen["writes"] if w[0] == "item"]
    assert [i.type for i in created] == ["hotel", "ground", "dining", "experience"]
    assert all(i.status == "planned" for i in created)
    flips = [w for w in seen["writes"] if w[0] == "status"]
    assert [f[1] for f in flips] == [i.item_id for i in created]
    assert all(f[2] == "booked" for f in flips)
    # Dates and destination derive from the booked trip.
    assert all(i.trip_id == "t-1" for i in created)
    assert "SFO" in created[0].location


def test_instructions_carry_the_guided_script():
    for phrase in ("search_flights", "book_flight", "complete_trip",
                   "destination", "pick one by number"):
        assert phrase in concierge.BASE_INSTRUCTIONS
    # The retired magic utterance is gone from the script...
    assert "book_trip " not in concierge.BASE_INSTRUCTIONS
    # ...and the guard against re-booking a pinned trip stands.
    assert (
        "Never call search_flights or book_flight when a trip is already "
        "booked" in concierge.BASE_INSTRUCTIONS
    )
    # Disruption rules untouched.
    assert "fix_trip" in concierge.BASE_INSTRUCTIONS


# --- the acceptance shape (Phase 5's test over the seam) -------------------------


def test_talk_while_repairing_acceptance_shape(monkeypatch, bq):
    """fix_trip launches the REAL cascade (real launch seam, real repair
    tools against the Sabre mock with latency); a follow-up turn is answered
    while the repairs are still in flight; every completion event lands ok."""
    monkeypatch.setattr(sabre_client._mock, "latency_seconds", 0.5)
    _mock_runner(monkeypatch, reply="Repairs are humming along.")

    async def scenario():
        msg = await asyncio.wait_for(concierge.fix_trip_impl("vb-room-1"), 2.0)
        assert "5 parts" in msg

        session = core.get_session("vb-room-1")
        assert len(session.pending()) == 5  # nothing awaited inline

        reply = await asyncio.wait_for(
            concierge.answer_query("vb-room-1", "how's it going?"), 2.0
        )
        assert reply == "Repairs are humming along."
        assert session.pending(), "flight/hotel repairs should still be in flight"

        await asyncio.gather(*session.tasks)
        assert len(session.events) == 5
        assert all(e.status == "ok" for e in session.events)
        assert {e.name for e in session.events} == {
            "rebook_flight", "shift_hotel_dates", "reschedule_ground",
            "move_dining", "rebook_experience",
        }

    asyncio.run(scenario())
