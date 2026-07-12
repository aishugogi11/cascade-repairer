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


def test_page_contains_all_status_visual_hooks(bq):
    """Every status in the repair lifecycle has a visual on the page."""
    with TestClient(app) as client:
        text = client.get("/v1/itinerary/").text
    for status in ("planned", "booked", "broken", "repairing", "fixed", "cancelled"):
        assert f'[data-status="{status}"]' in text


def test_page_is_self_contained(bq):
    """No external requests — inline CSS/JS only, per the no-dependency rule."""
    with TestClient(app) as client:
        text = client.get("/v1/itinerary/").text
    assert "src=\"http" not in text and "href=\"http" not in text


def test_page_renders_times_pacific_labeled_pt(bq):
    """Phase 19: card times, the feed clock, and the trip selector's
    created-at label all render America/Los_Angeles for every viewer,
    labeled "PT" — never "PST" (it's PDT in July), never browser-local."""
    with TestClient(app) as client:
        text = client.get("/v1/itinerary/").text
    assert text.count('timeZone: "America/Los_Angeles"') == 3
    assert text.count('" PT"') == 2
    assert '" PT)"' in text  # the selector's "(… PT)" created-at label
    assert "PST" not in text


def test_page_selector_labels_and_sorts_by_created_at(bq):
    """The trip dropdown shows each trip's creation time and orders
    newest-first client-side (explicit, not transport order)."""
    with TestClient(app) as client:
        text = client.get("/v1/itinerary/").text
    assert "fmtCreated(trip.created_at)" in text
    assert "trips.sort" in text and "b.created_at" in text


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
    # Three selects per request since Phase 17: trip, items, bookings (the
    # detail read). Assertions unchanged.
    bq.select.side_effect = [
        (True, [TRIP_ROW], None),
        (True, item_rows(("flight", "repairing"), ("hotel", "fixed")), None),
        (True, [], None),
        (True, [TRIP_ROW], None),
        (True, item_rows(("flight", "fixed"), ("hotel", "cancelled")), None),
        (True, [], None),
    ]
    with TestClient(app) as client:
        mid_repair = client.get("/v1/itinerary/status/t-1").json()
        repaired = client.get("/v1/itinerary/status/t-1").json()

    assert mid_repair["summary"]["all_clear"] is False
    assert repaired["summary"]["all_clear"] is True


def test_status_all_clear_false_for_broken_items(bq):
    bq.select.side_effect = [
        (True, [TRIP_ROW], None),
        (True, item_rows(("flight", "broken"), ("hotel", "booked")), None),
    ]
    with TestClient(app) as client:
        body = client.get("/v1/itinerary/status/t-1").json()

    assert body["summary"]["all_clear"] is False


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


# --- per-item detail (Phase 17, feeds the iOS recommendation sheet) -----------

def booking_row(item_id, raw_response):
    return {
        "booking_id": f"b-{item_id}",
        "item_id": item_id,
        "trip_id": "t-1",
        "sabre_confirmation_ref": "ABCDEF",
        "state": "confirmed",
        "raw_response": raw_response,
    }


VOICE_RAW = {
    "source": "voice_guided_booking",
    "option": {"option_number": 1, "price": 187.6, "stops": 0,
               "arrive_time": "10:05"},
    "options_offered": [
        {"option_number": 1, "price": 187.6},
        {"option_number": 2, "price": 242.0},
        {"option_number": 3, "price": 155.0},
    ],
}


def test_status_detail_for_voice_booked_flight(bq):
    bq.select.side_effect = [
        (True, [TRIP_ROW], None),
        (True, item_rows(("flight", "booked"), ("hotel", "booked")), None),
        (True, [booking_row("i-0", VOICE_RAW)], None),
    ]
    with TestClient(app) as client:
        body = client.get("/v1/itinerary/status/t-1").json()

    flight, hotel = body["items"]
    detail = flight["detail"]
    assert "three options" in detail["why_chosen"]
    assert "nonstop" in detail["why_chosen"]
    assert detail["price_delta"] == "+$33"  # 187.6 vs the 155.0 alternative
    assert detail["impact"]
    # The hotel has no booking row — the key is omitted, not nulled.
    assert "detail" not in hotel


def test_status_detail_for_repaired_item_and_latest_booking_wins(bq):
    bq.select.side_effect = [
        (True, [TRIP_ROW], None),
        (True, item_rows(("ground", "fixed")), None),
        (
            True,
            [
                booking_row("i-0", {"seeded": True, "type": "ground"}),
                booking_row("i-0", {"provider": "mock-ground",
                                    "pickup_time": "13:00"}),
            ],
            None,
        ),
    ]
    with TestClient(app) as client:
        body = client.get("/v1/itinerary/status/t-1").json()

    detail = body["items"][0]["detail"]
    # The later (repair) booking speaks, not the seeded one.
    assert "rescheduled" in detail["why_chosen"]
    assert detail["price_delta"] == "$0"
    assert "landing" in detail["impact"] or "ride" in detail["impact"]


def test_status_detail_read_failure_never_breaks_the_poll(bq):
    bq.select.side_effect = [
        (True, [TRIP_ROW], None),
        (True, item_rows(("flight", "booked")), None),
        (False, [], "bookings table on fire"),
    ]
    with TestClient(app) as client:
        resp = client.get("/v1/itinerary/status/t-1")

    assert resp.status_code == 200
    assert "detail" not in resp.json()["items"][0]


# --- GET /trips --------------------------------------------------------------

def test_trips_returns_selector_fields(bq):
    bq.select.return_value = (
        True,
        [
            {**TRIP_ROW, "trip_id": "t-2", "title": "Newer",
             "start_date": "2026-07-17", "end_date": "2026-07-19",
             "created_at": "2026-07-12T18:05:52+00:00"},
            TRIP_ROW,
        ],
        None,
    )
    with TestClient(app) as client:
        resp = client.get("/v1/itinerary/trips")

    assert resp.status_code == 200
    listed = resp.json()["trips"]
    assert [t["trip_id"] for t in listed] == ["t-2", "t-1"]
    assert set(listed[0]) == {
        "trip_id", "title", "status", "start_date", "end_date", "created_at",
    }
    assert listed[0]["start_date"] == "2026-07-17"
    # created_at feeds the selector's "(Jul 12, 11:05 AM PT)" label and its
    # newest-first sort; a row without one serializes as null, not an error.
    assert listed[0]["created_at"] == "2026-07-12T18:05:52+00:00"
    assert listed[1]["created_at"] is None


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
