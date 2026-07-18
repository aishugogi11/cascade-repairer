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
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Set, Tuple

from agents import Agent, Runner, function_tool
from pydantic import BaseModel

from api import concurrency_core as core
from api import consent
from api import trip_emails
from api.concurrency_agent import session_snapshot
from api.email_client import send_email
# Re-exported so concierge.FlightOption / concierge._parse_instaflights_options
# (and every existing caller and test) keep resolving after the Phase 29
# extract into the shared, cycle-free flight_options module (decision 1).
from api.flight_options import (  # noqa: F401 — re-export surface
    _MAX_SPOKEN_OPTIONS,
    _NUMBER_WORDS,
    _PACIFIC,
    _parse_instaflights_options,
    _spoken_clock,
    _spoken_option,
    details_from_option,
    FlightOption,
    fmt_duration,
    option_timestamps,
)
from api.repositories import bookings, itinerary_items, trips
from api.repositories.models import Booking, ItineraryItem, Trip
from api.sabre import client as sabre_client
from api.sabre import shapes
from api.sabre_tools import launch_trip_repairs

logger = logging.getLogger(__name__)

DEFAULT_LLM_MODEL = "gpt-5.4-mini"

# _PACIFIC is imported from flight_options (the Phase 29 extract) — the same
# America/Los_Angeles zone concierge's booking/completion timestamps and the
# _today_line all still declare (decision 2026-07-12).

