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
    airline_name,
    details_from_option,
    FlightOption,
    fmt_duration,
    option_timestamps,
    select_airline_diverse,
)
from ml.inference import predict_delay_risk
from ml.ranking import (
    TravelerPrefs,
    parse_clock,
    rank_options,
    spoken_recommendation,
)
from api import memory_trips
from api.llm_client import agents_model, configure_agents_sdk
from api.saily import plan_for_trip
from api.repositories import bookings, itinerary_items, trips
from api.repositories.models import Booking, ItineraryItem, Trip
from api.sabre import client as sabre_client
from api.sabre import shapes
from api.sabre.airport_tz import AIRPORT_TZ
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
    "When the traveler reports a cancelled flight, a cancelled trip to the "
    "airport, or a cancelled airport departure ('trip to airport cancelled', "
    "'my flight was cancelled', 'airport transfer cancelled'), call "
    "offer_rebook in the same turn — do not call fix_trip for that. "
    "offer_rebook marks the leg disrupted, searches replacements, and puts "
    "numbered options on the traveler's screen. Read the recommendation "
    "sentence first, then the numbered options, and ask them to pick by "
    "number. When they choose, call book_flight with that option number. "
    "Call the fix_trip tool only when they ask to fix the whole trip after "
    "a disruption already on screen, or say 'fix my trip' — it launches "
    "every remaining repair in the background and returns at once. Never wait silently "
    "for repairs to finish and never refuse other questions while they run; "
    "keep helping. You cannot send notifications or follow up on your own — "
    "never promise to 'let them know' when something finishes; instead "
    "invite the traveler to ask again in a moment. When the traveler asks "
    "how their trip or its repairs are going ('how's my trip?'), call the "
    "trip_status tool and answer from its result — it is the authoritative "
    "live read, even when your live status section shows nothing (repairs "
    "may have run under another session). When there is no booked "
    "trip and the traveler wants to plan or book one, call search_flights "
    "in the same turn as soon as you have a destination and departure date "
    "— do not confirm first and do not ask them to wait. Do not call "
    "search_flights for a cancelled trip to the airport or a cancelled "
    "flight on a booked itinerary — offer_rebook does that search and "
    "scores replacements with the delay-risk model. Never invent delay "
    "percentages. If they name a different city or date after options are "
    "on screen, then call search_flights with those. Origin airport "
    "code (assume MSP unless the "
    "traveler says otherwise), destination airport code, and the departure "
    "date as YYYY-MM-DD; turn city names into airport codes yourself — "
    "always a specific airport, never a metro or city code (New York is "
    "JFK, not NYC). Read "
    "the tool's recommendation sentence first (it already names the delay "
    "risk), then the numbered options, and ask them to pick by number. Speak "
    "airline names, never airline codes or fare-class letters. The search "
    "result's bracketed reference section is not part of the read-back — "
    "use it to answer follow-up questions about the airline, cabin, total "
    "duration, connections, a next-day arrival, or delay risk without "
    "searching again, "
    "and say connection airports as city names. When they change what "
    "matters — cheaper, nonstop, earlier, arrive before a clock time, "
    "lowest risk — call set_recovery_preferences and read the new "
    "recommendation; do not search again if options are already on the "
    "table. Nearby bookable dates appear on the traveler's screen after a "
    "search — when they name a different day, call search_flights with the "
    "same route and that new date. When they "
    "choose, call book_flight with that option number and confirm the "
    "booking in one short sentence, then offer to arrange the rest of the "
    "trip; when they agree, call complete_trip and tell them the pieces are "
    "being added now. After a booking is confirmed, offer exactly once: "
    "'Would you like me to send this to your email?' If they want it, have "
    "them say their email address, turn the spoken form into a standard "
    "written address — 'at' becomes the at sign, 'dot' becomes a period — "
    "then read it back and ask if you got it right, spelling the part "
    "before the at sign letter by letter (for example \"that's "
    "J-O-S-H at gmail dot com — did I get it right?\") so a doubled or "
    "missing letter can't slip through the read-back. Only when they "
    "clearly confirm the spelled address, call email_itinerary with it. "
    "If they decline the offer, or never clearly confirm the address, "
    "drop the subject — never guess or invent an address, never call "
    "email_itinerary with an unconfirmed one, and don't offer again. "
    "If the traveler asks what email is on file, repeat the address they "
    "confirmed in this conversation, spelled out the same way; if they "
    "correct it or give a new one, confirm it the same spelled way and "
    "call email_itinerary with the new address — the newest confirmed "
    "address replaces the old one for every later update, and the "
    "itinerary is sent again to the new address. "
    "When a trip is booked and healthy, prefer trip_status over "
    "a new search. A disruption or an explicit ask for alternatives is the "
    "exception — then offer_rebook or search_flights is correct. If they already have an "
    "itinerary — including one loaded from a trip PDF — and they pick a "
    "replacement flight by number, call book_flight; that updates the "
    "existing trip's flight and must not start a second trip. Do not call "
    "complete_trip when hotel, dining, or other legs are already on the "
    "itinerary. When a traveler asks if you have their itinerary, can see "
    "their trip, or what's on their plan, call trip_status in the same turn "
    "even if the live status section says there is no booked trip — the tool "
    "loads the itinerary already on their screen. Never say you don't have "
    "their itinerary until that tool says so. "
    "When a traveler with a booked trip asks about "
    "getting back or getting home ('is there a way to get home', 'flights "
    "to get me back', any return question), call check_return_flights — "
    "never search_flights, and never refuse the question. If they haven't "
    "given a return date, ask for it in one short turn first — suggest the "
    "trip's end date when there is one; if they decline or say whenever, "
    "call the tool without a date. Relay its answer as an indication that "
    "flights exist, never as fares or options they can book. "
    "When the traveler asks to optimize the trip, find a better route, "
    "save time or money on transportation, compare Uber and the subway, "
    "or analyze the itinerary, call analyze_itinerary in the same turn "
    "even if the live status section says there is no booked trip — the "
    "tool loads the itinerary already on their screen. Never say you "
    "don't have their itinerary until that tool says so. "
    "Pass any preference they just stated (save time, stay cheap, hate "
    "walking). Read the tool's spoken recommendation — do not invent "
    "minutes, dollars, or savings, and never say you used a machine "
    "learning model. When they accept a numbered optimization or say "
    "apply, call apply_optimization with that number. When they decline "
    "or say keep the current plan, call reject_optimization. "
    "When the traveler asks what's happening at "
    "their destination or for things to do there, call destination_info "
    "with their question and relay its answer conversationally — don't "
    "offer it unprompted, and never read web addresses aloud. "
    "When they ask about roaming, mobile data, wifi, an eSIM, or staying "
    "online abroad, call esim_plan and relay its spoken line — never read "
    "the checkout URL aloud. "
    "When they ask for the cheapest Uber, Uber from here, Uber from the "
    "first stop, the best option from the first stop, or how to get from "
    "the first stop to the next one, call first_stop_uber in the same turn "
    "even if trip status says there is no booked trip — that tool uses the "
    "itinerary already on their screen. Read its spoken line; do not invent "
    "fares. "
    "When the traveler asks to reschedule, change, or move their hotel "
    "reservation or stay dates, call reschedule_hotel in the same turn "
    "once you have the new check-in date as YYYY-MM-DD — even if the live "
    "status section says there is no booked trip. If they also name a "
    "check-out date, pass that too; if they only name a new check-in or "
    "say move it a day later or earlier, pass the new check-in and leave "
    "check-out empty so the stay length stays the same. If they haven't "
    "given a new date, ask for it in one short turn. Read the tool's "
    "confirmation; do not invent confirmation numbers, and do not call "
    "fix_trip or offer_rebook for a hotel date change. "
    "Never ask the traveler for destination, dates, or itinerary details "
    "when a trip is already on their screen — call trip_status, "
    "analyze_itinerary, or first_stop_uber instead. Only ask for booking "
    "details on a fresh new-flight request with no loaded itinerary. "
    "Your replies are spoken "
    "aloud: one or two short, conversational sentences. No markdown, no "
    "lists, no stage directions, and never speak ids or tool names. "
    "Language: respond in English by default. If the traveler explicitly "
    "asks for another language, give that answer in the requested "
    "language, then return to English on the next turn. If they ask you "
    "to speak a language from now on, stay in it until they ask to "
    "change back. Never switch languages without being asked. "
)

