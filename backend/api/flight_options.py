"""Shared InstaFlights parsing — the guided-booking search (concierge) and
the flight-repair re-shop (repair_tools) both speak real InstaFlights data,
so the parser and its FlightOption shape live here, importable by both
without a cycle.

concierge imports sabre_tools (launch_trip_repairs) and sabre_tools imports
repair_tools, so repair_tools importing concierge for the parser would cycle
(repair_tools -> concierge -> sabre_tools -> repair_tools). This module
imports only sabre.shapes, sabre.airport_tz, pydantic, and datetime — no
concierge/sabre_tools/repair_tools — so both callers import it freely
(Phase 29, decision 1).

All dates and times a FlightOption carries are Pacific: converted from
offset-less airport-local upstream in real mode, declared-Pacific fiction in
mock mode (the Phase 19 discipline).
"""
from datetime import date, datetime
from typing import Dict, List, Set, Tuple
from zoneinfo import ZoneInfo

from pydantic import BaseModel, model_validator

from api.sabre import shapes
from api.sabre.airport_tz import airport_zone

# Everything displayed or spoken to a user is Pacific time (decision
# 2026-07-12): mock wall-clock times are *declared* Pacific here, and
# BigQuery TIMESTAMP stores the honest UTC instant on write.
_PACIFIC = ZoneInfo("America/Los_Angeles")

# Speakable option numbers — spoken copy never uses digits-as-labels.
_NUMBER_WORDS = {1: "one", 2: "two", 3: "three"}

_MAX_SPOKEN_OPTIONS = 3

# Airline code -> spoken/displayed name (Phase 33). Static table, never a
# live lookup (the AIRPORT_TZ pattern): zero demo-day calls, works in mock
# mode. Promoted here from itinerary_ui so there is exactly one copy —
# itinerary_ui imports it. Carriers InstaFlights actually returns; an
# unknown code falls back to the bare code via airline_name().
AIRLINE_NAMES = {
    "AA": "American", "DL": "Delta", "UA": "United", "B6": "JetBlue",
    "WN": "Southwest", "AS": "Alaska", "NK": "Spirit", "F9": "Frontier",
    "HA": "Hawaiian", "G4": "Allegiant",
}

# Booking-class letter -> conversational cabin name (Phase 33, from the
# sabre_endpoints notebook). Unknown letters display as themselves —
# degraded, not broken.
CABIN_NAMES = {
    "Y": "Economy", "S": "Economy", "B": "Economy", "M": "Economy",
    "W": "Premium Economy",
    "C": "Business", "J": "Business", "D": "Business", "I": "Business",
    "F": "First Class", "A": "First Class", "P": "First Class",
}


def airline_name(code: str) -> str:
    """Spoken/displayed carrier name for an IATA code; the bare code when
    the table doesn't know it."""
    return AIRLINE_NAMES.get((code or "").strip().upper(), code)


def fmt_duration(minutes: int) -> str:
    """349 -> '5h 49m'; whole hours drop the minutes ('2h')."""
    hours, mins = minutes // 60, minutes % 60
    if hours and mins:
        return f"{hours}h {mins}m"
    if hours:
        return f"{hours}h"
    return f"{mins}m"


class FlightOption(BaseModel):
    """One speakable flight choice, parsed from an InstaFlights itinerary
    (Phase 27; the mock serves the same shape). `spoken` is the clause the
    agent reads aloud; the structured fields feed the booking rows (and the
    status endpoint's detail payload). All dates and times are Pacific —
    converted from airport-local upstream in real mode, declared-Pacific
    fiction in mock mode (the Phase 19 discipline)."""

    option_number: int
    airline: str
    flight_number: int
    origin: str
    destination: str
    depart_date: str  # YYYY-MM-DD
    depart_time: str  # HH:MM
    arrive_time: str  # HH:MM
    # PT arrival date — a converted red-eye can land the next PT day.
    # Defaults to depart_date so pre-Phase-27 construction sites and stored
    # payloads stay valid (additive change).
    arrive_date: str = ""
    stops: int
    price: float
    currency: str
    spoken: str
    # Rich fields (Phase 33) — all additive with safe defaults so stored
    # booking payloads (raw_response.option) and pre-33 construction sites
    # stay valid, the arrive_date precedent. Upstream fields missing from a
    # real itinerary degrade to these defaults; the option is still offered.
    airline_name: str = ""  # "Delta"; falls back to the code upstream
    cabin: str = ""  # "Economy" / "Business" / ...; "" = unknown
    duration_minutes: int = 0  # whole journey incl. layovers; 0 = unknown
    layover_airports: List[str] = []  # via codes; [] when nonstop
    arrives_next_day: bool = False  # PT arrival date past the PT depart date

    @model_validator(mode="after")
    def _arrive_date_defaults_to_depart_date(self):
        if not self.arrive_date:
            self.arrive_date = self.depart_date
        return self


