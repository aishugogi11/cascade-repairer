"""Phase 41 — airline-diverse flight options, hermetic.

The guided-booking search parses a wider pool (limit=15) and offers one
option per distinct airline via flight_options.select_airline_diverse:
each carrier's cheapest itinerary (tie: earliest PT departure), spoken
cheapest-representative first, at most three airlines. A single-carrier
pool degrades to the pre-41 response-order top three, and the repair
re-shop's parser contract (default cap, response order) is byte-identical
to pre-41 — guarded here structurally. Travel dates are computed (the
Phase 26 rule), never literals.
"""
import asyncio
from datetime import date, timedelta

import pytest

from api import concierge, flight_options
from api.sabre import shapes

_DAY = (date.today() + timedelta(days=21)).isoformat()


def _option(number, airline, price, depart="08:00", arrive="10:05",
            depart_date=_DAY, stops=0, cabin="Economy"):
    """A parse-shaped FlightOption: numbering sequential over the pool,
    spoken generated the way the parser generates it."""
    carrier = flight_options.airline_name(airline)
    return flight_options.FlightOption(
        option_number=number,
        airline=airline,
        flight_number=100 + number,
        origin="JFK",
        destination="LAX",
        depart_date=depart_date,
        depart_time=depart,
        arrive_time=arrive,
        arrive_date=depart_date,
        stops=stops,
        price=price,
        currency="USD",
        spoken=flight_options._spoken_option(
            number, carrier, stops, depart, arrive, price
        ),
        airline_name=carrier,
        cabin=cabin,
        duration_minutes=125,
        layover_airports=[],
        arrives_next_day=False,
    )


# --- selection: diversity, representative pick, cap, degrade -----------------


def test_multi_airline_pool_yields_one_option_per_airline_cheapest_first():
    """The TODO's motivating shape: a B6-heavy pool with AA content further
    down yields one JetBlue and one American — cheapest representative
    spoken first."""
    pool = [
        _option(1, "B6", 198.4, depart="17:45"),
        _option(2, "B6", 198.4, depart="17:50"),
        _option(3, "B6", 246.2, depart="19:30", stops=1),
        _option(4, "AA", 278.4, depart="06:00"),
        _option(5, "AA", 278.4, depart="07:05"),
    ]
    selected = flight_options.select_airline_diverse(pool)

    assert [o.airline for o in selected] == ["B6", "AA"]
    assert [o.price for o in selected] == [198.4, 278.4]


def test_representative_is_cheapest_with_equal_fare_tie_to_earliest():
    """Within an airline the lowest fare wins; the equal-fare pair
    tie-breaks to the earlier PT departure."""
    pool = [
        _option(1, "DL", 310.0, depart="06:00"),
        _option(2, "DL", 250.0, depart="15:00"),
        _option(3, "DL", 250.0, depart="09:30"),
        _option(4, "UA", 400.0, depart="08:00"),
    ]
    selected = flight_options.select_airline_diverse(pool)

    dl = next(o for o in selected if o.airline == "DL")
    assert dl.price == 250.0
    assert dl.depart_time == "09:30"


def test_four_airline_pool_caps_at_three_cheapest_representatives():
    pool = [
        _option(1, "B6", 198.4),
        _option(2, "AA", 278.4),
        _option(3, "DL", 260.0),
        _option(4, "UA", 320.0),
    ]
    selected = flight_options.select_airline_diverse(pool)

    assert len(selected) == 3
    assert [o.airline for o in selected] == ["B6", "DL", "AA"]  # UA is out


def test_single_airline_pool_degrades_to_response_order_top_three():
    """One distinct carrier — pre-41 behavior exactly: the first three pool
    options in response order, field-for-field equal to the input slice."""
    pool = [
        _option(1, "B6", 246.2, depart="19:30"),
        _option(2, "B6", 198.4, depart="17:45"),
        _option(3, "B6", 198.4, depart="17:50"),
        _option(4, "B6", 198.4, depart="17:55"),
    ]
    selected = flight_options.select_airline_diverse(pool)

    assert selected == pool[:3]