_NO_TRIP_LINE = (
    "No trip is pinned on this voice session yet. If the traveler asks about "
    "an itinerary, their trip, flights, hotel, or schedule, call trip_status "
    "or analyze_itinerary before saying you lack their itinerary — those tools "
    "load the trip already on their screen. Only say there is no trip if the "
    "tool says so. Fresh booking requests stay unpinned: search_flights and "
    "book_flight still work. "
)

# The speakable reply for a session with no pinned trip — one line shared by
# the unpinned and trip-not-found paths so fix_trip answers the same either way.
_NO_TRIP_SPOKEN = "I don't see a booked trip for you yet."

# session_name -> Agents SDK input list (multi-turn memory).
_HISTORY: Dict[str, List] = {}


def _wants_first_stop_uber(query: str) -> bool:
    lower = (query or "").lower()
    has_first_stop = (
        "first stop" in lower
        or "from the first" in lower
        or ("first" in lower and "stop" in lower)
        or "from here" in lower
        or "standing at" in lower
        or "i'm at the first" in lower
        or "im at the first" in lower
    )
    has_rideshare = any(w in lower for w in (
        "uber", "lyft", "rideshare", "best option", "best way",
        "how should i get", "how do i get", "what should i take",
        "transport", "pickup",
    ))
    if has_first_stop:
        return True
    if any(w in lower for w in ("uber", "lyft", "rideshare")) and any(
        w in lower for w in (
            "cheap", "cheapest", "best", "option", "from here",
            "live", "available", "should i",
        )
    ):
        return True
    return has_rideshare and any(
        w in lower for w in ("first", "stop", "here", "curb", "next stop")
    )


def _wants_fresh_booking(query: str) -> bool:
    """True only for new guided-booking asks — not itinerary / first-stop help."""
    if _wants_first_stop_uber(query) or _wants_itinerary_confirm(query):
        return False
    lower = (query or "").lower()
    if any(w in lower for w in (
        "itinerary", "my trip", "first stop", "optimize", "reschedule",
        "uber", "lyft", "rideshare",
    )):
        return False
    return any(w in lower for w in (
        "book me a flight", "book a flight", "book me", "search flights",
        "find flights", "flights to", "fly to", "i want to go to",
        "take me to", "new trip",
    ))


def _wants_itinerary_confirm(query: str) -> bool:
    lower = (query or "").lower()
    if not any(w in lower for w in (
        "itinerary", "my trip", "my plan", "my stops", "my schedule",
    )):
        return False
    return any(w in lower for w in (
        "have my", "got my", "see my", "get my", "getting my",
        "know my", "loaded", "on file", "do you have", "can you see",
        "what's on", "what is on", "tell me about", "look at",
        "check my", "read my", "show my", "pull up",
    ))


def _wants_loaded_trip(query: str) -> bool:
    """Questions that should use the Cascade/Optimize trip already on screen."""
    lower = (query or "").lower()
    if _wants_itinerary_confirm(query) or _wants_first_stop_uber(query):
        return True
    return any(w in lower for w in (
        "itinerary", "my trip", "my plan", "my flight", "my hotel",
        "my schedule", "optimize", "reschedule", "trip status",
        "how's my", "how is my", "where am i staying", "where do i",
        "what's my", "what is my", "when do i", "uber from",
        "first stop", "best option", "best way", "rideshare",
    ))


def _llm_model():
    return agents_model()


class TripContext(BaseModel):
    """A session's pinned trip: the one BigQuery read, kept in process."""

    trip: Trip
    items: List[ItineraryItem]
    summary: str


def _confirm_loaded_itinerary(context: TripContext) -> str:
    n = len(context.items or [])
    title = (context.trip.title or "trip").strip() or "trip"
    return (
        f"Yes — I have your {title} itinerary with {n} stops loaded. "
        "Ask me to optimize it, check status, or change the hotel dates."
    )


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
    def _part(item: ItineraryItem) -> str:
        loc = f" ({item.location})" if item.location else ""
        line = f"{item.type}{loc}"
        details = item.details or {}
        title = (details.get("title") or "").strip()
        if title:
            line = f"{item.type} '{title}'{loc}"
        if item.type == "hotel":
            check_in = _pacific_day(item.start_ts)
            check_out = _pacific_day(item.end_ts)
            if check_in:
                line += f" check-in {check_in.isoformat()}"
            if check_out:
                line += f" check-out {check_out.isoformat()}"
        if details.get("must_keep") or details.get("importance") == "must_keep":
            line += " [must-keep]"
        elif details.get("flexibility") == "high":
            line += " [flexible]"
        return line

    parts = "; ".join(_part(item) for item in items)
    prefs_blob = {}
    for item in items:
        blob = (item.details or {}).get("traveler_prefs") or {}
        if blob:
            prefs_blob = blob
            break
    prefs_line = ""
    if prefs_blob:
        interests = ", ".join(prefs_blob.get("interests") or []) or "unspecified"
        prefs_line = (
            f" Traveler prefs: budget={prefs_blob.get('budget') or 'unspecified'}"
            f", interests={interests}"
            f", pace={prefs_blob.get('pace') or 'unspecified'}."
        )
    return (
        "TRIP CONTEXT (authoritative — this IS the traveler's booked trip; "
        "answer where/when/what questions about it directly, never say you "
        f"lack their itinerary): '{trip.title}' from {trip.origin or 'unknown'} "
        f"to {destinations}, {dates}. Parts: {parts}.{prefs_line} "
        "When repairing a disruption, protect [must-keep] items and prefer "
        "moving [flexible] ones. Live repair progress comes only from the "
        "LIVE STATUS section, not from here. "
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


def _pacific_day(ts: Optional[datetime]) -> Optional[date]:
    """Calendar day of a timestamp in Pacific, the display/spoken zone."""
    if ts is None:
        return None
    if ts.tzinfo:
        return ts.astimezone(_PACIFIC).date()
    return ts.replace(tzinfo=_PACIFIC).date()


# --- guided booking (Phase 17) — search → options → book → complete -----------
# FlightOption + the InstaFlights parser now live in flight_options (Phase 29,
# decision 1) and are re-exported at the top of this module.


# session_name -> the options the agent just offered (the _SESSION_TRIPS
# pattern: in-process, single-instance by standing decision). Replaced on
# every search, cleared by a successful booking.
_SESSION_FLIGHT_OPTIONS: Dict[str, List[FlightOption]] = {}
_SESSION_PREFS: Dict[str, TravelerPrefs] = {}


class LatestSearch(BaseModel):
    """The most recent search, bridged for the booking page (Phase 21):
    _SESSION_FLIGHT_OPTIONS is session-keyed and the trip doesn't exist until
    book_flight, so the trip-keyed status endpoint needs this one slot to
    surface what the Concierge just offered. `insights` is additive ML
    display data, parallel to `options` (empty on pre-ML constructors)."""

    session_id: str
    options: List[FlightOption]
    recorded_at: datetime
    insights: List[dict] = []
    prefs_summary: str = ""
    origin: str = ""
    destination: str = ""
    depart_date: str = ""
    available_dates: List[dict] = []


# Written by search_flights_impl alongside _SESSION_FLIGHT_OPTIONS, cleared
# by book_flight_impl on a successful booking. One slot, not per-session:
# with two simultaneous unpinned conversations an unrelated trip's poll could
# briefly show the other session's candidates — accepted demo-grade looseness
# for a single-operator demo.
_LATEST_SEARCH: Optional[LatestSearch] = None

# The flight the Concierge just booked — in-memory display payload for the
# cascade dashboard so available times stay on screen after pick, even when
# BigQuery status polling is slow or unavailable locally.
_LATEST_BOOKING: Optional[dict] = None

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
    "I can't search that route right now — want to try another "
    "one, something like San Francisco to New York?"
)

