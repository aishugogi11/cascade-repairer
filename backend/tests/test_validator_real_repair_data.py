"""Independent-validator coverage for Phase 29 acceptance contracts."""

import asyncio
import base64
import json
import os
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, call

import pytest

from api import concurrency_core as core
from api import flight_options, itinerary_ui, repair_tools
from api.sabre import client as sabre_client
from api.sabre import shapes
from api.sabre.real_client import RealSabreClient


_CERT_BASE_URL = "https://api.cert.platform.sabre.com"


def _future_date(days_ahead):
    return (date.today() + timedelta(days=days_ahead)).isoformat()


def _basic_secret(user_id, password):
    encoded_user = base64.b64encode(user_id.encode()).decode()
    encoded_password = base64.b64encode(password.encode()).decode()
    return base64.b64encode(f"{encoded_user}:{encoded_password}".encode()).decode()


def _live_client(monkeypatch):
    user_id = os.environ.get("SABRE_API_USER_ID")
    password = os.environ.get("SABRE_API_SECRET")
    if not user_id or not password:
        pytest.skip("live validator checks need the raw Sabre credential pair")
    monkeypatch.setenv("SABRE_BASE_URL", _CERT_BASE_URL)
    monkeypatch.setenv("SABRE_CLIENT_SECRET", _basic_secret(user_id, password))
    monkeypatch.setenv("SABRE_MODE", "real")
    client = RealSabreClient()
    monkeypatch.setattr(sabre_client, "_real", client)
    monkeypatch.setattr(sabre_client._mock, "latency_seconds", 0)
    return client


async def _options(client, origin, destination, departure_date):
    response = await client.instaflights_search(
        shapes.InstaFlightsRequest(
            origin=origin,
            destination=destination,
            departuredate=departure_date,
        )
    )
    return response, flight_options._parse_instaflights_options(
        response, origin, destination
    )


async def _run_as_cascade_unit(monkeypatch, item_id, repair):
    status_write = MagicMock(return_value=(True, 1, None))
    monkeypatch.setattr(core.itinerary_items, "update_status", status_write)
    spec = core.RepairSpec(
        item_id=item_id,
        name="rebook_flight",
        duration_seconds=0.0,
    )

    async def do_repair(_spec):
        return await repair()

    result = await core._repair_one("validator-session", spec, do_repair)
    return result, status_write


def test_validator_real_mode_uses_mock_pnr_client_only(monkeypatch):
    """Only the re-shop may be real; cancel/create must use the mock client."""

    async def scenario():
        departure_date = (date.today() + timedelta(days=2)).isoformat()
        request = shapes.InstaFlightsRequest(
            origin="JFK", destination="LAX", departuredate=departure_date
        )

        monkeypatch.setenv("SABRE_MODE", "real")
        monkeypatch.setattr(sabre_client._mock, "latency_seconds", 0)

        mock_rebook = sabre_client._mock.rebook_flight
        real_search = AsyncMock(
            return_value=await sabre_client._mock.instaflights_search(request)
        )
        real_rebook = AsyncMock(side_effect=mock_rebook)
        mock_rebook_spy = AsyncMock(side_effect=mock_rebook)

        monkeypatch.setattr(sabre_client._real, "instaflights_search", real_search)
        monkeypatch.setattr(sabre_client._real, "rebook_flight", real_rebook)
        monkeypatch.setattr(sabre_client._mock, "rebook_flight", mock_rebook_spy)
        monkeypatch.setattr(
            repair_tools, "_latest_sabre_ref", AsyncMock(return_value="MOCKREF")
        )
        monkeypatch.setattr(
            repair_tools, "_write_booking", AsyncMock(return_value="b-1")
        )

        result = await repair_tools._rebook_flight(
            "trip-validator",
            "flight-validator",
            "JFK",
            "LAX",
            departure_date,
            original_price=500.0,
        )

        assert result["from_mock_fallback"] is False
        real_search.assert_awaited_once()
        real_rebook.assert_not_awaited()
        mock_rebook_spy.assert_awaited_once()

    asyncio.run(scenario())


