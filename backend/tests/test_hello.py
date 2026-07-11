"""Phase 1 smoke tests.

These run inside the built container in Cloud Build (no GCP credentials, no
OPENAI_API_KEY), so they double as the proof that the app boots hermetically.
"""
from fastapi.testclient import TestClient

import main

client = TestClient(main.app)


def test_hello_world_returns_200():
    resp = client.get("/v1/hello/hello_world")
    assert resp.status_code == 200


def test_hello_world_body():
    body = client.get("/v1/hello/hello_world").json()
    assert body["message"].startswith("Hello, World!")


def test_expected_routes_registered():
    paths = main.app.openapi()["paths"]
    assert "/v1/hello/hello_world" in paths
    assert "/v1/itinerary/status/{trip_id}" in paths
    assert "/v1/itinerary/trips" in paths
    assert "/v1/legal/privacy" in paths
    assert "/v1/legal/support" in paths
    assert "/v1/mobile_voice/" in paths
