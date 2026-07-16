"""Tests for the typed repository layer over the six trip/session/eval tables.

BigQuery is mocked at the helper boundary (run_dml / run_select on the
bq_helper singleton) — no GCP credentials, no network. Assertions cover the
generated SQL, query parameters, row→model mapping, and enum validation.
"""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import get_args
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from api.helpers.bigquery_helper import bq_helper
from api.helpers.gcs_helper import gcs_helper
from api.repositories import (
    bookings,
    eval_runs,
    itinerary_items,
    sessions,
    trips,
    turns,
)
from api.repositories.models import (
    Booking,
    EvalRun,
    ItemStatus,
    ItineraryItem,
    Session,
    Trip,
    Turn,
)


@pytest.fixture
def bq(monkeypatch):
    """Mock the helper's query primitives on the shared singleton."""
    dml = MagicMock(return_value=(True, 1, None))
    select = MagicMock(return_value=(True, [], None))
    monkeypatch.setattr(bq_helper, "run_dml", dml)
    monkeypatch.setattr(bq_helper, "run_select", select)
    return SimpleNamespace(dml=dml, select=select)


def params_by_name(mock, call_index=0):
    args = mock.call_args_list[call_index].args
    return {p.name: p for p in args[1]}


# --- status enums -----------------------------------------------------------

def test_item_status_covers_exact_repair_lifecycle():
    assert get_args(ItemStatus) == (
        "planned", "booked", "broken", "repairing", "fixed", "cancelled",
    )


# --- trips ------------------------------------------------------------------

def test_create_trip_generates_uuid_and_parameterized_insert(bq):
    trip = Trip(user_id="josh", title="Hackathon trip", destinations=["SFO", "MTV"])
    success, created, error = trips.create_trip(trip)

    assert success is True and error is None
    uuid.UUID(created.trip_id)  # valid generated id

    query = bq.dml.call_args.args[0]
    assert "INSERT INTO" in query and "@trip_id" in query
    assert "CURRENT_TIMESTAMP()" in query  # created_at stamped in SQL
    assert "josh" not in query  # values go through params, not interpolation

    params = params_by_name(bq.dml)
    assert params["user_id"].value == "josh"
    assert params["destinations"].values == ["SFO", "MTV"]  # REPEATED field


def test_get_trip_maps_row_to_model_with_repeated_destinations(bq):
    bq.select.return_value = (
        True,
        [{
            "trip_id": "t-1", "user_id": "josh", "title": "Trip",
            "status": "booked", "origin": "MSP", "destinations": ["SFO", "MTV"],
            "start_date": "2026-07-17", "end_date": "2026-07-19",
            "created_at": datetime(2026, 7, 6, tzinfo=timezone.utc),
        }],
        None,
    )
    success, trip, error = trips.get_trip("t-1")

    assert success is True
    assert trip.status == "booked"
    assert trip.destinations == ["SFO", "MTV"]
    assert params_by_name(bq.select)["trip_id"].value == "t-1"


def test_get_trip_no_rows_returns_none_without_error(bq):
    success, trip, error = trips.get_trip("missing")
    assert (success, trip, error) == (True, None, None)


def test_update_trip_status_rejects_invalid_status(bq):
    with pytest.raises(ValidationError):
        trips.update_trip_status("t-1", "on-fire")
    bq.dml.assert_not_called()


def test_list_recent_trips_orders_newest_first_with_limit_param(bq):
    bq.select.return_value = (
        True,
        [
            {"trip_id": "t-2", "user_id": "josh", "title": "Newer", "status": "booked"},
            {"trip_id": "t-1", "user_id": "josh", "title": "Older", "status": "booked"},
        ],
        None,
    )
    success, result, error = trips.list_recent_trips(limit=2)

    assert success is True and error is None
    assert [t.trip_id for t in result] == ["t-2", "t-1"]
    query = bq.select.call_args.args[0]
    assert "ORDER BY created_at DESC" in query and "LIMIT @limit" in query
    assert params_by_name(bq.select)["limit"].value == 2


def test_list_recent_trips_empty_table_returns_empty_list(bq):
    success, result, error = trips.list_recent_trips()
    assert (success, result, error) == (True, [], None)


def test_list_recent_trips_propagates_helper_failure(bq):
    bq.select.return_value = (False, [], "quota exceeded")
    success, result, error = trips.list_recent_trips()
    assert success is False
    assert result == []
    assert error == "quota exceeded"


def test_get_trip_with_items_returns_unified_view(bq):
    trip_row = {"trip_id": "t-1", "user_id": "josh", "title": "Trip", "status": "booked"}
    item_row = {"item_id": "i-1", "trip_id": "t-1", "type": "flight", "status": "broken"}
    bq.select.side_effect = [(True, [trip_row], None), (True, [item_row], None)]

    success, view, error = trips.get_trip_with_items("t-1")

    assert success is True
    assert view.trip.trip_id == "t-1"
    assert [i.status for i in view.items] == ["broken"]
    items_query = bq.select.call_args_list[1].args[0]
    assert "itinerary_items" in items_query


