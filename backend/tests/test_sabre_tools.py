"""Walkthrough-surface tests (seed + repair endpoints) — hermetic, BigQuery
mocked at the bq_helper boundary per test_repositories.py conventions."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import concurrency_core as core
from api.helpers.bigquery_helper import bq_helper
from api.sabre import client as sabre_client
from api.sabre_tools import _SEED_ITEMS, sabre_tools

app = FastAPI()
app.include_router(sabre_tools, prefix="/v1/sabre_tools")


@pytest.fixture
def bq(monkeypatch):
    """Mock the helper's query primitives on the shared singleton."""
    dml = MagicMock(return_value=(True, 1, None))
    select = MagicMock(return_value=(True, [], None))
    monkeypatch.setattr(bq_helper, "run_dml", dml)
    monkeypatch.setattr(bq_helper, "run_select", select)
    return SimpleNamespace(dml=dml, select=select)


@pytest.fixture(autouse=True)
def fast_sabre_and_fresh_sessions(monkeypatch):
    monkeypatch.delenv("SABRE_MODE", raising=False)
    monkeypatch.setattr(sabre_client._mock, "latency_seconds", 0)
    core._SESSIONS.clear()
    yield
    core._SESSIONS.clear()


# --- seed_trip ----------------------------------------------------------------

def test_seed_trip_creates_booked_trip_all_five_items_and_two_bookings(bq):
    with TestClient(app) as client:
        resp = client.post("/v1/sabre_tools/seed_trip", json={})

    assert resp.status_code == 200
    body = resp.json()
    assert {i["type"] for i in body["items"]} == {
        "flight", "hotel", "ground", "dining", "experience",
    }
    assert all(i["status"] == "booked" for i in body["items"])
    assert len(body["bookings"]) == 2  # initial flight + hotel bookings

    # 1 trip insert + 5 item inserts + 2 booking inserts, all through run_dml.
    assert bq.dml.call_count == 8
    queries = [c.args[0] for c in bq.dml.call_args_list]
    assert all("INSERT INTO" in q for q in queries)


def test_seed_items_declare_pacific_wall_clock():
    """Phase 19 timezone discipline: seed wall clocks are Pacific, so the
    stored UTC instant is shifted, not equal — the 8:00 AM July 17 flight
    is 15:00Z (PDT = UTC−7)."""
    flight = next(s for s in _SEED_ITEMS if s["type"] == "flight")
    assert flight["start"].astimezone(timezone.utc) == datetime(
        2026, 7, 17, 15, 0, tzinfo=timezone.utc
    )
    assert flight["end"].astimezone(timezone.utc) == datetime(
        2026, 7, 17, 19, 5, tzinfo=timezone.utc
    )
    # Every seed timestamp carries the Pacific declaration (July = PDT).
    for seed in _SEED_ITEMS:
        for key in ("start", "end"):
            assert seed[key].utcoffset() == timedelta(hours=-7)


def test_seed_trip_failed_item_insert_aborts_with_500(bq):
    # Trip insert succeeds, first item insert fails.
    bq.dml.side_effect = [(True, 1, None), (False, 0, "quota exceeded")]
    with TestClient(app) as client:
        resp = client.post("/v1/sabre_tools/seed_trip", json={})
    assert resp.status_code == 500
    assert "quota exceeded" in resp.json()["detail"]


# --- repair_trip ----------------------------------------------------------------

def five_item_rows():
    return [
        {
            "item_id": f"i-{t}", "trip_id": "t-1", "type": t, "status": "broken"
            if t == "flight" else "booked",
            "location": "MSP-SFO" if t == "flight" else "Mountain View",
        }
        for t in ("flight", "hotel", "ground", "dining", "experience")
    ]


