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


# --- rich fields (Phase 33) -------------------------------------------------------


def _rich_itinerary():
    """A two-segment JFK→ORD→LAX connection carrying every rich field the
    notebook extracts: ElapsedTime and the FareInfos cabin chain."""
    return {
        "AirItinerary": {
            "OriginDestinationOptions": {
                "OriginDestinationOption": [{
                    "FlightSegment": [
                        {
                            "DepartureAirport": {"LocationCode": "JFK"},
                            "ArrivalAirport": {"LocationCode": "ORD"},
                            "DepartureDateTime": f"{_DAY}T08:00:00",
                            "ArrivalDateTime": f"{_DAY}T09:40:00",
                            "FlightNumber": "212",
                            "MarketingAirline": {"Code": "DL"},
                            "StopQuantity": 0,
                        },
                        {
                            "DepartureAirport": {"LocationCode": "ORD"},
                            "ArrivalAirport": {"LocationCode": "LAX"},
                            "DepartureDateTime": f"{_DAY}T10:45:00",
                            "ArrivalDateTime": f"{_DAY}T13:05:00",
                            "FlightNumber": "213",
                            "MarketingAirline": {"Code": "DL"},
                            "StopQuantity": 0,
                        },
                    ],
                    "ElapsedTime": 485,
                }]
            }
        },
        "AirItineraryPricingInfo": {
            "ItinTotalFare": {"TotalFare": {"Amount": "205.40",
                                            "CurrencyCode": "USD"}},
            "FareInfos": {
                "FareInfo": [{"TPA_Extensions": {"Cabin": {"Cabin": "Y"}}}]
            },
        },
    }


def test_parser_fills_rich_fields():
    response = shapes.InstaFlightsResponse.model_validate(
        {"PricedItineraries": [_rich_itinerary()]}
    )
    option = flight_options._parse_instaflights_options(response, "JFK", "LAX")[0]

    assert option.airline_name == "Delta"
    assert option.cabin == "Economy"
    assert option.duration_minutes == 485
    assert option.layover_airports == ["ORD"]
    assert option.arrives_next_day is False
    assert option.stops == 1


def test_parser_missing_rich_fields_degrade_never_skip():
    """An itinerary with neither ElapsedTime nor the cabin chain is still
    offered — rich fields are garnish, not correctness."""
    payload = {"PricedItineraries": [
        _itinerary("JFK", "LAX", f"{_DAY}T07:20:00", f"{_DAY}T10:35:00",
                   "439", "DL", "260.60"),
    ]}
    response = shapes.InstaFlightsResponse.model_validate(payload)
    options = flight_options._parse_instaflights_options(response, "JFK", "LAX")

    assert len(options) == 1  # offered, not skipped
    assert options[0].duration_minutes == 0
    assert options[0].cabin == ""
    assert options[0].layover_airports == []
    assert options[0].airline_name == "Delta"  # the table always answers


def test_parser_red_eye_sets_arrives_next_day():
    payload = {"PricedItineraries": [
        _itinerary("JFK", "LAX", f"{_DAY}T21:00:00",
                   f"{(date.fromisoformat(_DAY) + timedelta(days=1)).isoformat()}"
                   f"T00:30:00", "1187", "UA", "189.20"),
    ]}
    response = shapes.InstaFlightsResponse.model_validate(payload)
    option = flight_options._parse_instaflights_options(response, "JFK", "LAX")[0]

    assert option.arrives_next_day is True
    assert option.arrive_date != option.depart_date


def test_spoken_clause_names_the_airline_never_codes():
    """Phase 33 decision 2: the clause gains the airline name ONLY — no
    duration, cabin, or fare-class letters ride the per-option read-out."""
    response = shapes.InstaFlightsResponse.model_validate(
        {"PricedItineraries": [_rich_itinerary()]}
    )
    option = flight_options._parse_instaflights_options(response, "JFK", "LAX")[0]

    assert "on Delta" in option.spoken
    assert "DL" not in option.spoken
    assert "Economy" not in option.spoken  # cabin is on-request only
    assert "485" not in option.spoken and "8h" not in option.spoken
    assert "ORD" not in option.spoken  # via codes never spoken unprompted


def test_pre_33_stored_payload_still_validates():
    """The additive-field guarantee, Phase 33 edition: a stored option
    payload with none of the rich fields validates with defaults."""
    option = flight_options.FlightOption(
        option_number=1, airline="AA", flight_number=100, origin="MSP",
        destination="SFO", depart_date=_DAY, depart_time="08:00",
        arrive_time="10:05", stops=0, price=250.0, currency="USD",
        spoken="Option one.",
    )
    assert option.airline_name == ""
    assert option.cabin == ""
    assert option.duration_minutes == 0
    assert option.layover_airports == []
    assert option.arrives_next_day is False


def test_airline_name_falls_back_to_the_code():
    assert flight_options.airline_name("DL") == "Delta"
    assert flight_options.airline_name(" ua ") == "United"
    assert flight_options.airline_name("ZZ") == "ZZ"
    assert flight_options.airline_name("") == ""


def test_unknown_cabin_letter_passes_through():
    """The notebook contract: CABIN_NAMES.get(letter, letter) — degraded,
    not broken."""
    rich = _rich_itinerary()
    rich["AirItineraryPricingInfo"]["FareInfos"]["FareInfo"][0][
        "TPA_Extensions"]["Cabin"]["Cabin"] = "Q"
    response = shapes.InstaFlightsResponse.model_validate(
        {"PricedItineraries": [rich]}
    )
    option = flight_options._parse_instaflights_options(response, "JFK", "LAX")[0]
    assert option.cabin == "Q"


def test_fmt_duration():
    assert flight_options.fmt_duration(349) == "5h 49m"
    assert flight_options.fmt_duration(120) == "2h"
    assert flight_options.fmt_duration(45) == "45m"
    assert flight_options.fmt_duration(0) == "0m"


def test_airline_table_has_exactly_one_copy():
    """itinerary_ui's table is the flight_options object itself (Phase 33
    promotion) — no second dict to drift."""
    from api import itinerary_ui

    assert itinerary_ui._AIRLINE_NAMES is flight_options.AIRLINE_NAMES


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