def test_selection_renumbers_and_regenerates_spoken():
    """Selected options are 1..N with `spoken` matching the new position —
    airline NAME in the clause, never the code — and every other field
    carried over unchanged."""
    pool = [
        _option(1, "B6", 198.4, depart="17:45"),
        _option(2, "AA", 278.4, depart="06:00"),
    ]
    # Pool order is already fare order, so selection keeps it — but the AA
    # option was number 2 spoken as "option two"; it must stay number 2 here.
    selected = flight_options.select_airline_diverse(pool)

    for position, option in enumerate(selected, start=1):
        word = flight_options._NUMBER_WORDS[position]
        assert option.option_number == position
        assert f"Option {word} on {option.airline_name}" in option.spoken
        assert option.airline not in option.spoken  # name, never the code

    reordering_pool = [
        _option(1, "DL", 300.0),
        _option(2, "AA", 200.0),
    ]
    reordered = flight_options.select_airline_diverse(reordering_pool)
    assert [o.airline for o in reordered] == ["AA", "DL"]
    assert [o.option_number for o in reordered] == [1, 2]
    assert "Option one on American" in reordered[0].spoken
    assert "Option two on Delta" in reordered[1].spoken
    # Non-renumbered fields carry over intact.
    original_aa = reordering_pool[1]
    selected_aa = reordered[0]
    assert selected_aa.model_dump(exclude={"option_number", "spoken"}) == \
        original_aa.model_dump(exclude={"option_number", "spoken"})


# --- repair parity: the shared parser's default contract is pre-41 ----------


def _priced_itinerary(dep_clock, arr_clock, flight, airline, amount):
    return {
        "AirItinerary": {
            "OriginDestinationOptions": {
                "OriginDestinationOption": [{"FlightSegment": [{
                    "DepartureAirport": {"LocationCode": "JFK"},
                    "ArrivalAirport": {"LocationCode": "LAX"},
                    "DepartureDateTime": f"{_DAY}T{dep_clock}",
                    "ArrivalDateTime": f"{_DAY}T{arr_clock}",
                    "FlightNumber": flight,
                    "MarketingAirline": {"Code": airline},
                    "StopQuantity": 0,
                }]}]
            }
        },
        "AirItineraryPricingInfo": {
            "ItinTotalFare": {
                "TotalFare": {"Amount": amount, "CurrencyCode": "USD"}
            }
        },
    }


_FIVE_ITINERARY_RESPONSE = {
    "PricedItineraries": [
        _priced_itinerary("17:45:00", "20:57:00", 3988, "B6", 198.4),
        _priced_itinerary("17:50:00", "20:59:00", 3997, "B6", 198.4),
        _priced_itinerary("18:00:00", "21:10:00", 3994, "B6", 198.4),
        _priced_itinerary("06:00:00", "09:01:00", 171, "AA", 278.4),
        _priced_itinerary("07:05:00", "10:07:00", 33, "AA", 278.4),
    ]
}


def test_parser_default_cap_is_first_three_response_order():
    """The repair re-shop calls the parser with default arguments — on a
    five-itinerary response it must get exactly the first three in response
    order, the pre-41 contract, no diversity applied."""
    search = shapes.InstaFlightsResponse(**_FIVE_ITINERARY_RESPONSE)
    options = flight_options._parse_instaflights_options(search, "JFK", "LAX")

    assert [(o.airline, o.flight_number) for o in options] == [
        ("B6", 3988), ("B6", 3997), ("B6", 3994),
    ]
    assert [o.option_number for o in options] == [1, 2, 3]


def test_parser_max_options_widens_the_pool():
    search = shapes.InstaFlightsResponse(**_FIVE_ITINERARY_RESPONSE)
    pool = flight_options._parse_instaflights_options(
        search, "JFK", "LAX", max_options=15
    )

    assert len(pool) == 5
    assert flight_options.select_airline_diverse(pool) != pool[:3]
    assert [o.airline for o in flight_options.select_airline_diverse(pool)] \
        == ["B6", "AA"]


