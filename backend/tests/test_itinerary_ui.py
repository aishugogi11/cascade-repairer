"""Live itinerary UI tests — hermetic, BigQuery mocked at the bq_helper
boundary per test_repositories.py conventions.

The router is mounted on a local app here; main.py wiring has its own smoke
test.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.helpers.bigquery_helper import bq_helper
from api.itinerary_ui import itinerary_ui

app = FastAPI()
app.include_router(itinerary_ui, prefix="/v1/itinerary")

TRIP_ROW = {
    "trip_id": "t-1",
    "user_id": "josh",
    "title": "Hackathon trip",
    "status": "booked",
}


def item_rows(*types_and_statuses):
    return [
        {"item_id": f"i-{n}", "trip_id": "t-1", "type": t, "status": s}
        for n, (t, s) in enumerate(types_and_statuses)
    ]


@pytest.fixture
def bq(monkeypatch):
    """Mock the helper's query primitives on the shared singleton."""
    dml = MagicMock(return_value=(True, 1, None))
    select = MagicMock(return_value=(True, [], None))
    monkeypatch.setattr(bq_helper, "run_dml", dml)
    monkeypatch.setattr(bq_helper, "run_select", select)
    return SimpleNamespace(dml=dml, select=select)


# --- GET / (the page) --------------------------------------------------------

def test_page_serves_html(bq):
    with TestClient(app) as client:
        resp = client.get("/v1/itinerary/")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "Live Itinerary — Cascade Repairer" in resp.text
    bq.select.assert_not_called()  # the page itself costs no BigQuery read


def test_page_is_self_contained(bq):
    """No external requests — inline CSS/JS only, per the no-dependency rule."""
    with TestClient(app) as client:
        text = client.get("/v1/itinerary/").text
    assert "src=\"http" not in text and "href=\"http" not in text


# --- GET /status/{trip_id} ---------------------------------------------------

def test_status_returns_trip_items_summary_and_fetched_at(bq):
    bq.select.side_effect = [
        (True, [TRIP_ROW], None),
        (
            True,
            item_rows(
                ("flight", "broken"),
                ("hotel", "booked"),
                ("ground", "repairing"),
                ("dining", "fixed"),
                ("experience", "booked"),
            ),
            None,
        ),
    ]
    with TestClient(app) as client:
        resp = client.get("/v1/itinerary/status/t-1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["trip"]["trip_id"] == "t-1"
    assert [i["type"] for i in body["items"]] == [
        "flight", "hotel", "ground", "dining", "experience",
    ]
    assert body["fetched_at"]  # server timestamp for staleness display

    counts = body["summary"]["counts"]
    assert set(counts) == {
        "planned", "booked", "broken", "repairing", "fixed", "cancelled",
    }
    assert sum(counts.values()) == len(body["items"])
    assert counts["booked"] == 2 and counts["broken"] == 1


def test_status_items_query_orders_by_start_ts(bq):
    bq.select.side_effect = [
        (True, [TRIP_ROW], None),
        (True, item_rows(("flight", "booked")), None),
    ]
    with TestClient(app) as client:
        client.get("/v1/itinerary/status/t-1")

    items_query = bq.select.call_args_list[1].args[0]
    assert "ORDER BY start_ts" in items_query


def test_status_all_clear_only_when_nothing_broken_or_repairing(bq):
    bq.select.side_effect = [
        (True, [TRIP_ROW], None),
        (True, item_rows(("flight", "repairing"), ("hotel", "fixed")), None),
        (True, [TRIP_ROW], None),
        (True, item_rows(("flight", "fixed"), ("hotel", "cancelled")), None),
    ]
    with TestClient(app) as client:
        mid_repair = client.get("/v1/itinerary/status/t-1").json()
        repaired = client.get("/v1/itinerary/status/t-1").json()

    assert mid_repair["summary"]["all_clear"] is False
    assert repaired["summary"]["all_clear"] is True


def test_status_unknown_trip_is_404(bq):
    with TestClient(app) as client:
        resp = client.get("/v1/itinerary/status/missing")
    assert resp.status_code == 404


def test_status_repository_failure_is_500_not_empty_200(bq):
    bq.select.return_value = (False, [], "quota exceeded")
    with TestClient(app) as client:
        resp = client.get("/v1/itinerary/status/t-1")
    assert resp.status_code == 500
    assert "quota exceeded" in resp.json()["detail"]


# --- GET /trips --------------------------------------------------------------

def test_trips_returns_selector_fields(bq):
    bq.select.return_value = (
        True,
        [
            {**TRIP_ROW, "trip_id": "t-2", "title": "Newer",
             "start_date": "2026-07-17", "end_date": "2026-07-19"},
            TRIP_ROW,
        ],
        None,
    )
    with TestClient(app) as client:
        resp = client.get("/v1/itinerary/trips")

    assert resp.status_code == 200
    listed = resp.json()["trips"]
    assert [t["trip_id"] for t in listed] == ["t-2", "t-1"]
    assert set(listed[0]) == {"trip_id", "title", "status", "start_date", "end_date"}
    assert listed[0]["start_date"] == "2026-07-17"


def test_trips_passes_limit_through(bq):
    with TestClient(app) as client:
        client.get("/v1/itinerary/trips?limit=3")
    params = {p.name: p.value for p in bq.select.call_args.args[1]}
    assert params["limit"] == 3


def test_trips_repository_failure_is_500(bq):
    bq.select.return_value = (False, [], "quota exceeded")
    with TestClient(app) as client:
        resp = client.get("/v1/itinerary/trips")
    assert resp.status_code == 500
