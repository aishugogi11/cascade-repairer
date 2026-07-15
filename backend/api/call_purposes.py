"""Call scripts composed from the real pinned trip's data — Phase 23.

Both demo calls speak the traveler's actual trip: Call 1 (the disruption
call) names the real route and asks for the traveler's consent to repair;
Call 2 (the results callback) is composed from the post-repair state, so
the phone agent's script *is* the live data. These replace the Phase 12
hardcoded Minneapolis→San Francisco narratives, which described the wrong
trip the moment booking went voice-first — a voice-booked JFK→LAX trip must
get calls about JFK→LAX.

Pure functions over already-loaded models — no IO, no env reads: callers
(the demo orchestrator, the consent/completion watchers) do the repository
reads off the event loop and pass the data in, so a purpose can never block
and never leaks anything transport-level. Spoken-copy rules apply: plain
city names, no airport codes, ids, or fare codes read aloud.
"""
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from api.concierge import _spoken_date
from api.flight_options import _PACIFIC
from api.repositories.models import ItineraryItem, Trip

# Airport code → spoken city name for the call scripts (the standing rule:
# a traveler-facing name, never a bare code). Covers the demo anchors and
# the larger US markets the live supported-pairs list carries; an unknown
# code falls back to itself — still functional, just less warm.
_CITY_NAMES = {
    "ATL": "Atlanta", "AUS": "Austin", "BNA": "Nashville", "BOS": "Boston",
    "BWI": "Baltimore", "CLT": "Charlotte", "DCA": "Washington",
    "DEN": "Denver", "DFW": "Dallas", "DTW": "Detroit", "EWR": "Newark",
    "FLL": "Fort Lauderdale", "HNL": "Honolulu", "IAD": "Washington",
    "IAH": "Houston", "JFK": "New York", "LAS": "Las Vegas",
    "LAX": "Los Angeles", "LGA": "New York", "MCO": "Orlando",
    "MIA": "Miami", "MSP": "Minneapolis", "OAK": "Oakland",
    "ORD": "Chicago", "PDX": "Portland", "PHL": "Philadelphia",
    "PHX": "Phoenix", "SAN": "San Diego", "SEA": "Seattle",
    "SFO": "San Francisco", "SJC": "San Jose", "SLC": "Salt Lake City",
    "TPA": "Tampa",
}

# Leg type → the spoken phrase for "the rest of the trip".
_LEG_PHRASES = {
    "hotel": "the hotel",
    "ground": "the airport ride",
    "dining": "the dinner reservation",
    "experience": "the tour",
}


def _city(code: Optional[str]) -> str:
    code = (code or "").strip().upper()
    return _CITY_NAMES.get(code, code) or "your city"


def _flight_route(
    flight: Optional[ItineraryItem], trip: Trip
) -> Tuple[str, str]:
    """(origin, destination) codes — the flight item's location ("JFK-LAX")
    first, the trip header as fallback. Either half may come back empty."""
    if flight and flight.location and "-" in flight.location:
        origin, _, dest = flight.location.partition("-")
        if origin and dest:
            return origin.strip(), dest.strip()
    dest = trip.destinations[0] if trip.destinations else ""
    return (trip.origin or ""), dest


def _spoken_route(flight: Optional[ItineraryItem], trip: Trip) -> str:
    """'from New York to Los Angeles', or a title fallback when the trip
    carries no route at all — the script must read either way."""
    origin, dest = _flight_route(flight, trip)
    if origin and dest:
        return f"from {_city(origin)} to {_city(dest)}"
    return f'for their trip "{trip.title}"'


def _pt_date(ts: datetime):
    """The flight's Pacific calendar date — the database stores UTC, the
    edges speak Pacific (the standing Phase 19 discipline)."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(_PACIFIC).date()


def _join_spoken(parts: List[str]) -> str:
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + f", and {parts[-1]}"


def _rest_of_trip(items: List[ItineraryItem]) -> str:
    """'the hotel, the airport ride, the dinner reservation, and the tour' —
    only the legs this trip actually has, in itinerary order."""
    seen = []
    for item in items:
        phrase = _LEG_PHRASES.get(item.type)
        if phrase and phrase not in seen:
            seen.append(phrase)
    return _join_spoken(seen)


def build_disrupt_purpose(trip: Trip, items: List[ItineraryItem]) -> str:
    """Call 1 — the disruption call. Names the real cancelled flight, then
    asks one clear consent question. The agent must not claim repairs are
    already running: nothing launches until the traveler's spoken yes (the
    consent watcher reads it from this call's transcript)."""
    flight = next((i for i in items if i.type == "flight"), None)
    route = _spoken_route(flight, trip)
    when = ""
    if flight and flight.start_ts:
        when = f" on {_spoken_date(_pt_date(flight.start_ts))}"
    rest = _rest_of_trip(items)
    recheck = (
        f"rebook the flight and recheck the rest of the trip — {rest} — "
        if rest
        else "rebook the flight "
    )
    return (
        "You are the traveler's AI travel agent, calling them proactively — "
        f"they do not know yet. Their flight {route}{when} was just "
        "cancelled by the airline. Tell them right away, calmly and "
        "concretely. You have NOT started any rebooking — you need their "
        f"go-ahead first. Ask one clear question: you can {recheck}"
        "but only once they say yes — for example, 'I can rebook it and "
        "recheck the rest of the trip — want me to?'. If they agree, tell "
        "them the repairs are starting right away and they can watch every "
        "piece flip to fixed on their live itinerary screen; you'll call "
        "back when it's done. If they decline, reassure them nothing will "
        "change without their say-so. Keep the call short."
    )


