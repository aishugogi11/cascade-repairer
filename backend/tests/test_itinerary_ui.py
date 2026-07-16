"""Live itinerary UI tests — hermetic, BigQuery mocked at the bq_helper
boundary per test_repositories.py conventions.

The router is mounted on a local app here; main.py wiring has its own smoke
test.
"""
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import concierge, itinerary_ui as itinerary_ui_mod
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


# --- flight_repair detail (Phase 29) — real why-chosen + signed price-delta ---


def _flight_repair_raw(price=420.0, original=500.0, airline="DL",
                       flight_number=2412, stops=0, arrive_time="15:10"):
    return {
        "source": "flight_repair",
        "option": {
            "airline": airline, "flight_number": flight_number, "stops": stops,
            "arrive_time": arrive_time, "price": price,
        },
        "alternatives": [{"flight_number": 999}],
        "original_price": original,
        "original_currency": "USD",
        "from_mock_fallback": False,
    }


def test_flight_repair_detail_names_flight_and_signs_a_cheaper_delta():
    detail = itinerary_ui_mod._flight_repair_detail(_flight_repair_raw())
    # Names the airline + flight number + arrival, warm and jargon-free.
    assert "Delta 2412" in detail["why_chosen"]
    assert "3:10 PM" in detail["why_chosen"]  # 15:10 -> 12-hour PT clock
    assert "nonstop" in detail["why_chosen"]
    for jargon in ("mock", "sandbox", "API", "InstaFlights", "DL"):
        assert jargon not in detail["why_chosen"]
    assert detail["price_delta"] == "-$80"  # 420 vs 500 — a cheaper rebooking
    assert detail["impact"]


def test_flight_repair_detail_signed_delta_costlier_and_zero():
    costlier = itinerary_ui_mod._flight_repair_detail(
        _flight_repair_raw(price=560.0, original=500.0, stops=1, airline="AA",
                           flight_number=100)
    )
    assert costlier["price_delta"] == "+$60"
    assert "American 100" in costlier["why_chosen"] and "one stop" in costlier["why_chosen"]

    within = itinerary_ui_mod._flight_repair_detail(
        _flight_repair_raw(price=500.30, original=500.0)
    )
    assert within["price_delta"] == "$0"  # inside the +/-$0.50 threshold


# --- rebooked_from "was" line (Phase 32) — the old -> new treatment ------------


def test_flight_repair_detail_rebooked_from_full_context():
    raw = _flight_repair_raw()
    raw["rebooked_from"] = {
        "airline": "UA", "flight_number": 512, "depart_time": "08:05",
        "arrive_time": "10:40", "price": 214.0, "currency": "USD",
    }
    detail = itinerary_ui_mod._flight_repair_detail(raw)
    assert detail["rebooked_from"] == "Was United 512 · departed 8:05 AM PT · $214"


def test_flight_repair_detail_rebooked_from_without_identity():
    """Seed/pre-31 trips carry no flight identity — the line degrades to
    times/price only, never crashes."""
    raw = _flight_repair_raw()
    raw["rebooked_from"] = {
        "airline": None, "flight_number": None, "depart_time": "08:05",
        "arrive_time": None, "price": 214.0, "currency": "USD",
    }
    detail = itinerary_ui_mod._flight_repair_detail(raw)
    assert detail["rebooked_from"] == "Was the 8:05 AM PT departure · $214"
    assert "None" not in detail["rebooked_from"]


def test_flight_repair_detail_rebooked_from_omitted_when_nothing_usable():
    """Pre-32 bookings (no rebooked_from block) and all-empty blocks omit the
    key entirely — the page shows no was-line rather than an empty one."""
    detail = itinerary_ui_mod._flight_repair_detail(_flight_repair_raw())
    assert "rebooked_from" not in detail

    raw = _flight_repair_raw()
    raw["rebooked_from"] = {
        "airline": None, "flight_number": None, "depart_time": None,
        "arrive_time": None, "price": 0.0, "currency": "USD",
    }
    detail = itinerary_ui_mod._flight_repair_detail(raw)
    assert "rebooked_from" not in detail


def test_flight_repair_detail_rebooked_from_never_raises_on_garbage():
    raw = _flight_repair_raw()
    raw["rebooked_from"] = {"depart_time": "not-a-clock", "price": 100.0}
    detail = itinerary_ui_mod._flight_repair_detail(raw)
    # The malformed clock is swallowed; the detail block itself survives.
    assert detail["why_chosen"]
    assert detail.get("rebooked_from") is None


