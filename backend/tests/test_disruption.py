"""Disruption injector tests — hermetic, BigQuery mocked at the bq_helper
boundary per test_repositories.py conventions.

The router is mounted on a local app here; main.py wiring has its own smoke
test.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.disruption import disruption
from api.helpers.bigquery_helper import bq_helper

app = FastAPI()
app.include_router(disruption, prefix="/v1/disruption")


@pytest.fixture
def bq(monkeypatch):
    """Mock the helper's query primitives on the shared singleton."""
    dml = MagicMock(return_value=(True, 1, None))
    select = MagicMock(return_value=(True, [], None))
    monkeypatch.setattr(bq_helper, "run_dml", dml)
    monkeypatch.setattr(bq_helper, "run_select", select)
    return SimpleNamespace(dml=dml, select=select)


def trip_rows(*types_and_statuses):
    return [
        {"item_id": f"i-{n}", "trip_id": "t-1", "type": t, "status": s}
        for n, (t, s) in enumerate(types_and_statuses)
    ]


def test_break_flight_flips_the_flight_item_to_broken(bq):
    bq.select.return_value = (
        True,
        trip_rows(("hotel", "booked"), ("flight", "booked"), ("dining", "booked")),
        None,
    )
    with TestClient(app) as client:
        resp = client.post("/v1/disruption/break_flight", json={"trip_id": "t-1"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["item_id"] == "i-1"  # the flight, not the hotel
    assert body["status"] == "broken"
    assert body["previous_status"] == "booked"
    assert body["affected_rows"] == 1

    query = bq.dml.call_args.args[0]
    params = {p.name: p.value for p in bq.dml.call_args.args[1]}
    assert "UPDATE" in query and "updated_at" in query
    assert params == {"status": "broken", "item_id": "i-1"}


def test_break_flight_is_idempotent_on_an_already_broken_flight(bq):
    bq.select.return_value = (True, trip_rows(("flight", "broken")), None)
    with TestClient(app) as client:
        resp = client.post("/v1/disruption/break_flight", json={"trip_id": "t-1"})
    assert resp.status_code == 200
    assert resp.json()["previous_status"] == "broken"


def test_break_flight_404_when_trip_has_no_flight_item(bq):
    bq.select.return_value = (True, trip_rows(("hotel", "booked")), None)
    with TestClient(app) as client:
        resp = client.post("/v1/disruption/break_flight", json={"trip_id": "t-1"})
    assert resp.status_code == 404
    bq.dml.assert_not_called()


def test_break_flight_404_when_trip_unknown(bq):
    with TestClient(app) as client:  # select returns no rows
        resp = client.post("/v1/disruption/break_flight", json={"trip_id": "nope"})
    assert resp.status_code == 404
    bq.dml.assert_not_called()


def test_break_flight_failed_write_is_an_error_not_success(bq):
    bq.select.return_value = (True, trip_rows(("flight", "booked")), None)
    bq.dml.return_value = (False, 0, "quota exceeded")
    with TestClient(app) as client:
        resp = client.post("/v1/disruption/break_flight", json={"trip_id": "t-1"})
    assert resp.status_code == 500
    assert "quota exceeded" in resp.json()["detail"]


def test_break_flight_zero_row_write_is_an_error_not_success(bq):
    bq.select.return_value = (True, trip_rows(("flight", "booked")), None)
    bq.dml.return_value = (True, 0, None)
    with TestClient(app) as client:
        resp = client.post("/v1/disruption/break_flight", json={"trip_id": "t-1"})
    assert resp.status_code == 500
    assert "matched no rows" in resp.json()["detail"]


def test_break_flight_failed_list_is_a_500(bq):
    bq.select.return_value = (False, [], "connection refused")
    with TestClient(app) as client:
        resp = client.post("/v1/disruption/break_flight", json={"trip_id": "t-1"})
    assert resp.status_code == 500
    assert "connection refused" in resp.json()["detail"]
