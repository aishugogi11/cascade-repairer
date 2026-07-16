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
from typing import List, Set, Tuple
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

    @model_validator(mode="after")
    def _arrive_date_defaults_to_depart_date(self):
        if not self.arrive_date:
            self.arrive_date = self.depart_date
        return self


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


def _spoken_option(option_number: int, stops: int, depart: str, arrive: str,
                   price: float) -> str:
    """One listenable clause: short, price rounded, no airline or fare codes
    (the standing spoken-copy rule)."""
    word = _NUMBER_WORDS.get(option_number, str(option_number))
    legs = "nonstop" if stops == 0 else ("one stop" if stops == 1 else f"{stops} stops")
    return (
        f"Option {word}: {legs}, leaves at {_spoken_clock(depart)} and lands "
        f"at {_spoken_clock(arrive)}, about {round(price)} dollars."
    )


def _parse_instaflights_options(
    search: shapes.InstaFlightsResponse, origin: str, destination: str,
) -> List[FlightOption]:
    """Walk PricedItineraries in response order into at most
    _MAX_SPOKEN_OPTIONS speakable options.

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
        if len(options) >= _MAX_SPOKEN_OPTIONS:
            break
        segments = (
            itinerary.AirItinerary.OriginDestinationOptions
            .OriginDestinationOption[0].FlightSegment
        )
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
                    number, stops, depart_pt.strftime("%H:%M"),
                    arrive_pt.strftime("%H:%M"), fare.Amount,
                ),
            )
        )
    return options