def test_status_routes_flight_repair_booking_to_the_real_builder(bq):
    """The status endpoint dispatches a flight_repair booking to
    _flight_repair_detail, not the static _REPAIR_WHY fallback."""
    bq.select.side_effect = [
        (True, [TRIP_ROW], None),
        (True, item_rows(("flight", "fixed")), None),
        (True, [booking_row("i-0", _flight_repair_raw())], None),
    ]
    with TestClient(app) as client:
        body = client.get("/v1/itinerary/status/t-1").json()

    detail = body["items"][0]["detail"]
    assert "Delta 2412" in detail["why_chosen"]
    assert detail["price_delta"] == "-$80"
    # not the static "Rebooked automatically to keep the trip on track." copy
    assert "automatically" not in detail["why_chosen"]


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


# --- pending_options (Phase 21, feeds the booking page's candidates) ----------


def flight_option(n, price=250.0):
    return concierge.FlightOption(
        option_number=n, airline="AA", flight_number=100 + n, origin="MSP",
        destination="SFO", depart_date="2026-07-17", depart_time="08:00",
        arrive_time="10:05", stops=0, price=price, currency="USD",
        spoken=f"Option {n}.",
    )


def latest_search(session="s-1"):
    # recorded_at must be fresh: since Phase 22 (item H) a slot older than
    # concierge._LATEST_SEARCH_TTL stops surfacing — a fixed past date here
    # would test the expiry path, which has its own tests in test_concierge.
    return concierge.LatestSearch(
        session_id=session,
        options=[flight_option(1), flight_option(2, price=311.4)],
        recorded_at=datetime.now(timezone.utc),
    )


def pinned_context(trip_id):
    return concierge.TripContext(
        trip=concierge.Trip(**dict(TRIP_ROW, trip_id=trip_id)),
        items=[], summary="pinned",
    )


def _one_flight_status(bq):
    bq.select.side_effect = [
        (True, [TRIP_ROW], None),
        (True, item_rows(("flight", "booked")), None),
        (True, [], None),
    ]


def test_status_pending_options_for_unpinned_session(bq, monkeypatch):
    """The pre-booking window: a search happened but no trip is pinned yet —
    whatever trip the page polls sees the candidates."""
    slot = latest_search()
    monkeypatch.setattr(concierge, "_LATEST_SEARCH", slot)
    monkeypatch.setattr(concierge, "_SESSION_TRIPS", {})
    _one_flight_status(bq)
    with TestClient(app) as client:
        body = client.get("/v1/itinerary/status/t-1").json()

    block = body["pending_options"]
    assert block["recorded_at"] == slot.recorded_at.isoformat()
    assert [o["option_number"] for o in block["options"]] == [1, 2]
    option = block["options"][0]
    # The speakable-summary shape: route, PT wall-clock labels, rounded
    # price — and no airline codes anywhere in it.
    assert option["route"] == "MSP → SFO"
    assert option["depart_time"] == "8 AM"
    assert option["arrive_time"] == "10:05 AM"
    assert option["stops"] == 0
    assert option["price"] == 250
    assert block["options"][1]["price"] == 311
    assert "airline" not in option and "AA" not in str(block)
    # The additive contract: everything else is untouched.
    assert body["trip"]["trip_id"] == "t-1"
    assert body["summary"]["counts"]["booked"] == 1


def test_status_pending_options_for_session_pinned_to_this_trip(bq, monkeypatch):
    monkeypatch.setattr(concierge, "_LATEST_SEARCH", latest_search())
    monkeypatch.setattr(
        concierge, "_SESSION_TRIPS", {"s-1": pinned_context("t-1")}
    )
    _one_flight_status(bq)
    with TestClient(app) as client:
        body = client.get("/v1/itinerary/status/t-1").json()

    assert "pending_options" in body


def test_status_omits_pending_options_when_slot_empty(bq, monkeypatch):
    monkeypatch.setattr(concierge, "_LATEST_SEARCH", None)
    _one_flight_status(bq)
    with TestClient(app) as client:
        body = client.get("/v1/itinerary/status/t-1").json()

    assert "pending_options" not in body


def test_status_omits_pending_options_pinned_to_a_different_trip(bq, monkeypatch):
    """A session mid-conversation about trip t-other must not leak its
    candidates onto every other trip's poll."""
    monkeypatch.setattr(concierge, "_LATEST_SEARCH", latest_search())
    monkeypatch.setattr(
        concierge, "_SESSION_TRIPS", {"s-1": pinned_context("t-other")}
    )
    _one_flight_status(bq)
    with TestClient(app) as client:
        body = client.get("/v1/itinerary/status/t-1").json()

    assert "pending_options" not in body


def test_status_pending_options_read_failure_never_breaks_the_poll(bq, monkeypatch):
    def explode(trip_id):
        raise RuntimeError("slot on fire")

    monkeypatch.setattr(concierge, "pending_options_for_trip", explode)
    _one_flight_status(bq)
    with TestClient(app) as client:
        resp = client.get("/v1/itinerary/status/t-1")

    assert resp.status_code == 200
    body = resp.json()
    assert "pending_options" not in body
    assert body["trip"]["trip_id"] == "t-1"  # the poll stays valid


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