def details_from_option(option: FlightOption) -> dict:
    """The flight item's `details` stamp, shared by the initial booking
    (concierge._booking_writes) and the repair write-back
    (repair_tools._rebook_flight) so the key sets cannot drift (Phase 33):
    the repair replaces `details` WHOLESALE (Phase 32), so any key stamped
    only at booking would be wiped from the card by the first repair.
    `airline`/`flight_number` are the Phase 31 exclusion identity —
    byte-identical to the pre-33 stamp. The repair path adds
    `rebooked_from` on top of this dict."""
    return {
        "airline": option.airline,
        "flight_number": option.flight_number,
        "airline_name": option.airline_name or airline_name(option.airline),
        "cabin": option.cabin,
        "duration_minutes": option.duration_minutes,
        "layover_airports": option.layover_airports,
        "arrives_next_day": option.arrives_next_day,
        "stops": option.stops,
    }


def option_timestamps(option: FlightOption) -> Tuple[datetime, datetime]:
    """A chosen option's PT departure/arrival instants for an
    itinerary_items row (start_ts/end_ts) — the arrival gets its own PT
    date, not the departure's: a converted red-eye lands the next PT day,
    and end_ts must never precede start_ts. Extracted from
    concierge._booking_writes (Phase 32) so the repair write-back computes
    the row exactly the way the original booking did."""
    depart = date.fromisoformat(option.depart_date)
    arrive = date.fromisoformat(option.arrive_date or option.depart_date)
    dep_h, dep_m = int(option.depart_time[:2]), int(option.depart_time[3:5])
    arr_h, arr_m = int(option.arrive_time[:2]), int(option.arrive_time[3:5])
    start_ts = datetime(depart.year, depart.month, depart.day, dep_h, dep_m,
                        tzinfo=_PACIFIC)
    end_ts = datetime(arrive.year, arrive.month, arrive.day, arr_h, arr_m,
                      tzinfo=_PACIFIC)
    return start_ts, end_ts


def _spoken_clock(time_str: str) -> str:
    """'08:00:00-05:00' (or '08:00') -> '8 AM' / '11:30 AM' — times are read
    aloud, never 24-hour."""
    hour, minute = int(time_str[:2]), int(time_str[3:5])
    ampm = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    return f"{hour12}:{minute:02d} {ampm}" if minute else f"{hour12} {ampm}"


def _spoken_option(option_number: int, carrier: str, stops: int, depart: str,
                   arrive: str, price: float) -> str:
    """One listenable clause: short, price rounded, airline NAME only —
    codes and fare-class letters are never spoken (the standing spoken-copy
    rule; Phase 33 added the name, nothing else — duration/cabin/layovers
    stay on-request so three options don't kill the pacing)."""
    word = _NUMBER_WORDS.get(option_number, str(option_number))
    legs = "nonstop" if stops == 0 else ("one stop" if stops == 1 else f"{stops} stops")
    return (
        f"Option {word} on {carrier}: {legs}, leaves at {_spoken_clock(depart)} "
        f"and lands at {_spoken_clock(arrive)}, about {round(price)} dollars."
    )


