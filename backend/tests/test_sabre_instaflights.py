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
from datetime import date, datetime, timedelta
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


def test_parser_skips_itinerary_with_unmapped_connection_airport():
    """Phase 28 (validation criterion 5): mapped endpoints are not enough —
    a JFK→XXQ→LAX itinerary connects through an airport absent from the
    timezone table and must be skipped, with the next fully mapped
    itinerary renumbering into slot one."""
    payload = {
        "PricedItineraries": [
            _itinerary(
                [
                    _segment("JFK", "XXQ", f"{_DAY}T07:00:00",
                             f"{_DAY}T08:30:00", flight="501"),
                    _segment("XXQ", "LAX", f"{_DAY}T09:30:00",
                             f"{_DAY}T11:45:00", flight="502"),
                ],
                "150.00",
            ),
            _itinerary(
                [_segment("JFK", "LAX", f"{_DAY}T07:20:00",
                          f"{_DAY}T10:35:00", flight="439")],
                "260.60",
            ),
        ]
    }
    response = shapes.InstaFlightsResponse.model_validate(payload)
    options = concierge._parse_instaflights_options(response, "JFK", "LAX")

    assert [o.flight_number for o in options] == [439]
    assert options[0].option_number == 1
    assert "Option one" in options[0].spoken


def test_parser_mapped_multi_segment_still_parses():
    """The over-skipping guard: an itinerary whose every segment end is
    mapped survives the all-segment check, with stops counted as the
    segment StopQuantity sum plus one per plane change."""
    payload = {
        "PricedItineraries": [
            _itinerary(
                [
                    _segment("JFK", "ORD", f"{_DAY}T08:00:00",
                             f"{_DAY}T09:40:00", flight="212", stops=1),
                    _segment("ORD", "LAX", f"{_DAY}T10:45:00",
                             f"{_DAY}T13:05:00", flight="213"),
                ],
                "205.40",
            ),
        ]
    }
    response = shapes.InstaFlightsResponse.model_validate(payload)
    options = concierge._parse_instaflights_options(response, "JFK", "LAX")

    assert len(options) == 1
    assert options[0].stops == 2  # one in-segment stop + one plane change
    assert options[0].depart_time == "05:00"  # 08:00 at JFK is 05:00 PT


def test_parser_dedupes_identical_itineraries():
    """Phase 28 (live finding): CERT returned byte-identical itineraries and
    the agent said 'option three is the same as option two' aloud. The
    duplicate is offered once; numbering stays contiguous and no spoken
    clause repeats another."""
    duplicate = _itinerary(
        [_segment("JFK", "LAX", f"{_DAY}T07:20:00",
                  f"{_DAY}T10:35:00", flight="439")],
        "260.60",
    )
    distinct = _itinerary(
        [_segment("JFK", "LAX", f"{_DAY}T11:00:00",
                  f"{_DAY}T14:15:00", flight="777")],
        "199.00",
    )
    payload = {"PricedItineraries": [duplicate, duplicate, distinct]}
    response = shapes.InstaFlightsResponse.model_validate(payload)
    options = concierge._parse_instaflights_options(response, "JFK", "LAX")

    assert len(options) == 2
    assert [o.option_number for o in options] == [1, 2]
    assert [o.flight_number for o in options] == [439, 777]
    assert options[0].spoken != options[1].spoken


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


# --- mock times are airport-local (Phase 28, validation criterion 14) -----------


def _pt_instant(day: str, clock: str) -> datetime:
    return datetime.fromisoformat(f"{day}T{clock}").replace(
        tzinfo=ZoneInfo("America/Los_Angeles")
    )


def _searched_options(origin, destination):
    asyncio.run(
        concierge.search_flights_impl("room-1", origin, destination, _DAY)
    )
    return concierge._SESSION_FLIGHT_OPTIONS.get("room-1", [])


def test_mock_west_to_east_preserves_pacific_wall_clock_order():
    """The criterion-14 regression: mock-mode SFO→JFK used to emit Pacific
    fiction clocks that the parser re-read as JFK-local, so arrivals landed
    'before' departures. The mock now speaks airport-local; the parsed PT
    round trip is the classic spread, arrivals strictly after departures."""
    options = _searched_options("SFO", "JFK")

    assert len(options) == 3
    for option in options:
        depart = _pt_instant(option.depart_date, option.depart_time)
        arrive = _pt_instant(option.arrive_date, option.arrive_time)
        assert arrive > depart
    assert options[0].depart_time == "08:00"
    assert options[0].arrive_time == "10:05"
    assert "leaves at 8 AM and lands at 10:05 AM" in options[0].spoken


def test_mock_east_to_west_parses_to_the_same_pt_spread():
    """Direction independence: the reverse pair round-trips to the identical
    classic PT spread — the fiction is the instant, not the string."""
    east_west = _searched_options("JFK", "SFO")
    concierge._SESSION_FLIGHT_OPTIONS.pop("room-1", None)
    west_east = _searched_options("MSP", "SFO")

    for options in (east_west, west_east):
        assert [(o.depart_time, o.arrive_time) for o in options] == [
            ("08:00", "10:05"), ("11:30", "13:40"), ("06:15", "11:20"),
        ]
        assert all(o.depart_date == _DAY for o in options)
        assert all(o.arrive_date == _DAY for o in options)


