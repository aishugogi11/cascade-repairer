"""Phase 9 tests — the Concierge hybrid, hermetic.

BigQuery mocked at the bq_helper boundary, the agent at the Runner boundary,
Sabre through its mock client (no OPENAI_API_KEY, no GCP, no network). The
load-bearing contracts: fix_trip launches and returns while repairs are still
in flight (the inversion), the per-turn instructions carry the authoritative
session snapshot, failures come back speakable, and the acceptance shape —
a turn is answered while five real repair coroutines run — holds end to end.
"""
import asyncio
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from agents.tool_context import ToolContext

from api import concierge
from api import concurrency_core as core
from api.helpers.bigquery_helper import bq_helper
from api.sabre import client as sabre_client
from api.sabre import shapes


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
    monkeypatch.setattr(concierge, "_LATEST_SEARCH", None)
    monkeypatch.setattr(concierge, "_LATEST_BOOKING", None)
    core._SESSIONS.clear()
    yield
    core._SESSIONS.clear()


def trip_row():
    return {
        "trip_id": "t-1", "user_id": "demo-traveler",
        "title": "The Complete Trip", "status": "booked",
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
    monkeypatch.delenv("FEATHERLESS_API_KEY", raising=False)
    agent = concierge.build_agent("room-1")
    assert agent.model == "gpt-5.4-mini"
    # The Phase 17 guided flow replaces the Phase 16 magic utterance;
    # Phase 23 adds the live trip_status read; Phase 35 the Tavily
    # destination_info lookup (registered key or no key); Phase 34 the
    # verify-only check_return_flights indication (same always-registered
    # rule); Phase 40 the email_itinerary offer (registered key or no key —
    # the send module degrades to "disabled", never an import-time gate).
    assert {t.name for t in agent.tools} == {
        "fix_trip", "offer_rebook", "search_flights", "set_recovery_preferences",
        "book_flight", "complete_trip",
        "trip_status", "destination_info", "check_return_flights",
        "email_itinerary",
        "analyze_itinerary", "apply_optimization", "reject_optimization",
        "esim_plan", "first_stop_uber", "reschedule_hotel",
    }
    # Without a pinned trip, the agent is told so instead of guessing.
    assert concierge._NO_TRIP_LINE in agent.instructions


# --- trip context (QA addendum) ---------------------------------------------


def test_trip_summary_injected_into_instructions(monkeypatch, bq):
    captured = {}
    _mock_runner(monkeypatch, captured=captured)

    async def scenario():
        # Phase 18: pins come only from an explicit trip_id (the disrupt
        # flow's seam) — a cold answer_query no longer pins anything.
        await concierge.ensure_trip_context("room-1", trip_id="t-1")
        await concierge.answer_query("room-1", "where do I fly into?")

    asyncio.run(scenario())

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
        await concierge.ensure_trip_context("room-1", trip_id="t-1")
        await concierge.answer_query("room-1", "hi")
        await concierge.answer_query("room-1", "where am I staying?")

    asyncio.run(scenario())
    # One trips read + one items read for the whole session, not per turn.
    assert len(_trip_selects(bq.select)) == 1
    assert len([
        c for c in bq.select.call_args_list if "itinerary_items" in c.args[0]
    ]) == 1


def test_cold_session_stays_unpinned_no_fallback_query(monkeypatch, bq):
    """Phase 18: with no cached pin and no trip_id there is NO trips-table
    SELECT — the latest-trip fallback is gone — and the speakable no-trip
    line comes back instead."""
    context, error = asyncio.run(concierge.ensure_trip_context("room-1"))

    assert context is None
    assert error == "I don't see a booked trip for you yet."
    assert "room-1" not in concierge._SESSION_TRIPS
    assert bq.select.call_args_list == []


def test_failed_pin_never_blocks_the_turn_and_retries(monkeypatch, bq):
    """A failed explicit pin comes back speakable, is never cached, and the
    session keeps answering unpinned until a healthy pin lands."""
    captured = {}
    _mock_runner(monkeypatch, reply="Still here.", captured=captured)
    healthy_route = bq.select.side_effect
    bq.select.side_effect = lambda query, params=None: (False, [], "bq down")

    async def failed_pin_then_turn():
        context, error = await concierge.ensure_trip_context(
            "room-1", trip_id="t-1"
        )
        assert context is None
        assert "trouble reaching the booking system" in error
        return await concierge.answer_query("room-1", "hello?")

    reply = asyncio.run(failed_pin_then_turn())
    assert reply == "Still here."  # the turn survived the failed pin
    assert concierge._NO_TRIP_LINE in captured["agent"].instructions
    assert "room-1" not in concierge._SESSION_TRIPS  # failure not cached

    bq.select.side_effect = healthy_route

    async def healthy_pin_then_turn():
        await concierge.ensure_trip_context("room-1", trip_id="t-1")
        await concierge.answer_query("room-1", "and now?")

    asyncio.run(healthy_pin_then_turn())
    assert "TRIP CONTEXT" in captured["agent"].instructions  # retry pinned it


def test_answer_query_trip_id_pins_the_displayed_trip(monkeypatch, bq):
    """Phase 19: the caller's displayed trip rides through answer_query into
    ensure_trip_context — an unpinned session pins it and the agent's
    instructions carry its summary."""
    captured = {}
    _mock_runner(monkeypatch, captured=captured)

    asyncio.run(
        concierge.answer_query("room-1", "where am I staying?", trip_id="t-1")
    )

    assert concierge._SESSION_TRIPS["room-1"].trip.trip_id == "t-1"
    instructions = captured["agent"].instructions
    assert "TRIP CONTEXT" in instructions
    assert "MSP" in instructions and "SFO, Mountain View" in instructions


def test_answer_query_confirms_loaded_itinerary_without_llm(monkeypatch, bq):
    """'Do you have my itinerary?' must not invent a no-trip answer when a
    Cascade/Optimize trip is already in memory — bypass the LLM."""
    from api import memory_trips

    memory_trips.clear()
    seeded = memory_trips.seed("optimize-upload", "SFO → New York")
    calls = _mock_runner(monkeypatch)
    reply = asyncio.run(concierge.answer_query(
        "confirm-room",
        "Do you have my itinerary?",
        trip_id=seeded["trip_id"],
    ))
    assert calls == []
    assert "yes" in reply.lower()
    assert "itinerary" in reply.lower()
    assert "sfo" in reply.lower() or "new york" in reply.lower()
    assert concierge._SESSION_TRIPS["confirm-room"].trip.trip_id == seeded["trip_id"]
    memory_trips.clear()


def test_answer_query_adopts_memory_trip_for_look_at_itinerary(monkeypatch, bq):
    """Even without trip_id, itinerary questions must adopt the loaded trip
    instead of answering from the unpinned no-trip line."""
    from api import memory_trips

    memory_trips.clear()
    seeded = memory_trips.seed("optimize-upload", "SFO → New York")
    calls = _mock_runner(monkeypatch)
    reply = asyncio.run(concierge.answer_query(
        "adopt-room",
        "Look at my itinerary",
    ))
    assert calls == []
    assert "yes" in reply.lower()
    assert concierge._SESSION_TRIPS["adopt-room"].trip.trip_id == seeded["trip_id"]
    memory_trips.clear()


def test_fresh_booking_detector_ignores_first_stop_asks():
    assert concierge._wants_fresh_booking(
        "book me a flight from Minneapolis to Dallas on 2026-07-13"
    )
    assert not concierge._wants_fresh_booking(
        "What is the best option for the first stop?"
    )
    assert concierge._wants_first_stop_uber(
        "What is the best option for the first stop?"
    )


def test_answer_query_trip_id_never_clobbers_an_existing_pin(monkeypatch, bq):
    """Pin-only-if-unpinned (decision 2026-07-12): a session pinned to trip A
    queried with trip_id=B stays on A — no re-read, no re-pin. The selector
    repoints polling; voice follows the session's first pinned trip."""
    captured = {}
    _mock_runner(monkeypatch, captured=captured)
    pinned = concierge.TripContext(
        trip=concierge.Trip(**dict(trip_row(), trip_id="t-A", title="Trip A")),
        items=[],
        summary="TRIP CONTEXT: Trip A. ",
    )
    concierge._SESSION_TRIPS["room-1"] = pinned

    asyncio.run(concierge.answer_query("room-1", "what trip is this?",
                                       trip_id="t-B"))

    assert concierge._SESSION_TRIPS["room-1"] is pinned
    assert "Trip A" in captured["agent"].instructions
    assert bq.select.call_args_list == []  # cache hit — B never read


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
    """A cold unpinned session gets the no-trip line — no raise, and no
    trips-table read now that the latest-trip fallback is gone (Phase 18)."""
    msg = asyncio.run(concierge.fix_trip_impl("room-1"))
    assert "don't see a booked trip" in msg
    assert bq.select.call_args_list == []


def test_explicit_pin_lookup_failure_is_speakable_never_raises(monkeypatch, bq):
    bq.select.side_effect = lambda query, params=None: (False, [], "bq down")
    _, error = asyncio.run(concierge.ensure_trip_context("room-1", trip_id="t-1"))
    assert "trouble reaching the booking system" in error


def test_fix_trip_launches_all_items_and_returns_before_completion(monkeypatch, bq):
    seen = {}

    def fake_launch(session_id, items):
        seen["session_id"] = session_id
        seen["items"] = items
        seen["task"] = asyncio.ensure_future(asyncio.sleep(30))
        return ["rebook_flight", "shift_hotel_dates"], [seen["task"]]

    monkeypatch.setattr(concierge, "launch_trip_repairs", fake_launch)

    async def scenario():
        await concierge.ensure_trip_context("room-1", trip_id="t-1")
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


def test_fix_trip_defers_to_the_phone_during_a_consent_wait(monkeypatch, bq):
    """Phase 31 (interview decision): one consent channel at a time. While
    Call 1 is out asking, fix_trip launches nothing and points the traveler
    at the phone; a resolved window launches normally again."""
    from api import consent as consent_module

    consent_module.reset()
    launched = []
    monkeypatch.setattr(
        concierge, "launch_trip_repairs",
        lambda sid, items: (launched.append(sid), (["rebook_flight"], []))[1],
    )

    async def scenario():
        await concierge.ensure_trip_context("room-1", trip_id="t-1")
        consent_module.register_awaiting("t-1", "room-77")
        deferred = await concierge.fix_trip_impl("room-1")
        token = consent_module.current("t-1").token
        consent_module.resolve("t-1", token, consent_module.DECLINED)
        after = await concierge.fix_trip_impl("room-1")
        return deferred, after

    deferred, after = asyncio.run(scenario())
    assert "on the phone" in deferred and "say yes" in deferred
    assert "Repairs are launched" in after
    assert launched == ["room-1"]  # only the post-window call launched
    consent_module.reset()


def test_fix_trip_ignores_another_trips_consent_wait(monkeypatch, bq):
    from api import consent as consent_module

    consent_module.reset()
    launched = []
    monkeypatch.setattr(
        concierge, "launch_trip_repairs",
        lambda sid, items: (launched.append(sid), (["rebook_flight"], []))[1],
    )

    async def scenario():
        await concierge.ensure_trip_context("room-1", trip_id="t-1")
        consent_module.register_awaiting("t-other", "room-99")
        return await concierge.fix_trip_impl("room-1")

    msg = asyncio.run(scenario())
    assert "Repairs are launched" in msg
    assert launched == ["room-1"]
    consent_module.reset()


def test_fix_trip_registry_failure_never_kills_the_turn(monkeypatch, bq):
    """A consent-registry hiccup reads as 'no wait' — the spoken turn and
    the launch survive (best-effort by contract)."""
    def explode(trip_id):
        raise RuntimeError("registry on fire")

    monkeypatch.setattr(concierge.consent, "current", explode)
    launched = []
    monkeypatch.setattr(
        concierge, "launch_trip_repairs",
        lambda sid, items: (launched.append(sid), (["rebook_flight"], []))[1],
    )

    async def scenario():
        await concierge.ensure_trip_context("room-1", trip_id="t-1")
        return await concierge.fix_trip_impl("room-1")

    msg = asyncio.run(scenario())
    assert "Repairs are launched" in msg
    assert launched == ["room-1"]


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
    assert 2 <= len(options) <= 6
    assert [o.option_number for o in options] == list(range(1, len(options) + 1))
    # Listenable, not readable: numbered words, rounded dollars, and none of
    # the airline/fare codes or markdown the spoken-copy rule bans.
    assert "Option one" in msg and "Option two" in msg
    assert "dollars" in msg
    assert "AA" not in msg and "USD" not in msg and "*" not in msg


def test_search_flights_failure_is_speakable_never_raises(monkeypatch, bq):
    async def broken_search(request):
        raise RuntimeError("sabre down")

    # Phase 27: the guided flow searches InstaFlights, not BFM.
    monkeypatch.setattr(
        concierge.sabre_client, "instaflights_search", broken_search
    )

    msg = _search()

    assert "trouble searching flights" in msg
    assert "room-1" not in concierge._SESSION_FLIGHT_OPTIONS


def test_search_flights_blank_args_ask_instead_of_searching(bq):
    msg = asyncio.run(concierge.search_flights_impl("room-1", "MSP", " ", ""))

    assert "where" in msg.lower()
    assert "room-1" not in concierge._SESSION_FLIGHT_OPTIONS


def test_search_flights_records_the_latest_search_slot(bq):
    """Phase 21: the booking page's candidates come from this slot — search
    fills it with the same options the session stores, stamped when."""
    _search()

    slot = concierge._LATEST_SEARCH
    assert slot is not None
    assert slot.session_id == "room-1"
    assert slot.options == concierge._SESSION_FLIGHT_OPTIONS["room-1"]
    assert slot.recorded_at.tzinfo is not None  # an honest UTC instant
    assert slot.origin == "MSP" and slot.destination == "SFO"
    assert slot.depart_date == "2026-07-17"
    assert len(slot.available_dates) == concierge._CALENDAR_DAYS
    assert slot.available_dates[0]["date"] == "2026-07-17"
    assert slot.available_dates[0]["selected"] is True
    assert slot.available_dates[0]["available"] is True
    assert slot.available_dates[0]["lowest_price"] is not None
    assert all(d["date"] for d in slot.available_dates)


def test_search_flights_mentions_other_dates_on_the_screen(bq):
    msg = _search()
    assert "on the screen" in msg


def test_select_search_date_reshops_same_route_and_keeps_window(bq):
    _search()
    second = concierge._LATEST_SEARCH.available_dates[1]["date"]
    msg = asyncio.run(concierge.select_search_date_impl(second))

    slot = concierge._LATEST_SEARCH
    assert "Option one" in msg
    assert slot.depart_date == second
    assert slot.origin == "MSP" and slot.destination == "SFO"
    assert slot.available_dates[0]["date"] == "2026-07-17"  # window held
    selected = [d for d in slot.available_dates if d["selected"]]
    assert selected == [d for d in slot.available_dates if d["date"] == second]


def test_select_search_date_without_a_route_asks(bq):
    msg = asyncio.run(concierge.select_search_date_impl("2026-07-18"))
    assert "destination" in msg.lower()


def test_empty_day_still_surfaces_available_neighbor_dates(monkeypatch, bq):
    """InstaFlights 404s a cache-miss day; neighbors that have fares must
    still land on the screen so the traveler can pick a date."""
    from api.sabre.mock_client import MockSabreClient

    mock = MockSabreClient()
    empty = shapes.InstaFlightsResponse(PricedItineraries=[])

    async def missing_requested(request):
        if request.departuredate == "2026-07-17":
            return empty
        return await mock.instaflights_search(request)

    monkeypatch.setattr(
        concierge.sabre_client, "instaflights_search", missing_requested
    )
    msg = asyncio.run(
        concierge.search_flights_impl("room-1", "JFK", "LAX", "2026-07-17")
    )

    assert "couldn't find any flights" in msg
    assert "on the screen" in msg
    assert "room-1" not in concierge._SESSION_FLIGHT_OPTIONS
    slot = concierge._LATEST_SEARCH
    assert slot is not None
    assert slot.options == []
    assert slot.depart_date == "2026-07-17"
    chips = slot.available_dates
    asked = next(c for c in chips if c["date"] == "2026-07-17")
    assert asked["available"] is False and asked["selected"] is True
    open_days = [c for c in chips if c["available"]]
    assert open_days
    assert any(c["lowest_price"] is not None for c in open_days)
    block = concierge.current_pending_options()
    assert block["options"] == []
    assert any(d["available"] for d in block["available_dates"])


def test_calendar_neighbor_failure_still_keeps_the_selected_day(monkeypatch, bq):
    from api.sabre.mock_client import MockSabreClient

    mock = MockSabreClient()

    async def flaky(request):
        if request.departuredate != "2026-07-17":
            raise RuntimeError("cache miss")
        return await mock.instaflights_search(request)

    monkeypatch.setattr(concierge.sabre_client, "instaflights_search", flaky)
    _search()

    chips = concierge._LATEST_SEARCH.available_dates
    assert chips[0]["available"] is True and chips[0]["selected"] is True
    assert all(not c["available"] for c in chips[1:])


def test_pending_options_include_available_dates(bq):
    _search()
    block = concierge.current_pending_options()
    assert len(block["available_dates"]) == 7
    assert block["origin"] == "MSP"
    assert block["depart_date"] == "2026-07-17"


def test_second_search_replaces_the_latest_search_slot(bq):
    _search("room-1")
    first = concierge._LATEST_SEARCH
    _search("room-2")

    assert concierge._LATEST_SEARCH is not first
    assert concierge._LATEST_SEARCH.session_id == "room-2"


def test_search_failure_leaves_the_latest_search_slot_empty(monkeypatch, bq):
    async def broken_search(request):
        raise RuntimeError("sabre down")

    monkeypatch.setattr(
        concierge.sabre_client, "instaflights_search", broken_search
    )
    _search()

    assert concierge._LATEST_SEARCH is None


def test_book_flight_clears_the_latest_search_slot(monkeypatch, bq):
    _mock_repos(monkeypatch)
    _search()
    assert concierge._LATEST_SEARCH is not None

    asyncio.run(concierge.book_flight_impl("room-1", 1))

    assert concierge._LATEST_SEARCH is None
    booked = concierge.latest_booking()
    assert booked is not None
    assert booked["status"] == "booked"
    assert booked["trip_id"]
    assert "depart_time" in booked and "arrive_time" in booked


def test_book_flight_leaves_another_sessions_slot_alone(monkeypatch, bq):
    """room-2 searched after room-1 — room-1's booking must not clear the
    candidates room-2's conversation is still discussing."""
    _mock_repos(monkeypatch)
    _search("room-1")
    _search("room-2")

    asyncio.run(concierge.book_flight_impl("room-1", 1))

    assert concierge._LATEST_SEARCH is not None
    assert concierge._LATEST_SEARCH.session_id == "room-2"


# --- item H (Phase 22): the pending-options slot expires by age ----------------


def _slot_option(n=1):
    return concierge.FlightOption(
        option_number=n, airline="AA", flight_number=100 + n, origin="MSP",
        destination="SFO", depart_date="2026-07-17", depart_time="08:00",
        arrive_time="10:05", stops=0, price=250.0, currency="USD",
        spoken=f"Option {n}.",
    )


def _slot(age=timedelta(0), session="s-1"):
    return concierge.LatestSearch(
        session_id=session,
        options=[_slot_option(1), _slot_option(2)],
        recorded_at=datetime.now(timezone.utc) - age,
    )


def _pinned(trip_id):
    return concierge.TripContext(
        trip=concierge.Trip(**dict(trip_row(), trip_id=trip_id)),
        items=[], summary="pinned",
    )


def test_pending_options_fresh_slot_surfaces_unpinned():
    """The pre-booking window is untouched by the TTL: a fresh unpinned
    slot still surfaces on whatever trip the page polls."""
    concierge._LATEST_SEARCH = _slot()

    block = concierge.pending_options_for_trip("any-trip")

    assert block is not None
    assert [o["option_number"] for o in block["options"]] == [1, 2]


def test_pending_options_fresh_slot_surfaces_pinned_to_the_trip():
    concierge._LATEST_SEARCH = _slot()
    concierge._SESSION_TRIPS["s-1"] = _pinned("t-1")

    assert concierge.pending_options_for_trip("t-1") is not None


def test_pending_options_fresh_slot_still_hidden_from_other_trips():
    """The TTL check must not loosen the pinned-session resolution: a fresh
    slot pinned elsewhere stays off this trip's poll."""
    concierge._LATEST_SEARCH = _slot()
    concierge._SESSION_TRIPS["s-1"] = _pinned("t-other")

    assert concierge.pending_options_for_trip("t-1") is None


def test_pending_options_expired_slot_returns_none():
    """Item H: an abandoned search (older than the TTL) stops surfacing on
    the poll — the age-expiry hardening from the Phase 21 validation."""
    concierge._LATEST_SEARCH = _slot(
        age=concierge._LATEST_SEARCH_TTL + timedelta(seconds=1)
    )

    assert concierge.pending_options_for_trip("any-trip") is None


def test_pending_options_expired_slot_hidden_even_when_pinned():
    concierge._LATEST_SEARCH = _slot(
        age=concierge._LATEST_SEARCH_TTL + timedelta(seconds=1)
    )
    concierge._SESSION_TRIPS["s-1"] = _pinned("t-1")

    assert concierge.pending_options_for_trip("t-1") is None


def test_pending_options_slot_just_inside_the_ttl_still_surfaces():
    concierge._LATEST_SEARCH = _slot(
        age=concierge._LATEST_SEARCH_TTL - timedelta(seconds=5)
    )

    assert concierge.pending_options_for_trip("any-trip") is not None


def test_current_pending_options_surfaces_without_a_trip_id():
    """The cascade awaiting view has no trip yet — times still have to show."""
    concierge._LATEST_SEARCH = _slot()
    concierge._SESSION_TRIPS["s-1"] = _pinned("t-other")

    block = concierge.current_pending_options()
    assert block is not None
    assert [o["depart_time"] for o in block["options"]]
    # Pin matching still hides this from the other trip's status poll.
    assert concierge.pending_options_for_trip("t-1") is None


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

    msg = asyncio.run(concierge.book_flight_impl("room-1", 9))

    assert "options" in msg
    assert seen["writes"] == []
    # The options survive so the traveler can just say a valid number next.
    assert "room-1" in concierge._SESSION_FLIGHT_OPTIONS


def test_book_flight_accepts_a_string_option_number(monkeypatch, bq):
    _mock_repos(monkeypatch)
    _search()
    msg = asyncio.run(concierge.book_flight_impl("room-1", "1"))
    assert "Done" in msg


def test_book_flight_uses_latest_search_when_session_has_no_options(
    monkeypatch, bq
):
    _mock_repos(monkeypatch)
    _search("room-search")
    concierge._SESSION_FLIGHT_OPTIONS.pop("room-voice", None)
    msg = asyncio.run(concierge.book_flight_impl("room-voice", 1))
    assert "Done" in msg


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
    # Phase 31: the flight's identity rides on the item so the repair
    # re-shop can exclude the cancelled flight (live QA: without this the
    # traveler was "repaired" onto their original flight). Phase 33: the
    # stamp is the shared rich-field dict — identity keys unchanged.
    chosen = booking.raw_response["option"]
    assert item.details == concierge.details_from_option(
        concierge.FlightOption(**chosen)
    )
    assert item.details["airline"] == chosen["airline"]
    assert item.details["flight_number"] == chosen["flight_number"]
    # Blocking writes ran off the event loop's thread (the to_thread rule).
    assert seen["threads"][0] is not threading.main_thread()
    # Pin replaced with the new trip; the spent options are gone.
    assert concierge._SESSION_TRIPS["room-1"].trip.trip_id == trip.trip_id
    assert "room-1" not in concierge._SESSION_FLIGHT_OPTIONS
    # Spoken copy: confirmation with the spoken date, no ids or markdown.
    assert "booked" in msg and "July 17th" in msg
    assert trip.trip_id not in msg and "*" not in msg


def test_booking_writes_declare_pacific_wall_clock(monkeypatch, bq):
    """Phase 19 timezone discipline: the mock's 06:15 wall clock is Pacific,
    so the stored instant is 13:15Z for a July date (PDT = UTC−7) — not the
    old wall-clock-as-UTC that displayed 1:15 AM to Josh."""
    seen = _mock_repos(monkeypatch)
    option = concierge.FlightOption(
        option_number=1, airline="AA", flight_number=100, origin="MSP",
        destination="DFW", depart_date="2026-07-13", depart_time="06:15",
        arrive_time="09:52", stops=0, price=250.0, currency="USD",
        spoken="Option one.",
    )

    concierge._booking_writes(option, [option])

    item = next(w[1] for w in seen["writes"] if w[0] == "item")
    assert item.start_ts.astimezone(timezone.utc) == datetime(
        2026, 7, 13, 13, 15, tzinfo=timezone.utc
    )
    assert item.end_ts.astimezone(timezone.utc) == datetime(
        2026, 7, 13, 16, 52, tzinfo=timezone.utc
    )


def test_completion_items_declare_pacific_wall_clock():
    """Same discipline for the build-out items: the 7 PM dinner is 02:00Z
    the next day (PDT = UTC−7)."""
    trip = concierge.Trip(**dict(trip_row(), trip_id="t-1"))
    assert trip.start_date == date(2026, 7, 17)

    items = concierge._completion_items(trip)

    dinner = next(i for i in items if i.type == "dining")
    assert dinner.start_ts.astimezone(timezone.utc) == datetime(
        2026, 7, 18, 2, 0, tzinfo=timezone.utc
    )
    hotel = next(i for i in items if i.type == "hotel")
    assert hotel.start_ts.astimezone(timezone.utc) == datetime(
        2026, 7, 18, 5, 0, tzinfo=timezone.utc
    )


def test_book_flight_write_failure_is_speakable(monkeypatch, bq):
    _mock_repos(monkeypatch)
    _search()
    monkeypatch.setattr(
        concierge.trips, "create_trip",
        lambda trip: (False, None, "bq down"),
    )

    msg = asyncio.run(concierge.book_flight_impl("room-1", 1))

    assert "couldn't get that flight booked" in msg


def test_book_flight_updates_existing_itinerary_instead_of_new_trip(monkeypatch, bq):
    from api import memory_trips

    memory_trips.clear()
    seeded = memory_trips.seed("whatsapp-demo", "PDF trip")
    view = memory_trips.get(seeded["trip_id"])
    concierge._SESSION_TRIPS["room-1"] = concierge.TripContext(
        trip=view.trip, items=list(view.items), summary="pdf",
    )
    _search()
    option = concierge._SESSION_FLIGHT_OPTIONS["room-1"][0]

    msg = asyncio.run(concierge.book_flight_impl("room-1", 1))

    assert "updated your itinerary" in msg
    assert concierge._SESSION_TRIPS["room-1"].trip.trip_id == seeded["trip_id"]
    refreshed = memory_trips.get(seeded["trip_id"])
    flight = next(i for i in refreshed.items if i.type == "flight")
    assert flight.details["flight_number"] == option.flight_number
    assert flight.location == f"{option.origin}-{option.destination}"
    assert len([i for i in refreshed.items if i.type == "hotel"]) == 1
    memory_trips.clear()


def test_recovery_route_uses_flight_location():
    trip = concierge.Trip(
        user_id="u", title="t", origin="MSP", destinations=["SFO"],
        start_date=date(2026, 8, 20), end_date=date(2026, 8, 22),
    )
    items = [concierge.ItineraryItem(
        trip_id="x", type="flight", status="booked", location="MSP-SFO",
        start_ts=datetime(2026, 8, 20, 8, 0, tzinfo=timezone.utc),
    )]
    origin, dest, depart = concierge._recovery_route(trip, items)
    assert (origin, dest, depart) == ("MSP", "SFO", "2026-08-20")


def test_recovery_route_airport_departure_goes_home():
    trip = concierge.Trip(
        user_id="u", title="SF weekend", origin="MSP", destinations=["SFO"],
        start_date=date(2026, 8, 22), end_date=date(2026, 8, 23),
    )
    items = [
        concierge.ItineraryItem(
            trip_id="x", type="dining", status="booked",
            location="Union Square",
            start_ts=datetime(2026, 8, 22, 8, 0, tzinfo=timezone.utc),
        ),
        concierge.ItineraryItem(
            trip_id="x", type="ground", status="booked",
            location="Airport departure — SFO",
            details={"title": "Airport departure — SFO"},
            start_ts=datetime(2026, 8, 23, 20, 0, tzinfo=timezone.utc),
        ),
    ]
    origin, dest, depart = concierge._recovery_route(trip, items)
    assert origin == "SFO"
    assert dest == "MSP"
    assert depart == "2026-08-23"


def test_offer_rebook_no_trip_is_speakable(bq):
    msg = asyncio.run(concierge.offer_rebook_impl("room-1"))
    assert "don't see a booked trip" in msg
    assert concierge._LATEST_SEARCH is None


def test_offer_rebook_marks_leg_broken_and_stores_options(monkeypatch, bq):
    from api import memory_trips

    memory_trips.clear()
    seeded = memory_trips.seed("whatsapp-demo", "PDF trip")
    view = memory_trips.get(seeded["trip_id"])
    concierge._SESSION_TRIPS["room-1"] = concierge.TripContext(
        trip=view.trip, items=list(view.items), summary="pdf",
    )

    msg = asyncio.run(concierge.offer_rebook_impl("room-1"))

    assert "Option one" in msg
    slot = concierge._LATEST_SEARCH
    assert slot is not None
    assert slot.origin == "MSP"
    assert slot.destination == "SFO"
    flight = next(i for i in view.items if i.type == "flight")
    assert flight.status == "broken"
    memory_trips.clear()


def test_offer_rebook_airport_departure_searches_home(monkeypatch, bq):
    from api import memory_trips
    from api.repositories.models import ItineraryItem, Trip

    memory_trips.clear()
    trip = Trip(
        user_id="whatsapp-demo", title="SF weekend", status="booked",
        origin="MSP", destinations=["SFO"],
        start_date=date(2026, 8, 22), end_date=date(2026, 8, 23),
    )
    items = [
        ItineraryItem(
            trip_id=trip.trip_id, type="dining", status="booked",
            location="Union Square",
            details={"title": "Breakfast — Union Square"},
            start_ts=datetime(2026, 8, 22, 8, 0, tzinfo=timezone.utc),
        ),
        ItineraryItem(
            trip_id=trip.trip_id, type="ground", status="booked",
            location="Airport departure — SFO",
            details={"title": "Airport departure — SFO"},
            start_ts=datetime(2026, 8, 23, 20, 0, tzinfo=timezone.utc),
        ),
    ]
    memory_trips.put(trip, items)
    concierge._SESSION_TRIPS["room-1"] = concierge.TripContext(
        trip=trip, items=list(items), summary="pdf",
    )

    msg = asyncio.run(concierge.offer_rebook_impl("room-1"))

    assert "Option one" in msg
    slot = concierge._LATEST_SEARCH
    assert slot.origin == "SFO"
    assert slot.destination == "MSP"
    assert items[1].status == "broken"
    memory_trips.clear()


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


def test_fresh_session_booking_reaches_search_flights(monkeypatch, bq):
    """The Phase 18 regression guard: a fresh session with a NON-EMPTY trips
    table (the bq fixture serves a latest trip) stays unpinned, its agent is
    built with _NO_TRIP_LINE — not the authoritative TRIP CONTEXT block that
    forbade booking — and a booking-intent turn's search_flights call goes
    through search_flights_impl to the mock Sabre client and comes back as a
    speakable options string. Fails on the old latest-trip auto-pin."""
    seen = {}

    class _BookingIntentRunner:
        """Acts like a model with booking intent: invokes the agent's real
        search_flights FunctionTool, exactly as the SDK would."""

        @classmethod
        async def run(cls, agent, input, max_turns=None):
            seen["agent"] = agent
            tool = next(t for t in agent.tools if t.name == "search_flights")
            args = (
                '{"origin": "MSP", "destination": "DFW", '
                '"depart_date": "2026-07-13"}'
            )
            ctx = ToolContext(
                context=None, tool_name=tool.name, tool_call_id="call-1",
                tool_arguments=args,
            )
            seen["tool_result"] = await tool.on_invoke_tool(ctx, args)
            return _FakeResult(input, "Here are your options.")

    monkeypatch.setattr(concierge, "Runner", _BookingIntentRunner)

    reply = asyncio.run(concierge.answer_query(
        "fresh-session",
        "book me a flight from Minneapolis to Dallas on 2026-07-13",
    ))

    assert reply == "Here are your options."
    # The non-empty trips table never shadowed the session: no pin, no
    # latest-trip read, and the agent was told there is no trip.
    assert "fresh-session" not in concierge._SESSION_TRIPS
    assert _trip_selects(bq.select) == []
    instructions = seen["agent"].instructions
    assert concierge._NO_TRIP_LINE in instructions
    assert "TRIP CONTEXT" not in instructions
    # The search reached the mock Sabre client: options stored per session,
    # readback speakable.
    options = concierge._SESSION_FLIGHT_OPTIONS["fresh-session"]
    assert 2 <= len(options) <= 6
    assert all(o.origin == "MSP" and o.destination == "DFW" for o in options)
    assert "Option one" in seen["tool_result"]
    assert "dollars" in seen["tool_result"]


def test_instructions_carry_the_guided_script():
    for phrase in ("search_flights", "book_flight", "complete_trip",
                   "destination", "pick by number",
                   "set_recovery_preferences", "offer_rebook",
                   "trip to airport cancelled",
                   "analyze_itinerary", "apply_optimization",
                   "even if the live status",
                   "reschedule_hotel", "hotel reservation"):
        assert phrase in concierge.BASE_INSTRUCTIONS
    assert "same turn" in concierge.BASE_INSTRUCTIONS
    assert "do not confirm first" in concierge.BASE_INSTRUCTIONS
    # The retired magic utterance is gone from the script...
    assert "book_trip " not in concierge.BASE_INSTRUCTIONS
    # A healthy booked trip still prefers status; disruption is the
    # exception that may search again (ML recovery ranking).
    assert "When a trip is booked and healthy" in concierge.BASE_INSTRUCTIONS
    assert "second trip" in concierge.BASE_INSTRUCTIONS
    assert "delay-risk model" in concierge.BASE_INSTRUCTIONS
    assert "fix_trip" in concierge.BASE_INSTRUCTIONS
    assert "do not call fix_trip" in concierge.BASE_INSTRUCTIONS


# --- today's date in the instructions (Phase 18) -----------------------------


class _FrozenDatetime(datetime):
    """Clock frozen at 2026-07-13 02:30 UTC — 19:30 on Sunday 2026-07-12 in
    Pacific time, so the Pacific date differs from the UTC date and a wrong
    (or missing) timezone conversion fails the assertion."""

    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 7, 13, 2, 30, tzinfo=timezone.utc).astimezone(tz)


