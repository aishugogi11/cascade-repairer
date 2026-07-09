"""Phase 5 concurrency spike — hermetic proofs.

No OPENAI_API_KEY, no GCP, no network: BigQuery is mocked at the bq_helper
boundary (per test_repositories.py) and the LLM turn is a stub coroutine.
Durations are shortened to keep the suite fast; the assertions are about
ordering and overlap, which are duration-independent.

The repo pins no pytest-asyncio, so async scenarios run via asyncio.run()
inside sync tests.
"""
import asyncio
import time
from itertools import combinations
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api import concurrency_agent
from api import concurrency_core as core
from api.concurrency_core import RepairSpec
from api.helpers.bigquery_helper import bq_helper
from main import app


@pytest.fixture
def bq(monkeypatch):
    """Mock the helper's DML primitive on the shared singleton."""
    dml = MagicMock(return_value=(True, 1, None))
    monkeypatch.setattr(bq_helper, "run_dml", dml)
    return dml


@pytest.fixture(autouse=True)
def fresh_sessions():
    core._SESSIONS.clear()
    yield
    core._SESSIONS.clear()


def dml_status_writes(dml):
    """(item_id, status) tuples in DML call order, from the mocked run_dml."""
    writes = []
    for call in dml.call_args_list:
        params = {p.name: p.value for p in call.args[1]}
        writes.append((params["item_id"], params["status"]))
    return writes


def make_specs(durations):
    return [
        RepairSpec(item_id=f"item-{n}", name=f"repair-{n}", duration_seconds=d)
        for n, d in enumerate(durations)
    ]


# --- Proof A: the session answers while background work is in flight ---------

def test_followup_answered_while_background_call_still_running():
    async def scenario():
        task = core.start_background_call(
            "s-a", "slow_api_call", concurrency_agent._slow_api_call(0.5)
        )
        t0 = time.monotonic()

        async def stub_followup_turn():  # the LLM stand-in
            await asyncio.sleep(0.01)
            return "here is your answer"

        answer = await stub_followup_turn()
        latency = time.monotonic() - t0

        assert answer == "here is your answer"
        assert not task.done(), "background call must still be in flight"
        assert latency < 0.25, "follow-up latency must be well under the call duration"

        await task
        events = core.get_session("s-a").events
        assert [e.name for e in events] == ["slow_api_call"]
        assert events[0].status == "ok"

    asyncio.run(scenario())


# --- Proof B: N>=3 repairs run concurrently, reporting as each lands ---------

def test_repairs_overlap_and_complete_in_duration_order(bq):
    async def scenario():
        # Launch order 0,1,2 — durations force completion order 2,1,0.
        specs = make_specs([0.30, 0.20, 0.10])
        t0 = time.monotonic()
        tasks = core.run_repairs("s-b", specs, concurrency_agent.fake_repair)
        await asyncio.gather(*tasks)
        return time.monotonic() - t0

    wall = asyncio.run(scenario())
    events = core.get_session("s-b").events
    assert len(events) == 3 and all(e.status == "ok" for e in events)

    # Concurrent, not sequential: wall time ~ max duration (0.3s), not sum (0.6s).
    assert wall < 0.55, f"wall time {wall:.2f}s looks sequential"

    # Every pair of repair intervals overlaps.
    for a, b in combinations(events, 2):
        assert a.started_monotonic < b.finished_monotonic
        assert b.started_monotonic < a.finished_monotonic

    # Completions land as each finishes: duration order, not launch order.
    assert [e.name for e in events] == ["repair-2", "repair-1", "repair-0"]


def test_each_repair_writes_repairing_then_fixed(bq):
    async def scenario():
        tasks = core.run_repairs(
            "s-c", make_specs([0.15, 0.10, 0.05]), concurrency_agent.fake_repair
        )
        await asyncio.gather(*tasks)

    asyncio.run(scenario())
    writes = dml_status_writes(bq)

    for item_id in ("item-0", "item-1", "item-2"):
        assert [s for i, s in writes if i == item_id] == ["repairing", "fixed"]

    # `fixed` writes land as each task finishes — duration order, not launch order.
    fixed_order = [i for i, s in writes if s == "fixed"]
    assert fixed_order == ["item-2", "item-1", "item-0"]


