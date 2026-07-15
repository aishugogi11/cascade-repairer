"""Repair tool tests — the plain functions, hermetic.

BigQuery is mocked at the bq_helper boundary; Sabre goes through the
dispatcher in its default mock mode (no network). Assertions cover the DML
the tools emit and the payload the agent reads back. Single-writer rule
(Phase 9): repair tools write their bookings row ONLY — itinerary status
transitions belong to the cascade unit; only the initial booking tool still
flips its item (to `booked`).
"""
import asyncio
import json
import logging
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from api import flight_options, repair_tools
from api.helpers.bigquery_helper import bq_helper
from api.sabre import client as sabre_client
from api.sabre import shapes

# Computed travel date (the Phase 26 rule) — never a literal.
_DAY = (date.today() + timedelta(days=21)).isoformat()


@pytest.fixture
def bq(monkeypatch):
    """Mock the helper's query primitives on the shared singleton."""
    dml = MagicMock(return_value=(True, 1, None))
    select = MagicMock(return_value=(True, [], None))
    monkeypatch.setattr(bq_helper, "run_dml", dml)
    monkeypatch.setattr(bq_helper, "run_select", select)
    return SimpleNamespace(dml=dml, select=select)


@pytest.fixture(autouse=True)
def fast_sabre(monkeypatch):
    monkeypatch.delenv("SABRE_MODE", raising=False)
    monkeypatch.setattr(sabre_client._mock, "latency_seconds", 0)


def booking_row(item_id="i-flight", ref="GLEBNY"):
    return {
        "booking_id": "b-1", "item_id": item_id, "trip_id": "t-1",
        "sabre_confirmation_ref": ref, "state": "confirmed",
        "raw_response": json.dumps({"seeded": True}),
    }


def dml_writes(dml):
    """(query, params-dict) per DML call, in order."""
    return [
        (c.args[0], {p.name: p.value for p in c.args[1]})
        for c in dml.call_args_list
    ]


def assert_booking_insert(writes, item_id):
    insert_query, insert_params = writes[0]
    assert "INSERT INTO" in insert_query and "bookings" in insert_query
    assert insert_params["item_id"] == item_id
    assert insert_params["state"] == "confirmed"
    assert insert_params["raw_response"] is not None  # Sabre payload captured


def assert_booking_insert_only(dml, item_id):
    """The repair-tool contract: one bookings insert, zero status writes."""
    writes = dml_writes(dml)
    assert len(writes) == 1
    assert_booking_insert(writes, item_id)


def assert_booking_insert_then_status(dml, item_id, status):
    """The initial-booking contract: bookings insert, then the status flip."""
    writes = dml_writes(dml)
    assert len(writes) == 2
    assert_booking_insert(writes, item_id)
    update_query, update_params = writes[1]
    assert "UPDATE" in update_query and "updated_at" in update_query
    assert update_params == {"status": status, "item_id": item_id}


# --- Sabre-backed tools ---------------------------------------------------------

def test_search_and_book_flight_books_and_flips_to_booked(bq):
    payload = asyncio.run(repair_tools._search_and_book_flight(
        "t-1", "i-flight", "MSP", "SFO", "2026-07-17"
    ))

    assert_booking_insert_then_status(bq.dml, "i-flight", "booked")
    assert payload["item_status"] == "booked"
    assert payload["confirmation_ref"]
    assert payload["airline"] == "AA" and payload["flight_number"] > 0
    assert payload["departure_date"] == "2026-07-17"
    assert payload["price"] == 187.6 and payload["currency"] == "USD"

    # The bookings row carries the full Sabre create response.
    raw = json.loads(dml_writes(bq.dml)[0][1]["raw_response"])
    assert raw["confirmationId"] == payload["confirmation_ref"]
    assert raw["booking"]["flights"][0]["flightStatusName"] == "Confirmed"