def test_mock_west_to_east_booking_write_keeps_end_after_start(monkeypatch):
    """The _booking_writes regression from criterion 14: booking a mock
    SFO→JFK option must produce end_ts > start_ts."""
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

    option = _searched_options("SFO", "JFK")[0]
    concierge._booking_writes(option, [option])

    item = writes["item"]
    assert item.end_ts > item.start_ts


def test_mock_unmapped_airport_emits_the_fiction_unchanged():
    """An airport code missing from the timezone table gets the fiction
    clock as-is — no crash, no fabricated zone; the parser then skips the
    itinerary and the search speaks the honest no-flights line."""
    from api.sabre.mock_client import MockSabreClient

    assert MockSabreClient._airport_local(_DAY, "08:00:00", "XXQ") == (
        f"{_DAY}T08:00:00"
    )

    msg = asyncio.run(
        concierge.search_flights_impl("room-1", "XXQ", "ZZQ", _DAY)
    )
    assert "couldn't find any flights" in msg
    assert "room-1" not in concierge._SESSION_FLIGHT_OPTIONS


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


# --- honest empties: the documented no-results 404 (Phase 28) -------------------


def _token_response():
    return httpx.Response(200, json={
        "access_token": "T1RLtoken", "token_type": "bearer",
        "expires_in": 604800,
    })


def _no_results_body():
    """The live-captured InstaFlights empty-cache body (probed 2026-07-14,
    Phase 28): a documented empty, not a failure."""
    return {
        "status": "Complete",
        "reportingSystem": "raf",
        "type": "Application",
        "errorCode": "WARN.RAF.APPLICATION",
        "message": "No results were found",
    }


def test_real_client_documented_404_returns_empty_response(monkeypatch):
    def handler(request):
        if request.url.path == "/v2/auth/token":
            return _token_response()
        return httpx.Response(404, json=_no_results_body())

    _mock_transport(monkeypatch, handler)
    real = _configured_real_client(monkeypatch)

    response = asyncio.run(real.instaflights_search(
        shapes.InstaFlightsRequest(
            origin="SFO", destination="JFK", departuredate=_DAY,
        )
    ))

    assert isinstance(response, shapes.InstaFlightsResponse)
    assert response.PricedItineraries == []


def test_real_client_404_message_fallback_without_error_code(monkeypatch):
    """Strict match, second leg: a 404 whose body lost the errorCode marker
    but still says 'No results were found' counts as the documented empty."""
    def handler(request):
        if request.url.path == "/v2/auth/token":
            return _token_response()
        return httpx.Response(404, json={"message": "No results were found"})

    _mock_transport(monkeypatch, handler)
    real = _configured_real_client(monkeypatch)

    response = asyncio.run(real.instaflights_search(
        shapes.InstaFlightsRequest(
            origin="SFO", destination="JFK", departuredate=_DAY,
        )
    ))

    assert response.PricedItineraries == []


def test_real_client_other_404_still_raises(monkeypatch):
    """Any other 404 — entitlement drift, a bad path, a gateway flap — stays
    a genuine failure so the dispatcher's mock swap covers it."""
    def handler(request):
        if request.url.path == "/v2/auth/token":
            return _token_response()
        return httpx.Response(404, json={
            "errorCode": "ERR.2SG.CLIENT.INVALID_REQUEST",
            "message": "Resource not found in rest table",
        })

    _mock_transport(monkeypatch, handler)
    real = _configured_real_client(monkeypatch)

    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        asyncio.run(real.instaflights_search(
            shapes.InstaFlightsRequest(
                origin="SFO", destination="JFK", departuredate=_DAY,
            )
        ))
    assert excinfo.value.response.status_code == 404


def test_documented_empty_speaks_no_flights_end_to_end(monkeypatch, caplog):
    """The realness posture, seam to seam: SABRE_MODE=real, an empty cache
    date answers the documented 404 — the agent speaks the existing
    no-flights line, the mock is never consulted, and no fallback warning
    is logged (this is not the insurance path)."""
    monkeypatch.setenv("SABRE_MODE", "real")

    def handler(request):
        if request.url.path == "/v2/auth/token":
            return _token_response()
        if "origins-destinations" in request.url.path:
            return httpx.Response(200, json={
                "OriginDestinationLocations": [
                    {"OriginLocation": {"AirportCode": "SFO"},
                     "DestinationLocation": {"AirportCode": "JFK"}},
                ]
            })
        return httpx.Response(404, json=_no_results_body())

    _mock_transport(monkeypatch, handler)
    monkeypatch.setattr(client, "_real", _configured_real_client(monkeypatch))

    async def mock_never(request):
        raise AssertionError("the mock must not serve a documented empty")

    monkeypatch.setattr(client._mock, "instaflights_search", mock_never)

    with caplog.at_level(logging.WARNING):
        msg = asyncio.run(
            concierge.search_flights_impl("room-1", "SFO", "JFK", _DAY)
        )

    assert "couldn't find any flights" in msg
    assert "room-1" not in concierge._SESSION_FLIGHT_OPTIONS
    assert concierge._LATEST_SEARCH is None
    assert "falling back" not in caplog.text