def test_repair_tools_call_sites_use_default_parser_args():
    """Structural guard: repair_tools never passes max_options and never
    calls select_airline_diverse — its candidate pool is byte-identical to
    pre-41."""
    import inspect

    from api import repair_tools

    source = inspect.getsource(repair_tools)
    assert "select_airline_diverse" not in source
    assert "max_options" not in source


# --- concierge flow: request limit, stored menu, booking by new number -------


def test_concierge_request_carries_limit_15_and_shapes_default_stays_10(
    monkeypatch,
):
    captured = {}

    async def capture_search(request):
        captured.setdefault("request", request)
        return shapes.InstaFlightsResponse(**_FIVE_ITINERARY_RESPONSE)

    monkeypatch.setattr(
        concierge.sabre_client, "instaflights_search", capture_search
    )
    session = "phase41-limit"
    try:
        asyncio.run(
            concierge.search_flights_impl(session, "JFK", "LAX", _DAY)
        )
        assert captured["request"].limit == 15
        assert shapes.InstaFlightsRequest(
            origin="JFK", destination="LAX", departuredate=_DAY
        ).limit == 10
    finally:
        concierge._SESSION_FLIGHT_OPTIONS.pop(session, None)
        concierge._LATEST_SEARCH = None


def test_search_stores_diverse_menu_and_booking_resolves_new_numbers(
    monkeypatch,
):
    """Against the multi-carrier mock: the stored menu is one option per
    airline, ML-ranked (not fare order), and book_flight resolves 'option
    two' against the renumbered list."""
    session = "phase41-flow"
    created = {}
    monkeypatch.setattr(
        concierge.trips, "create_trip",
        lambda trip: (created.setdefault("trip", trip), (True, trip, None))[1],
    )
    monkeypatch.setattr(
        concierge.itinerary_items, "create_item",
        lambda item: (created.setdefault("item", item), (True, item, None))[1],
    )
    monkeypatch.setattr(
        concierge.itinerary_items, "update_status",
        lambda item_id, status: (True, 1, None),
    )
    monkeypatch.setattr(
        concierge.bookings, "create_booking",
        lambda booking: (True, booking, None),
    )
    # book_flight_impl re-pins via ensure_trip_context, which reads the trip
    # and its items back — serve the just-created rows.
    monkeypatch.setattr(
        concierge.trips, "get_trip",
        lambda trip_id: (True, created.get("trip"), None),
    )
    monkeypatch.setattr(
        concierge.itinerary_items, "list_items_for_trip",
        lambda trip_id: (True, [created["item"]], None),
    )
    try:
        spoken = asyncio.run(
            concierge.search_flights_impl(session, "MSP", "SFO", _DAY)
        )
        menu = concierge._SESSION_FLIGHT_OPTIONS[session]
        airlines = {o.airline for o in menu}
        assert airlines >= {"UA", "AA", "DL"}
        assert [o.option_number for o in menu] == list(range(1, len(menu) + 1))
        assert {o.price for o in menu} >= {155.0, 187.6, 242.0}
        assert "Option one on" in spoken
        assert "I recommend option one" in spoken
        assert concierge._LATEST_SEARCH is not None
        assert concierge._LATEST_SEARCH.options == menu
        second = menu[1]

        result = asyncio.run(concierge.book_flight_impl(session, 2))
        assert "booked" in result
        item = created["item"]
        assert item.details["airline"] == second.airline
        assert item.details["airline_name"] == second.airline_name
    finally:
        concierge._SESSION_FLIGHT_OPTIONS.pop(session, None)
        concierge._LATEST_SEARCH = None
        concierge._SESSION_TRIPS.pop(session, None)
        concierge._SESSION_PREFS.pop(session, None)
