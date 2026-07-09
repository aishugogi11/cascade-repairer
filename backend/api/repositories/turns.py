"""Repository for the turns table, plus the audio GCS path convention."""
from typing import List, Optional, Tuple

from google.cloud import bigquery

from api.helpers.bigquery_helper import bq_helper
from api.helpers.gcs_helper import gcs_helper
from api.repositories.models import Turn, rows_to_models


def _table() -> str:
    return bq_helper.get_table_reference("turns")


def audio_uri_for(session_id: str, turn_id: str) -> str:
    """The audio artifact convention: audio/<session_id>/<turn_id>.wav in the
    configured audio bucket."""
    return f"gs://{gcs_helper.bucket_name}/audio/{session_id}/{turn_id}.wav"


def create_turn(turn: Turn) -> Tuple[bool, Optional[Turn], Optional[str]]:
    """Insert a turn; started_at defaults to insert time when not provided."""
    query = f"""
        INSERT INTO `{_table()}`
            (turn_id, session_id, role, transcript, audio_gcs_uri,
             started_at, ttfb_ms, duration_ms)
        VALUES
            (@turn_id, @session_id, @role, @transcript, @audio_gcs_uri,
             COALESCE(@started_at, CURRENT_TIMESTAMP()), @ttfb_ms, @duration_ms)
    """
    params = [
        bigquery.ScalarQueryParameter("turn_id", "STRING", turn.turn_id),
        bigquery.ScalarQueryParameter("session_id", "STRING", turn.session_id),
        bigquery.ScalarQueryParameter("role", "STRING", turn.role),
        bigquery.ScalarQueryParameter("transcript", "STRING", turn.transcript),
        bigquery.ScalarQueryParameter("audio_gcs_uri", "STRING", turn.audio_gcs_uri),
        bigquery.ScalarQueryParameter("started_at", "TIMESTAMP", turn.started_at),
        bigquery.ScalarQueryParameter("ttfb_ms", "INT64", turn.ttfb_ms),
        bigquery.ScalarQueryParameter("duration_ms", "INT64", turn.duration_ms),
    ]
    success, _, error = bq_helper.run_dml(query, params)
    return success, turn if success else None, error


def list_turns_for_session(session_id: str) -> Tuple[bool, List[Turn], Optional[str]]:
    query = f"""
        SELECT * FROM `{_table()}`
        WHERE session_id = @session_id
        ORDER BY started_at
    """
    params = [bigquery.ScalarQueryParameter("session_id", "STRING", session_id)]
    success, rows, error = bq_helper.run_select(query, params)
    if not success:
        return False, [], error
    return True, rows_to_models(Turn, rows), None