# Phase 41: the guided-booking fetch/parse ceiling — a pool wide enough for
# select_airline_diverse to find every carrier the cache holds. Deliberately
# a concierge-local policy: shapes.InstaFlightsRequest.limit keeps its
# default (10) so the repair re-shop's request is byte-identical to pre-41.
_SEARCH_POOL_SIZE = 15
# Airline-diversity cap after parse: wide enough for the ML ranker to see
# a morning nonstop, a cheap connection, and a late nonstop in mock mode.
_RANK_POOL_SIZE = 6
# Nearby-date strip: requested day plus the next six, shopped in parallel
# after the speakable search. Neighbor days use a smaller limit so live
# Sabre latency stays bounded; a timeout falls back to the selected day.
_CALENDAR_DAYS = 7
_CALENDAR_LIMIT = 6
_CALENDAR_TIMEOUT_S = 3.0

_PRIORITY_ALIASES = {
    "risk": "risk", "lowest_risk": "risk", "safest": "risk",
    "disruption": "risk", "lowest disruption risk": "risk",
    "price": "price", "lowest_price": "price", "cheaper": "price",
    "cheapest": "price", "cost": "price",
    "arrival": "arrival", "earliest": "arrival", "earliest_arrival": "arrival",
    "earlier": "arrival",
    "nonstop": "nonstop", "non-stop": "nonstop", "no_stops": "nonstop",
    "direct": "nonstop",
    "duration": "duration", "shortest": "duration",
    "shortest_time": "duration", "fastest": "duration",
}


def _prefs_for(session_id: str) -> TravelerPrefs:
    return _SESSION_PREFS.get(session_id) or TravelerPrefs()


def _insight_payload(ranked) -> dict:
    return {
        "delay_risk_pct": ranked.delay_risk_pct,
        "recommendation_score": int(round(ranked.score * 100)),
        "recommended": ranked.recommended,
        "why": ranked.why,
        "key_factors": ranked.factors,
    }


def _parse_iso_date(value: str) -> Optional[date]:
    try:
        return date.fromisoformat((value or "").strip()[:10])
    except ValueError:
        return None


def _date_chip(
    day: date,
    *,
    available: bool,
    selected: bool,
    lowest_price: Optional[int] = None,
    delay_risk_pct: Optional[int] = None,
    n_flights: int = 0,
) -> dict:
    return {
        "date": day.isoformat(),
        "label": f"{day.strftime('%a')} {day.day}",
        "weekday": day.strftime("%A"),
        "available": available,
        "selected": selected,
        "lowest_price": lowest_price,
        "delay_risk_pct": delay_risk_pct,
        "n_flights": n_flights,
    }


def _summary_from_options(
    options: List[FlightOption],
) -> Tuple[Optional[int], Optional[int], int]:
    if not options:
        return None, None, 0
    lowest_price = int(round(min(float(o.price or 0) for o in options)))
    risks = [predict_delay_risk(o)["delay_risk_pct"] for o in options]
    return lowest_price, min(risks), len(options)


async def _shop_one_calendar_day(
    origin: str, destination: str, day: date,
) -> dict:
    """Best-effort neighbor-day shop. Empty or failed → unavailable chip."""
    try:
        search = await sabre_client.instaflights_search(
            shapes.InstaFlightsRequest(
                origin=origin,
                destination=destination,
                departuredate=day.isoformat(),
                limit=_CALENDAR_LIMIT,
            )
        )
        pool = _parse_instaflights_options(
            search, origin, destination, max_options=_CALENDAR_LIMIT,
        )
    except Exception:  # noqa: BLE001 — a dead neighbor must not kill search
        pool = []
    price, risk, n = _summary_from_options(pool)
    return _date_chip(
        day, available=bool(pool), selected=False,
        lowest_price=price, delay_risk_pct=risk, n_flights=n,
    )


async def shop_available_dates(
    origin: str,
    destination: str,
    selected_date: str,
    selected_options: List[FlightOption],
    window_start: Optional[str] = None,
) -> List[dict]:
    """Requested day plus the next six. Selected day uses already-parsed
    options (no second search); neighbors shop in parallel."""
    selected = _parse_iso_date(selected_date)
    start = _parse_iso_date(window_start or "") or selected
    if selected is None or start is None:
        return []
    days = [start + timedelta(days=i) for i in range(_CALENDAR_DAYS)]
    price, risk, n = _summary_from_options(selected_options)
    selected_chip = _date_chip(
        selected, available=bool(selected_options), selected=True,
        lowest_price=price, delay_risk_pct=risk, n_flights=n,
    )
    others = [d for d in days if d != selected]
    results = await asyncio.gather(
        *[_shop_one_calendar_day(origin, destination, d) for d in others],
        return_exceptions=True,
    )
    by_date = {selected.isoformat(): selected_chip}
    for day, result in zip(others, results):
        if isinstance(result, Exception):
            by_date[day.isoformat()] = _date_chip(
                day, available=False, selected=False,
            )
        else:
            by_date[day.isoformat()] = result
    chips = [by_date[d.isoformat()] for d in days]
    if selected.isoformat() not in {c["date"] for c in chips}:
        chips.insert(0, selected_chip)
    return chips


def _rank_and_store(
    session_id: str,
    options: List[FlightOption],
    *,
    origin: str = "",
    destination: str = "",
    depart_date: str = "",
    available_dates: Optional[List[dict]] = None,
) -> Tuple[List[FlightOption], str]:
    """Score with the delay-risk model, reorder by current prefs, store."""
    global _LATEST_SEARCH
    prev = _LATEST_SEARCH
    if prev is not None and prev.session_id == session_id:
        origin = origin or prev.origin
        destination = destination or prev.destination
        depart_date = depart_date or prev.depart_date
        if available_dates is None:
            available_dates = list(prev.available_dates)
    dates = [dict(chip) for chip in (available_dates or [])]
    for chip in dates:
        chip["selected"] = chip.get("date") == depart_date
    prefs = _prefs_for(session_id)
    ranked = rank_options(options, prefs)
    numbered: List[FlightOption] = []
    for i, row in enumerate(ranked, start=1):
        carrier = row.option.airline_name or airline_name(row.option.airline)
        numbered.append(row.option.model_copy(update={
            "option_number": i,
            "spoken": _spoken_option(
                i, carrier, row.option.stops, row.option.depart_time,
                row.option.arrive_time, row.option.price,
            ),
        }))
        row.option = numbered[-1]
    _SESSION_FLIGHT_OPTIONS[session_id] = numbered
    _LATEST_SEARCH = LatestSearch(
        session_id=session_id,
        options=numbered,
        recorded_at=datetime.now(timezone.utc),
        insights=[_insight_payload(row) for row in ranked],
        prefs_summary=prefs.describe(),
        origin=origin,
        destination=destination,
        depart_date=depart_date,
        available_dates=dates,
    )
    return numbered, spoken_recommendation(ranked, prefs)


