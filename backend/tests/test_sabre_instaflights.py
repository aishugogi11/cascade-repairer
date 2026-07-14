"""Phase 27 tests — real Sabre search in the demo path, hermetic.

No network, no credentials: the real client runs against a mocked httpx
transport, the dispatcher against the deterministic mock, and the concierge
flow against both. The load-bearing contracts: InstaFlights times are
airport-local and must arrive Pacific-converted in FlightOption (the Phase 19
bug class), a red-eye's PT arrival date shifts end_ts forward, unmapped
airports are skipped rather than mangled, `onlineitinerariesonly=N` is
unconditional (Y = CERT 500), the per-call mock fallback stays silent, and
the Phase 21 pending_options payload shape is byte-for-byte unchanged.

Travel dates are computed (the Phase 26 rule), never literals. The repo pins
no pytest-asyncio, so async scenarios run via asyncio.run() inside sync
tests (the test_sabre_client.py convention).
"""
import asyncio
import logging
from datetime import date, timedelta
from zoneinfo import ZoneInfo

import httpx
import pytest

from api import concierge
from api.sabre import client, shapes
from api.sabre.airport_tz import airport_zone
from api.sabre.mock_client import MockSabreClient
from api.sabre.real_client import RealSabreClient

_DEPART = date.today() + timedelta(days=21)
_DAY = _DEPART.isoformat()
_NEXT_DAY = (_DEPART + timedelta(days=1)).isoformat()


def _segment(dep_airport, arr_airport, dep_dt, arr_dt, flight="439",
             airline="DL", stops=0):
    """One FlightSegment in the captured CERT shape (booking_lifecycle.py):
    FlightNumber and money arrive as strings, times carry no offset."""
    return {
        "DepartureAirport": {"LocationCode": dep_airport},
        "ArrivalAirport": {"LocationCode": arr_airport},
        "DepartureDateTime": dep_dt,
        "ArrivalDateTime": arr_dt,
        "FlightNumber": flight,
        "MarketingAirline": {"Code": airline},
        "StopQuantity": stops,
        "ResBookDesigCode": "E",  # extra field — must be tolerated
    }


def _itinerary(segments, amount):
    return {
        "AirItinerary": {
            "OriginDestinationOptions": {
                "OriginDestinationOption": [{"FlightSegment": segments}]
            },
            "DirectionInd": "OneWay",  # extra field — must be tolerated
        },
        "AirItineraryPricingInfo": {
            "ItinTotalFare": {
                "TotalFare": {"Amount": amount, "CurrencyCode": "USD"}
            }
        },
    }


def instaflights_payload():
    """Captured-shape response, computed future dates: a JFK 7:20 AM
    departure (the 04:20 PT conversion case), a red-eye whose PT arrival
    lands the next calendar day, an itinerary touching an airport absent
    from the timezone table, and a two-segment connection that must take
    the skipped itinerary's slot."""
    return {
        "PricedItineraries": [
            _itinerary(
                [_segment("JFK", "LAX", f"{_DAY}T07:20:00",
                          f"{_DAY}T10:35:00")],
                "260.60",
            ),
            _itinerary(
                [_segment("JFK", "LAX", f"{_DAY}T21:00:00",
                          f"{_NEXT_DAY}T00:30:00", flight="1187",
                          airline="UA")],
                "189.20",
            ),
            _itinerary(
                [_segment("XXQ", "LAX", f"{_DAY}T09:00:00",
                          f"{_DAY}T11:10:00", flight="77")],
                "99.00",
            ),
            _itinerary(
                [
                    _segment("JFK", "ORD", f"{_DAY}T08:00:00",
                             f"{_DAY}T09:40:00", flight="212", airline="AA"),
                    _segment("ORD", "LAX", f"{_DAY}T10:45:00",
                             f"{_DAY}T13:05:00", flight="213", airline="AA"),
                ],
                "205.40",
            ),
        ]
    }


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.delenv("SABRE_MODE", raising=False)
    monkeypatch.setattr(client._mock, "latency_seconds", 0)
    monkeypatch.setattr(concierge, "_SESSION_FLIGHT_OPTIONS", {})
    monkeypatch.setattr(concierge, "_SESSION_TRIPS", {})
    monkeypatch.setattr(concierge, "_LATEST_SEARCH", None)