def _parse_instaflights_options(
    search: shapes.InstaFlightsResponse, origin: str, destination: str,
    max_options: int = _MAX_SPOKEN_OPTIONS,
) -> List[FlightOption]:
    """Walk PricedItineraries in response order into at most `max_options`
    speakable options (default _MAX_SPOKEN_OPTIONS — the repair re-shop's
    unchanged contract; the concierge passes a larger pool ceiling and
    applies select_airline_diverse on the result, Phase 41).

    InstaFlights times are offset-less airport-local, so each end is
    localized to its own airport's zone and converted to Pacific before
    anything is spoken or stored (the Phase 19 discipline — speaking
    '2026-XX-XXT07:20:00' at JFK as Pacific would be the old bug class).
    An itinerary touching ANY airport missing from the timezone table —
    connections included, not just the endpoints — is skipped in favor of
    the next (requirements, decision 2 of Phase 27; the Phase 28 fix) —
    never a mangled time. Byte-identical itineraries are offered once:
    CERT has returned duplicates, and the agent read 'option three is the
    same as option two' aloud (Phase 28, decision 5)."""
    options: List[FlightOption] = []
    offered: Set[Tuple] = set()
    for itinerary in search.PricedItineraries:
        if len(options) >= max_options:
            break
        od_option = (
            itinerary.AirItinerary.OriginDestinationOptions
            .OriginDestinationOption[0]
        )
        segments = od_option.FlightSegment
        if not segments:
            continue
        if any(
            airport_zone(seg.DepartureAirport.LocationCode) is None
            or airport_zone(seg.ArrivalAirport.LocationCode) is None
            for seg in segments
        ):
            continue
        first, last = segments[0], segments[-1]
        depart_zone = airport_zone(first.DepartureAirport.LocationCode)
        arrive_zone = airport_zone(last.ArrivalAirport.LocationCode)
        fare = itinerary.AirItineraryPricingInfo.ItinTotalFare.TotalFare
        key = (
            first.FlightNumber, first.DepartureDateTime,
            last.ArrivalDateTime, fare.Amount,
        )
        if key in offered:
            continue
        offered.add(key)
        depart_pt = (
            datetime.fromisoformat(first.DepartureDateTime)
            .replace(tzinfo=depart_zone).astimezone(_PACIFIC)
        )
        arrive_pt = (
            datetime.fromisoformat(last.ArrivalDateTime)
            .replace(tzinfo=arrive_zone).astimezone(_PACIFIC)
        )
        # Connections count as stops too: segment-internal StopQuantity
        # plus one per plane change.
        stops = sum(seg.StopQuantity for seg in segments) + len(segments) - 1
        # Rich fields (Phase 33) — all degrade to defaults when the response
        # omits them; a missing garnish field never skips an itinerary
        # (contrast the timezone check above, which is correctness).
        carrier = airline_name(first.MarketingAirline.Code)
        cabin_letter = ""
        fare_infos = itinerary.AirItineraryPricingInfo.FareInfos
        if fare_infos and fare_infos.FareInfo:
            tpa = fare_infos.FareInfo[0].TPA_Extensions
            if tpa and tpa.Cabin:
                cabin_letter = tpa.Cabin.Cabin.strip().upper()
        cabin = CABIN_NAMES.get(cabin_letter, cabin_letter)
        number = len(options) + 1
        options.append(
            FlightOption(
                option_number=number,
                airline=first.MarketingAirline.Code,
                flight_number=first.FlightNumber,
                origin=origin,
                destination=destination,
                depart_date=depart_pt.strftime("%Y-%m-%d"),
                depart_time=depart_pt.strftime("%H:%M"),
                arrive_time=arrive_pt.strftime("%H:%M"),
                arrive_date=arrive_pt.strftime("%Y-%m-%d"),
                stops=stops,
                price=fare.Amount,
                currency=fare.CurrencyCode,
                spoken=_spoken_option(
                    number, carrier, stops, depart_pt.strftime("%H:%M"),
                    arrive_pt.strftime("%H:%M"), fare.Amount,
                ),
                airline_name=carrier,
                cabin=cabin,
                duration_minutes=od_option.ElapsedTime or 0,
                layover_airports=[
                    seg.ArrivalAirport.LocationCode for seg in segments[:-1]
                ],
                arrives_next_day=(
                    arrive_pt.date() != depart_pt.date()
                ),
            )
        )
    return options


def _fare_depart_key(option: FlightOption) -> Tuple[float, str, str]:
    """Cheapest-first, tie-break earliest PT departure. The date/time
    strings are zero-padded PT, so lexicographic compare is chronological."""
    return (option.price, option.depart_date, option.depart_time)


def select_airline_diverse(
    options: List[FlightOption], max_airlines: int = _MAX_SPOKEN_OPTIONS,
) -> List[FlightOption]:
    """Phase 41: from a parsed pool, one option per distinct airline — each
    carrier's cheapest itinerary (tie: earliest PT departure), spoken
    cheapest-representative first, at most `max_airlines` airlines. Applied
    only by the guided-booking search (concierge); the repair re-shop never
    calls this — its closest-arrival pick is a different contract.

    A single-carrier pool degrades to the pre-41 behavior exactly: the
    first `max_airlines` options in response order, numbering untouched.
    Selected options are renumbered 1..N with `spoken` regenerated so
    'option one/two' always matches the offered list; every other field
    carries over unchanged."""
    if len({option.airline for option in options}) <= 1:
        return options[:max_airlines]
    best: Dict[str, FlightOption] = {}
    for option in options:
        current = best.get(option.airline)
        if current is None or _fare_depart_key(option) < _fare_depart_key(current):
            best[option.airline] = option
    representatives = sorted(best.values(), key=_fare_depart_key)[:max_airlines]
    selected = []
    for number, option in enumerate(representatives, start=1):
        carrier = option.airline_name or airline_name(option.airline)
        selected.append(option.model_copy(update={
            "option_number": number,
            "spoken": _spoken_option(
                number, carrier, option.stops, option.depart_time,
                option.arrive_time, option.price,
            ),
        }))
    return selected