def _store_date_strip_only(
    session_id: str,
    origin: str,
    destination: str,
    depart_date: str,
    dates: List[dict],
) -> None:
    """Requested day had no fares, but neighbors did — keep the strip
    visible and drop any stale numbered options so they cannot book by
    saying option one."""
    global _LATEST_SEARCH
    _SESSION_FLIGHT_OPTIONS.pop(session_id, None)
    _LATEST_SEARCH = LatestSearch(
        session_id=session_id,
        options=[],
        recorded_at=datetime.now(timezone.utc),
        insights=[],
        prefs_summary=_prefs_for(session_id).describe(),
        origin=origin,
        destination=destination,
        depart_date=depart_date,
        available_dates=dates,
    )


def _spoken_open_dates(dates: List[dict]) -> str:
    """'July 18th from 198 dollars and July 19th from 210 dollars'."""
    open_days = [d for d in dates if d.get("available")]
    parts: List[str] = []
    for chip in open_days[:3]:
        day = _parse_iso_date(chip.get("date") or "")
        label = _spoken_date(day) if day else (chip.get("label") or "another day")
        price = chip.get("lowest_price")
        if price is not None:
            parts.append(f"{label} from {int(price)} dollars")
        else:
            parts.append(label)
    if not parts:
        return ""
    if len(parts) == 1:
        spoken = parts[0]
    elif len(parts) == 2:
        spoken = f"{parts[0]} and {parts[1]}"
    else:
        spoken = f"{', '.join(parts[:-1])}, and {parts[-1]}"
    if len(open_days) > 3:
        spoken += ", among others"
    return spoken


_IATA_TOKEN = re.compile(r"\b([A-Z]{3})\b")
_AIRPORT_HINTS = ("airport", "departure", "terminal", "gate")


def _item_text(item: ItineraryItem) -> str:
    title = ""
    if isinstance(item.details, dict):
        title = str(item.details.get("title") or "")
    return f"{item.location or ''} {title}"


def _airports_in(text: str) -> List[str]:
    return [
        code for code in _IATA_TOKEN.findall((text or "").upper())
        if code in AIRPORT_TZ
    ]


def _pair_from_location(location: Optional[str]) -> Optional[Tuple[str, str]]:
    loc = (location or "").strip().upper()
    loc = loc.replace("→", "-").replace("->", "-").replace(">", "-")
    loc = loc.replace("–", "-").replace("—", "-")
    if "-" not in loc:
        return None
    left, right = loc.split("-", 1)
    a_codes = _airports_in(left) or (
        [left.strip()] if left.strip() in AIRPORT_TZ else []
    )
    b_codes = _airports_in(right) or (
        [right.strip()] if right.strip() in AIRPORT_TZ else []
    )
    if a_codes and b_codes:
        return a_codes[0], b_codes[0]
    return None


def _leg_score(item: ItineraryItem) -> int:
    blob = _item_text(item)
    score = 0
    if item.type == "flight":
        score += 4
    if any(hint in blob.lower() for hint in _AIRPORT_HINTS):
        score += 5
    if _airports_in(blob) or _pair_from_location(item.location):
        score += 2
    return score


def _item_when(item: ItineraryItem) -> datetime:
    ts = item.start_ts
    if ts is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts


def _recovery_leg(items: List[ItineraryItem]) -> Optional[ItineraryItem]:
    """The cancelled airport/flight stop — last high-scoring itinerary item."""
    scored = [
        (_leg_score(item), _item_when(item), item) for item in items
    ]
    scored = [row for row in scored if row[0] > 0]
    if not scored:
        return None
    scored.sort(key=lambda row: (row[0], row[1]))
    return scored[-1][2]


def _other_end(trip: Trip, origin: str) -> str:
    origin = (origin or "").strip().upper()
    for dest in trip.destinations or []:
        codes = _airports_in(str(dest).upper())
        raw = str(dest).strip().upper()
        if not codes and raw in AIRPORT_TZ:
            codes = [raw]
        if codes and codes[0] != origin:
            return codes[0]
    home = (trip.origin or "").strip().upper()
    if home in AIRPORT_TZ and home != origin:
        return home
    return "MSP" if origin != "MSP" else "SFO"


def _iso_depart(ts) -> str:
    today = datetime.now(_PACIFIC).date()
    day = None
    if ts is not None:
        day = ts.date() if hasattr(ts, "date") else ts
    if not isinstance(day, date) or day < today:
        return today.isoformat()
    return day.isoformat()


def _recovery_route(
    trip: Trip, items: List[ItineraryItem]
) -> Tuple[str, str, str]:
    """Origin, destination, and YYYY-MM-DD for a cancelled airport/flight leg."""
    origin = dest = None
    when = None
    leg = _recovery_leg(items)
    if leg is not None:
        when = leg.start_ts
        pair = _pair_from_location(leg.location)
        if pair:
            origin, dest = pair
        else:
            codes = _airports_in(_item_text(leg))
            if codes:
                origin = codes[0]
                dest = _other_end(trip, origin)
    if not origin:
        origin = (trip.origin or "").strip().upper() or "MSP"
        dest = None
        for candidate in trip.destinations or []:
            codes = _airports_in(str(candidate).upper())
            raw = str(candidate).strip().upper()
            if codes:
                dest = codes[0]
                break
            if raw in AIRPORT_TZ:
                dest = raw
                break
        dest = dest or _other_end(trip, origin)
        when = trip.start_date
    origin = _METRO_ALIASES.get(origin, origin)
    dest = _METRO_ALIASES.get(dest or "", dest or "")
    if not dest or origin == dest:
        dest = _other_end(trip, origin)
        dest = _METRO_ALIASES.get(dest, dest)
    if origin == dest:
        dest = "SFO" if origin != "SFO" else "MSP"
    return origin, dest, _iso_depart(when)


async def offer_rebook_impl(session_id: str) -> str:
    """Mark the cancelled airport/flight leg broken and search replacements
    so the traveler can pick by number. Speakable on every failure path —
    this is the voice turn, not the silent repair cascade."""
    try:
        context, speakable_error = await ensure_trip_context(session_id)
        if speakable_error:
            return speakable_error
        if _consent_wait_pending(context.trip.trip_id):
            return _CONSENT_PENDING_LINE
        origin, destination, depart_date = _recovery_route(
            context.trip, context.items
        )
        target = _recovery_leg(context.items)
        if target is not None:
            try:
                await asyncio.to_thread(
                    itinerary_items.update_status, target.item_id, "broken"
                )
            except Exception:  # noqa: BLE001 — still offer the flights
                logger.exception("offer_rebook status update failed")
            target.status = "broken"
        return await search_flights_impl(
            session_id, origin, destination, depart_date
        )
    except Exception:  # noqa: BLE001 — the voice turn must survive anything
        return _SEARCH_ERROR_LINE


