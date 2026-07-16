"""Repository for the itinerary_items table.

`update_status` is the cascade's write path: every transition (booked →
broken → repairing → fixed) is a DML UPDATE that also stamps updated_at, so
the live itinerary UI sees each flip immediately.
"""
import json
from typing import List, Optional, Tuple

from google.cloud import bigquery

from api.helpers.bigquery_helper import bq_helper
from api.repositories.models import (
    ITEM_STATUS_ADAPTER,
    ItineraryItem,
    rows_to_models,
)


def _table() -> str:
    return bq_helper.get_table_reference("itinerary_items")


def create_item(item: ItineraryItem) -> Tuple[bool, Optional[ItineraryItem], Optional[str]]:
    """Insert an itinerary item; updated_at is stamped by BigQuery."""
    query = f"""
        INSERT INTO `{_table()}`
            (item_id, trip_id, type, status, provider, provider_ref,
             start_ts, end_ts, location, details, price, currency, updated_at)
        VALUES
            (@item_id, @trip_id, @type, @status, @provider, @provider_ref,
             @start_ts, @end_ts, @location, PARSE_JSON(@details), @price,
             @currency, CURRENT_TIMESTAMP())
    """
    details = json.dumps(item.details) if item.details is not None else None
    params = [
        bigquery.ScalarQueryParameter("item_id", "STRING", item.item_id),
        bigquery.ScalarQueryParameter("trip_id", "STRING", item.trip_id),
        bigquery.ScalarQueryParameter("type", "STRING", item.type),
        bigquery.ScalarQueryParameter("status", "STRING", item.status),
        bigquery.ScalarQueryParameter("provider", "STRING", item.provider),
        bigquery.ScalarQueryParameter("provider_ref", "STRING", item.provider_ref),
        bigquery.ScalarQueryParameter("start_ts", "TIMESTAMP", item.start_ts),
        bigquery.ScalarQueryParameter("end_ts", "TIMESTAMP", item.end_ts),
        bigquery.ScalarQueryParameter("location", "STRING", item.location),
        bigquery.ScalarQueryParameter("details", "STRING", details),
        bigquery.ScalarQueryParameter("price", "FLOAT64", item.price),
        bigquery.ScalarQueryParameter("currency", "STRING", item.currency),
    ]
    success, _, error = bq_helper.run_dml(query, params)
    return success, item if success else None, error


def get_item(item_id: str) -> Tuple[bool, Optional[ItineraryItem], Optional[str]]:
    """Fetch one item. (True, None, None) means the query ran but no row."""
    query = f"SELECT * FROM `{_table()}` WHERE item_id = @item_id"
    params = [bigquery.ScalarQueryParameter("item_id", "STRING", item_id)]
    success, rows, error = bq_helper.run_select(query, params)
    if not success:
        return False, None, error
    models = rows_to_models(ItineraryItem, rows)
    return True, models[0] if models else None, None


def list_items_for_trip(
    trip_id: str,
) -> Tuple[bool, List[ItineraryItem], Optional[str]]:
    query = f"""
        SELECT * FROM `{_table()}`
        WHERE trip_id = @trip_id
        ORDER BY start_ts
    """
    params = [bigquery.ScalarQueryParameter("trip_id", "STRING", trip_id)]
    success, rows, error = bq_helper.run_select(query, params)
    if not success:
        return False, [], error
    return True, rows_to_models(ItineraryItem, rows), None


def update_flight_fields(
    item_id: str,
    *,
    start_ts,
    end_ts,
    price: float,
    currency: str,
    details: Optional[dict],
) -> Tuple[bool, int, Optional[str]]:
    """Rewrite a flight item's display fields after a repair rebooks it
    (Phase 32) — the cascade page renders exactly this row, so the rebooked
    flight's times/price/identity must land here or the card keeps showing
    the cancelled flight. Stamps updated_at like every lifecycle write.

    Returns (success, affected_rows, error) — affected_rows 0 means no such
    item (a no-op, not an error; the caller decides whether that's fatal).
    """
    query = f"""
        UPDATE `{_table()}`
        SET start_ts = @start_ts, end_ts = @end_ts, price = @price,
            currency = @currency, details = PARSE_JSON(@details),
            updated_at = CURRENT_TIMESTAMP()
        WHERE item_id = @item_id
    """
    params = [
        bigquery.ScalarQueryParameter("start_ts", "TIMESTAMP", start_ts),
        bigquery.ScalarQueryParameter("end_ts", "TIMESTAMP", end_ts),
        bigquery.ScalarQueryParameter("price", "FLOAT64", price),
        bigquery.ScalarQueryParameter("currency", "STRING", currency),
        bigquery.ScalarQueryParameter(
            "details", "STRING",
            json.dumps(details) if details is not None else None,
        ),
        bigquery.ScalarQueryParameter("item_id", "STRING", item_id),
    ]
    return bq_helper.run_dml(query, params)


def update_status(item_id: str, status: str) -> Tuple[bool, int, Optional[str]]:
    """Transition an item through the repair lifecycle, stamping updated_at.

    Raises pydantic ValidationError on a status outside
    planned/booked/broken/repairing/fixed/cancelled. Returns
    (success, affected_rows, error) — affected_rows 0 means no such item
    (a no-op, not an error).
    """
    status = ITEM_STATUS_ADAPTER.validate_python(status)
    query = f"""
        UPDATE `{_table()}`
        SET status = @status, updated_at = CURRENT_TIMESTAMP()
        WHERE item_id = @item_id
    """
    params = [
        bigquery.ScalarQueryParameter("status", "STRING", status),
        bigquery.ScalarQueryParameter("item_id", "STRING", item_id),
    ]
    return bq_helper.run_dml(query, params)
