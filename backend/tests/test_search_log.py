"""Phase 23 tests — the Sabre live-search log (ring buffer + endpoint).

Hermetic: the mock client serves the searches, the real client is
monkeypatched where a real-mode path is exercised, no network. Recording
is best-effort by contract — it can never break a search — and only search
operations land in the ring (bookings are writes, not searches).
"""
import asyncio

from fastapi.testclient import TestClient

import main
from api.sabre import client as sabre_client
from api.sabre import shapes

client = TestClient(main.app)


def setup_function():
    sabre_client._SEARCH_LOG.clear()


def _search(origin="JFK", destination="LAX", date="2026-08-14"):
    return asyncio.run(
        sabre_client.instaflights_search(
            shapes.InstaFlightsRequest(
                origin=origin, destination=destination, departuredate=date
            )
        )
    )


def test_mock_search_is_recorded_newest_first(monkeypatch):
    monkeypatch.delenv("SABRE_MODE", raising=False)
    _search("JFK", "LAX")
    _search("SFO", "MIA")

    log = sabre_client.search_log()
    assert len(log) == 2
    assert log[0]["route"] == "SFO → MIA"  # newest first
    assert log[1]["route"] == "JFK → LAX"
    entry = log[0]
    assert entry["op"] == "instaflights_search"
    assert entry["mode"] == "mock"
    assert entry["outcome"].endswith("fares")  # the mock's deterministic set
    assert entry["date"] == "2026-08-14"
    assert entry["at"]


def test_real_mode_failure_records_a_fallback_entry(monkeypatch):
    monkeypatch.setenv("SABRE_MODE", "real")

    async def broken(request):
        raise RuntimeError("sandbox flaked")

    monkeypatch.setattr(sabre_client._real, "instaflights_search", broken)
    response = _search("JFK", "LAX")
    assert response.PricedItineraries  # the mock still served the caller

    log = sabre_client.search_log()
    assert len(log) == 1
    assert log[0]["mode"] == "fallback"


def test_booking_operations_are_not_recorded(monkeypatch):
    monkeypatch.delenv("SABRE_MODE", raising=False)
    asyncio.run(
        sabre_client.cancel_booking(
            shapes.CancelBookingRequest(confirmationId="GHI789")
        )
    )
    assert sabre_client.search_log() == []


def test_ring_is_bounded():
    for i in range(30):
        _search("JFK", "LAX", f"2026-08-{(i % 28) + 1:02d}")
    assert len(sabre_client.search_log()) == 25


def test_endpoint_serves_the_log_and_is_gated(monkeypatch):
    monkeypatch.delenv("DEMO_ACCESS_CODE", raising=False)  # fail-open locally
    _search("JFK", "LAX")
    resp = client.get("/v1/sabre_tools/search_log")
    assert resp.status_code == 200
    searches = resp.json()["searches"]
    assert searches[0]["route"] == "JFK → LAX"

    monkeypatch.setenv("DEMO_ACCESS_CODE", "code-1234")
    assert client.get("/v1/sabre_tools/search_log").status_code == 401
    ok = client.get(
        "/v1/sabre_tools/search_log", headers={"X-Access-Code": "code-1234"}
    )
    assert ok.status_code == 200