def _mock_options(origin, dest, day):
    """The parsed mock InstaFlights options for a route/date — the same three
    the re-shop sees in SABRE_MODE=mock."""
    request = shapes.InstaFlightsRequest(
        origin=origin, destination=dest, departuredate=day
    )
    response = asyncio.run(sabre_client._mock.instaflights_search(request))
    return flight_options._parse_instaflights_options(response, origin, dest)


def test_rebook_flight_reshops_real_instaflights_and_writes_flight_repair(bq):
    """Phase 29: the re-shop parses real InstaFlights (the mock serves the
    same shape in SABRE_MODE=mock), stores the chosen option + the
    alternatives it beat + the original fare, and the PNR write stays mock —
    still a single bookings insert (the cascade unit owns the status flip)."""
    bq.select.return_value = (True, [booking_row()], None)

    payload = asyncio.run(repair_tools._rebook_flight(
        "t-1", "i-flight", "MSP", "SFO", _DAY,
        original_price=500.0, original_currency="USD",
        original_arrive_time="10:05",
    ))

    assert_booking_insert_only(bq.dml, "i-flight")  # single writer: no status DML
    assert payload["cancelled_ref"] == "GLEBNY"  # from the existing booking row
    assert payload["confirmation_ref"] != "GLEBNY"  # a new PNR
    assert "item_status" not in payload
    assert payload["from_mock_fallback"] is False  # real parse succeeded
    assert payload["price_delta"] == payload["price"] - 500.0

    raw = json.loads(dml_writes(bq.dml)[0][1]["raw_response"])
    assert raw["source"] == "flight_repair"
    assert raw["option"]["flight_number"] > 0  # a parsed itinerary
    assert raw["option"]["origin"] == "MSP" and raw["option"]["destination"] == "SFO"
    assert raw["option"]["price"] == payload["price"]
    assert len(raw["alternatives"]) >= 1  # it beat at least one other
    assert raw["option"] not in raw["alternatives"]  # the chosen isn't its own alt
    assert raw["original_price"] == 500.0 and raw["original_currency"] == "USD"
    assert raw["from_mock_fallback"] is False
    # The mock PNR write is carried unchanged under `rebooked`.
    assert raw["rebooked"]["cancelled"]["booking"]["bookingId"] == "GLEBNY"
    assert raw["rebooked"]["created"]["confirmationId"] == payload["confirmation_ref"]


def test_rebook_flight_chooses_a_different_flight_than_the_cancelled_one(bq):
    """Selection excludes the cancelled (airline, flight_number) when the
    alternatives allow — the rebooked flight is a genuinely different one."""
    bq.select.return_value = (True, [booking_row()], None)
    options = _mock_options("MSP", "SFO", _DAY)
    cancelled = (options[0].airline, options[0].flight_number)

    payload = asyncio.run(repair_tools._rebook_flight(
        "t-1", "i-flight", "MSP", "SFO", _DAY,
        original_price=200.0, original_arrive_time=options[0].arrive_time,
        cancelled_flight=cancelled,
    ))

    assert payload["flight_number"] != cancelled[1]
    raw = json.loads(dml_writes(bq.dml)[0][1]["raw_response"])
    assert (raw["option"]["airline"], raw["option"]["flight_number"]) != cancelled


def test_rebook_flight_without_existing_booking_uses_placeholder_ref(bq):
    payload = asyncio.run(repair_tools._rebook_flight(
        "t-1", "i-flight", "MSP", "SFO", _DAY
    ))
    assert payload["cancelled_ref"] == "UNKNWN"
    assert payload["confirmation_ref"]


# --- selection: closest arrival, exclude cancelled, tolerate the edges ----------

def _opt(number, flight, arrive, airline="AA", price=200.0):
    return flight_options.FlightOption(
        option_number=number, airline=airline, flight_number=flight,
        origin="JFK", destination="LAX", depart_date=_DAY, depart_time="08:00",
        arrive_time=arrive, stops=0, price=price, currency="USD",
        spoken=f"Option {number}.",
    )