# --- itinerary_items --------------------------------------------------------

def test_create_item_serializes_details_through_parse_json(bq):
    item = ItineraryItem(
        trip_id="t-1", type="flight", status="booked", provider="sabre",
        details={"flight_no": "DL 1234"}, price=420.0, currency="USD",
    )
    success, created, error = itinerary_items.create_item(item)

    assert success is True
    uuid.UUID(created.item_id)
    query = bq.dml.call_args.args[0]
    assert "PARSE_JSON(@details)" in query
    assert params_by_name(bq.dml)["details"].value == '{"flight_no": "DL 1234"}'


def test_get_item_parses_json_details_from_string(bq):
    bq.select.return_value = (
        True,
        [{
            "item_id": "i-1", "trip_id": "t-1", "type": "flight",
            "status": "fixed", "provider": "sabre",
            "details": '{"flight_no": "DL 1234"}',
        }],
        None,
    )
    success, item, error = itinerary_items.get_item("i-1")

    assert item.details == {"flight_no": "DL 1234"}
    assert item.status == "fixed"


def test_list_items_for_trip_filters_by_trip_id(bq):
    success, items, error = itinerary_items.list_items_for_trip("t-1")
    assert success is True and items == []
    assert params_by_name(bq.select)["trip_id"].value == "t-1"


def test_update_status_stamps_updated_at(bq):
    success, affected, error = itinerary_items.update_status("i-1", "repairing")

    assert (success, affected, error) == (True, 1, None)
    query = bq.dml.call_args.args[0]
    assert "updated_at = CURRENT_TIMESTAMP()" in query
    params = params_by_name(bq.dml)
    assert params["status"].value == "repairing"
    assert params["item_id"].value == "i-1"


def test_update_status_rejects_status_outside_lifecycle(bq):
    with pytest.raises(ValidationError):
        itinerary_items.update_status("i-1", "exploded")
    bq.dml.assert_not_called()


def test_update_status_on_missing_item_is_noop_not_error(bq):
    bq.dml.return_value = (True, 0, None)
    success, affected, error = itinerary_items.update_status("ghost", "fixed")
    assert (success, affected, error) == (True, 0, None)


def test_update_flight_fields_parameterized_dml_stamps_updated_at(bq):
    """Phase 32: the repair's write-back is query-job DML (never streaming),
    every value rides a parameter, and updated_at refreshes in SQL."""
    start = datetime(2026, 7, 18, 15, 5, tzinfo=timezone.utc)
    end = datetime(2026, 7, 18, 23, 40, tzinfo=timezone.utc)
    success, affected, error = itinerary_items.update_flight_fields(
        "i-1",
        start_ts=start,
        end_ts=end,
        price=214.0,
        currency="USD",
        details={"airline": "UA", "flight_number": 512},
    )

    assert (success, affected, error) == (True, 1, None)
    query = bq.dml.call_args.args[0]
    assert "UPDATE" in query
    assert "updated_at = CURRENT_TIMESTAMP()" in query
    assert "PARSE_JSON(@details)" in query
    assert "UA" not in query  # values go through params, not interpolation

    params = params_by_name(bq.dml)
    assert params["item_id"].value == "i-1"
    assert params["start_ts"].value == start
    assert params["end_ts"].value == end
    assert params["price"].value == 214.0
    assert params["currency"].value == "USD"
    assert '"flight_number": 512' in params["details"].value


def test_update_flight_fields_on_missing_item_reports_zero_rows(bq):
    bq.dml.return_value = (True, 0, None)
    success, affected, error = itinerary_items.update_flight_fields(
        "ghost",
        start_ts=datetime(2026, 7, 18, tzinfo=timezone.utc),
        end_ts=datetime(2026, 7, 18, tzinfo=timezone.utc),
        price=0.0,
        currency="USD",
        details=None,
    )
    assert (success, affected, error) == (True, 0, None)


def test_update_flight_fields_surfaces_helper_failure(bq):
    bq.dml.return_value = (False, 0, "quota exceeded")
    success, affected, error = itinerary_items.update_flight_fields(
        "i-1",
        start_ts=datetime(2026, 7, 18, tzinfo=timezone.utc),
        end_ts=datetime(2026, 7, 18, tzinfo=timezone.utc),
        price=1.0,
        currency="USD",
        details={},
    )
    assert success is False and error == "quota exceeded"


def test_repair_lifecycle_sequence_issues_one_update_per_transition(bq):
    """The cascade contract in miniature: booked → broken → repairing → fixed."""
    for status in ["booked", "broken", "repairing", "fixed"]:
        success, _, _ = itinerary_items.update_status("i-1", status)
        assert success is True

    assert bq.dml.call_count == 4
    statuses = [params_by_name(bq.dml, i)["status"].value for i in range(4)]
    assert statuses == ["booked", "broken", "repairing", "fixed"]
    for i in range(4):
        assert "UPDATE" in bq.dml.call_args_list[i].args[0]


