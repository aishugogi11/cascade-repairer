"""Repository for the eval_runs table."""
from typing import List, Optional, Tuple

from google.cloud import bigquery

from api.helpers.bigquery_helper import bq_helper
from api.repositories.models import EvalRun, rows_to_models


def _table() -> str:
    return bq_helper.get_table_reference("eval_runs")


def create_run(run: EvalRun) -> Tuple[bool, Optional[EvalRun], Optional[str]]:
    """Insert an eval run; run_at defaults to insert time when not provided."""
    query = f"""
        INSERT INTO `{_table()}`
            (run_id, architecture, git_sha, scenario, ttfb_ms, e2e_latency_ms,
             wer, mos_estimate, notes, run_at)
        VALUES
            (@run_id, @architecture, @git_sha, @scenario, @ttfb_ms,
             @e2e_latency_ms, @wer, @mos_estimate, @notes,
             COALESCE(@run_at, CURRENT_TIMESTAMP()))
    """
    params = [
        bigquery.ScalarQueryParameter("run_id", "STRING", run.run_id),
        bigquery.ScalarQueryParameter("architecture", "STRING", run.architecture),
        bigquery.ScalarQueryParameter("git_sha", "STRING", run.git_sha),
        bigquery.ScalarQueryParameter("scenario", "STRING", run.scenario),
        bigquery.ScalarQueryParameter("ttfb_ms", "FLOAT64", run.ttfb_ms),
        bigquery.ScalarQueryParameter("e2e_latency_ms", "FLOAT64", run.e2e_latency_ms),
        bigquery.ScalarQueryParameter("wer", "FLOAT64", run.wer),
        bigquery.ScalarQueryParameter("mos_estimate", "FLOAT64", run.mos_estimate),
        bigquery.ScalarQueryParameter("notes", "STRING", run.notes),
        bigquery.ScalarQueryParameter("run_at", "TIMESTAMP", run.run_at),
    ]
    success, _, error = bq_helper.run_dml(query, params)
    return success, run if success else None, error


def list_runs(
    architecture: Optional[str] = None, scenario: Optional[str] = None
) -> Tuple[bool, List[EvalRun], Optional[str]]:
    """List eval runs, optionally filtered by architecture and/or scenario."""
    conditions = []
    params = []
    if architecture is not None:
        conditions.append("architecture = @architecture")
        params.append(
            bigquery.ScalarQueryParameter("architecture", "STRING", architecture)
        )
    if scenario is not None:
        conditions.append("scenario = @scenario")
        params.append(bigquery.ScalarQueryParameter("scenario", "STRING", scenario))
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM `{_table()}` {where} ORDER BY run_at DESC"
    success, rows, error = bq_helper.run_select(query, params or None)
    if not success:
        return False, [], error
    return True, rows_to_models(EvalRun, rows), None