def test_other_404_still_mock_swaps_at_the_dispatcher(monkeypatch, caplog):
    """The event-day insurance asserted intact: a non-documented 404 raises
    out of the real client and the dispatcher serves the mock for that call,
    logging the warning."""
    monkeypatch.setenv("SABRE_MODE", "real")

    def handler(request):
        if request.url.path == "/v2/auth/token":
            return _token_response()
        return httpx.Response(404, json={"errorCode": "ERR.2SG.SEC.SOMETHING"})

    _mock_transport(monkeypatch, handler)
    monkeypatch.setattr(client, "_real", _configured_real_client(monkeypatch))

    with caplog.at_level(logging.WARNING):
        response = asyncio.run(client.instaflights_search(_request()))

    assert len(response.PricedItineraries) == 3  # the mock served this call
    assert "falling back" in caplog.text


# --- token refresh: retry once on 401 (Phase 28) ---------------------------------


def test_401_clears_token_refetches_and_retries_once(monkeypatch):
    calls = {"token": 0, "search": 0}
    seen = {}

    def handler(request):
        if request.url.path == "/v2/auth/token":
            calls["token"] += 1
            return httpx.Response(200, json={
                "access_token": f"T1RLtoken{calls['token']}",
                "token_type": "bearer", "expires_in": 604800,
            })
        calls["search"] += 1
        if calls["search"] == 1:
            return httpx.Response(401, json={"error": "invalid_token"})
        seen["retry_auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json=instaflights_payload())

    _mock_transport(monkeypatch, handler)
    real = _configured_real_client(monkeypatch)

    response = asyncio.run(real.instaflights_search(
        shapes.InstaFlightsRequest(
            origin="JFK", destination="LAX", departuredate=_DAY,
        )
    ))

    assert calls["token"] == 2  # cached token cleared, fresh one minted
    assert calls["search"] == 2  # the request retried exactly once
    assert seen["retry_auth"] == "Bearer T1RLtoken2"  # retry used the fresh token
    assert real._token == "T1RLtoken2"
    assert isinstance(response, shapes.InstaFlightsResponse)


def test_persistent_401_raises_after_exactly_one_retry(monkeypatch):
    calls = {"search": 0}

    def handler(request):
        if request.url.path == "/v2/auth/token":
            return _token_response()
        calls["search"] += 1
        return httpx.Response(401, json={"error": "invalid_token"})

    _mock_transport(monkeypatch, handler)
    real = _configured_real_client(monkeypatch)

    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        asyncio.run(real.instaflights_search(
            shapes.InstaFlightsRequest(
                origin="JFK", destination="LAX", departuredate=_DAY,
            )
        ))

    assert excinfo.value.response.status_code == 401
    assert calls["search"] == 2  # one retry, never a loop


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


def test_metro_codes_alias_to_airports_before_the_market_check(monkeypatch):
    """Phase 28 (live finding): the model resolved 'New York' to the metro
    code NYC and the airport-code-only market check redirected the traveler
    off a carried route. NYC→JFK and WAS→IAD alias before the market check
    and before the client sees the request."""
    seen = {}

    async def markets():
        # Airport codes only, like the real list — the metro pair is absent.
        return {("JFK", "IAD")}

    async def capture_search(request):
        seen["request"] = request
        return shapes.InstaFlightsResponse.model_validate(instaflights_payload())

    monkeypatch.setattr(concierge.sabre_client, "supported_markets", markets)
    monkeypatch.setattr(
        concierge.sabre_client, "instaflights_search", capture_search
    )

    msg = asyncio.run(
        concierge.search_flights_impl("room-1", "NYC", "WAS", _DAY)
    )

    assert seen["request"].origin == "JFK"  # aliased, not NYC
    assert seen["request"].destination == "IAD"  # aliased, not WAS
    assert msg != concierge._UNSUPPORTED_MARKET_LINE  # market check passed
    assert "Option one" in msg


def test_non_alias_codes_pass_through_untouched(monkeypatch):
    seen = {}

    async def capture_search(request):
        seen["request"] = request
        return shapes.InstaFlightsResponse.model_validate(instaflights_payload())

    monkeypatch.setattr(
        concierge.sabre_client, "instaflights_search", capture_search
    )

    asyncio.run(concierge.search_flights_impl("room-1", "msp", "SFO", _DAY))

    assert seen["request"].origin == "MSP"  # normalized, never remapped
    assert seen["request"].destination == "SFO"


def test_instructions_carry_the_airport_code_clause():
    """The other half of decision 4: the model is told airport codes, never
    metro/city codes, with the New York example — terse, riding every turn."""
    assert "never a metro or city code" in concierge.BASE_INSTRUCTIONS
    assert "JFK, not NYC" in concierge.BASE_INSTRUCTIONS


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