# The self-identification is the live proof answers come from this backend
# (the Phase 8 manual check); the disruption/launch rules are the Concierge.
BASE_INSTRUCTIONS = (
    "You are the Cascade Repairer concierge — a traveler's live voice travel "
    "assistant, running inside the vocal-bridge-be-dev service on Google "
    "Cloud Run. If asked who you are or where you run, say exactly that. "
    "On your very first turn of a session, greet the traveler in one short "
    "sentence and ask what they need — never open by saying you're pulling "
    "up details or checking on anything; only say you're looking something "
    "up when you're actually about to use a tool. "
    "When the traveler reports a disruption (a cancelled flight, a broken "
    "trip, 'fix my trip'), call the fix_trip tool immediately — it launches "
    "every repair in the background and returns at once. Never wait silently "
    "for repairs to finish and never refuse other questions while they run; "
    "keep helping. You cannot send notifications or follow up on your own — "
    "never promise to 'let them know' when something finishes; instead "
    "invite the traveler to ask again in a moment. When the traveler asks "
    "how their trip or its repairs are going ('how's my trip?'), call the "
    "trip_status tool and answer from its result — it is the authoritative "
    "live read, even when your live status section shows nothing (repairs "
    "may have run under another session). When there is no booked "
    "trip and the traveler wants to plan or book one, follow the guided "
    "flow: confirm the destination and departure date in one short turn, "
    "then call search_flights — origin airport code (assume MSP unless the "
    "traveler says otherwise), destination airport code, and the departure "
    "date as YYYY-MM-DD; turn city names into airport codes yourself — "
    "always a specific airport, never a metro or city code (New York is "
    "JFK, not NYC). Read "
    "the options back and ask the traveler to pick one by number. Speak "
    "airline names, never airline codes or fare-class letters. The search "
    "result's bracketed reference section is not part of the read-back — "
    "use it to answer follow-up questions about the airline, cabin, total "
    "duration, connections, or a next-day arrival without searching again, "
    "and say connection airports as city names. When they "
    "choose, call book_flight with that option number and confirm the "
    "booking in one short sentence, then offer to arrange the rest of the "
    "trip; when they agree, call complete_trip and tell them the pieces are "
    "being added now. After a booking is confirmed, offer exactly once: "
    "'Would you like me to send this to your email?' If they want it, have "
    "them say their email address, turn the spoken form into a standard "
    "written address — 'at' becomes the at sign, 'dot' becomes a period — "
    "then read it back and ask if you got it right. Only when they clearly "
    "confirm the address, call email_itinerary with it. If they decline "
    "the offer, or never clearly confirm the address, drop the subject — "
    "never guess or invent an address, never call email_itinerary with an "
    "unconfirmed one, and don't offer again. "
    "Never call search_flights or book_flight when a trip "
    "is already booked; offer fix_trip or answer questions about the "
    "existing trip instead. When a traveler with a booked trip asks about "
    "getting back or getting home ('is there a way to get home', 'flights "
    "to get me back', any return question), call check_return_flights — "
    "never search_flights, and never refuse the question. If they haven't "
    "given a return date, ask for it in one short turn first — suggest the "
    "trip's end date when there is one; if they decline or say whenever, "
    "call the tool without a date. Relay its answer as an indication that "
    "flights exist, never as fares or options they can book. "
    "When the traveler asks what's happening at "
    "their destination or for things to do there, call destination_info "
    "with their question and relay its answer conversationally — don't "
    "offer it unprompted, and never read web addresses aloud. Your replies are spoken "
    "aloud: one or two short, conversational sentences. No markdown, no "
    "lists, no stage directions, and never speak ids or tool names. "
    "Language: respond in English by default. If the traveler explicitly "
    "asks for another language, give that answer in the requested "
    "language, then return to English on the next turn. If they ask you "
    "to speak a language from now on, stay in it until they ask to "
    "change back. Never switch languages without being asked. "
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


# One consent channel at a time (Phase 31, interview decision): while
# Call 1 is out asking the traveler, the orb defers to the phone instead
# of racing the watcher — observed live 2026-07-15, when fix_trip repaired
# the trip while the watcher was still waiting for the spoken yes.
_CONSENT_PENDING_LINE = (
    "I'm already asking you on the phone — just say yes on the call and "
    "I'll get started."
)


def _consent_wait_pending(trip_id: str) -> bool:
    """True while the consent watcher is awaiting the traveler's answer for
    this trip. Best-effort by contract — a registry hiccup must never kill
    the spoken turn, so any failure reads as 'no wait'."""
    try:
        record = consent.current(trip_id)
        return record is not None and record.state == consent.AWAITING
    except Exception:  # noqa: BLE001 — never load-bearing for the turn
        return False


async def fix_trip_impl(session_id: str) -> str:
    """Launch the repair cascade for the traveler's trip — the tool body,
    kept a plain function for tests (the hello.py pattern).

    Fires one background repair per itinerary item through the same seam as
    /repair_trip and returns immediately with a speakable summary; the tasks
    report into this session's event log as they land. Items come from the
    session's pinned trip. During an awaiting_consent window for that trip,
    defers to the phone instead of launching (Phase 31). Failures return
    speakable strings — a tool that raises would kill the spoken turn."""
    try:
        context, speakable_error = await ensure_trip_context(session_id)
        if speakable_error:
            return speakable_error
        if _consent_wait_pending(context.trip.trip_id):
            return _CONSENT_PENDING_LINE
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
# FlightOption + the InstaFlights parser now live in flight_options (Phase 29,
# decision 1) and are re-exported at the top of this module.


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

# Age expiry for the slot (Phase 22, item H): a conversation that got real
# options and was then abandoned — no booking, no further search — must not
# leave its candidates on the poll indefinitely. Ten minutes is comfortably
# longer than a real guided-booking turn (search → read back → pick, well
# under a minute) but short enough that an abandoned conversation clears
# within the demo. Read-time filter only: the pinned/unpinned resolution is
# untouched, and a stale slot simply stops surfacing.
_LATEST_SEARCH_TTL = timedelta(minutes=10)

# Strong refs so the complete_trip background task isn't garbage-collected
# (the web_call._LOG_TASKS pattern).
_BUILD_TASKS: Set[asyncio.Task] = set()

# Seam for tests to observe the item spacing without waiting wall-clock time.
_sleep = asyncio.sleep

# _NUMBER_WORDS, _MAX_SPOKEN_OPTIONS, _spoken_clock, _spoken_option, and
# _parse_instaflights_options are imported from flight_options (Phase 29
# extract) and re-exported above — book_flight_impl and pending_options_for_trip
# still call _spoken_clock/_NUMBER_WORDS from this module's namespace.

# Metro/city codes the model sometimes produces despite the instructions
# ("New York" → NYC); the supported-markets list is airport codes only, so
# an unaliased metro code redirects the traveler off a route the system
# actually carries (live finding, 2026-07-14). Belt-and-suspenders to the
# BASE_INSTRUCTIONS clause (Phase 28, decision 4).
_METRO_ALIASES = {"NYC": "JFK", "WAS": "IAD", "CHI": "ORD"}

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


async def search_flights_impl(
    session_id: str, origin: str, destination: str, depart_date: str
) -> str:
    """Search flights and offer 2–3 options by voice — the tool body, kept a
    plain function for tests (the fix_trip_impl pattern). Stores the options
    per session so book_flight can resolve 'option one'. Every failure path
    returns a speakable string — a raising tool kills the spoken turn."""
    origin = (origin or "").strip().upper()
    destination = (destination or "").strip().upper()
    origin = _METRO_ALIASES.get(origin, origin)
    destination = _METRO_ALIASES.get(destination, destination)
    depart_date = (depart_date or "").strip()

    def _clear_search_state() -> None:
        """Drop this session's stored options so a non-result can't leave a
        stale choice bookable (Phase 30): every non-optioned return below clears
        both slots. Mirrors book_flight_impl's ownership-guarded clear — never
        wipes another session's in-flight slot."""
        global _LATEST_SEARCH
        _SESSION_FLIGHT_OPTIONS.pop(session_id, None)
        if _LATEST_SEARCH is not None and _LATEST_SEARCH.session_id == session_id:
            _LATEST_SEARCH = None

    if not origin or not destination or not depart_date:
        _clear_search_state()
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
            _clear_search_state()
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
        _clear_search_state()
        return _SEARCH_ERROR_LINE
    if not options:
        _clear_search_state()
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
    reference = " ".join(_option_facts(option) for option in options)
    facts = f" [Reference, don't read aloud unless asked: {reference}]"
    if len(options) == 1:
        return (
            f"I found one flight. {spoken} Should I book it? Just say "
            f"option one.{facts}"
        )
    return (
        f"I found {count_word} good options. {spoken} Which one would "
        f"you like?{facts}"
    )


def _option_facts(option: FlightOption) -> str:
    """One option's rich facts for the tool result's bracketed reference
    section (Phase 33) — the agent answers 'how long is it?' / 'is that
    economy?' from this instead of re-searching. Never part of the spoken
    read-back; fields the response didn't carry are simply absent."""
    word = _NUMBER_WORDS.get(option.option_number, str(option.option_number))
    parts = [f"{option.airline_name or option.airline} {option.flight_number}"]
    if option.cabin:
        parts.append(option.cabin)
    if option.duration_minutes:
        parts.append(fmt_duration(option.duration_minutes))
    if option.layover_airports:
        parts.append("connects in " + ", ".join(option.layover_airports))
    if option.arrives_next_day:
        parts.append("arrives the next day")
    return f"Option {word}: {', '.join(parts)}."


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

    start_ts, end_ts = option_timestamps(option)
    item = ItineraryItem(
        trip_id=trip.trip_id,
        type="flight",
        status="planned",
        provider="sabre",
        provider_ref=f"VOICE-FLIGHT-{uuid.uuid4().hex[:6].upper()}",
        start_ts=start_ts,
        end_ts=end_ts,
        location=f"{option.origin}-{option.destination}",
        # The booked flight's identity (Phase 31) plus the rich display
        # fields (Phase 33), via the stamp shared with the repair
        # write-back — the repair replaces `details` wholesale, so a key
        # stamped only here would be wiped from the card by the first
        # repair. The exclusion filter reads airline/flight_number exactly
        # as before.
        details=details_from_option(option),
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
    # Item H (Phase 22): an abandoned search stops surfacing once the slot
    # ages past the TTL. Best-effort read-time filter — no exception path,
    # and the pinned/unpinned logic below is unchanged for a fresh slot.
    if datetime.now(timezone.utc) - slot.recorded_at > _LATEST_SEARCH_TTL:
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
                # Phase 33: the candidates panel names the carrier and shows
                # the journey length — still a name, never a code; empty
                # strings when the response didn't carry them.
                "airline_name": o.airline_name,
                "duration": (
                    fmt_duration(o.duration_minutes)
                    if o.duration_minutes else ""
                ),
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


# --- trip_status (Phase 23) — the honest "how's my trip?" read ----------------

# Statuses and item types in the traveler's words — the reply is spoken.
_STATUS_SPOKEN = {
    "planned": "planned",
    "booked": "booked and confirmed",
    "broken": "disrupted",
    "repairing": "being repaired right now",
    "fixed": "repaired and confirmed",
    "cancelled": "cancelled",
}
_TYPE_SPOKEN = {
    "flight": "flight",
    "hotel": "hotel",
    "ground": "ride",
    "dining": "dinner reservation",
    "experience": "tour",
}

# Severity order: problems first, then progress, then the quiet statuses.
_STATUS_ORDER = ("broken", "repairing", "fixed", "booked", "planned", "cancelled")


def _spoken_list(names: List[str]) -> str:
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + f", and {names[-1]}"


async def trip_status_impl(session_id: str) -> str:
    """One fresh read of the pinned trip's item statuses — the tool body,
    kept a plain function for tests. The pinned TripContext caches static
    facts; statuses move underneath it (and repairs may run under another
    session id entirely — the page-triggered disrupt flow), so this reads
    the repository every call instead of the cache or the snapshot.
    Failures return speakable strings — a raising tool kills the turn."""
    context = _SESSION_TRIPS.get(session_id)
    if context is None:
        return _NO_TRIP_SPOKEN
    try:
        success, items, _error = await asyncio.to_thread(
            itinerary_items.list_items_for_trip, context.trip.trip_id
        )
    except Exception:  # noqa: BLE001 — the voice turn must survive anything
        success, items = False, None
    if not success or not items:
        return (
            "I can't read your trip's live status right now — give me a "
            "second and ask me again."
        )

    groups: Dict[str, List[str]] = {}
    for item in items:
        groups.setdefault(item.status, []).append(
            _TYPE_SPOKEN.get(item.type, item.type)
        )
    clauses = []
    for status in _STATUS_ORDER:
        names = groups.get(status)
        if not names:
            continue
        verb = "is" if len(names) == 1 else "are"
        clauses.append(
            f"your {_spoken_list(names)} {verb} {_STATUS_SPOKEN[status]}"
        )
    summary = "; ".join(clauses)
    # No all-clear while anything is broken, repairing, or cancelled — a
    # cancelled leg is not "on track" (Phase 31, validator finding).
    if any(item.status in ("broken", "repairing", "cancelled") for item in items):
        return f"Here's your trip right now: {summary}."
    return f"Here's your trip right now: {summary}. Everything is on track."


# Destination info (Phase 35): one trip-aware, read-only Tavily lookup —
# conversational only, nothing enters session options, trip state, or
# BigQuery. Diverges deliberately from the agent_search.ipynb proof:
# basic depth (advanced can take seconds inside a live voice turn) and
# Tavily's own condensed answer instead of raw result dicts.
_DESTINATION_INFO_FALLBACK = (
    "I couldn't look that up just now — ask me again in a moment."
)
_DESTINATION_INFO_MAX_CHARS = 600
_TAVILY_TIMEOUT_S = 8.0
# Protocol or bare-www URLs — both arrive in real Tavily answers (the Phase
# 35 validation caught www. forms passing the original https?:// pattern).
_URL_RE = re.compile(r"(?:https?://|www\.)\S+")
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_UNDERSCORE_RE = re.compile(r"\b_+([^_]+)_+\b")
_MD_MARKS_RE = re.compile(r"[*`#]+")


def _speakable(text: str) -> str:
    """Strip web/Markdown artifacts a TTS voice would mangle: Markdown links
    keep their text, URLs (protocol or bare www.) drop, emphasis/code/heading
    marks drop, whitespace collapses. Order matters — links resolve to their
    text before the URL pass so the label survives."""
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _URL_RE.sub("", text)
    text = _MD_UNDERSCORE_RE.sub(r"\1", text)
    text = _MD_MARKS_RE.sub("", text)
    return " ".join(text.split())


def _tavily_client():
    """A fresh TavilyClient, or None without a key. The import and the key
    read both happen at call time so importing this module — and the
    hermetic suite — needs no TAVILY_API_KEY (the GCP-helpers convention)."""
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return None
    from tavily import TavilyClient

    return TavilyClient(api_key=api_key)


def _tavily_search(query: str) -> str:
    """Synchronous Tavily search condensed for voice — callers run it off
    the event loop via asyncio.to_thread (the standing blocking-call rule).
    Prefers Tavily's own answer over raw results, strips URLs, and caps at
    a speakable length. Raises on any failure — destination_info_impl owns
    the speakable fallback."""
    client = _tavily_client()
    if client is None:
        raise RuntimeError("TAVILY_API_KEY is not set")
    response = client.search(
        query,
        search_depth="basic",
        include_answer=True,
        max_results=3,
    )
    answer = (response.get("answer") or "").strip()
    if not answer:
        snippets = (
            (result.get("content") or "").strip()
            for result in response.get("results", [])
        )
        answer = " ".join(s for s in snippets if s)
    answer = _speakable(answer)
    if not answer:
        raise RuntimeError("Tavily returned no usable content")
    if len(answer) > _DESTINATION_INFO_MAX_CHARS:
        # Cap on a word boundary — a mid-word slice would be spoken as-is.
        answer = answer[:_DESTINATION_INFO_MAX_CHARS].rsplit(" ", 1)[0]
    return answer


async def destination_info_impl(session_id: str, question: str) -> str:
    """Live "what's happening there" answers during the call — the tool
    body, kept a plain function for tests. The pinned trip's destination
    and dates garnish the query server-side (cache-first — no BigQuery
    read lands here after the pin); an unpinned session searches the
    question as-is. Every failure — missing key, Tavily error, timeout —
    returns the speakable fallback: a raising tool kills the turn."""
    try:
        query = question.strip()
        context, _ = await ensure_trip_context(session_id)
        if context is not None:
            trip = context.trip
            if trip.destinations:
                query += f" in {', '.join(trip.destinations)}"
            if trip.start_date and trip.end_date:
                query += f" between {trip.start_date} and {trip.end_date}"
        return await asyncio.wait_for(
            asyncio.to_thread(_tavily_search, query),
            timeout=_TAVILY_TIMEOUT_S,
        )
    except Exception:  # noqa: BLE001 — the voice turn must survive anything
        logger.warning("destination_info failed for %s", session_id, exc_info=True)
        return _DESTINATION_INFO_FALLBACK


# Phase 34 — the honesty framing every successful return indication starts
# with, baked into the tool result (never left to the model): web schedule
# info spoken as an indication, not searched fares or bookable inventory.
_RETURN_FRAMING = "I can't book the return from here, but here's what I found: "


def _return_fallback(route: Optional[str] = None) -> str:
    """The honest soft fallback for a failed return lookup — route-aware when
    the route is known, but never invented schedule facts (no airline names,
    counts, or times; the honesty rule). Speakable, like every failure path."""
    if route:
        return (
            "I couldn't check return schedules just now, but "
            f"{route} is a well-traveled route — ask me again in a "
            "minute and I'll take another look."
        )
    return (
        "I couldn't check return schedules just now — ask me again in a "
        "minute and I'll take another look."
    )


def _return_query_date(return_date: str) -> str:
    """YYYY-MM-DD → 'July 26, 2026' for the Tavily query (the proven-quality
    query shape from the Phase 34 re-scope probe; distinct from _spoken_date,
    which formats date objects for speech). A malformed date passes through
    as-is — Tavily copes, and the tool never raises on input shape."""
    try:
        parsed = datetime.strptime(return_date, "%Y-%m-%d")
    except ValueError:
        return return_date
    return f"{parsed:%B} {parsed.day}, {parsed.year}"


async def check_return_flights_impl(
    session_id: str, return_date: Optional[str] = None
) -> str:
    """Verify-only "can I get back?" (Phase 34) — a spoken indication that
    return flights exist on the traveler's return date, from Tavily web
    schedule info. Deliberately NOT search_flights: this path stores nothing
    — no _SESSION_FLIGHT_OPTIONS, no _LATEST_SEARCH, no repository writes —
    so nothing bookable can enter the session and the never-book-once-booked
    rule holds by construction. The reverse route derives from the pinned
    trip (primary destination back to the origin); dateless calls ask about
    the route generally. Every failure returns the speakable fallback — a
    raising tool kills the turn."""
    route = None
    try:
        context, _ = await ensure_trip_context(session_id)
        if context is None:
            return _NO_TRIP_SPOKEN
        trip = context.trip
        destination = trip.destinations[0] if trip.destinations else None
        if not destination or not trip.origin:
            return _return_fallback()
        route = f"{destination} to {trip.origin}"
        query = f"flights from {route}"
        if return_date:
            query += f" on {_return_query_date(return_date)}"
        indication = await asyncio.wait_for(
            asyncio.to_thread(_tavily_search, query),
            timeout=_TAVILY_TIMEOUT_S,
        )
        return _RETURN_FRAMING + indication
    except Exception:  # noqa: BLE001 — the voice turn must survive anything
        logger.warning(
            "check_return_flights failed for %s", session_id, exc_info=True
        )
        return _return_fallback(route)


# --- email offers (Phase 40) — the booking-call itinerary email ---------------

# A conservative shape check — the code backstop behind the instructions'
# read-back-and-confirm contract (validity is code, adherence is
# instructions — the Phase 34 split). Anything it rejects gets a spoken
# re-ask, never a stored guess: spoken email capture is the demo's known
# STT hazard.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")

_EMAIL_REASK_LINE = (
    "I want to get that address exactly right — could you say it once "
    "more, maybe spelling out the part before the at sign?"
)
_EMAIL_SENT_LINE = "Done — your itinerary is on its way to your inbox."
_EMAIL_SEND_FAILED_LINE = (
    "I've saved your address, but the email didn't go through just now — "
    "ask me to try again in a minute."
)
_EMAIL_ERROR_LINE = (
    "Something went wrong sending that email — give me a second and ask "
    "me again."
)


async def email_itinerary_impl(session_id: str, email_address: str) -> str:
    """Store the traveler's confirmed address for their trip and email the
    booked itinerary — the tool body, kept a plain function for tests.

    Voice-safe by contract: the instructions make the agent read the
    address back and get an explicit yes BEFORE calling this; the shape
    check here is the code backstop, and a malformed capture gets a
    re-ask, never a stored guess. The address stores before the send
    (decision 3) so the repair callback can reuse it even when this send
    fails, and the send status is spoken honestly — never "sent" when the
    module said otherwise. Nothing bookable is touched and nothing is
    written to the repositories. Failures return speakable strings — a
    raising tool kills the spoken turn."""
    try:
        context, speakable_error = await ensure_trip_context(session_id)
        if speakable_error:
            return speakable_error
        address = (email_address or "").strip().lower()
        if not _EMAIL_RE.match(address):
            return _EMAIL_REASK_LINE
        trip = context.trip
        trip_emails.store(trip.trip_id, address)
        # Fresh items read (the trip_status rule): build-out legs land
        # after the pin, and the email carries whatever exists at send
        # time. The pinned items are the fallback — the pin guarantees
        # they exist, so a failed read still makes an honest email.
        items = context.items
        try:
            success, fresh, _error = await asyncio.to_thread(
                itinerary_items.list_items_for_trip, trip.trip_id
            )
            if success and fresh:
                items = fresh
        except Exception:  # noqa: BLE001 — cached items still make an email
            pass
        # Call-time import: email_content imports call_purposes, which
        # imports this module — top-importing it here would be a cycle
        # (the _tavily_client call-time-import precedent).
        from api import email_content

        content = email_content.build_itinerary_email(trip, items)
        result = await send_email(
            to=address,
            subject=content.subject,
            html=content.html,
            text=content.text,
        )
        if result.get("status") == "sent":
            return _EMAIL_SENT_LINE
        return _EMAIL_SEND_FAILED_LINE
    except Exception:  # noqa: BLE001 — the voice turn must survive anything
        logger.warning(
            "email_itinerary failed for %s", session_id, exc_info=True
        )
        return _EMAIL_ERROR_LINE


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

    async def _trip_status() -> str:
        """The live status of every part of the traveler's booked trip,
        read fresh from the bookings. Use whenever the traveler asks how
        their trip or its repairs are going."""
        return await trip_status_impl(session_id)

    async def _destination_info(question: str) -> str:
        """Live info about what's happening at the traveler's destination —
        events, things to do, local recommendations. Use when the traveler
        asks about the place they're going; pass their question."""
        return await destination_info_impl(session_id, question)

    async def _email_itinerary(email_address: str) -> str:
        """Email the traveler's booked itinerary to them and remember the
        address for later trip updates. Call ONLY after the traveler asked
        for the email, you read the address back to them, and they clearly
        confirmed it is right."""
        return await email_itinerary_impl(session_id, email_address)

    async def _check_return_flights(return_date: str = "") -> str:
        """Whether return flights exist for the traveler's booked trip — a
        spoken indication from web schedule info, never bookable fares or
        searched options. Use when a traveler with a booked trip asks about
        getting back or getting home; pass their return date as YYYY-MM-DD
        when they gave one, or leave it empty."""
        return await check_return_flights_impl(session_id, return_date or None)

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
            function_tool(_trip_status, name_override="trip_status"),
            function_tool(_destination_info, name_override="destination_info"),
            function_tool(
                _check_return_flights, name_override="check_return_flights"
            ),
            function_tool(_email_itinerary, name_override="email_itinerary"),
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