# --- shapes & airport timezone table --------------------------------------------


def test_captured_shape_validates_and_tolerates_extras():
    response = shapes.InstaFlightsResponse.model_validate(instaflights_payload())
    assert len(response.PricedItineraries) == 4
    seg = (response.PricedItineraries[0].AirItinerary.OriginDestinationOptions
           .OriginDestinationOption[0].FlightSegment[0])
    assert seg.FlightNumber == 439  # string "439" coerced
    fare = response.PricedItineraries[0].AirItineraryPricingInfo.ItinTotalFare
    assert fare.TotalFare.Amount == 260.60  # string "260.60" coerced


def test_supported_markets_shape_validates():
    payload = {
        "OriginDestinationLocations": [
            {
                "OriginLocation": {"AirportCode": "SFO", "CityName": "San Francisco"},
                "DestinationLocation": {"AirportCode": "JFK", "CityName": "New York"},
            }
        ],
        "Links": [],  # extra field — must be tolerated
    }
    response = shapes.SupportedMarketsResponse.model_validate(payload)
    assert response.OriginDestinationLocations[0].OriginLocation.AirportCode == "SFO"


def test_airport_zone_lookup():
    assert airport_zone("JFK") == ZoneInfo("America/New_York")
    assert airport_zone(" lax ") == ZoneInfo("America/Los_Angeles")
    assert airport_zone("PHX") == ZoneInfo("America/Phoenix")
    assert airport_zone("XXQ") is None
    assert airport_zone("") is None


# --- the parser: airport-local -> Pacific, red-eye, skip-not-mangle -------------


def _parsed_options():
    response = shapes.InstaFlightsResponse.model_validate(instaflights_payload())
    return concierge._parse_instaflights_options(response, "JFK", "LAX")


def test_parser_converts_airport_local_to_pacific():
    """07:20 at JFK is 04:20 PT — not 07:20 mis-declared Pacific (the
    Phase 19 bug class). Arrival is localized at the *destination*: 10:35
    at LAX is already Pacific wall clock."""
    option = _parsed_options()[0]
    assert option.depart_time == "04:20"
    assert option.depart_date == _DAY
    assert option.arrive_time == "10:35"
    assert option.arrive_date == _DAY


def test_parser_red_eye_shifts_the_pt_arrival_date():
    red_eye = _parsed_options()[1]
    assert red_eye.depart_time == "18:00"  # 21:00 EDT/EST at JFK
    assert red_eye.depart_date == _DAY
    assert red_eye.arrive_time == "00:30"  # LAX-local is PT already
    assert red_eye.arrive_date == _NEXT_DAY
    assert red_eye.arrive_date != red_eye.depart_date


def test_parser_skips_unmapped_airport_in_favor_of_the_next():
    """The XXQ itinerary never surfaces; the two-segment connection takes
    its slot (option three), with stops counted across the plane change."""
    options = _parsed_options()
    assert len(options) == 3
    assert [o.flight_number for o in options] == [439, 1187, 212]
    connection = options[2]
    assert connection.stops == 1  # two segments, no segment-internal stops
    assert connection.depart_time == "05:00"  # 08:00 at JFK
    assert connection.arrive_time == "13:05"  # 13:05 at LAX


def test_parser_all_unmappable_yields_no_options():
    payload = {
        "PricedItineraries": [
            _itinerary(
                [_segment("XXQ", "ZZQ", f"{_DAY}T09:00:00",
                          f"{_DAY}T11:10:00")],
                "99.00",
            )
        ]
    }
    response = shapes.InstaFlightsResponse.model_validate(payload)
    assert concierge._parse_instaflights_options(response, "XXQ", "ZZQ") == []