# --- bookings ---------------------------------------------------------------

def test_create_booking_serializes_raw_response(bq):
    booking = Booking(
        item_id="i-1", trip_id="t-1", sabre_confirmation_ref="ABC123",
        state="confirmed", raw_response={"pnr": "ABC123"},
    )
    success, created, error = bookings.create_booking(booking)

    assert success is True
    uuid.UUID(created.booking_id)
    assert "PARSE_JSON(@raw_response)" in bq.dml.call_args.args[0]
    assert params_by_name(bq.dml)["sabre_confirmation_ref"].value == "ABC123"


def test_list_bookings_for_trip_maps_rows(bq):
    bq.select.return_value = (
        True,
        [{"booking_id": "b-1", "item_id": "i-1", "trip_id": "t-1",
          "state": "confirmed", "raw_response": '{"pnr": "X"}'}],
        None,
    )
    success, results, error = bookings.list_bookings_for_trip("t-1")
    assert results[0].raw_response == {"pnr": "X"}
    assert params_by_name(bq.select)["trip_id"].value == "t-1"


def test_update_state_rejects_invalid_state(bq):
    with pytest.raises(ValidationError):
        bookings.update_state("b-1", "vaporized")
    bq.dml.assert_not_called()


# --- sessions ---------------------------------------------------------------

def test_create_session_stamps_started_at(bq):
    session = Session(trip_id="t-1", architecture="concierge")
    success, created, error = sessions.create_session(session)

    assert success is True
    uuid.UUID(created.session_id)
    assert "CURRENT_TIMESTAMP()" in bq.dml.call_args.args[0]
    assert params_by_name(bq.dml)["architecture"].value == "concierge"


def test_session_rejects_invalid_architecture():
    with pytest.raises(ValidationError):
        Session(architecture="quantum")


def test_end_session_stamps_ended_at(bq):
    success, affected, error = sessions.end_session("s-1")
    assert success is True
    query = bq.dml.call_args.args[0]
    assert "ended_at = CURRENT_TIMESTAMP()" in query
    assert params_by_name(bq.dml)["session_id"].value == "s-1"


# --- turns ------------------------------------------------------------------

def test_audio_uri_follows_convention():
    uri = turns.audio_uri_for("s-1", "t-9")
    assert uri == f"gs://{gcs_helper.bucket_name}/audio/s-1/t-9.wav"


def test_create_turn_defaults_started_at_in_sql(bq):
    turn = Turn(session_id="s-1", role="agent", transcript="On it.", ttfb_ms=250)
    success, created, error = turns.create_turn(turn)

    assert success is True
    assert "COALESCE(@started_at, CURRENT_TIMESTAMP())" in bq.dml.call_args.args[0]
    assert params_by_name(bq.dml)["ttfb_ms"].value == 250


def test_list_turns_for_session_maps_rows(bq):
    bq.select.return_value = (
        True,
        [{"turn_id": "t-1", "session_id": "s-1", "role": "user",
          "transcript": "My flight got cancelled", "ttfb_ms": 120}],
        None,
    )
    success, results, error = turns.list_turns_for_session("s-1")
    assert results[0].role == "user"
    assert params_by_name(bq.select)["session_id"].value == "s-1"


# --- eval_runs --------------------------------------------------------------

def test_create_run_parameterizes_metrics(bq):
    run = EvalRun(architecture="cascaded", git_sha="abc123", scenario="cascade",
                  ttfb_ms=310.5, wer=0.04)
    success, created, error = eval_runs.create_run(run)

    assert success is True
    uuid.UUID(created.run_id)
    params = params_by_name(bq.dml)
    assert params["wer"].value == 0.04
    assert params["git_sha"].value == "abc123"


def test_list_runs_builds_filters_only_when_given(bq):
    eval_runs.list_runs()
    assert "WHERE" not in bq.select.call_args_list[0].args[0]

    eval_runs.list_runs(architecture="concierge", scenario="cascade")
    query = bq.select.call_args_list[1].args[0]
    assert "architecture = @architecture" in query
    assert "scenario = @scenario" in query
    params = params_by_name(bq.select, 1)
    assert params["architecture"].value == "concierge"


# --- error propagation ------------------------------------------------------

def test_repository_propagates_helper_failure(bq):
    bq.dml.return_value = (False, 0, "quota exceeded")
    success, created, error = trips.create_trip(Trip(user_id="j", title="x"))
    assert success is False
    assert created is None
    assert "quota exceeded" in error

    bq.select.return_value = (False, [], "table not found")
    success, items, error = itinerary_items.list_items_for_trip("t-1")
    assert success is False
    assert items == []
