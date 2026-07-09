"""Repository for the bookings table."""
import json
from typing import List, Optional, Tuple

from google.cloud import bigquery

from api.helpers.bigquery_helper import bq_helper
from api.repositories.models import BOOKING_STATE_ADAPTER, Booking, rows_to_models


def _table() -> str:
    return bq_helper.get_table_reference("bookings")


def create_booking(booking: Booking) -> Tuple[bool, Optional[Booking], Optional[str]]:
    """Insert a booking; booked_at is stamped by BigQuery."""
    query = f"""
        INSERT INTO `{_table()}`
            (booking_id, item_id, trip_id, sabre_confirmation_ref, state,
             booked_at, raw_response)
        VALUES
            (@booking_id, @item_id, @trip_id, @sabre_confirmation_ref, @state,
             CURRENT_TIMESTAMP(), PARSE_JSON(@raw_response))
    """
    raw = json.dumps(booking.raw_response) if booking.raw_response is not None else None
    params = [
        bigquery.ScalarQueryParameter("booking_id", "STRING", booking.booking_id),
        bigquery.ScalarQueryParameter("item_id", "STRING", booking.item_id),
        bigquery.ScalarQueryParameter("trip_id", "STRING", booking.trip_id),
        bigquery.ScalarQueryParameter(
            "sabre_confirmation_ref", "STRING", booking.sabre_confirmation_ref
        ),
        bigquery.ScalarQueryParameter("state", "STRING", booking.state),
        bigquery.ScalarQueryParameter("raw_response", "STRING", raw),
    ]
    success, _, error = bq_helper.run_dml(query, params)
    return success, booking if success else None, error


def get_booking(booking_id: str) -> Tuple[bool, Optional[Booking], Optional[str]]:
    """Fetch one booking. (True, None, None) means the query ran but no row."""
    query = f"SELECT * FROM `{_table()}` WHERE booking_id = @booking_id"
    params = [bigquery.ScalarQueryParameter("booking_id", "STRING", booking_id)]
    success, rows, error = bq_helper.run_select(query, params)
    if not success:
        return False, None, error
    models = rows_to_models(Booking, rows)
    return True, models[0] if models else None, None


def list_bookings_for_trip(trip_id: str) -> Tuple[bool, List[Booking], Optional[str]]:
    query = f"""
        SELECT * FROM `{_table()}`
        WHERE trip_id = @trip_id
        ORDER BY booked_at
    """
    params = [bigquery.ScalarQueryParameter("trip_id", "STRING", trip_id)]
    success, rows, error = bq_helper.run_select(query, params)
    if not success:
        return False, [], error
    return True, rows_to_models(Booking, rows), None


def update_state(booking_id: str, state: str) -> Tuple[bool, int, Optional[str]]:
    """Set a booking's state (pending/confirmed/cancelled).

    Raises pydantic ValidationError on a bad state. Returns
    (success, affected_rows, error) — affected_rows 0 means no such booking.
    """
    state = BOOKING_STATE_ADAPTER.validate_python(state)
    query = f"UPDATE `{_table()}` SET state = @state WHERE booking_id = @booking_id"
    params = [
        bigquery.ScalarQueryParameter("state", "STRING", state),
        bigquery.ScalarQueryParameter("booking_id", "STRING", booking_id),
    ]
    return bq_helper.run_dml(query, params)
