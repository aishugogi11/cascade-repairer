"""Concierge hybrid architecture — Phase 9, the demo architecture.

The foreground half of the hybrid: a fast agent that answers every spoken
turn behind the web_call /query seam while background repairs run on the
same loop. The inversion (from the Phase 5 spike, concurrency_agent.py) is
the whole architecture: the fix_trip tool *launches* the real repair cascade
via launch_trip_repairs and returns immediately — repairs are never awaited
on the turn path, so the traveler keeps a conversation while five BigQuery
lifecycles run in parallel.

Each turn rebuilds the agent so its instructions carry a fresh session
snapshot of pending/finished repairs (per-turn build, not once — the Phase 5
finding: the snapshot must be marked authoritative or the model asks
clarifying questions instead of answering "how are the repairs coming?").
The VB session name is the concurrency session id, so the snapshot, the
event log, and the voice session are one thing.

Trip context (QA addendum, 2026-07-09; narrowed by Phase 18): a trip pins
to the session only on an explicit trip_id (ensure_trip_context's
parameter, the Phase 12 seam) or when book_flight re-pins the trip it just
created — a fresh session stays unpinned so guided booking is reachable.
Once pinned, static facts come from that one read, cached in process and
injected into every turn's instructions; live repair progress comes only
from the in-memory snapshot — so no BigQuery read ever lands on the
per-turn hot path after the pin, and a mid-call seed of a new trip cannot
switch the agent's trip.

Session history is an in-process dict (single Cloud Run instance — the
standing scope decision); blocking BigQuery reads go through
asyncio.to_thread.
"""
import asyncio
import logging
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

from agents import Agent, Runner, function_tool
from pydantic import BaseModel, model_validator

from api import concurrency_core as core
from api.concurrency_agent import session_snapshot
from api.repositories import bookings, itinerary_items, trips
from api.repositories.models import Booking, ItineraryItem, Trip
from api.sabre import client as sabre_client
from api.sabre import shapes
from api.sabre.airport_tz import airport_zone
from api.sabre_tools import launch_trip_repairs

logger = logging.getLogger(__name__)

DEFAULT_LLM_MODEL = "gpt-5.4-mini"

# Everything displayed or spoken to a user is Pacific time (decision
# 2026-07-12): mock wall-clock times are *declared* Pacific here, and
# BigQuery TIMESTAMP stores the honest UTC instant on write.
_PACIFIC = ZoneInfo("America/Los_Angeles")

# The self-identification is the live proof answers come from this backend
# (the Phase 8 manual check); the disruption/launch rules are the Concierge.
BASE_INSTRUCTIONS = (
    "You are the Cascade Repairer concierge — a traveler's live voice travel "
    "assistant, running inside the vocal-bridge-be-dev service on Google "
    "Cloud Run. If asked who you are or where you run, say exactly that. "
    "When the traveler reports a disruption (a cancelled flight, a broken "
    "trip, 'fix my trip'), call the fix_trip tool immediately — it launches "
    "every repair in the background and returns at once. Never wait silently "
    "for repairs to finish and never refuse other questions while they run; "
    "keep helping. You cannot send notifications or follow up on your own — "
    "never promise to 'let them know' when something finishes; instead "
    "invite the traveler to ask again in a moment. When there is no booked "
    "trip and the traveler wants to plan or book one, follow the guided "
    "flow: confirm the destination and departure date in one short turn, "
    "then call search_flights — origin airport code (assume MSP unless the "
    "traveler says otherwise), destination airport code, and the departure "
    "date as YYYY-MM-DD; turn city names into airport codes yourself. Read "
    "the options back and ask the traveler to pick one by number. When they "
    "choose, call book_flight with that option number and confirm the "
    "booking in one short sentence, then offer to arrange the rest of the "
    "trip; when they agree, call complete_trip and tell them the pieces are "
    "being added now. Never call search_flights or book_flight when a trip "
    "is already booked; offer fix_trip or answer questions about the "
    "existing trip instead. Your replies are spoken "
    "aloud: one or two short, conversational sentences. No markdown, no "
    "lists, no stage directions, and never speak ids or tool names. "
)

_NO_TRIP_LINE = (
    "There is no booked trip on file for this traveler yet — say so plainly "
    "if asked about trip details. "
)

# The speakable reply for a session with no pinned trip — one line shared by
# the unpinned and trip-not-found paths so fix_trip answers the same either way.
_NO_TRIP_SPOKEN = "I don't see a booked trip for you yet."

