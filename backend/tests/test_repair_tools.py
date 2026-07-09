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
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from api import repair_tools
from api.helpers.bigquery_helper import bq_helper
from api.sabre import client as sabre_client


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


def test_rebook_flight_cancels_old_ref_and_writes_booking_only(bq):
    bq.select.return_value = (True, [booking_row()], None)

    payload = asyncio.run(repair_tools._rebook_flight(
        "t-1", "i-flight", "MSP", "SFO", "2026-07-18"
    ))

    assert_booking_insert_only(bq.dml, "i-flight")  # single writer: no status DML
    assert payload["cancelled_ref"] == "GLEBNY"  # from the existing booking row
    assert payload["confirmation_ref"] != "GLEBNY"  # a new PNR
    assert "item_status" not in payload
    assert payload["departure_date"] == "2026-07-18"

    raw = json.loads(dml_writes(bq.dml)[0][1]["raw_response"])
    assert raw["cancelled"]["booking"]["bookingId"] == "GLEBNY"
    assert raw["created"]["confirmationId"] == payload["confirmation_ref"]


def test_rebook_flight_without_existing_booking_uses_placeholder_ref(bq):
    payload = asyncio.run(repair_tools._rebook_flight(
        "t-1", "i-flight", "MSP", "SFO", "2026-07-18"
    ))
    assert payload["cancelled_ref"] == "UNKNWN"
    assert payload["confirmation_ref"]


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