# --- Phase 6 (gap 1): failed status writes surface as error events -------------

def test_failed_status_write_produces_error_event(bq):
    bq.return_value = (False, 0, "quota exceeded")

    async def scenario():
        tasks = core.run_repairs("s-w1", make_specs([0.01]), concurrency_agent.fake_repair)
        await asyncio.gather(*tasks)

    asyncio.run(scenario())
    events = core.get_session("s-w1").events
    assert len(events) == 1
    assert events[0].status == "error"
    assert "item-0" in events[0].error and "quota exceeded" in events[0].error


def test_zero_row_status_write_produces_error_event(bq):
    bq.return_value = (True, 0, None)  # DML ran but matched no such item

    async def scenario():
        tasks = core.run_repairs("s-w2", make_specs([0.01]), concurrency_agent.fake_repair)
        await asyncio.gather(*tasks)

    asyncio.run(scenario())
    events = core.get_session("s-w2").events
    assert len(events) == 1
    assert events[0].status == "error"
    assert "item-0" in events[0].error and "matched no rows" in events[0].error


def test_failed_fixed_write_surfaces_after_successful_repairing_write(bq):
    # First flip (repairing) lands; the final flip (fixed) matches no rows.
    bq.side_effect = [(True, 1, None), (True, 0, None)]

    async def scenario():
        tasks = core.run_repairs("s-w3", make_specs([0.01]), concurrency_agent.fake_repair)
        await asyncio.gather(*tasks)

    asyncio.run(scenario())
    events = core.get_session("s-w3").events
    assert events[0].status == "error"
    assert "fixed" in events[0].error


def test_happy_path_status_writes_still_report_ok(bq):
    async def scenario():
        tasks = core.run_repairs("s-w4", make_specs([0.01]), concurrency_agent.fake_repair)
        await asyncio.gather(*tasks)

    asyncio.run(scenario())
    events = core.get_session("s-w4").events
    assert [e.status for e in events] == ["ok"]


# --- Edge cases ---------------------------------------------------------------

def test_failing_repair_does_not_kill_siblings_or_flip_fixed(bq):
    specs = make_specs([0.05, 0.10, 0.15])

    async def do_repair(spec):
        if spec.item_id == "item-0":
            return await concurrency_agent.failing_repair(spec)
        return await concurrency_agent.fake_repair(spec)

    async def scenario():
        tasks = core.run_repairs("s-d", specs, do_repair)
        await asyncio.gather(*tasks)  # must not raise — errors stay in the log

    asyncio.run(scenario())
    events = {e.name: e for e in core.get_session("s-d").events}
    assert len(events) == 3
    assert events["repair-0"].status == "error"
    assert "RuntimeError" in events["repair-0"].error
    assert events["repair-1"].status == "ok" and events["repair-2"].status == "ok"

    writes = dml_status_writes(bq)
    assert [s for i, s in writes if i == "item-0"] == ["repairing"]  # never fixed
    assert [s for i, s in writes if i == "item-1"] == ["repairing", "fixed"]
    assert [s for i, s in writes if i == "item-2"] == ["repairing", "fixed"]


def test_concurrent_sessions_do_not_cross_contaminate(bq):
    async def scenario():
        t1 = core.run_repairs("s-one", make_specs([0.05, 0.06, 0.07]), concurrency_agent.fake_repair)
        t2 = core.run_repairs("s-two", make_specs([0.05, 0.06, 0.07]), concurrency_agent.fake_repair)
        await asyncio.gather(*t1, *t2)

    asyncio.run(scenario())
    assert len(core.get_session("s-one").events) == 3
    assert len(core.get_session("s-two").events) == 3


# --- Agent wiring (no API key needed to construct) ----------------------------

def test_build_agent_has_background_launching_tool():
    agent = concurrency_agent.build_agent("s-agent")
    assert agent.model == "gpt-4.1-mini"
    assert len(agent.tools) == 1


