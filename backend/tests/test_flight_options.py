"""Phase 29 extract — the shared flight_options module, hermetic.

The parser's behavior is exercised in depth through concierge in
test_sabre_instaflights.py (the same object, re-exported). This file guards
the extract itself: the module carries no cycle-forming import, the re-export
identity holds so every existing concierge.* caller keeps resolving, and a
direct call parses the captured InstaFlights shape. Travel dates are computed
(the Phase 26 rule), never literals.
"""
import ast
import inspect
from datetime import date, timedelta

from api import concierge, flight_options
from api.sabre import shapes

_DAY = (date.today() + timedelta(days=21)).isoformat()


def _itinerary(dep, arr, dep_dt, arr_dt, flight, airline, amount, stops=0):
    return {
        "AirItinerary": {
            "OriginDestinationOptions": {
                "OriginDestinationOption": [{"FlightSegment": [{
                    "DepartureAirport": {"LocationCode": dep},
                    "ArrivalAirport": {"LocationCode": arr},
                    "DepartureDateTime": dep_dt,
                    "ArrivalDateTime": arr_dt,
                    "FlightNumber": flight,
                    "MarketingAirline": {"Code": airline},
                    "StopQuantity": stops,
                }]}]
            }
        },
        "AirItineraryPricingInfo": {
            "ItinTotalFare": {"TotalFare": {"Amount": amount, "CurrencyCode": "USD"}}
        },
    }


def test_module_has_no_cycle_forming_import():
    """decision 1: flight_options imports only sabre.shapes / sabre.airport_tz
    / pydantic / datetime — never concierge/sabre_tools/repair_tools, the
    cycle the extract exists to avoid. AST-checked (actual imports, not
    mentions in comments)."""
    tree = ast.parse(inspect.getsource(flight_options))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    for forbidden in ("api.concierge", "api.sabre_tools", "api.repair_tools"):
        assert forbidden not in imported


def test_reexport_identity_holds():
    """concierge.* is the very object flight_options defines — every existing
    caller and test keeps resolving after the move."""
    assert concierge.FlightOption is flight_options.FlightOption
    assert (
        concierge._parse_instaflights_options
        is flight_options._parse_instaflights_options
    )
    assert concierge._spoken_option is flight_options._spoken_option
    assert concierge._spoken_clock is flight_options._spoken_clock
    assert concierge._MAX_SPOKEN_OPTIONS == flight_options._MAX_SPOKEN_OPTIONS
    assert concierge._NUMBER_WORDS == flight_options._NUMBER_WORDS


def test_direct_parse_converts_airport_local_to_pacific():
    payload = {"PricedItineraries": [
        _itinerary("JFK", "LAX", f"{_DAY}T07:20:00", f"{_DAY}T10:35:00",
                   "439", "DL", "260.60"),
        _itinerary("JFK", "LAX", f"{_DAY}T11:00:00", f"{_DAY}T14:15:00",
                   "777", "AA", "199.00"),
    ]}
    response = shapes.InstaFlightsResponse.model_validate(payload)
    options = flight_options._parse_instaflights_options(response, "JFK", "LAX")

    assert [o.flight_number for o in options] == [439, 777]
    assert options[0].depart_time == "04:20"  # 07:20 at JFK -> PT
    assert options[0].airline == "DL"
    assert "Option one" in options[0].spoken
    assert "DL" not in options[0].spoken  # no codes in the spoken clause


def test_arrive_date_defaults_to_depart_date():
    option = flight_options.FlightOption(
        option_number=1, airline="AA", flight_number=100, origin="MSP",
        destination="SFO", depart_date=_DAY, depart_time="08:00",
        arrive_time="10:05", stops=0, price=250.0, currency="USD",
        spoken="Option one.",
    )
    assert option.arrive_date == _DAY


def test_option_timestamps_are_pacific_instants():
    """Phase 32: the shared start_ts/end_ts derivation (extracted from
    concierge._booking_writes) declares the option's clocks Pacific."""
    option = flight_options.FlightOption(
        option_number=1, airline="AA", flight_number=100, origin="MSP",
        destination="SFO", depart_date=_DAY, depart_time="08:00",
        arrive_time="10:05", stops=0, price=250.0, currency="USD",
        spoken="Option one.",
    )
    start_ts, end_ts = flight_options.option_timestamps(option)
    assert start_ts.tzinfo is flight_options._PACIFIC
    assert (start_ts.hour, start_ts.minute) == (8, 0)
    assert (end_ts.hour, end_ts.minute) == (10, 5)
    assert start_ts.isoformat().startswith(_DAY)
    assert end_ts > start_ts


def test_option_timestamps_red_eye_lands_next_pt_day():
    """A converted red-eye arrives on the next PT date — end_ts must never
    precede start_ts."""
    next_day = (date.fromisoformat(_DAY) + timedelta(days=1)).isoformat()
    option = flight_options.FlightOption(
        option_number=1, airline="AA", flight_number=200, origin="JFK",
        destination="LAX", depart_date=_DAY, depart_time="22:30",
        arrive_time="01:10", arrive_date=next_day, stops=0, price=180.0,
        currency="USD", spoken="Option one.",
    )
    start_ts, end_ts = flight_options.option_timestamps(option)
    assert end_ts > start_ts
    assert end_ts.isoformat().startswith(next_day)