def _spoken_delta(price_delta: Optional[str]) -> str:
    """The detail payload's signed delta string ('+$23' / '-$15' / '$0') as
    a spoken clause about the fare."""
    if not price_delta or price_delta == "$0":
        return "at no change in fare"
    amount = price_delta.lstrip("+-")
    if price_delta.startswith("-"):
        return f"and it's {amount} cheaper than the original"
    return f"for {amount} more than the original fare"


def build_results_purpose(
    trip: Trip,
    items: List[ItineraryItem],
    details: Dict[str, dict],
) -> str:
    """Call 2 — the results callback, composed from the actual post-repair
    state (the items' live statuses plus the bookings-derived detail
    payload: why-chosen / price-delta / impact). Best-effort by contract:
    a missing detail degrades to a plainer sentence, never raises — a
    crashed callback is worse than a generic one."""
    flight = next((i for i in items if i.type == "flight"), None)
    route = _spoken_route(flight, trip)

    detail = details.get(flight.item_id, {}) if flight else {}
    why = (detail.get("why_chosen") or "").strip()
    if flight and flight.status == "fixed" and why:
        flight_line = (
            f"The flight is rebooked, {_spoken_delta(detail.get('price_delta'))}: "
            f"{why}"
        )
    elif flight and flight.status == "fixed":
        flight_line = "The flight is rebooked and confirmed."
    else:
        flight_line = (
            "The flight rebooking is still in progress — be honest about that."
        )

    unresolved = [
        _LEG_PHRASES.get(i.type, i.type)
        for i in items
        if i.type != "flight" and i.status in ("broken", "repairing")
    ]
    rest = _rest_of_trip([i for i in items if i.type != "flight"])
    if unresolved:
        rest_line = (
            f"Not everything is settled yet: {_join_spoken(unresolved)} "
            "still being worked on — say so honestly and promise the live "
            "itinerary screen will show it the moment it lands."
        )
    elif rest:
        rest_line = (
            f"The rest of the trip — {rest} — was re-checked against the "
            "new flight and everything is confirmed."
        )
    else:
        rest_line = "There was nothing else on the trip to re-check."

    return (
        "You are the traveler's AI travel agent, calling back with the "
        "results they asked for. Earlier their flight "
        f"{route} was cancelled and they gave you the go-ahead to fix the "
        f"trip. {flight_line} {rest_line} Tell them their live itinerary "
        "screen shows every detail, thank them for their patience, and "
        "wish them a great trip. Keep the call short and warm — plain "
        "words, no booking codes or ids."
    )


def build_book_purpose(title: str, seed_items: List[dict]) -> str:
    """Beat 1's call script, derived from the same seed data the backend is
    about to write (sabre_tools._SEED_ITEMS) — voice and screen tell the
    same story because they share a source, not because the prose was kept
    in sync by hand. seed_items is passed in (not imported) so the builder
    stays a pure function and the orchestrator keeps owning the seed shape."""
    by_type = {}
    for seed in seed_items:
        by_type.setdefault(seed["type"], seed)

    flight = by_type.get("flight", {})
    origin, _, dest = (flight.get("location") or "-").partition("-")
    flight_when = (
        f" on the morning of {_spoken_date(flight['start'].date())}"
        if flight.get("start")
        else ""
    )
    hotel = by_type.get("hotel", {})
    hotel_clause = (
        f"a hotel in {hotel['location']}"
        + (f" through {_spoken_date(hotel['end'].date())}" if hotel.get("end") else "")
        if hotel.get("location")
        else "a hotel"
    )
    experience = by_type.get("experience", {})
    tour_clause = (
        f"a {experience['location']} tour"
        + (
            f" on {_spoken_date(experience['start'].date())}"
            if experience.get("start")
            else ""
        )
        if experience.get("location")
        else "a tour"
    )
    return (
        "You are the traveler's AI travel agent calling with good news "
        f'about their trip "{title}". Their complete trip is now booked: '
        f"a flight from {_city(origin)} to {_city(dest)}{flight_when}, "
        f"{hotel_clause}, a ride from the airport, dinner that evening, "
        f"and {tour_clause}. Walk them through it briefly and warmly, tell "
        "them every detail is on their live itinerary screen, and wish "
        "them a great trip. Keep the call short."
    )