def test_validator_empty_reshop_fallback_flips_fixed(monkeypatch, caplog):
    """An empty real re-shop must still complete the cascade's fixed flip."""

    async def scenario():
        departure_date = _future_date(2)
        monkeypatch.setenv("SABRE_MODE", "real")
        monkeypatch.setattr(sabre_client._mock, "latency_seconds", 0)
        monkeypatch.setattr(
            sabre_client._real,
            "instaflights_search",
            AsyncMock(return_value=shapes.InstaFlightsResponse(PricedItineraries=[])),
        )
        monkeypatch.setattr(
            sabre_client._real,
            "rebook_flight",
            AsyncMock(side_effect=RuntimeError("real PNR path blocked by validator")),
        )
        monkeypatch.setattr(
            repair_tools, "_latest_sabre_ref", AsyncMock(return_value="MOCKREF")
        )
        write = AsyncMock(return_value="b-empty")
        monkeypatch.setattr(repair_tools, "_write_booking", write)

        async def repair():
            return await repair_tools._rebook_flight(
                "trip-empty-validator",
                "flight-empty-validator",
                "SFO",
                "MIA",
                departure_date,
                original_price=300.0,
            )

        with caplog.at_level("WARNING"):
            result, status_write = await _run_as_cascade_unit(
                monkeypatch, "flight-empty-validator", repair
            )
        raw = write.await_args.args[3]

        assert result["from_mock_fallback"] is True
        assert raw["from_mock_fallback"] is True
        assert write.await_count == 1
        assert status_write.call_args_list == [
            call("flight-empty-validator", "repairing"),
            call("flight-empty-validator", "fixed"),
        ]
        assert f"SFO-MIA {departure_date}" in caplog.text

    asyncio.run(scenario())


@pytest.mark.cert
def test_validator_live_anchor_repair_uses_real_fares(monkeypatch):
    """Run the repair against live JFK-LAX shopping with PNR writes sandboxed."""

    async def scenario():
        client = _live_client(monkeypatch)
        live_date = None
        offered = []
        for days_ahead in (2, 7, 14, 21, 30):
            candidate_date = _future_date(days_ahead)
            _, offered = await _options(client, "JFK", "LAX", candidate_date)
            if offered:
                live_date = candidate_date
                break
        assert live_date is not None, "JFK-LAX was cache-empty at every probed date"

        original_mock_rebook = sabre_client._mock.rebook_flight
        safe_real_pnr = AsyncMock(side_effect=original_mock_rebook)
        mock_pnr = AsyncMock(side_effect=original_mock_rebook)
        monkeypatch.setattr(client, "rebook_flight", safe_real_pnr)
        monkeypatch.setattr(sabre_client._mock, "rebook_flight", mock_pnr)
        monkeypatch.setattr(
            repair_tools, "_latest_sabre_ref", AsyncMock(return_value="MOCKREF")
        )
        write = AsyncMock(return_value="b-live")
        monkeypatch.setattr(repair_tools, "_write_booking", write)

        cancelled = None
        if len(offered) > 1:
            cancelled = (offered[0].airline, offered[0].flight_number)
        result = await repair_tools._rebook_flight(
            "trip-live-validator",
            "flight-live-validator",
            "JFK",
            "LAX",
            live_date,
            original_price=offered[0].price,
            original_currency=offered[0].currency,
            original_arrive_time=offered[0].arrive_time,
            cancelled_flight=cancelled,
        )
        raw = write.await_args.args[3]
        detail = itinerary_ui._flight_repair_detail(raw)

        assert result["from_mock_fallback"] is False
        assert raw["from_mock_fallback"] is False
        assert detail["price_delta"] == itinerary_ui._signed_delta(
            result["price_delta"]
        )
        assert raw["option"]["flight_number"] in {
            option.flight_number for option in offered
        }
        if cancelled is not None:
            assert (result["airline"], result["flight_number"]) != cancelled
        assert safe_real_pnr.await_count + mock_pnr.await_count == 1
        pnr_route = (
            "real client intercepted to mock"
            if safe_real_pnr.await_count
            else "mock client"
        )
        print(
            json.dumps(
                {
                    "route": "JFK-LAX",
                    "date": live_date,
                    "offered": len(offered),
                    "chosen": {
                        "airline": result["airline"],
                        "flight_number": result["flight_number"],
                        "fare": result["price"],
                        "currency": result["currency"],
                    },
                    "from_mock_fallback": result["from_mock_fallback"],
                    "price_delta": result["price_delta"],
                    "detail": detail,
                    "cancelled": cancelled,
                    "pnr_write": pnr_route,
                },
                sort_keys=True,
            )
        )

    asyncio.run(scenario())


