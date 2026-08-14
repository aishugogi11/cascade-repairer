"""Turn a trip PDF (or sample text) into Cascade itinerary items."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from api.repositories.models import ItineraryItem, Trip
from ml.transport.parse import (
    SAMPLE_ITINERARY,
    SAMPLE_NYC_BUSINESS,
    _decode_b64,
    extract_pdf_text,
    parse_text,
    parse_upload,
    venue_type,
)

_PACIFIC = ZoneInfo("America/Los_Angeles")
_AIRLINES = {
    "AA", "AS", "B6", "DL", "F9", "G4", "HA", "NK", "SY", "UA", "WN",
    "MX", "AM", "VS", "BA", "LH", "AF", "KL", "EI", "AC", "WS",
}
_FLIGHT = re.compile(
    r"\b(" + "|".join(sorted(_AIRLINES)) + r")\s*0*(\d{1,4})\b"
)
_ROUTE = re.compile(
    r"\b([A-Z]{3})\s*(?:-|–|—|to|→|>)\s*([A-Z]{3})\b"
)
_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_DATE = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|"
    r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)"
    r"\.?\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s*(20\d{2}))?\b",
    re.I,
)
_IATA = re.compile(r"\b([A-Z]{3})\b")
_AIRPORTS = {
    "SFO", "SJC", "OAK", "LAX", "SAN", "SEA", "PDX", "LAS", "PHX",
    "DEN", "DFW", "AUS", "IAH", "ORD", "MDW", "MSP", "DTW", "ATL",
    "MIA", "MCO", "FLL", "JFK", "LGA", "EWR", "BOS", "DCA", "IAD",
    "PHL", "CLT", "BNA", "SLC", "HNL",
}


def _base_date(text: str) -> date:
    matches = list(_DATE.finditer(text or ""))
    if matches:
        m = matches[0]
        month = _MONTHS[m.group(1).lower()]
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else date.today().year
        try:
            return date(year, month, day)
        except ValueError:
            pass
    today = date.today()
    return today + timedelta(days=(5 - today.weekday()) % 7 or 7)


def _ts(day: date, clock: str, day_offset: int = 0) -> datetime:
    hour, minute = (int(p) for p in clock.split(":"))
    d = day + timedelta(days=day_offset)
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=_PACIFIC)


def _duration_hours(kind: str) -> float:
    return {
        "flight": 4.0,
        "hotel": 18.0,
        "ground": 0.75,
        "dining": 1.5,
        "experience": 1.5,
    }.get(kind, 1.5)


def _kind_for_stop(title: str) -> str:
    v = venue_type(title)
    t = (title or "").lower()
    if v == "dining":
        return "dining"
    if v == "hotel":
        return "hotel"
    if any(w in t for w in ("uber", "lyft", "rideshare", "taxi", "ferry", "transfer")):
        return "ground"
    if v == "airport" or "flight" in t:
        return "flight"
    return "experience"


def _parse_flights(text: str, base: date) -> List[Dict[str, Any]]:
    flights: List[Dict[str, Any]] = []
    seen = set()
    for match in _FLIGHT.finditer(text or ""):
        airline, number = match.group(1), int(match.group(2))
        window = (text or "")[max(0, match.start() - 80): match.end() + 80]
        route = _ROUTE.search(window) or _ROUTE.search(text or "")
        origin = dest = None
        if route:
            origin, dest = route.group(1), route.group(2)
        else:
            codes = [c for c in _IATA.findall(window) if c in _AIRPORTS]
            if len(codes) >= 2:
                origin, dest = codes[0], codes[1]
        if not origin or not dest or origin == dest:
            continue
        key = (airline, number, origin, dest)
        if key in seen:
            continue
        seen.add(key)
        flights.append({
            "airline": airline,
            "flight_number": number,
            "origin": origin,
            "destination": dest,
            "start": _ts(base, "08:00"),
            "end": _ts(base, "12:00"),
        })
    return flights


def stops_to_items(
    trip_id: str,
    stops: List[Dict[str, Any]],
    flights: List[Dict[str, Any]],
    base: date,
) -> List[ItineraryItem]:
    items: List[ItineraryItem] = []
    hotel_span: Optional[Tuple[datetime, datetime, str]] = None

    for flight in flights:
        origin, dest = flight["origin"], flight["destination"]
        items.append(ItineraryItem(
            trip_id=trip_id,
            type="flight",
            status="booked",
            provider="sabre",
            provider_ref=f"PDF-{flight['airline']}{flight['flight_number']}",
            start_ts=flight["start"],
            end_ts=flight["end"],
            location=f"{origin}-{dest}",
            details={
                "title": f"{flight['airline']} {flight['flight_number']}",
                "airline": flight["airline"],
                "flight_number": flight["flight_number"],
            },
            price=None,
            currency="USD",
        ))

    for stop in stops:
        title = (stop.get("title") or "").strip()
        title = _FLIGHT.sub("", title)
        title = _ROUTE.sub("", title)
        title = re.sub(r"\s+", " ", title).strip(" -–—")
        if not title:
            continue
        kind = _kind_for_stop(title)
        if kind == "flight":
            if flights:
                continue
            kind = "ground"
        clock = stop.get("start_time") or "09:00"
        offset = int(stop.get("day") or 0)
        start = _ts(base, clock, offset)
        if kind == "hotel":
            loc = stop.get("location") or title
            if hotel_span is None:
                hotel_span = (start, start + timedelta(hours=18), loc)
            else:
                hotel_span = (hotel_span[0], start + timedelta(hours=4), hotel_span[2])
            continue
        items.append(ItineraryItem(
            trip_id=trip_id,
            type=kind,  # type: ignore[arg-type]
            status="booked",
            provider="other",
            provider_ref=f"PDF-{kind.upper()}",
            start_ts=start,
            end_ts=start + timedelta(hours=_duration_hours(kind)),
            location=stop.get("location") or title,
            details={"title": title},
            currency="USD",
        ))

    if hotel_span is not None:
        start, end, loc = hotel_span
        items.append(ItineraryItem(
            trip_id=trip_id,
            type="hotel",
            status="booked",
            provider="other",
            provider_ref="PDF-HOTEL",
            start_ts=start,
            end_ts=end,
            location=loc,
            details={"title": loc},
            currency="USD",
        ))

    items.sort(key=lambda i: i.start_ts or datetime.min.replace(tzinfo=_PACIFIC))
    return items[:24]


def _trip_fields(items: List[ItineraryItem], title: str, user_id: str) -> Trip:
    flights = [i for i in items if i.type == "flight"]
    origin = None
    dests: List[str] = []
    if flights and flights[0].location and "-" in flights[0].location:
        origin, dest = flights[0].location.split("-", 1)
        dests = [dest]
    if not dests:
        blob = " ".join(
            f"{i.location or ''} {(i.details or {}).get('title') or ''}"
            for i in items
        )
        codes = [c for c in _IATA.findall(blob.upper()) if c in _AIRPORTS]
        if codes:
            dests = [codes[-1]]
    starts = [i.start_ts.date() for i in items if i.start_ts]
    ends = [i.end_ts.date() for i in items if i.end_ts]
    return Trip(
        user_id=user_id,
        title=title,
        status="booked",
        origin=origin,
        destinations=dests,
        start_date=min(starts) if starts else None,
        end_date=max(ends) if ends else None,
    )


def build_from_upload(
    *,
    user_id: str,
    title: str,
    sample: bool = False,
    sample_kind: str = "",
    text: str = "",
    pdf_base64: str = "",
) -> Optional[Tuple[Trip, List[ItineraryItem]]]:
    parsed = parse_upload(
        text=text, pdf_base64=pdf_base64, sample=sample, sample_kind=sample_kind,
    )
    stops = parsed.get("stops") or []
    if (sample_kind or "").strip().lower() == "nyc":
        default_raw = SAMPLE_NYC_BUSINESS
    elif sample:
        default_raw = SAMPLE_ITINERARY
    else:
        default_raw = ""
    raw = parsed.get("raw_text") or text or default_raw
    if pdf_base64 and not raw:
        try:
            raw = extract_pdf_text(_decode_b64(pdf_base64))
        except Exception:  # noqa: BLE001
            raw = ""
    base = _base_date(raw)
    flights = _parse_flights(raw, base)
    if not stops and not flights:
        return None
    trip = Trip(user_id=user_id, title=title, status="booked")
    items = stops_to_items(trip.trip_id, stops, flights, base)
    if not items:
        return None
    filled = _trip_fields(items, title, user_id)
    filled.trip_id = trip.trip_id
    for item in items:
        item.trip_id = filled.trip_id
    return filled, items


def _flights_from_stops(
    stops: List[Dict[str, Any]], day0: date
) -> List[Dict[str, Any]]:
    """Recover Sabre-shaped flight rows from Optimize stop titles.

    Optimize parses "08:00 Flight UA 215 SFO-JFK" as a stop title. Without
    this, Cascade demotes it to a ground card titled "Flight" and loses
    the SFO → New York route on the trip header.
    """
    lines = []
    for stop in stops:
        clock = (stop.get("start_time") or "").strip()
        label = (stop.get("title") or stop.get("location") or "").strip()
        if label:
            lines.append(f"{clock} {label}".strip())
    flights = _parse_flights("\n".join(lines), day0)
    if not flights:
        return []
    for stop in stops:
        clock = (stop.get("start_time") or "").strip()
        label = (stop.get("title") or stop.get("location") or "").strip()
        if not clock or not label:
            continue
        match = _FLIGHT.search(label)
        route = _ROUTE.search(label)
        if not match or not route:
            continue
        airline, number = match.group(1), int(match.group(2))
        origin, dest = route.group(1), route.group(2)
        for flight in flights:
            if (
                flight["airline"] == airline
                and flight["flight_number"] == number
                and flight["origin"] == origin
                and flight["destination"] == dest
            ):
                try:
                    offset = int(stop.get("day") or 0)
                    flight["start"] = _ts(day0, clock, offset)
                    flight["end"] = (
                        flight["start"]
                        + timedelta(hours=_duration_hours("flight"))
                    )
                except Exception:  # noqa: BLE001
                    pass
                break
    return flights


def build_from_stops(
    *,
    user_id: str,
    title: str,
    stops: List[Dict[str, Any]],
    trip_id: str = "",
    base: Optional[date] = None,
) -> Optional[Tuple[Trip, List[ItineraryItem]]]:
    """Project already-parsed Optimize My Trip stops onto a Cascade trip."""
    if len(stops or []) < 2:
        return None
    trip = Trip(user_id=user_id, title=title, status="booked")
    if trip_id:
        trip.trip_id = trip_id
    day0 = base or date.today()
    flights = _flights_from_stops(list(stops), day0)
    items = stops_to_items(trip.trip_id, list(stops), flights, day0)
    if not items:
        return None
    filled = _trip_fields(items, title, user_id)
    filled.trip_id = trip.trip_id
    for item in items:
        item.trip_id = filled.trip_id
    return filled, items