def test_repair_trip_runs_one_repair_per_item_all_ok(bq):
    bq.select.return_value = (True, five_item_rows(), None)
    with TestClient(app) as client:
        resp = client.post(
            "/v1/sabre_tools/repair_trip", json={"trip_id": "t-1", "wait": True}
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["pending_tasks"] == []
    assert sorted(body["launched"]) == sorted([
        "rebook_flight", "shift_hotel_dates", "reschedule_ground",
        "move_dining", "rebook_experience",
    ])
    events = body["completed_events"]
    assert len(events) == 5
    assert all(e["status"] == "ok" for e in events)
    # Every tool's payload is readable by the agent (confirmation ref present).
    assert all(e["result"]["confirmation_ref"] for e in events)

    # Single writer (Phase 9): each item's status DML is exactly the cascade
    # unit's `repairing` -> `fixed` walk — no extra stamp from the tools.
    status_writes = {}
    for call in bq.dml.call_args_list:
        params = {p.name: p.value for p in call.args[1]}
        if "status" in params:
            status_writes.setdefault(params["item_id"], []).append(params["status"])
    assert len(status_writes) == 5
    for item_id, statuses in status_writes.items():
        assert statuses == ["repairing", "fixed"], item_id


def test_repair_trip_404_when_trip_has_no_items(bq):
    with TestClient(app) as client:
        resp = client.post("/v1/sabre_tools/repair_trip", json={"trip_id": "nope"})
    assert resp.status_code == 404


def test_repair_trip_failed_write_surfaces_as_error_event(bq):
    bq.select.return_value = (True, five_item_rows(), None)
    bq.dml.return_value = (True, 0, None)  # every status write matches no rows
    with TestClient(app) as client:
        resp = client.post(
            "/v1/sabre_tools/repair_trip", json={"trip_id": "t-1", "wait": True}
        )
    assert resp.status_code == 200
    events = resp.json()["completed_events"]
    assert len(events) == 5
    assert all(e["status"] == "error" for e in events)
    assert all("matched no rows" in e["error"] for e in events)


# --- latest_trip_id -------------------------------------------------------------

def test_latest_trip_id_returns_most_recent_by_created_at(bq):
    from datetime import datetime, timezone

    bq.select.return_value = (
        True,
        [{"trip_id": "t-9", "created_at": datetime(2026, 7, 8, 18, 8, tzinfo=timezone.utc)}],
        None,
    )
    with TestClient(app) as client:
        resp = client.get("/v1/sabre_tools/latest_trip_id")

    assert resp.status_code == 200
    body = resp.json()
    assert body["trip_id"] == "t-9"
    assert body["created_at"].startswith("2026-07-08T18:08")

    query = bq.select.call_args.args[0]
    assert "ORDER BY created_at DESC" in query
    assert "updated_at" not in query  # trips has no updated_at column


def test_latest_trip_id_404_when_no_trips(bq):
    with TestClient(app) as client:
        resp = client.get("/v1/sabre_tools/latest_trip_id")
    assert resp.status_code == 404


def test_latest_trip_id_failed_select_is_500(bq):
    bq.select.return_value = (False, [], "connection refused")
    with TestClient(app) as client:
        resp = client.get("/v1/sabre_tools/latest_trip_id")
    assert resp.status_code == 500
    assert "connection refused" in resp.json()["detail"]


# --- main.py wiring -------------------------------------------------------------

def test_routers_are_mounted_on_the_main_app(bq):
    """A mounted route rejects an invalid body with 422; an unmounted path
    would 404. (This FastAPI version defers included routers, so route
    objects can't be enumerated directly.)"""
    from main import app as main_app

    with TestClient(main_app) as client:
        for path in (
            "/v1/sabre_tools/repair_trip",
            "/v1/disruption/break_flight",
        ):
            assert client.post(path, json={}).status_code == 422, path
        # seed_trip's fields all default, so an empty body seeds a trip
        # (bq mocked); an unmounted path would 404 before reaching it.
        assert client.post("/v1/sabre_tools/seed_trip", json={}).status_code == 200


def test_landing_page_links_phase_6_endpoints():
    from main import app as main_app

    with TestClient(main_app) as client:
        html = client.get("/v1/hello/").text
    assert "/v1/sabre_tools/seed_trip" in html
    assert "/v1/disruption/break_flight" in html
    assert "/v1/sabre_tools/repair_trip" in html