def test_parser_spoken_contract_no_codes_rounded_prices():
    options = _parsed_options()
    spoken = " ".join(o.spoken for o in options)
    assert "Option one" in spoken and "Option two" in spoken
    assert "about 261 dollars" in spoken  # 260.60 rounds, never spoken exact
    assert "about 189 dollars" in spoken
    assert "4:20 AM" in spoken  # 12-hour clock, PT
    # No airline codes, currency codes, or airport codes in the clause.
    for token in ("DL", "UA", "AA", "USD", "JFK", "LAX"):
        assert token not in spoken
    # The airline still lands in the structured field for the booking rows.
    assert options[0].airline == "DL"


def test_red_eye_booking_writes_end_ts_after_start_ts(monkeypatch):
    """_booking_writes builds end_ts from arrive_date — a converted red-eye
    must not produce end_ts < start_ts."""
    writes = {}
    monkeypatch.setattr(concierge.trips, "create_trip",
                        lambda trip: (True, trip, None))
    monkeypatch.setattr(concierge.bookings, "create_booking",
                        lambda booking: (True, booking, None))
    monkeypatch.setattr(concierge.itinerary_items, "update_status",
                        lambda item_id, status: (True, 1, None))

    def create_item(item):
        writes["item"] = item
        return True, item, None

    monkeypatch.setattr(concierge.itinerary_items, "create_item", create_item)

    red_eye = _parsed_options()[1]
    concierge._booking_writes(red_eye, [red_eye])

    item = writes["item"]
    assert item.end_ts > item.start_ts
    assert item.end_ts.date().isoformat() == _NEXT_DAY


def test_flight_option_arrive_date_defaults_to_depart_date():
    """The additive-field guarantee: pre-Phase-27 construction sites (and
    stored payloads) that never set arrive_date stay valid."""
    option = concierge.FlightOption(
        option_number=1, airline="AA", flight_number=100, origin="MSP",
        destination="SFO", depart_date=_DAY, depart_time="08:00",
        arrive_time="10:05", stops=0, price=250.0, currency="USD",
        spoken="Option one.",
    )
    assert option.arrive_date == _DAY


# --- real client contract: mocked transport, no network -------------------------


def _mock_transport(monkeypatch, handler):
    """Route the real client's inline httpx.AsyncClient through a
    MockTransport; the factory closes over the real class."""
    real_async_client = httpx.AsyncClient

    def factory(**kwargs):
        return real_async_client(
            transport=httpx.MockTransport(handler), **kwargs
        )

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def _configured_real_client(monkeypatch) -> RealSabreClient:
    monkeypatch.setenv("SABRE_BASE_URL", "https://sabre.test")
    monkeypatch.setenv("SABRE_CLIENT_SECRET", "c2VjcmV0")
    return RealSabreClient()


def test_real_client_always_sends_onlineitinerariesonly_n(monkeypatch):
    """Y triggers a CERT-side 500 (verified-live, Phase 25) — the client
    merges N in unconditionally, even when the request object says Y."""
    seen = {}

    def handler(request):
        if request.url.path == "/v2/auth/token":
            return httpx.Response(200, json={
                "access_token": "T1RLtoken", "token_type": "bearer",
                "expires_in": 604800,
            })
        seen["params"] = dict(request.url.params)
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=instaflights_payload())

    _mock_transport(monkeypatch, handler)
    real = _configured_real_client(monkeypatch)

    response = asyncio.run(real.instaflights_search(
        shapes.InstaFlightsRequest(
            origin="JFK", destination="LAX", departuredate=_DAY,
            onlineitinerariesonly="Y",  # must be overridden
        )
    ))

    assert seen["params"]["onlineitinerariesonly"] == "N"
    assert seen["params"]["origin"] == "JFK"
    assert seen["params"]["destination"] == "LAX"
    assert seen["auth"] == "Bearer T1RLtoken"  # _get carries the token
    assert isinstance(response, shapes.InstaFlightsResponse)


