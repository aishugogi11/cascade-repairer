"""Independent-validator coverage for Phase 32 acceptance gaps.

These tests deliberately exercise behavior that the implementer suite only
covered at the repair-tool boundary: cascade error propagation for a failed
field write, and every field written by the empty-real-search mock fallback.
"""
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from zoneinfo import ZoneInfo

import pytest

from api import concurrency_core as core
from api import flight_options, repair_tools, sabre_tools
from api.repositories.models import ItineraryItem
from api.sabre import client as sabre_client
from api.sabre import shapes


_PACIFIC = ZoneInfo("America/Los_Angeles")


@pytest.fixture(autouse=True)
def isolated_repair_state(monkeypatch):
    monkeypatch.delenv("SABRE_MODE", raising=False)
    monkeypatch.setattr(sabre_client._mock, "latency_seconds", 0)
    core._SESSIONS.clear()
    yield
    core._SESSIONS.clear()


def test_validator_field_write_failure_records_error_without_fixed(monkeypatch):
    """A Phase 32 field-write failure must stop before the fixed transition."""
    statuses = []

    def update_status(item_id, status):
        statuses.append((item_id, status))
        return True, 1, None

    monkeypatch.setattr(core.itinerary_items, "update_status", update_status)
    monkeypatch.setattr(
        repair_tools, "_latest_sabre_ref", AsyncMock(return_value="OLDPNR")
    )
    monkeypatch.setattr(
        repair_tools, "_write_booking", AsyncMock(return_value="booking-validator")
    )
    monkeypatch.setattr(
        repair_tools.itinerary_items,
        "update_flight_fields",
        MagicMock(return_value=(False, 0, "quota exceeded")),
    )

    item = ItineraryItem(
        item_id="flight-validator",
        trip_id="trip-validator",
        type="flight",
        status="broken",
        provider="sabre",
        location="MSP-SFO",
        start_ts=datetime(2026, 7, 17, 8, 0, tzinfo=_PACIFIC),
        end_ts=datetime(2026, 7, 17, 12, 5, tzinfo=_PACIFIC),
        details={"airline": "AA", "flight_number": 100},
        price=385.0,
        currency="USD",
    )

    async def scenario():
        _, tasks = sabre_tools.launch_trip_repairs(
            "phase32-validator-failure", [item]
        )
        await asyncio.gather(*tasks)
        return core.get_session("phase32-validator-failure")

    session = asyncio.run(scenario())

    assert statuses == [("flight-validator", "repairing")]
    assert len(session.events) == 1
    assert session.events[0].status == "error"
    assert "flight field write failed" in session.events[0].error


def test_validator_mock_fallback_rewrites_every_flight_field(monkeypatch):
    """An honest-empty real search must rewrite all fields from its mock option."""
    monkeypatch.setenv("SABRE_MODE", "real")

    async def empty_search(_request):
        return shapes.InstaFlightsResponse(PricedItineraries=[])

    monkeypatch.setattr(sabre_client._real, "instaflights_search", empty_search)
    monkeypatch.setattr(
        repair_tools, "_latest_sabre_ref", AsyncMock(return_value="OLDPNR")
    )
    write_booking = AsyncMock(return_value="booking-validator")
    monkeypatch.setattr(repair_tools, "_write_booking", write_booking)
    field_write = MagicMock(return_value=(True, 1, None))
    monkeypatch.setattr(
        repair_tools.itinerary_items, "update_flight_fields", field_write
    )

    result = asyncio.run(
        repair_tools._rebook_flight(
            "trip-validator",
            "flight-validator",
            "MSP",
            "SFO",
            "2026-07-17",
            original_price=385.0,
            original_currency="USD",
            original_depart_time="08:00",
            original_arrive_time="12:05",
            cancelled_flight=("AA", 100),
        )
    )

    raw_response = write_booking.await_args.args[3]
    chosen = flight_options.FlightOption(**raw_response["option"])
    expected_start, expected_end = flight_options.option_timestamps(chosen)
    written = field_write.call_args.kwargs

    assert result["from_mock_fallback"] is True
    assert written["start_ts"] == expected_start
    assert written["end_ts"] == expected_end
    assert written["price"] == chosen.price
    assert written["currency"] == chosen.currency
    assert written["details"]["airline"] == chosen.airline
    assert written["details"]["flight_number"] == chosen.flight_number
    assert written["details"]["rebooked_from"] == raw_response["rebooked_from"]