# session_name -> Agents SDK input list (multi-turn memory).
_HISTORY: Dict[str, List] = {}


def _llm_model() -> str:
    return os.environ.get("CONCIERGE_LLM_MODEL", DEFAULT_LLM_MODEL)


class TripContext(BaseModel):
    """A session's pinned trip: the one BigQuery read, kept in process."""

    trip: Trip
    items: List[ItineraryItem]
    summary: str


# session_name -> pinned trip. A trip pins in exactly two cases: an explicit
# trip_id (the Phase 12 disrupt seam) or book_flight re-pinning the trip it
# just created — a fresh session stays unpinned (Phase 18). Pinned once per
# session so a mid-call seed of a new trip can't switch the agent's trip, and
# no turn after the first pays a BigQuery read for context.
_SESSION_TRIPS: Dict[str, TripContext] = {}


def _trip_summary(trip: Trip, items: List[ItineraryItem]) -> str:
    """Static trip facts for the instructions — authoritative, like the
    repair snapshot (the measured Phase 5 wording rule). Statuses are
    deliberately absent: live progress belongs to the snapshot."""
    destinations = ", ".join(trip.destinations) if trip.destinations else "unknown"
    dates = (
        f"{trip.start_date} to {trip.end_date}"
        if trip.start_date and trip.end_date
        else "dates unknown"
    )
    parts = "; ".join(
        f"{item.type}" + (f" ({item.location})" if item.location else "")
        for item in items
    )
    return (
        "TRIP CONTEXT (authoritative — this IS the traveler's booked trip; "
        "answer where/when/what questions about it directly, never say you "
        f"lack their itinerary): '{trip.title}' from {trip.origin or 'unknown'} "
        f"to {destinations}, {dates}. Parts: {parts}. Live repair progress "
        "comes only from the LIVE STATUS section, not from here. "
    )


async def ensure_trip_context(
    session_id: str, trip_id: Optional[str] = None
) -> Tuple[Optional[TripContext], Optional[str]]:
    """Resolve and pin the session's trip on first call; cached afterwards.
    Returns (context, speakable_error) — at most one is set, and a failed
    resolution is never cached, so the next turn retries.

    trip_id is the Phase 12 seam: the disruption/outbound-call flow knows
    exactly which trip broke and pins it explicitly (book_flight re-pins its
    new trip through the same parameter). Without it, the session stays
    unpinned — no fallback read. The old latest-trip fallback shadowed every
    fresh session with someone else's trip and made guided booking
    unreachable (Phase 18)."""
    context = _SESSION_TRIPS.get(session_id)
    if context is not None:
        return context, None
    if not trip_id:
        return None, _NO_TRIP_SPOKEN

    success, trip, _error = await asyncio.to_thread(trips.get_trip, trip_id)
    if not success:
        return None, (
            "I'm having trouble reaching the booking system right now — "
            "give me a second and ask me again."
        )
    if trip is None:
        return None, _NO_TRIP_SPOKEN

    success, items, _error = await asyncio.to_thread(
        itinerary_items.list_items_for_trip, trip.trip_id
    )
    if not success:
        return None, (
            "I found your trip but can't read its details right now — "
            "give me a second and ask me again."
        )
    if not items:
        return None, "Your trip doesn't have any bookings on it yet."

    context = TripContext(trip=trip, items=items, summary=_trip_summary(trip, items))
    _SESSION_TRIPS[session_id] = context
    return context, None


async def fix_trip_impl(session_id: str) -> str:
    """Launch the repair cascade for the traveler's trip — the tool body,
    kept a plain function for tests (the hello.py pattern).

    Fires one background repair per itinerary item through the same seam as
    /repair_trip and returns immediately with a speakable summary; the tasks
    report into this session's event log as they land. Items come from the
    session's pinned trip. Failures return speakable strings — a tool that
    raises would kill the spoken turn."""
    try:
        context, speakable_error = await ensure_trip_context(session_id)
        if speakable_error:
            return speakable_error
        launched, _tasks = launch_trip_repairs(session_id, context.items)
    except Exception:  # noqa: BLE001 — the voice turn must survive anything
        return (
            "Something went wrong starting the repairs — give me a second "
            "and ask me again."
        )
    categories = ", ".join(name.replace("_", " ") for name in launched)
    return (
        f"Repairs are launched and running in the background for all "
        f"{len(launched)} parts of the trip ({categories}). They will "
        "finish on their own — keep talking with the traveler and answer "
        "progress questions from your live status."
    )