def test_real_client_supported_markets_fetches_once_and_caches(monkeypatch):
    calls = {"markets": 0}

    def handler(request):
        if request.url.path == "/v2/auth/token":
            return httpx.Response(200, json={
                "access_token": "T1RLtoken", "token_type": "bearer",
                "expires_in": 604800,
            })
        calls["markets"] += 1
        return httpx.Response(200, json={
            "OriginDestinationLocations": [
                {"OriginLocation": {"AirportCode": "SFO"},
                 "DestinationLocation": {"AirportCode": "JFK"}},
            ]
        })

    _mock_transport(monkeypatch, handler)
    real = _configured_real_client(monkeypatch)

    async def twice():
        first = await real.supported_markets()
        second = await real.supported_markets()
        return first, second

    first, second = asyncio.run(twice())
    assert first is second  # instance cache — one fetch for the process
    assert calls["markets"] == 1


# --- dispatcher: routing, silent fallback, best-effort markets ------------------


def _request():
    return shapes.InstaFlightsRequest(
        origin="MSP", destination="SFO", departuredate=_DAY
    )


def test_dispatcher_mock_mode_never_touches_the_real_client(monkeypatch):
    monkeypatch.setenv("SABRE_MODE", "mock")

    async def never(request):
        raise AssertionError("real client must not be touched in mock mode")

    monkeypatch.setattr(client._real, "instaflights_search", never)
    response = asyncio.run(client.instaflights_search(_request()))
    assert isinstance(response, shapes.InstaFlightsResponse)
    assert len(response.PricedItineraries) == 3


def test_dispatcher_real_failure_falls_back_to_mock_and_logs(monkeypatch, caplog):
    monkeypatch.setenv("SABRE_MODE", "real")

    async def boom(request):
        raise RuntimeError("sandbox flaked")

    monkeypatch.setattr(client._real, "instaflights_search", boom)

    with caplog.at_level(logging.WARNING):
        response = asyncio.run(client.instaflights_search(_request()))

    expected = asyncio.run(client._mock.instaflights_search(_request()))
    assert response == expected  # the mock served this call
    warning = next(r for r in caplog.records if r.levelno == logging.WARNING)
    assert "instaflights_search" in warning.getMessage()
    assert "falling back" in warning.getMessage()


def test_supported_markets_returns_none_in_mock_mode(monkeypatch):
    monkeypatch.setenv("SABRE_MODE", "mock")

    async def never():
        raise AssertionError("real client must not be touched in mock mode")

    monkeypatch.setattr(client._real, "supported_markets", never)
    assert asyncio.run(client.supported_markets()) is None


def test_supported_markets_returns_none_on_fetch_failure(monkeypatch, caplog):
    monkeypatch.setenv("SABRE_MODE", "real")

    async def boom():
        raise RuntimeError("sandbox flaked")

    monkeypatch.setattr(client._real, "supported_markets", boom)
    with caplog.at_level(logging.WARNING):
        assert asyncio.run(client.supported_markets()) is None
    assert "supported-markets" in caplog.text


def test_supported_markets_returns_uppercased_pairs(monkeypatch):
    monkeypatch.setenv("SABRE_MODE", "real")

    async def markets():
        return shapes.SupportedMarketsResponse.model_validate({
            "OriginDestinationLocations": [
                {"OriginLocation": {"AirportCode": "sfo"},
                 "DestinationLocation": {"AirportCode": "jfk"}},
                {"OriginLocation": {"AirportCode": "JFK"},
                 "DestinationLocation": {"AirportCode": "SFO"}},
            ]
        })

    monkeypatch.setattr(client._real, "supported_markets", markets)
    assert asyncio.run(client.supported_markets()) == {
        ("SFO", "JFK"), ("JFK", "SFO"),
    }


# --- concierge flow: end-to-end on the mock, markets check, Phase 21 shape ------


def test_search_flights_end_to_end_on_the_mock():
    msg = asyncio.run(
        concierge.search_flights_impl("room-1", "MSP", "SFO", _DAY)
    )

    options = concierge._SESSION_FLIGHT_OPTIONS["room-1"]
    assert len(options) == 3
    assert [o.option_number for o in options] == [1, 2, 3]
    assert all(o.arrive_date for o in options)
    slot = concierge._LATEST_SEARCH
    assert slot is not None and slot.session_id == "room-1"
    assert slot.options == options
    assert "Option one" in msg and "dollars" in msg
    assert "AA" not in msg and "USD" not in msg


