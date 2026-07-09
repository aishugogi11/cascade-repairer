"""Tests for the BigQuery helper's query primitives.

The client is mocked at the helper boundary — no GCP credentials, no network.
"""
from unittest.mock import MagicMock

import pytest
from google.cloud import bigquery

from api.helpers.bigquery_helper import TABLE_IDS, TABLE_NAMES, BigQueryHelper


@pytest.fixture
def helper():
    h = BigQueryHelper()
    h._client = MagicMock()
    return h


def test_client_is_lazy():
    """Importing/constructing the helper must not build a GCP client — this is
    what keeps the suite runnable with no credentials."""
    h = BigQueryHelper()
    assert h._client is None


def test_config_declares_all_six_table_ids():
    """config.yaml metadata must carry a <name>_table_id for every table —
    the same entries drive CI table creation (run_artifact_setup.sh), so a
    missing one means the deploy stops creating that table."""
    assert set(TABLE_NAMES) == {
        "trips", "itinerary_items", "bookings", "sessions", "turns", "eval_runs",
    }
    assert set(TABLE_IDS) == set(TABLE_NAMES)
    assert all(TABLE_IDS.values())


def test_get_table_reference_resolves_configured_table_ids():
    h = BigQueryHelper()
    for name in TABLE_NAMES:
        assert h.get_table_reference(name) == (
            f"{h.project_id}.{h.dataset_id}.{TABLE_IDS[name]}"
        )
    # Unknown names pass through unchanged.
    assert h.get_table_reference("mystery").endswith(".mystery")


def test_get_table_reference_honors_env_override(monkeypatch):
    monkeypatch.setenv("TRIPS_TABLE_ID", "trips_smoke_test")
    h = BigQueryHelper()
    assert h.get_table_reference("trips").endswith(".trips_smoke_test")


def test_run_select_without_params_passes_no_job_config(helper):
    row = MagicMock()
    row.items.return_value = [("a", 1)]
    helper._client.query.return_value.result.return_value = [row]

    success, rows, error = helper.run_select("SELECT a FROM t")

    assert success is True
    assert rows == [{"a": 1}]
    assert error is None
    helper._client.query.assert_called_once_with("SELECT a FROM t", job_config=None)


def test_run_select_with_params_passes_query_parameters(helper):
    helper._client.query.return_value.result.return_value = []
    params = [bigquery.ScalarQueryParameter("trip_id", "STRING", "t-1")]

    success, rows, error = helper.run_select(
        "SELECT * FROM t WHERE trip_id = @trip_id", params
    )

    assert success is True
    assert rows == []
    job_config = helper._client.query.call_args.kwargs["job_config"]
    assert job_config.query_parameters == params


def test_run_select_returns_error_tuple_on_exception(helper):
    helper._client.query.side_effect = Exception("boom")

    success, rows, error = helper.run_select("SELECT 1")

    assert success is False
    assert rows == []
    assert "boom" in error


def test_run_dml_executes_and_waits(helper):
    job = helper._client.query.return_value
    job.num_dml_affected_rows = 1
    params = [bigquery.ScalarQueryParameter("status", "STRING", "fixed")]

    success, affected, error = helper.run_dml(
        "UPDATE t SET status = @status WHERE id = @id", params
    )

    assert success is True
    assert affected == 1
    assert error is None
    job.result.assert_called_once()  # waits for completion
    job_config = helper._client.query.call_args.kwargs["job_config"]
    assert job_config.query_parameters == params


def test_run_dml_reports_zero_affected_rows(helper):
    job = helper._client.query.return_value
    job.num_dml_affected_rows = 0

    success, affected, error = helper.run_dml("UPDATE t SET a = 1 WHERE FALSE")

    assert success is True
    assert affected == 0
    assert error is None


def test_run_dml_returns_error_tuple_on_exception(helper):
    helper._client.query.side_effect = Exception("dml boom")

    success, affected, error = helper.run_dml("INSERT INTO t VALUES (1)")

    assert success is False
    assert affected == 0
    assert "dml boom" in error