def test_pick_replacement_returns_closest_arrival():
    options = [_opt(1, 100, "15:00"), _opt(2, 200, "10:10"), _opt(3, 300, "12:00")]
    chosen = repair_tools._pick_replacement(options, None, "10:00")
    assert chosen.flight_number == 200  # 10:10 is nearest 10:00


def test_pick_replacement_excludes_the_cancelled_flight():
    options = [_opt(1, 100, "10:05"), _opt(2, 200, "10:40")]
    chosen = repair_tools._pick_replacement(options, ("AA", 100), "10:00")
    assert chosen.flight_number == 200  # 100 is closer but is the cancelled one


def test_pick_replacement_none_cancelled_and_none_arrival_takes_first():
    options = [_opt(1, 100, "09:00"), _opt(2, 200, "23:30")]
    assert repair_tools._pick_replacement(options, None, None).flight_number == 100


def test_pick_replacement_all_same_number_falls_back_to_closest_over_all():
    """Excluding the cancelled number would empty the list — keep them all and
    pick closest-arrival (the best-effort 'where possible')."""
    options = [_opt(1, 500, "15:00"), _opt(2, 500, "10:10")]
    chosen = repair_tools._pick_replacement(options, ("AA", 500), "10:00")
    assert chosen.arrive_time == "10:10"


def test_pick_replacement_arrival_distance_wraps_the_clock():
    options = [_opt(1, 100, "00:10"), _opt(2, 200, "22:00")]
    chosen = repair_tools._pick_replacement(options, None, "23:55")
    assert chosen.flight_number == 100  # 00:10 is 15 min from 23:55, not 1425


def test_pick_replacement_without_identity_excludes_equal_clocks():
    """Phase 31 (live QA): with no flight identity on the item (seed trips,
    pre-31 rows), an option matching the original's depart AND arrive
    clocks is the same flight — the rebooked flight must differ."""
    # All _opt options depart 08:00; option 1 also arrives at the
    # original's 10:00 — the same-flight tell.
    options = [_opt(1, 100, "10:00"), _opt(2, 200, "10:40")]
    chosen = repair_tools._pick_replacement(
        options, None, "10:00", original_depart_time="08:00"
    )
    assert chosen.flight_number == 200

    # A different depart clock is a different flight, even with the same
    # arrival — closest-arrival keeps it.
    chosen = repair_tools._pick_replacement(
        options, None, "10:00", original_depart_time="09:30"
    )
    assert chosen.flight_number == 100


def test_pick_replacement_equal_clock_exclusion_never_empties(caplog):
    """The only cached itinerary IS the original's clocks — fall back to
    the unfiltered pool with a warning rather than crash or skip."""
    options = [_opt(1, 100, "10:00")]
    with caplog.at_level("WARNING"):
        chosen = repair_tools._pick_replacement(
            options, None, "10:00", original_depart_time="08:00"
        )
    assert chosen.flight_number == 100
    assert "unfiltered pool" in caplog.text


# --- empty re-shop -> mock fallback, never a stall ------------------------------

def test_empty_reshop_falls_back_to_mock_and_still_writes(bq, monkeypatch, caplog):
    """decision 3: the dispatcher returns an honest empty on the documented
    no-results 404 (it does not mock-swap), so the re-shop can reach here with
    zero options. It calls the mock directly, flags from_mock_fallback, logs
    the route, and still writes a booking row — the cascade never stalls."""
    monkeypatch.setenv("SABRE_MODE", "real")
    bq.select.return_value = (True, [booking_row()], None)

    async def empty(request):
        return shapes.InstaFlightsResponse(PricedItineraries=[])

    monkeypatch.setattr(sabre_client._real, "instaflights_search", empty)

    with caplog.at_level(logging.WARNING):
        payload = asyncio.run(repair_tools._rebook_flight(
            "t-1", "i-flight", "MSP", "SFO", _DAY, original_price=300.0,
        ))

    assert payload["from_mock_fallback"] is True
    assert_booking_insert_only(bq.dml, "i-flight")  # a real booking row still lands
    raw = json.loads(dml_writes(bq.dml)[0][1]["raw_response"])
    assert raw["from_mock_fallback"] is True
    assert raw["option"]["flight_number"] > 0  # the mock's option, parsed
    assert f"MSP-SFO {_DAY}" in caplog.text and "using mock" in caplog.text