def _spoken_date(d) -> str:
    """'July 17th' — dates are read aloud, never ISO."""
    day = d.day
    if 11 <= day % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{d.strftime('%B')} {day}{suffix}"


# --- guided booking (Phase 17) — search → options → book → complete -----------


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


# session_name -> the options the agent just offered (the _SESSION_TRIPS
# pattern: in-process, single-instance by standing decision). Replaced on
# every search, cleared by a successful booking.
_SESSION_FLIGHT_OPTIONS: Dict[str, List[FlightOption]] = {}


class LatestSearch(BaseModel):
    """The most recent search, bridged for the booking page (Phase 21):
    _SESSION_FLIGHT_OPTIONS is session-keyed and the trip doesn't exist until
    book_flight, so the trip-keyed status endpoint needs this one slot to
    surface what the Concierge just offered."""

    session_id: str
    options: List[FlightOption]
    recorded_at: datetime


# Written by search_flights_impl alongside _SESSION_FLIGHT_OPTIONS, cleared
# by book_flight_impl on a successful booking. One slot, not per-session:
# with two simultaneous unpinned conversations an unrelated trip's poll could
# briefly show the other session's candidates — accepted demo-grade looseness
# for a single-operator demo.
_LATEST_SEARCH: Optional[LatestSearch] = None

# Strong refs so the complete_trip background task isn't garbage-collected
# (the web_call._LOG_TASKS pattern).
_BUILD_TASKS: Set[asyncio.Task] = set()

# Seam for tests to observe the item spacing without waiting wall-clock time.
_sleep = asyncio.sleep

# Speakable option numbers — spoken copy never uses digits-as-labels.
_NUMBER_WORDS = {1: "one", 2: "two", 3: "three"}

_MAX_SPOKEN_OPTIONS = 3

_SEARCH_ERROR_LINE = (
    "I'm having trouble searching flights right now — give me a second and "
    "ask me again."
)

