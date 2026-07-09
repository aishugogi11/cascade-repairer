"""Unit tests for /v1/hello/gcp_check with mocked GCP clients (hermetic CI)."""
from fastapi.testclient import TestClient

import main
from api.helpers.bigquery_helper import bq_helper
from api.helpers.gcs_helper import gcs_helper

client = TestClient(main.app)


def test_gcp_check_all_ok(monkeypatch):
    monkeypatch.setattr(bq_helper, "run_select", lambda query: (True, [{"ping": 1}], None))
    monkeypatch.setattr(gcs_helper, "list_files", lambda prefix="": (True, [], None))

    resp = client.get("/v1/hello/gcp_check")
    assert resp.status_code == 200
    body = resp.json()
    assert body["bigquery"]["status"] == "ok"
    assert body["gcs"]["status"] == "ok"


def test_gcp_check_bigquery_failure_is_reported_not_500(monkeypatch):
    monkeypatch.setattr(
        bq_helper, "run_select", lambda query: (False, [], "dataset not found")
    )
    monkeypatch.setattr(gcs_helper, "list_files", lambda prefix="": (True, [], None))

    resp = client.get("/v1/hello/gcp_check")
    assert resp.status_code == 200
    body = resp.json()
    assert body["bigquery"]["status"] == "error"
    assert "dataset not found" in body["bigquery"]["detail"]
    assert body["gcs"]["status"] == "ok"


def test_gcp_check_gcs_failure_is_reported_not_500(monkeypatch):
    monkeypatch.setattr(bq_helper, "run_select", lambda query: (True, [{"ping": 1}], None))
    monkeypatch.setattr(
        gcs_helper, "list_files", lambda prefix="": (False, [], "bucket not found")
    )

    resp = client.get("/v1/hello/gcp_check")
    assert resp.status_code == 200
    body = resp.json()
    assert body["bigquery"]["status"] == "ok"
    assert body["gcs"]["status"] == "error"
    assert "bucket not found" in body["gcs"]["detail"]