def test_empty_reshop_failed_write_still_raises(bq, monkeypatch):
    """The standing rule survives the fallback: a 0-row/failed booking write
    raises even when the mock served the options."""
    monkeypatch.setenv("SABRE_MODE", "real")

    async def empty(request):
        return shapes.InstaFlightsResponse(PricedItineraries=[])

    monkeypatch.setattr(sabre_client._real, "instaflights_search", empty)
    bq.dml.return_value = (False, 0, "quota exceeded")
    with pytest.raises(RuntimeError, match="booking insert failed"):
        asyncio.run(repair_tools._rebook_flight(
            "t-1", "i-flight", "MSP", "SFO", _DAY,
        ))


def test_shift_hotel_dates_moves_stay_and_writes_booking_only(bq):
    bq.select.return_value = (True, [booking_row(item_id="i-hotel", ref="UEEBMH")], None)

    payload = asyncio.run(repair_tools._shift_hotel_dates(
        "t-1", "i-hotel", "2026-07-18", "2026-07-20"
    ))

    assert_booking_insert_only(bq.dml, "i-hotel")
    assert payload["confirmation_ref"] == "UEEBMH"  # modify keeps the PNR
    assert (payload["check_in"], payload["check_out"]) == ("2026-07-18", "2026-07-20")
    assert payload["total"] == "426.02" and payload["currency"] == "USD"


# --- Simple category mocks ------------------------------------------------------

@pytest.mark.parametrize("tool,item_id,arg,payload_key", [
    (repair_tools._reschedule_ground, "i-ground", "2026-07-17T14:00", "pickup_time"),
    (repair_tools._move_dining, "i-dining", "2026-07-17T20:30", "reservation_time"),
    (repair_tools._rebook_experience, "i-exp", "2026-07-19", "date"),
])
def test_category_mocks_write_booking_only(bq, tool, item_id, arg, payload_key):
    payload = asyncio.run(tool("t-1", item_id, arg))

    assert_booking_insert_only(bq.dml, item_id)
    assert payload[payload_key] == arg
    assert "item_status" not in payload
    assert payload["confirmation_ref"]

    # Deterministic ref: same item, same ref.
    rerun = asyncio.run(tool("t-1", item_id, arg))
    assert rerun["confirmation_ref"] == payload["confirmation_ref"]


# --- failure surfacing ----------------------------------------------------------

def test_failed_booking_insert_raises(bq):
    bq.dml.return_value = (False, 0, "quota exceeded")
    with pytest.raises(RuntimeError, match="booking insert failed"):
        asyncio.run(repair_tools._move_dining("t-1", "i-dining", "2026-07-17T20:30"))


def test_zero_row_status_write_raises_for_initial_booking(bq):
    # The one tool that still flips status: booking insert lands, the
    # `booked` flip matches no rows. (Repair tools have no status write to
    # fail — the cascade unit's flips are covered in test_concurrency_spike.)
    bq.dml.side_effect = [(True, 1, None), (True, 0, None)]
    with pytest.raises(RuntimeError, match="matched no rows"):
        asyncio.run(repair_tools._search_and_book_flight(
            "t-1", "i-ghost", "MSP", "SFO", "2026-07-17"
        ))


# --- agent wiring ---------------------------------------------------------------

def test_all_six_tools_are_function_tools():
    from agents import FunctionTool

    assert len(repair_tools.ALL_REPAIR_TOOLS) == 6
    assert all(isinstance(t, FunctionTool) for t in repair_tools.ALL_REPAIR_TOOLS)
    assert {t.name for t in repair_tools.ALL_REPAIR_TOOLS} == {
        "search_and_book_flight", "rebook_flight", "shift_hotel_dates",
        "reschedule_ground", "move_dining", "rebook_experience",
    }
