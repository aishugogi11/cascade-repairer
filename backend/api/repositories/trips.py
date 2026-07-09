"""Repository for the trips table."""
from typing import List, Optional, Tuple

from google.cloud import bigquery

from api.helpers.bigquery_helper import bq_helper
from api.repositories.models import (
    TRIP_STATUS_ADAPTER,
    ItineraryItem,
    Trip,
    TripWithItems,
    rows_to_models,
)


def _table() -> str:
    return bq_helper.get_table_reference("trips")


def create_trip(trip: Trip) -> Tuple[bool, Optional[Trip], Optional[str]]:
    """Insert a trip; created_at is stamped by BigQuery. Returns the trip."""
    query = f"""
        INSERT INTO `{_table()}`
            (trip_id, user_id, title, status, origin, destinations,
             start_date, end_date, created_at)
        VALUES
            (@trip_id, @user_id, @title, @status, @origin, @destinations,
             @start_date, @end_date, CURRENT_TIMESTAMP())
    """
    params = [
        bigquery.ScalarQueryParameter("trip_id", "STRING", trip.trip_id),
        bigquery.ScalarQueryParameter("user_id", "STRING", trip.user_id),
        bigquery.ScalarQueryParameter("title", "STRING", trip.title),
        bigquery.ScalarQueryParameter("status", "STRING", trip.status),
        bigquery.ScalarQueryParameter("origin", "STRING", trip.origin),
        bigquery.ArrayQueryParameter("destinations", "STRING", trip.destinations),
        bigquery.ScalarQueryParameter("start_date", "DATE", trip.start_date),
        bigquery.ScalarQueryParameter("end_date", "DATE", trip.end_date),
    ]
    success, _, error = bq_helper.run_dml(query, params)
    return success, trip if success else None, error


def get_trip(trip_id: str) -> Tuple[bool, Optional[Trip], Optional[str]]:
    """Fetch one trip. (True, None, None) means the query ran but no row."""
    query = f"SELECT * FROM `{_table()}` WHERE trip_id = @trip_id"
    params = [bigquery.ScalarQueryParameter("trip_id", "STRING", trip_id)]
    success, rows, error = bq_helper.run_select(query, params)
    if not success:
        return False, None, error
    models = rows_to_models(Trip, rows)
    return True, models[0] if models else None, None


def list_recent_trips(limit: int = 10) -> Tuple[bool, List[Trip], Optional[str]]:
    """Most recent trips, newest first — backs the itinerary UI trip selector."""
    query = f"""
        SELECT * FROM `{_table()}`
        ORDER BY created_at DESC
        LIMIT @limit
    """
    params = [bigquery.ScalarQueryParameter("limit", "INT64", limit)]
    success, rows, error = bq_helper.run_select(query, params)
    if not success:
        return False, [], error
    return True, rows_to_models(Trip, rows), None


def update_trip_status(trip_id: str, status: str) -> Tuple[bool, int, Optional[str]]:
    """Set a trip's status. Raises pydantic ValidationError on a bad status.

    Returns (success, affected_rows, error) — affected_rows 0 means no such
    trip (a no-op, not an error).
    """
    status = TRIP_STATUS_ADAPTER.validate_python(status)
    query = f"UPDATE `{_table()}` SET status = @status WHERE trip_id = @trip_id"
    params = [
        bigquery.ScalarQueryParameter("status", "STRING", status),
        bigquery.ScalarQueryParameter("trip_id", "STRING", trip_id),
    ]
    return bq_helper.run_dml(query, params)


def get_trip_with_items(
    trip_id: str,
) -> Tuple[bool, Optional[TripWithItems], Optional[str]]:
    """The unified trip view: the trip plus all its itinerary items ordered by
    start_ts — the read the live itinerary UI polls."""
    success, trip, error = get_trip(trip_id)
    if not success or trip is None:
        return success, None, error
    items_table = bq_helper.get_table_reference("itinerary_items")
    query = f"""
        SELECT * FROM `{items_table}`
        WHERE trip_id = @trip_id
        ORDER BY start_ts
    """
    params = [bigquery.ScalarQueryParameter("trip_id", "STRING", trip_id)]
    success, rows, error = bq_helper.run_select(query, params)
    if not success:
        return False, None, error
    return True, TripWithItems(trip=trip, items=rows_to_models(ItineraryItem, rows)), None