async def search_flights_impl(
    session_id: str, origin: str, destination: str, depart_date: str,
    calendar_start: Optional[str] = None,
) -> str:
    """Search flights, score delay risk, and offer a ranked menu. Stores
    the options per session so book_flight and set_recovery_preferences can
    resolve 'option one'. Every failure path returns a speakable string."""
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
                limit=_SEARCH_POOL_SIZE,
            )
        )
        pool = _parse_instaflights_options(
            search, origin, destination, max_options=_SEARCH_POOL_SIZE
        )
        options = select_airline_diverse(pool, max_airlines=_RANK_POOL_SIZE)
    except Exception:  # noqa: BLE001 — the voice turn must survive anything
        _clear_search_state()
        return _SEARCH_ERROR_LINE
    if not options:
        dates: List[dict] = []
        try:
            dates = await asyncio.wait_for(
                shop_available_dates(
                    origin, destination, depart_date, [],
                    window_start=calendar_start,
                ),
                timeout=_CALENDAR_TIMEOUT_S,
            )
        except Exception:  # noqa: BLE001
            dates = []
        open_days = [d for d in dates if d.get("available")]
        if not open_days:
            _clear_search_state()
            return (
                "I couldn't find any flights for that day — want to try a "
                "different date?"
            )
        _store_date_strip_only(
            session_id, origin, destination, depart_date, dates,
        )
        asked = _parse_iso_date(depart_date)
        asked_s = _spoken_date(asked) if asked else "that day"
        alts = _spoken_open_dates(dates)
        return (
            f"I couldn't find any flights for {asked_s}. "
            f"These days have flights: {alts}. "
            f"They're on the screen — tap one or say the date."
        )

    dates: List[dict] = []
    try:
        dates = await asyncio.wait_for(
            shop_available_dates(
                origin, destination, depart_date, options,
                window_start=calendar_start,
            ),
            timeout=_CALENDAR_TIMEOUT_S,
        )
    except Exception:  # noqa: BLE001 — strip is additive; search still speaks
        start = _parse_iso_date(depart_date)
        if start is not None:
            price, risk, n = _summary_from_options(options)
            dates = [_date_chip(
                start, available=True, selected=True,
                lowest_price=price, delay_risk_pct=risk, n_flights=n,
            )]

    options, lead = _rank_and_store(
        session_id, options,
        origin=origin, destination=destination, depart_date=depart_date,
        available_dates=dates,
    )
    spoken = " ".join(option.spoken for option in options)
    reference = " ".join(_option_facts(option) for option in options)
    facts = f" [Reference, don't read aloud unless asked: {reference}]"
    pick = "Should I book it? Just say option one." if len(options) == 1 else (
        "Which one would you like?"
    )
    other_days = sum(1 for d in dates if d.get("available") and not d.get("selected"))
    screen = (
        " Other bookable dates are on the screen if you want a different day."
        if other_days else ""
    )
    return f"{lead} {spoken} {pick}{screen}{facts}"


def _as_bool(value) -> Optional[bool]:
    if value is True or value is False:
        return value
    if value is None:
        return None
    raw = str(value).strip().lower()
    if raw in ("true", "yes", "1", "on"):
        return True
    if raw in ("false", "no", "0", "off"):
        return False
    return None


async def set_recovery_preferences_impl(
    session_id: str,
    priority: str = "",
    arrive_before: str = "",
    avoid_connections: str = "",
) -> str:
    """Rerank stored flight options from the traveler's new priorities.
    Does not search again. Speakable on every path."""
    prefs = _prefs_for(session_id)
    if priority:
        mapped = _PRIORITY_ALIASES.get(priority.strip().lower())
        if mapped:
            prefs = TravelerPrefs(
                priority=mapped,
                arrive_before=prefs.arrive_before,
                avoid_connections=prefs.avoid_connections,
            )
    clock = parse_clock(arrive_before or "")
    if clock:
        prefs = TravelerPrefs(
            priority=prefs.priority,
            arrive_before=clock,
            avoid_connections=prefs.avoid_connections,
        )
    flag = _as_bool(avoid_connections)
    if flag is not None:
        prefs = TravelerPrefs(
            priority=prefs.priority,
            arrive_before=prefs.arrive_before,
            avoid_connections=flag,
        )
    _SESSION_PREFS[session_id] = prefs
    options = _SESSION_FLIGHT_OPTIONS.get(session_id)
    if not options:
        return (
            f"I'll rank the next search by {prefs.describe()}. Tell me "
            "where you're headed and when, and I'll search."
        )
    options, lead = _rank_and_store(session_id, options)
    spoken = " ".join(option.spoken for option in options)
    reference = " ".join(_option_facts(option) for option in options)
    facts = f" [Reference, don't read aloud unless asked: {reference}]"
    return f"{lead} {spoken} Which one would you like?{facts}"


