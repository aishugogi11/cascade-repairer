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
    core._SESSIONS.clear()
    yield
    core._SESSIONS.clear()


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
        return True, [{"trip_id": "t-1"}], None

    dml = MagicMock(return_value=(True, 1, None))
    select = MagicMock(side_effect=route_select)
    monkeypatch.setattr(bq_helper, "run_dml", dml)
    monkeypatch.setattr(bq_helper, "run_select", select)
    return SimpleNamespace(dml=dml, select=select)


# --- answer_query (module-level seam) -----------------------------------------


def test_answer_query_replays_and_stores_history(monkeypatch):
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


def test_agent_instructions_carry_authoritative_snapshot(monkeypatch):
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


def test_agent_uses_fast_model_and_fix_trip_tool(monkeypatch):
    monkeypatch.delenv("CONCIERGE_LLM_MODEL", raising=False)
    agent = concierge.build_agent("room-1")
    assert agent.model == "gpt-4.1-mini"
    assert [t.name for t in agent.tools] == ["fix_trip"]


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