@pytest.mark.cert
def test_validator_live_empty_route_falls_back_without_stall(monkeypatch, caplog):
    """Find a live cache-empty route/date and observe the repair's fallback."""

    async def scenario():
        client = _live_client(monkeypatch)
        empty_case = None
        empty_response = None
        candidates = (
            ("SFO", "MIA"),
            ("SEA", "BOS"),
            ("DFW", "EWR"),
            ("JFK", "ORD"),
            ("MCO", "JFK"),
        )
        departure_date = _future_date(2)
        for origin, destination in candidates:
            response, offered = await _options(
                client, origin, destination, departure_date
            )
            if not offered:
                empty_case = (origin, destination)
                empty_response = response
                break
        assert empty_case is not None, "every candidate route returned live content"
        origin, destination = empty_case

        live_empty = AsyncMock(return_value=empty_response)
        monkeypatch.setattr(client, "instaflights_search", live_empty)
        original_mock_rebook = sabre_client._mock.rebook_flight
        safe_real_pnr = AsyncMock(side_effect=original_mock_rebook)
        mock_pnr = AsyncMock(side_effect=original_mock_rebook)
        monkeypatch.setattr(client, "rebook_flight", safe_real_pnr)
        monkeypatch.setattr(sabre_client._mock, "rebook_flight", mock_pnr)
        monkeypatch.setattr(
            repair_tools, "_latest_sabre_ref", AsyncMock(return_value="MOCKREF")
        )
        write = AsyncMock(return_value="b-empty")
        monkeypatch.setattr(repair_tools, "_write_booking", write)

        async def repair():
            return await repair_tools._rebook_flight(
                "trip-empty-validator",
                "flight-empty-validator",
                origin,
                destination,
                departure_date,
                original_price=300.0,
            )

        with caplog.at_level("WARNING"):
            result, status_write = await _run_as_cascade_unit(
                monkeypatch, "flight-empty-validator", repair
            )
        raw = write.await_args.args[3]

        assert result["from_mock_fallback"] is True
        assert raw["from_mock_fallback"] is True
        assert f"{origin}-{destination} {departure_date}" in caplog.text
        assert "using mock" in caplog.text
        assert safe_real_pnr.await_count + mock_pnr.await_count == 1
        assert status_write.call_args_list == [
            call("flight-empty-validator", "repairing"),
            call("flight-empty-validator", "fixed"),
        ]
        print(
            json.dumps(
                {
                    "route": f"{origin}-{destination}",
                    "date": departure_date,
                    "from_mock_fallback": result["from_mock_fallback"],
                    "booking_write": write.await_count,
                    "warning_observed": True,
                    "status_transitions": ["repairing", "fixed"],
                    "pnr_write": (
                        "real client intercepted to mock"
                        if safe_real_pnr.await_count
                        else "mock client"
                    ),
                },
                sort_keys=True,
            )
        )

    asyncio.run(scenario())