def test_search_flights_real_mode_failure_serves_mock_silently(monkeypatch, caplog):
    """The event-day insurance, end to end: SABRE_MODE=real with a raising
    real client still speaks options — and the reply never mentions the
    failure (the judges hear no apology for Sabre's sandbox)."""
    monkeypatch.setenv("SABRE_MODE", "real")

    async def boom(request):
        raise RuntimeError("sandbox flaked")

    async def no_markets():
        return None

    monkeypatch.setattr(client._real, "instaflights_search", boom)
    monkeypatch.setattr(client._real, "supported_markets", no_markets)

    with caplog.at_level(logging.WARNING):
        msg = asyncio.run(
            concierge.search_flights_impl("room-1", "MSP", "SFO", _DAY)
        )

    assert "Option one" in msg  # the mock's options, spoken normally
    for word in ("trouble", "error", "failed", "sandbox", "mock"):
        assert word not in msg.lower()
    assert "instaflights_search" in caplog.text  # but the log names it


def test_unsupported_market_redirects_and_never_searches(monkeypatch):
    async def markets():
        return {("SFO", "JFK")}

    async def never(request):
        raise AssertionError("no search call for an unsupported pair")

    monkeypatch.setattr(concierge.sabre_client, "supported_markets", markets)
    monkeypatch.setattr(
        concierge.sabre_client, "instaflights_search", never
    )

    msg = asyncio.run(
        concierge.search_flights_impl("room-1", "MSP", "SFO", _DAY)
    )

    assert msg == concierge._UNSUPPORTED_MARKET_LINE
    assert "San Francisco to New York" in msg  # a known-good suggestion
    assert "room-1" not in concierge._SESSION_FLIGHT_OPTIONS
    assert concierge._LATEST_SEARCH is None


def test_markets_none_skips_validation_and_searches(monkeypatch):
    async def no_markets():
        return None

    monkeypatch.setattr(concierge.sabre_client, "supported_markets", no_markets)

    msg = asyncio.run(
        concierge.search_flights_impl("room-1", "MSP", "SFO", _DAY)
    )

    assert "Option one" in msg
    assert "room-1" in concierge._SESSION_FLIGHT_OPTIONS


def test_all_unmappable_search_speaks_the_no_flights_line(monkeypatch):
    """Every candidate unmappable -> the existing honest line, not a crash
    and not a mangled time."""
    async def unmapped_search(request):
        return shapes.InstaFlightsResponse.model_validate({
            "PricedItineraries": [
                _itinerary(
                    [_segment("XXQ", "ZZQ", f"{_DAY}T09:00:00",
                              f"{_DAY}T11:10:00")],
                    "99.00",
                )
            ]
        })

    monkeypatch.setattr(
        concierge.sabre_client, "instaflights_search", unmapped_search
    )

    msg = asyncio.run(
        concierge.search_flights_impl("room-1", "XXQ", "ZZQ", _DAY)
    )

    assert "couldn't find any flights" in msg
    assert "room-1" not in concierge._SESSION_FLIGHT_OPTIONS


def test_pending_options_payload_is_the_phase_21_contract():
    """Byte-for-byte shape guard: exactly recorded_at + options[] of the
    seven Phase 21 keys — arrive_date stays internal to FlightOption; the
    booking page's contract does not grow."""
    asyncio.run(concierge.search_flights_impl("room-1", "MSP", "SFO", _DAY))

    block = concierge.pending_options_for_trip("any-trip")
    assert set(block.keys()) == {"recorded_at", "options"}
    for option in block["options"]:
        assert set(option.keys()) == {
            "option_number", "route", "depart_date", "depart_time",
            "arrive_time", "stops", "price",
        }
        assert isinstance(option["price"], int)  # rounded whole dollars
        assert "M" in option["depart_time"]  # spoken 12-hour label