async def select_search_date_impl(depart_date: str) -> str:
    """Re-shop the current route on a date from the available-dates strip.
    Speakable, same contract as search_flights_impl."""
    slot = _LATEST_SEARCH
    if slot is None or not slot.origin or not slot.destination:
        return (
            "I need a destination first — tell me where you're headed "
            "and when."
        )
    depart_date = (depart_date or "").strip()
    window_start = None
    chips = slot.available_dates or []
    if chips and any(c.get("date") == depart_date for c in chips):
        window_start = chips[0].get("date")
    return await search_flights_impl(
        slot.session_id, slot.origin, slot.destination, depart_date,
        calendar_start=window_start,
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
    insight = _insight_for_option(option)
    if insight:
        parts.append(f"{insight['delay_risk_pct']} percent delay risk")
    return f"Option {word}: {', '.join(parts)}."


def _insight_for_option(option: FlightOption) -> Optional[dict]:
    slot = _LATEST_SEARCH
    if slot is None or not slot.insights:
        return None
    idx = option.option_number - 1
    if 0 <= idx < len(slot.insights):
        return slot.insights[idx]
    return None


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


def _replace_or_add_flight(
    context: TripContext, option: FlightOption, options_offered: List[FlightOption],
) -> None:
    """Write the chosen option onto an existing itinerary (PDF or booked
    trip) instead of creating a second trip."""
    start_ts, end_ts = option_timestamps(option)
    details = details_from_option(option)
    details["title"] = (
        f"{option.airline_name or airline_name(option.airline)} "
        f"{option.flight_number}"
    )
    location = f"{option.origin}-{option.destination}"
    flight = next((i for i in context.items if i.type == "flight"), None)
    if flight is None:
        flight = ItineraryItem(
            trip_id=context.trip.trip_id,
            type="flight",
            status="planned",
            provider="sabre",
            provider_ref=f"VOICE-FLIGHT-{uuid.uuid4().hex[:6].upper()}",
            start_ts=start_ts,
            end_ts=end_ts,
            location=location,
            details=details,
            price=option.price,
            currency=option.currency,
        )
        success, _, error = itinerary_items.create_item(flight)
        if not success:
            raise RuntimeError(f"flight item insert failed: {error}")
    else:
        success, affected, error = itinerary_items.update_flight_fields(
            flight.item_id,
            start_ts=start_ts,
            end_ts=end_ts,
            price=option.price,
            currency=option.currency,
            details=details,
        )
        if not success or affected == 0:
            raise RuntimeError(f"flight field write failed: {error}")
        view = memory_trips.get(context.trip.trip_id)
        if view is not None:
            for item in view.items:
                if item.item_id == flight.item_id:
                    item.location = location
                    break

    booking = Booking(
        item_id=flight.item_id,
        trip_id=context.trip.trip_id,
        sabre_confirmation_ref=flight.provider_ref or f"REBOOK-{option.flight_number}",
        state="confirmed",
        raw_response={
            "source": "voice_rebook",
            "option": option.model_dump(),
            "options_offered": [o.model_dump() for o in options_offered],
        },
    )
    success, _, error = bookings.create_booking(booking)
    if not success:
        raise RuntimeError(f"flight booking insert failed: {error}")
    new_status = "fixed" if flight.status in ("broken", "repairing") else "booked"
    success, affected, error = itinerary_items.update_status(
        flight.item_id, new_status
    )
    if not success or affected == 0:
        raise RuntimeError(f"flight status flip failed: {error}")
    memory_trips.patch_trip_route(
        context.trip.trip_id,
        option.origin,
        option.destination,
        date.fromisoformat(option.depart_date),
    )


async def book_flight_impl(session_id: str, option_number: int) -> str:
    """Book one of the offered options by number — the tool body, kept a
    plain function for tests. Creates the Trip + flight item + booking rows,
    replaces the session's pinned trip (ensure_trip_context caches the pin
    for the session's life), and clears the offered options. Failures return
    speakable strings — a tool that raises kills the spoken turn."""
    global _LATEST_SEARCH, _LATEST_BOOKING
    from_latest = False
    options = _SESSION_FLIGHT_OPTIONS.get(session_id)
    if not options and _LATEST_SEARCH is not None and _LATEST_SEARCH.options:
        options = list(_LATEST_SEARCH.options)
        _SESSION_FLIGHT_OPTIONS[session_id] = options
        from_latest = True
        pinned = _SESSION_TRIPS.get(_LATEST_SEARCH.session_id)
        if pinned is not None and session_id not in _SESSION_TRIPS:
            _SESSION_TRIPS[session_id] = pinned
    if not options:
        return (
            "I don't have flight options in front of me yet — tell me where "
            "you're headed and I'll search first."
        )
    try:
        option_number = int(option_number)
    except (TypeError, ValueError):
        option_number = -1
    if option_number < 1 or option_number > len(options):
        count_word = _NUMBER_WORDS.get(len(options), str(len(options)))
        return (
            f"I only offered {count_word} options — which number would "
            "you like?"
        )
    option = options[option_number - 1]
    existing = _SESSION_TRIPS.get(session_id)
    updating = bool(existing and existing.items)

    try:
        if updating:
            await asyncio.to_thread(
                _replace_or_add_flight, existing, option, options
            )
            trip_id = existing.trip.trip_id
        else:
            trip = await asyncio.to_thread(_booking_writes, option, options)
            trip_id = trip.trip_id
    except Exception:  # noqa: BLE001 — the voice turn must survive anything
        return (
            "I couldn't get that flight booked just now — give me a second "
            "and ask me again."
        )

    # The booking is real from here on; replace the pin so this session's
    # remaining turns answer from the new trip, and drop the spent options.
    _SESSION_FLIGHT_OPTIONS.pop(session_id, None)
    if _LATEST_SEARCH is not None and (
        _LATEST_SEARCH.session_id == session_id or from_latest
    ):
        _LATEST_SEARCH = None
    _LATEST_BOOKING = _booking_display(trip_id, option)
    _SESSION_TRIPS.pop(session_id, None)
    await ensure_trip_context(session_id, trip_id=trip_id)

    depart = date.fromisoformat(option.depart_date)
    legs = "nonstop" if option.stops == 0 else "with a stop"
    if updating:
        return (
            f"Done — I updated your itinerary with that flight to "
            f"{option.destination}, {legs}, leaving {_spoken_date(depart)} at "
            f"{_spoken_clock(option.depart_time)}."
        )
    return (
        f"Done — your flight to {option.destination} is booked, {legs}, "
        f"leaving {_spoken_date(depart)} at "
        f"{_spoken_clock(option.depart_time)}. Want me to arrange the rest "
        "of the trip — hotel, ride, dinner, and something fun?"
    )


def _option_display(option: FlightOption) -> dict:
    """One speakable option as the dashboard candidates card (Phase 21 + 33)."""
    payload = {
        "option_number": option.option_number,
        "route": f"{option.origin} → {option.destination}",
        "depart_date": option.depart_date,
        "depart_time": _spoken_clock(option.depart_time),
        "arrive_time": _spoken_clock(option.arrive_time),
        "stops": option.stops,
        "price": round(option.price),
        "airline_name": option.airline_name,
        "duration": (
            fmt_duration(option.duration_minutes)
            if option.duration_minutes else ""
        ),
    }
    insight = _insight_for_option(option)
    if insight:
        payload.update(insight)
    return payload


def _pending_options_payload(slot: LatestSearch) -> dict:
    return {
        "recorded_at": slot.recorded_at.isoformat(),
        "prefs_summary": slot.prefs_summary,
        "origin": slot.origin,
        "destination": slot.destination,
        "depart_date": slot.depart_date,
        "available_dates": list(slot.available_dates),
        "options": [_option_display(o) for o in slot.options],
    }


def _booking_display(trip_id: str, option: FlightOption) -> dict:
    payload = _option_display(option)
    payload["trip_id"] = trip_id
    payload["status"] = "booked"
    payload["flight_number"] = (
        str(option.flight_number) if option.flight_number else ""
    )
    payload["cabin"] = option.cabin or ""
    return payload


def current_pending_options() -> Optional[dict]:
    """Latest search options for the cascade awaiting view — trip-agnostic
    so times show while the traveler is still picking, before a trip exists."""
    slot = _LATEST_SEARCH
    if slot is None:
        return None
    if datetime.now(timezone.utc) - slot.recorded_at > _LATEST_SEARCH_TTL:
        return None
    return _pending_options_payload(slot)


def latest_booking() -> Optional[dict]:
    """The flight just booked by voice, for the cascade dashboard card."""
    return _LATEST_BOOKING


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
    return _pending_options_payload(slot)


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
    context = await _adopt_itinerary_trip(session_id)
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


async def _adopt_itinerary_trip(session_id: str) -> Optional[TripContext]:
    """Pin the session to a loaded itinerary when the orb query omitted trip_id.

    Guided booking stays unpinned. Used by optimize/apply/reject and
    reschedule_hotel after a WhatsApp, My Trips, or Cascade itinerary is
    already in memory.
    """
    context = _SESSION_TRIPS.get(session_id)
    if context is not None:
        return context
    for trip in memory_trips.list_recent():
        pinned, _error = await ensure_trip_context(session_id, trip_id=trip.trip_id)
        if pinned is not None:
            return pinned
    return None


async def _refresh_pinned_items(session_id: str) -> None:
    context = _SESSION_TRIPS.get(session_id)
    if context is None:
        return
    view = memory_trips.get(context.trip.trip_id)
    if view is not None:
        context.items = list(view.items)
        context.summary = _trip_summary(context.trip, context.items)
        return
    try:
        success, items, _error = await asyncio.to_thread(
            itinerary_items.list_items_for_trip, context.trip.trip_id
        )
    except Exception:  # noqa: BLE001
        return
    if success and items:
        context.items = items
        context.summary = _trip_summary(context.trip, items)


async def analyze_itinerary_impl(session_id: str, preference_note: str = "") -> str:
    """Score the pinned itinerary. Speakable only — no ML jargon."""
    from api import cascade_optimize

    context = await _adopt_itinerary_trip(session_id)
    if context is None:
        return (
            "I don't see an itinerary loaded yet. Open your trip from "
            "WhatsApp or My Trips, then ask me again."
        )
    try:
        result = await asyncio.to_thread(
            cascade_optimize.analyze_by_id,
            context.trip.trip_id,
            pref_text=preference_note or "",
        )
    except Exception:  # noqa: BLE001
        logger.exception("analyze_itinerary failed")
        return "I couldn't finish comparing your routes just now — ask me again in a moment."
    return result.get("spoken") or "I looked over the itinerary."


async def apply_optimization_impl(session_id: str, option_number: int) -> str:
    from api import cascade_optimize

    context = await _adopt_itinerary_trip(session_id)
    if context is None:
        return (
            "I don't see an itinerary loaded yet. Open your trip from "
            "WhatsApp or My Trips, then ask me again."
        )
    try:
        number = int(option_number)
    except (TypeError, ValueError):
        return "Tell me which recommendation number to apply."
    try:
        result = await asyncio.to_thread(
            cascade_optimize.apply_recommendation,
            context.trip.trip_id,
            str(number),
        )
    except Exception:  # noqa: BLE001
        logger.exception("apply_optimization failed")
        return "I couldn't apply that change just now — ask me again in a moment."
    await _refresh_pinned_items(session_id)
    return result.get("spoken") or "Applied."


async def reject_optimization_impl(session_id: str, option_number: int = 1) -> str:
    from api import cascade_optimize

    context = await _adopt_itinerary_trip(session_id)
    if context is None:
        return (
            "I don't see an itinerary loaded yet. Open your trip from "
            "WhatsApp or My Trips, then ask me again."
        )
    try:
        number = int(option_number or 1)
    except (TypeError, ValueError):
        number = 1
    try:
        result = await asyncio.to_thread(
            cascade_optimize.reject_recommendation,
            context.trip.trip_id,
            str(number),
        )
    except Exception:  # noqa: BLE001
        logger.exception("reject_optimization failed")
        return "Okay — I'll leave your itinerary as it is."
    return result.get("spoken") or "Okay — I'll keep your current plan."


_HOTEL_NO_TRIP_LINE = (
    "I don't see a hotel on a loaded trip yet. Open your itinerary, then "
    "ask me again."
)
_HOTEL_NO_DATES_LINE = (
    "Tell me the new check-in date and I'll move the reservation."
)
_HOTEL_BAD_DATES_LINE = (
    "I need a check-in date that comes before check-out — try those dates "
    "again."
)
_HOTEL_FAILED_LINE = (
    "I couldn't move the hotel just now — give me a second and ask me again."
)


def _parse_iso_date(value: Optional[str]) -> Optional[date]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        return None


def _hotel_wall_clock(
    ts: Optional[datetime], new_day: date, default_hour: int
) -> datetime:
    """Keep the original check-in/out clock, moved onto the new calendar day."""
    if ts is None:
        return datetime(
            new_day.year, new_day.month, new_day.day, default_hour, 0,
            tzinfo=_PACIFIC,
        )
    local = ts.astimezone(_PACIFIC) if ts.tzinfo else ts.replace(tzinfo=_PACIFIC)
    return datetime(
        new_day.year, new_day.month, new_day.day,
        local.hour, local.minute, tzinfo=_PACIFIC,
    )


async def reschedule_hotel_impl(
    session_id: str, check_in: str, check_out: str = ""
) -> str:
    """Move the pinned trip's hotel stay to new dates. Speakable only."""
    from api import repair_tools

    context = await _adopt_itinerary_trip(session_id)
    if context is None:
        return _HOTEL_NO_TRIP_LINE
    hotel = next((item for item in context.items if item.type == "hotel"), None)
    if hotel is None:
        return (
            "There's no hotel reservation on this trip yet — I can add one "
            "after the flight is booked."
        )
    new_in = _parse_iso_date(check_in)
    if new_in is None:
        return _HOTEL_NO_DATES_LINE
    old_in = _pacific_day(hotel.start_ts)
    old_out = _pacific_day(hotel.end_ts)
    new_out = _parse_iso_date(check_out)
    if new_out is None:
        span = max((old_out - old_in).days, 1) if old_in and old_out else 1
        new_out = new_in + timedelta(days=span)
    if new_out <= new_in:
        return _HOTEL_BAD_DATES_LINE
    if old_in == new_in and old_out == new_out:
        return (
            f"Your hotel is already set for {_spoken_date(new_in)} through "
            f"{_spoken_date(new_out)}."
        )
    try:
        await repair_tools._shift_hotel_dates(
            context.trip.trip_id,
            hotel.item_id,
            new_in.isoformat(),
            new_out.isoformat(),
        )
        details = dict(hotel.details or {})
        details["check_in"] = new_in.isoformat()
        details["check_out"] = new_out.isoformat()
        write_ok, affected, write_error = await asyncio.to_thread(
            itinerary_items.update_item_fields,
            hotel.item_id,
            start_ts=_hotel_wall_clock(hotel.start_ts, new_in, 22),
            end_ts=_hotel_wall_clock(hotel.end_ts, new_out, 18),
            location=hotel.location,
            details=details,
        )
        if not write_ok:
            raise RuntimeError(write_error or "hotel field write failed")
        if affected == 0:
            raise RuntimeError("hotel field write matched no rows")
    except Exception:  # noqa: BLE001 — the voice turn must survive anything
        logger.warning(
            "reschedule_hotel failed for %s", session_id, exc_info=True
        )
        return _HOTEL_FAILED_LINE
    await _refresh_pinned_items(session_id)
    return (
        f"Done — I moved your hotel to check in {_spoken_date(new_in)} "
        f"and check out {_spoken_date(new_out)}."
    )


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


async def first_stop_uber_impl(
    session_id: str, trip_id: Optional[str] = None
) -> str:
    """Speak cheapest Uber from the first city stop on the loaded itinerary."""
    try:
        if trip_id:
            await ensure_trip_context(session_id, trip_id=trip_id)
        context = await _adopt_itinerary_trip(session_id)
        from api.optimize import speak_first_stop_uber
        bound = ""
        if context is not None:
            bound = context.trip.trip_id
        elif trip_id:
            bound = trip_id
        return speak_first_stop_uber(session_id, trip_id=bound)
    except Exception:  # noqa: BLE001
        logger.warning("first_stop_uber failed for %s", session_id, exc_info=True)
        return (
            "I couldn't look up Uber from the first stop just now. "
            "There's a See available Ubers link on the itinerary."
        )


async def esim_plan_impl(session_id: str) -> str:
    """Speak a Saily eSIM suggestion for the pinned trip. Always registered;
    catalog lookup is local, no Saily API, never raises."""
    try:
        context, _ = await ensure_trip_context(session_id)
        origin = ""
        destinations: list[str] = []
        if context is not None:
            origin = context.trip.origin or ""
            destinations = list(context.trip.destinations or [])
            extras = [
                (item.location or (item.details or {}).get("title") or "")
                for item in (context.items or [])
            ]
        else:
            extras = []
        return plan_for_trip(
            origin=origin, destinations=destinations, extra_places=extras,
        ).get("speak") or (
            "Saily sells travel eSIMs — I put a Get Saily link on your itinerary."
        )
    except Exception:  # noqa: BLE001
        logger.warning("esim_plan failed for %s", session_id, exc_info=True)
        return (
            "I couldn't match an eSIM just now. Saily has prepaid travel data "
            "if you want to look it up in the app."
        )


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


def _prefs_line(session_id: str) -> str:
    prefs = _prefs_for(session_id)
    return (
        f"Current recovery ranking: {prefs.describe()}. When they change "
        "priorities, call set_recovery_preferences; do not invent a new "
        "ranking yourself. "
    )


def build_agent(session_id: str, trip_context: Optional[TripContext] = None) -> Agent:
    """The foreground agent for one turn. Tools close over session_id so
    background completions report into this voice session's log; the fresh
    snapshot (and the pinned trip's summary) go into instructions at build
    time — build per turn, never once."""
    configure_agents_sdk()

    async def _fix_trip() -> str:
        """Start the full background repair cascade for every remaining
        itinerary item. Call only when they ask to fix the whole trip
        ('fix my trip') after a disruption is already on screen. Do not
        use this when they report a cancelled flight or trip to the
        airport — call offer_rebook so they can pick a replacement."""
        return await fix_trip_impl(session_id)

    async def _offer_rebook() -> str:
        """Show numbered replacement flights after a cancelled trip to the
        airport or a cancelled flight. Call this in the same turn for
        those phrases — do not call fix_trip. Marks the disrupted leg and
        searches so the traveler can pick by number."""
        return await offer_rebook_impl(session_id)

    async def _search_flights(origin: str, destination: str, depart_date: str) -> str:
        """Search flights immediately and get ranked speakable options for
        the traveler to pick from by number. Call in the same turn the
        traveler names a destination and date on a new booking. For a
        cancelled trip to the airport or cancelled flight on a booked
        itinerary, call offer_rebook instead. Airport codes for origin and
        destination; depart_date is YYYY-MM-DD. The result is already
        scored by the delay-risk model — read its recommendation sentence."""
        return await search_flights_impl(session_id, origin, destination, depart_date)

    async def _set_recovery_preferences(
        priority: str = "",
        arrive_before: str = "",
        avoid_connections: str = "",
    ) -> str:
        """Rerank the flight options already on the table. Call when the
        traveler changes what matters instead of searching again.
        priority is one of: price, arrival, risk, nonstop, duration.
        arrive_before is a clock like '9 AM' or '09:00'.
        avoid_connections is true/false."""
        return await set_recovery_preferences_impl(
            session_id, priority, arrive_before, avoid_connections,
        )

    async def _book_flight(option_number: int) -> str:
        """Book one of the flight options just offered, by its number.
        On a fresh session this creates the trip. If an itinerary is already
        pinned (including one loaded from a PDF), this updates that trip's
        flight instead of starting a second trip."""
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

    async def _first_stop_uber() -> str:
        """Best rideshare / Uber from the first stop on the loaded itinerary,
        as if the traveler is standing there now. Call when they ask cheapest
        Uber, best option from the first stop, Uber from here, or how to get
        from the first stop to the next one."""
        return await first_stop_uber_impl(session_id)

    async def _esim_plan() -> str:
        """Recommend a Saily travel eSIM for the pinned trip's destination.
        Call when they ask about roaming, mobile data, wifi abroad, or an eSIM."""
        return await esim_plan_impl(session_id)

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

    async def _analyze_itinerary(preference_note: str = "") -> str:
        """Analyze the traveler's loaded itinerary for cheaper, faster, or
        more efficient travel. Call when they ask to optimize the trip,
        find a better route, or compare transportation — even if you were
        told there is no booked trip. Pass any preference they stated.
        The result is already scored — read it; do not pick a winner
        yourself."""
        return await analyze_itinerary_impl(session_id, preference_note)

    async def _apply_optimization(option_number: int) -> str:
        """Apply one numbered itinerary optimization the traveler accepted."""
        return await apply_optimization_impl(session_id, option_number)

    async def _reject_optimization(option_number: int = 1) -> str:
        """Keep the current plan and dismiss that numbered optimization."""
        return await reject_optimization_impl(session_id, option_number)

    async def _reschedule_hotel(check_in: str, check_out: str = "") -> str:
        """Move the traveler's hotel reservation to new stay dates. Call when
        they ask to reschedule, change, or move the hotel — even if you were
        told there is no booked trip. check_in is YYYY-MM-DD; check_out is
        YYYY-MM-DD when they named one, or empty to keep the same number of
        nights. Read the result; do not invent a confirmation number."""
        return await reschedule_hotel_impl(session_id, check_in, check_out)

    trip_line = trip_context.summary if trip_context else _NO_TRIP_LINE
    return Agent(
        name="Concierge",
        model=_llm_model(),
        instructions=(
            BASE_INSTRUCTIONS + _today_line() + _prefs_line(session_id) + trip_line
            + session_snapshot(session_id)
        ),
        tools=[
            function_tool(_fix_trip, name_override="fix_trip"),
            function_tool(_offer_rebook, name_override="offer_rebook"),
            function_tool(_search_flights, name_override="search_flights"),
            function_tool(
                _set_recovery_preferences,
                name_override="set_recovery_preferences",
            ),
            function_tool(_book_flight, name_override="book_flight"),
            function_tool(_complete_trip, name_override="complete_trip"),
            function_tool(_trip_status, name_override="trip_status"),
            function_tool(_destination_info, name_override="destination_info"),
            function_tool(_esim_plan, name_override="esim_plan"),
            function_tool(_first_stop_uber, name_override="first_stop_uber"),
            function_tool(
                _check_return_flights, name_override="check_return_flights"
            ),
            function_tool(_email_itinerary, name_override="email_itinerary"),
            function_tool(_analyze_itinerary, name_override="analyze_itinerary"),
            function_tool(_apply_optimization, name_override="apply_optimization"),
            function_tool(_reject_optimization, name_override="reject_optimization"),
            function_tool(_reschedule_hotel, name_override="reschedule_hotel"),
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
    logger.info(
        "concierge query session=%s trip_id=%s text=%r",
        session_name, trip_id or "", (query or "")[:160],
    )
    if _wants_first_stop_uber(query):
        return await first_stop_uber_impl(session_name, trip_id=trip_id)
    trip_context, _ = await ensure_trip_context(session_name, trip_id=trip_id)
    # Prefer the Cascade/Optimize trip already on screen for anything that
    # isn't a fresh booking ask — stops "I need more info / destination"
    # replies when the itinerary is loaded but trip_id was omitted.
    if trip_context is None and not _wants_fresh_booking(query):
        trip_context = await _adopt_itinerary_trip(session_name)
    if _wants_itinerary_confirm(query):
        if trip_context is not None:
            return _confirm_loaded_itinerary(trip_context)
        return (
            "I don't see an itinerary loaded yet. Open your trip from "
            "WhatsApp, My Trips, or Optimize My Trip, then ask me again."
        )
    agent = build_agent(session_name, trip_context)
    history = _HISTORY.get(session_name, [])
    result = await Runner.run(
        agent,
        history + [{"role": "user", "content": query}],
        max_turns=6,
    )
    _HISTORY[session_name] = result.to_input_list()
    return str(result.final_output)