# The speakable redirect for a city pair the demo system's search doesn't
# carry (requirements, decision 4) — an honest answer, not an error, so no
# silent mock swap and no apology for anything technical.
_UNSUPPORTED_MARKET_LINE = (
    "I can't search that route in the demo system — want to try another "
    "one, something like San Francisco to New York?"
)


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
    An airport missing from the timezone table skips that itinerary in
    favor of the next (requirements, decision 2) — never a mangled time."""
    options: List[FlightOption] = []
    for itinerary in search.PricedItineraries:
        if len(options) >= _MAX_SPOKEN_OPTIONS:
            break
        segments = (
            itinerary.AirItinerary.OriginDestinationOptions
            .OriginDestinationOption[0].FlightSegment
        )
        if not segments:
            continue
        first, last = segments[0], segments[-1]
        depart_zone = airport_zone(first.DepartureAirport.LocationCode)
        arrive_zone = airport_zone(last.ArrivalAirport.LocationCode)
        if depart_zone is None or arrive_zone is None:
            continue
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
        fare = itinerary.AirItineraryPricingInfo.ItinTotalFare.TotalFare
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


async def search_flights_impl(
    session_id: str, origin: str, destination: str, depart_date: str
) -> str:
    """Search flights and offer 2–3 options by voice — the tool body, kept a
    plain function for tests (the fix_trip_impl pattern). Stores the options
    per session so book_flight can resolve 'option one'. Every failure path
    returns a speakable string — a raising tool kills the spoken turn."""
    origin = (origin or "").strip().upper()
    destination = (destination or "").strip().upper()
    depart_date = (depart_date or "").strip()
    if not origin or not destination or not depart_date:
        return (
            "I need the destination and a departure date to search — where "
            "are you headed, and when?"
        )
    try:
        # Best-effort market check (requirements, decision 4): a pair the
        # sandbox doesn't carry gets the honest redirect instead of a search
        # that can only mock-swap. None (mock mode, or the fetch failed)
        # means skip validation and search anyway.
        markets = await sabre_client.supported_markets()
        if markets and (origin, destination) not in markets:
            return _UNSUPPORTED_MARKET_LINE
        search = await sabre_client.instaflights_search(
            shapes.InstaFlightsRequest(
                origin=origin,
                destination=destination,
                departuredate=depart_date,
            )
        )
        options = _parse_instaflights_options(search, origin, destination)
    except Exception:  # noqa: BLE001 — the voice turn must survive anything
        return _SEARCH_ERROR_LINE
    if not options:
        return (
            "I couldn't find any flights for that day — want to try a "
            "different date?"
        )

    _SESSION_FLIGHT_OPTIONS[session_id] = options
    global _LATEST_SEARCH
    _LATEST_SEARCH = LatestSearch(
        session_id=session_id,
        options=options,
        recorded_at=datetime.now(timezone.utc),
    )
    count_word = {2: "two", 3: "three"}.get(len(options), str(len(options)))
    spoken = " ".join(option.spoken for option in options)
    if len(options) == 1:
        return (
            f"I found one flight. {spoken} Should I book it? Just say "
            "option one."
        )
    return (
        f"I found {count_word} good options. {spoken} Which one would "
        "you like?"
    )


def _booking_writes(option: FlightOption, options_offered: List[FlightOption]):
    """The three blocking repository writes plus the booked flip — one plain
    function so book_flight_impl can push it off the loop in one to_thread
    hop. Raises on the first failed write."""
    depart = date.fromisoformat(option.depart_date)
    trip = Trip(
        user_id="demo-traveler",
        title=f"Trip to {option.destination}",
        status="booked",
        origin=option.origin,
        destinations=[option.destination],
        start_date=depart,
        # The guided flow books the outbound flight; the demo trip keeps the
        # seed shape's two-night span for the rest of the itinerary.
        end_date=depart + timedelta(days=2),
    )
    success, _, error = trips.create_trip(trip)
    if not success:
        raise RuntimeError(f"trip insert failed: {error}")

    dep_h, dep_m = int(option.depart_time[:2]), int(option.depart_time[3:5])
    arr_h, arr_m = int(option.arrive_time[:2]), int(option.arrive_time[3:5])
    # The arrival's own PT date, not the departure's: a converted red-eye
    # lands the next PT day, and end_ts must never precede start_ts.
    arrive = date.fromisoformat(option.arrive_date or option.depart_date)
    item = ItineraryItem(
        trip_id=trip.trip_id,
        type="flight",
        status="planned",
        provider="sabre",
        provider_ref=f"VOICE-FLIGHT-{uuid.uuid4().hex[:6].upper()}",
        start_ts=datetime(depart.year, depart.month, depart.day, dep_h, dep_m,
                          tzinfo=_PACIFIC),
        end_ts=datetime(arrive.year, arrive.month, arrive.day, arr_h, arr_m,
                        tzinfo=_PACIFIC),
        location=f"{option.origin}-{option.destination}",
        price=option.price,
        currency=option.currency,
    )
    success, _, error = itinerary_items.create_item(item)
    if not success:
        raise RuntimeError(f"flight item insert failed: {error}")

    booking = Booking(
        item_id=item.item_id,
        trip_id=trip.trip_id,
        sabre_confirmation_ref=item.provider_ref,
        state="confirmed",
        # The chosen option plus what it beat — the status endpoint's detail
        # payload (why chosen / price delta) derives from this.
        raw_response={
            "source": "voice_guided_booking",
            "option": option.model_dump(),
            "options_offered": [o.model_dump() for o in options_offered],
        },
    )
    success, _, error = bookings.create_booking(booking)
    if not success:
        raise RuntimeError(f"flight booking insert failed: {error}")

    # The booking write landed — the planned flight is now booked.
    success, affected, error = itinerary_items.update_status(
        item.item_id, "booked"
    )
    if not success or affected == 0:
        raise RuntimeError(f"flight status flip failed: {error}")
    return trip


async def book_flight_impl(session_id: str, option_number: int) -> str:
    """Book one of the offered options by number — the tool body, kept a
    plain function for tests. Creates the Trip + flight item + booking rows,
    replaces the session's pinned trip (ensure_trip_context caches the pin
    for the session's life), and clears the offered options. Failures return
    speakable strings — a tool that raises kills the spoken turn."""
    options = _SESSION_FLIGHT_OPTIONS.get(session_id)
    if not options:
        return (
            "I don't have flight options in front of me yet — tell me where "
            "you're headed and I'll search first."
        )
    if not isinstance(option_number, int) or not 1 <= option_number <= len(options):
        count_word = _NUMBER_WORDS.get(len(options), str(len(options)))
        return (
            f"I only offered {count_word} options — which number would "
            "you like?"
        )
    option = options[option_number - 1]

    try:
        trip = await asyncio.to_thread(_booking_writes, option, options)
    except Exception:  # noqa: BLE001 — the voice turn must survive anything
        return (
            "I couldn't get that flight booked just now — give me a second "
            "and ask me again."
        )

    # The booking is real from here on; replace the pin so this session's
    # remaining turns answer from the new trip, and drop the spent options.
    _SESSION_FLIGHT_OPTIONS.pop(session_id, None)
    global _LATEST_SEARCH
    if _LATEST_SEARCH is not None and _LATEST_SEARCH.session_id == session_id:
        _LATEST_SEARCH = None
    _SESSION_TRIPS.pop(session_id, None)
    await ensure_trip_context(session_id, trip_id=trip.trip_id)

    depart = date.fromisoformat(option.depart_date)
    legs = "nonstop" if option.stops == 0 else "with a stop"
    return (
        f"Done — your flight to {option.destination} is booked, {legs}, "
        f"leaving {_spoken_date(depart)} at "
        f"{_spoken_clock(option.depart_time)}. Want me to arrange the rest "
        "of the trip — hotel, ride, dinner, and something fun?"
    )


def pending_options_for_trip(trip_id: str) -> Optional[dict]:
    """The latest search's options when they could be about this trip: the
    slot's session is pinned to it, or has no pin yet (the pre-booking
    window, where the trip being polled is whatever the page displays).
    None otherwise — the status endpoint omits the block entirely.

    The shape mirrors the speakable summary the Concierge reads aloud —
    option number, route, wall-clock times (already declared Pacific, the
    Phase 19 discipline), rounded price, no airline codes."""
    slot = _LATEST_SEARCH
    if slot is None:
        return None
    pinned = _SESSION_TRIPS.get(slot.session_id)
    if pinned is not None and pinned.trip.trip_id != trip_id:
        return None
    return {
        "recorded_at": slot.recorded_at.isoformat(),
        "options": [
            {
                "option_number": o.option_number,
                "route": f"{o.origin} → {o.destination}",
                "depart_date": o.depart_date,
                "depart_time": _spoken_clock(o.depart_time),
                "arrive_time": _spoken_clock(o.arrive_time),
                "stops": o.stops,
                "price": round(o.price),
            }
            for o in slot.options
        ],
    }


def _completion_items(trip: Trip) -> List[ItineraryItem]:
    """The four remaining itinerary items, derived from the booked flight's
    trip (dates and destination) — the _SEED_ITEMS shapes as templates."""
    start = trip.start_date or date(2026, 7, 17)
    end = trip.end_date or start + timedelta(days=2)
    span = max((end - start).days, 1)
    dest = trip.destinations[0] if trip.destinations else "your destination"

    def ts(day_offset: int, hour: int, minute: int = 0) -> datetime:
        d = start + timedelta(days=day_offset)
        return datetime(d.year, d.month, d.day, hour, minute, tzinfo=_PACIFIC)

    specs = [
        ("hotel", "sabre", f"Hotel in {dest}", ts(0, 22), ts(span, 18), 412.0),
        ("ground", "other", f"Airport to {dest}", ts(0, 12, 30), ts(0, 13, 15), 58.0),
        ("dining", "other", f"Dinner in {dest}", ts(0, 19), ts(0, 21), 120.0),
        ("experience", "other", f"Experience in {dest}", ts(span, 10), ts(span, 12), 37.5),
    ]
    return [
        ItineraryItem(
            trip_id=trip.trip_id,
            type=type_,
            status="planned",
            provider=provider,
            provider_ref=f"VOICE-{type_.upper()}-{uuid.uuid4().hex[:6].upper()}",
            start_ts=start_ts,
            end_ts=end_ts,
            location=location,
            price=price,
            currency="USD",
        )
        for type_, provider, location, start_ts, end_ts, price in specs
    ]


async def _build_out_trip(session_id: str, trip: Trip) -> None:
    """The complete_trip background task: create hotel/ground/dining/
    experience sequentially, ~1.5s apart, so cards materialize one by one on
    the 1.5s polling clients. Each item lands planned then flips to booked.
    Failures log and stop — this task must never take down the loop that is
    also holding the live conversation."""
    try:
        for item in _completion_items(trip):
            await _sleep(1.5)
            success, _, error = await asyncio.to_thread(
                itinerary_items.create_item, item
            )
            if not success:
                logger.warning("complete_trip %s insert failed: %s", item.type, error)
                return
            success, affected, error = await asyncio.to_thread(
                itinerary_items.update_status, item.item_id, "booked"
            )
            if not success or affected == 0:
                logger.warning("complete_trip %s flip failed: %s", item.type, error)
                return
        # Re-pin so later turns answer from the full itinerary, not just the
        # flight (same trip — the mid-call-seed rule is about *other* trips).
        _SESSION_TRIPS.pop(session_id, None)
        await ensure_trip_context(session_id, trip_id=trip.trip_id)
    except Exception:  # noqa: BLE001 — background task must never propagate
        logger.warning("complete_trip build-out failed", exc_info=True)


async def complete_trip_impl(session_id: str) -> str:
    """Fire the itinerary build-out in the background and return at once —
    the fix_trip inversion applied to booking. Failures return speakable
    strings — a tool that raises kills the spoken turn."""
    context = _SESSION_TRIPS.get(session_id)
    if context is None:
        return (
            "There's no booked trip to build on yet — let's get your flight "
            "booked first."
        )
    task = asyncio.create_task(_build_out_trip(session_id, context.trip))
    _BUILD_TASKS.add(task)
    task.add_done_callback(_BUILD_TASKS.discard)
    return (
        "I'm building the rest of your trip now — the hotel, your ride, "
        "dinner, and something fun will land on your itinerary one by one "
        "over the next few seconds."
    )


def _today_line() -> str:
    """Today's date for the instructions — without it the model cannot turn
    'leaving on Monday' into YYYY-MM-DD. Rendered fresh per build_agent call
    so a long-lived process never serves a stale date; Pacific because the
    demo audience and event are (decision 2026-07-12). A helper, not
    inlined, so tests can freeze the clock."""
    today = datetime.now(_PACIFIC)
    return (
        f"Today is {today:%A}, {today:%Y-%m-%d} (US Pacific time). Resolve "
        "relative dates like 'Monday' or 'tomorrow' from this date, always "
        "into the future. "
    )


def build_agent(session_id: str, trip_context: Optional[TripContext] = None) -> Agent:
    """The foreground agent for one turn. Tools close over session_id so
    background completions report into this voice session's log; the fresh
    snapshot (and the pinned trip's summary) go into instructions at build
    time — build per turn, never once."""

    async def _fix_trip() -> str:
        """Start repairs for the traveler's booked trip after a disruption.
        Repairs run in the background and this returns immediately — keep
        the conversation going while they work."""
        return await fix_trip_impl(session_id)

    async def _search_flights(origin: str, destination: str, depart_date: str) -> str:
        """Search flights and get 2-3 speakable options for the traveler to
        pick from by number. Airport codes for origin and destination;
        depart_date is YYYY-MM-DD. Use only when no trip is booked yet."""
        return await search_flights_impl(session_id, origin, destination, depart_date)

    async def _book_flight(option_number: int) -> str:
        """Book one of the flight options just offered, by its number.
        Creates the trip and books the flight; call only after
        search_flights has offered options."""
        return await book_flight_impl(session_id, option_number)

    async def _complete_trip() -> str:
        """Arrange the rest of the booked trip — hotel, ride, dinner, and an
        experience — in the background. Call after the flight is booked and
        the traveler agrees; it returns immediately."""
        return await complete_trip_impl(session_id)

    trip_line = trip_context.summary if trip_context else _NO_TRIP_LINE
    return Agent(
        name="Concierge",
        model=_llm_model(),
        instructions=(
            BASE_INSTRUCTIONS + _today_line() + trip_line
            + session_snapshot(session_id)
        ),
        tools=[
            function_tool(_fix_trip, name_override="fix_trip"),
            function_tool(_search_flights, name_override="search_flights"),
            function_tool(_book_flight, name_override="book_flight"),
            function_tool(_complete_trip, name_override="complete_trip"),
        ],
    )


async def answer_query(
    session_name: str, query: str, trip_id: Optional[str] = None
) -> str:
    """One delegated spoken turn — the Phase 8 seam, now the Concierge.

    A plain `await Runner.run(...)` on the same loop as the background
    repairs (the concurrency_core pattern); history replay makes the
    session multi-turn. trip_id is the caller's displayed trip (Phase 19):
    ensure_trip_context's cache-first order means it pins only an unpinned
    session — a just-booked trip's pin is never clobbered — and a failed
    resolution never blocks the turn; the agent just lacks trip details
    until a later turn's retry lands."""
    trip_context, _ = await ensure_trip_context(session_name, trip_id=trip_id)
    agent = build_agent(session_name, trip_context)
    history = _HISTORY.get(session_name, [])
    result = await Runner.run(
        agent,
        history + [{"role": "user", "content": query}],
        max_turns=6,
    )
    _HISTORY[session_name] = result.to_input_list()
    return str(result.final_output)