def test_agent_instructions_carry_session_snapshot(bq):
    async def scenario():
        tasks = core.run_repairs(
            "s-snap", make_specs([0.01, 0.02, 5.0]), concurrency_agent.fake_repair
        )
        await asyncio.gather(*tasks[:2])  # two land, one still in flight
        return concurrency_agent.build_agent("s-snap").instructions

    instructions = asyncio.run(scenario())
    assert "in progress: repair-2" in instructions
    assert "repair-0: done" in instructions and "repair-1: done" in instructions


def test_session_snapshot_empty_and_failed_states(bq):
    assert "No background work" in concurrency_agent.session_snapshot("s-nothing")

    async def scenario():
        tasks = core.run_repairs(
            "s-snap-fail", make_specs([0.01]), concurrency_agent.failing_repair
        )
        await asyncio.gather(*tasks)

    asyncio.run(scenario())
    assert "repair-0: FAILED" in concurrency_agent.session_snapshot("s-snap-fail")


def test_default_cascade_covers_all_five_categories():
    from api.concurrency_spike import _DEFAULT_ITEMS

    assert len(_DEFAULT_ITEMS) >= 3
    assert {s.name for s in _DEFAULT_ITEMS} == set(
        concurrency_agent.REPAIR_TOOL_NAMES.values()
    )


# --- Endpoints via TestClient (LLM stubbed, bq mocked) -------------------------

def test_talk_endpoint_answers_before_tool_finishes(monkeypatch, bq):
    async def stub_turn(session_id, question):
        await asyncio.sleep(0.02)
        return f"stub answer to: {question}"

    monkeypatch.setattr(concurrency_agent, "run_followup_turn", stub_turn)
    monkeypatch.setattr(concurrency_agent, "openai_key_present", lambda: True)

    with TestClient(app) as client:
        resp = client.post(
            "/v1/concurrency_spike/talk_while_tool_runs",
            json={"slow_seconds": 1.0, "question": "what should I pack?"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["answered_before_tool_finished"] is True
    assert body["slow_call"]["state"] == "running"
    assert body["followup_latency_seconds"] < 1.0
    assert "stub answer" in body["followup_answer"]


def test_talk_endpoint_without_key_is_structured_503(monkeypatch):
    monkeypatch.setattr(concurrency_agent, "openai_key_present", lambda: False)
    with TestClient(app) as client:
        resp = client.post("/v1/concurrency_spike/talk_while_tool_runs", json={})
    assert resp.status_code == 503
    assert "OPENAI_API_KEY" in resp.json()["detail"]


def test_cascade_endpoint_wait_returns_full_event_log(bq):
    items = [
        {"item_id": f"item-{n}", "name": f"repair-{n}", "duration_seconds": d}
        for n, d in enumerate([0.15, 0.10, 0.05])
    ]
    with TestClient(app) as client:
        resp = client.post(
            "/v1/concurrency_spike/cascade", json={"items": items, "wait": True}
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["pending_tasks"] == []
    assert [e["name"] for e in body["completed_events"]] == [
        "repair-2", "repair-1", "repair-0",
    ]
    assert all(e["status"] == "ok" for e in body["completed_events"])


def test_cascade_endpoint_returns_immediately_without_wait(bq):
    items = [
        {"item_id": f"item-{n}", "name": f"repair-{n}", "duration_seconds": 0.5}
        for n in range(3)
    ]
    with TestClient(app) as client:
        t0 = time.monotonic()
        resp = client.post("/v1/concurrency_spike/cascade", json={"items": items})
        elapsed = time.monotonic() - t0
    assert resp.status_code == 200
    assert elapsed < 0.4, "launch must not block on the repairs"
    assert len(resp.json()["pending_tasks"]) == 3


def test_cascade_endpoint_rejects_fewer_than_three_items(bq):
    with TestClient(app) as client:
        resp = client.post(
            "/v1/concurrency_spike/cascade",
            json={"items": [{"item_id": "i", "name": "r", "duration_seconds": 0.1}]},
        )
    assert resp.status_code == 422