def test_today_line_renders_pacific_date(monkeypatch):
    monkeypatch.setattr(concierge, "datetime", _FrozenDatetime)

    line = concierge._today_line()

    assert line.startswith("Today is Sunday, 2026-07-12 (US Pacific time).")
    assert "always into the future" in line


def test_agent_instructions_carry_today_line(monkeypatch):
    monkeypatch.setattr(concierge, "datetime", _FrozenDatetime)

    agent = concierge.build_agent("room-1")

    assert "Today is Sunday, 2026-07-12 (US Pacific time)." in agent.instructions


# --- the acceptance shape (Phase 5's test over the seam) -------------------------


def test_talk_while_repairing_acceptance_shape(monkeypatch, bq):
    """fix_trip launches the REAL cascade (real launch seam, real repair
    tools against the Sabre mock with latency); a follow-up turn is answered
    while the repairs are still in flight; every completion event lands ok."""
    monkeypatch.setattr(sabre_client._mock, "latency_seconds", 0.5)
    _mock_runner(monkeypatch, reply="Repairs are humming along.")

    async def scenario():
        # The disrupt flow pins the broken trip explicitly (the Phase 12
        # seam) — the only way a session gets a trip besides booking one.
        await concierge.ensure_trip_context("vb-room-1", trip_id="t-1")
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
