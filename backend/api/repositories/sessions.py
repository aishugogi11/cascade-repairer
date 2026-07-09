"""Repository for the sessions table."""
from typing import Optional, Tuple

from google.cloud import bigquery

from api.helpers.bigquery_helper import bq_helper
from api.repositories.models import Session, rows_to_models


def _table() -> str:
    return bq_helper.get_table_reference("sessions")


def create_session(session: Session) -> Tuple[bool, Optional[Session], Optional[str]]:
    """Insert a session; started_at is stamped by BigQuery."""
    query = f"""
        INSERT INTO `{_table()}`
            (session_id, trip_id, architecture, client, started_at, ended_at)
        VALUES
            (@session_id, @trip_id, @architecture, @client,
             CURRENT_TIMESTAMP(), NULL)
    """
    params = [
        bigquery.ScalarQueryParameter("session_id", "STRING", session.session_id),
        bigquery.ScalarQueryParameter("trip_id", "STRING", session.trip_id),
        bigquery.ScalarQueryParameter("architecture", "STRING", session.architecture),
        bigquery.ScalarQueryParameter("client", "STRING", session.client),
    ]
    success, _, error = bq_helper.run_dml(query, params)
    return success, session if success else None, error


def end_session(session_id: str) -> Tuple[bool, int, Optional[str]]:
    """Stamp ended_at. Returns (success, affected_rows, error) —
    affected_rows 0 means no such session."""
    query = f"""
        UPDATE `{_table()}`
        SET ended_at = CURRENT_TIMESTAMP()
        WHERE session_id = @session_id
    """
    params = [bigquery.ScalarQueryParameter("session_id", "STRING", session_id)]
    return bq_helper.run_dml(query, params)


def get_session(session_id: str) -> Tuple[bool, Optional[Session], Optional[str]]:
    """Fetch one session. (True, None, None) means the query ran but no row."""
    query = f"SELECT * FROM `{_table()}` WHERE session_id = @session_id"
    params = [bigquery.ScalarQueryParameter("session_id", "STRING", session_id)]
    success, rows, error = bq_helper.run_select(query, params)
    if not success:
        return False, None, error
    models = rows_to_models(Session, rows)
    return True, models[0] if models else None, None
