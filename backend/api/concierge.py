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

Trip context (QA addendum, 2026-07-09 — see the phase spec's
addendum-trip-context.md): the traveler's trip is pinned to the session at
first need — resolved once (latest trip, or an explicit trip_id via
ensure_trip_context's parameter, the Phase 12 seam), its static facts cached
in process and injected into every turn's instructions. Static facts come
from that one read; live repair progress comes only from the in-memory
snapshot — so no BigQuery read ever lands on the per-turn hot path after the
pin, and a mid-call seed of a new trip cannot switch the agent's trip.

Session history is an in-process dict (single Cloud Run instance — the
standing scope decision); blocking BigQuery reads go through
asyncio.to_thread.
"""
import asyncio
import os
from typing import Dict, List, Optional, Tuple

from agents import Agent, Runner, function_tool
from pydantic import BaseModel

from api import concurrency_core as core
from api.concurrency_agent import session_snapshot
from api.repositories import itinerary_items, trips
from api.repositories.models import ItineraryItem, Trip, rows_to_models
from api.sabre_tools import create_seed_trip, launch_trip_repairs

DEFAULT_LLM_MODEL = "gpt-5.4-mini"

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
    "trip and the traveler wants to plan or book one, confirm the "
    "destination in one short turn, then call the book_trip tool "
    "immediately — it books the complete trip in one go. Never call "
    "book_trip when a trip is already booked; offer fix_trip or answer "
    "questions about the existing trip instead. Your replies are spoken "
    "aloud: one or two short, conversational sentences. No markdown, no "
    "lists, no stage directions, and never speak ids or tool names. "
)

_NO_TRIP_LINE = (
    "There is no booked trip on file for this traveler yet — say so plainly "
    "if asked about trip details. "
)

# session_name -> Agents SDK input list (multi-turn memory).
_HISTORY: Dict[str, List] = {}


def _llm_model() -> str:
    return os.environ.get("CONCIERGE_LLM_MODEL", DEFAULT_LLM_MODEL)


class TripContext(BaseModel):
    """A session's pinned trip: the one BigQuery read, kept in process."""

    trip: Trip
    items: List[ItineraryItem]
    summary: str


# session_name -> pinned trip. Pinned once per session so a mid-call seed of
# a new trip can't switch the agent's trip, and no turn after the first pays
# a BigQuery read for context.
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
    exactly which trip broke and pins it explicitly. Without it, the most
    recently created trip wins — a voice flow can never ask for a UUID."""
    context = _SESSION_TRIPS.get(session_id)
    if context is not None:
        return context, None

    if trip_id:
        success, trip, _error = await asyncio.to_thread(trips.get_trip, trip_id)
    else:
        query = f"""
            SELECT *
            FROM `{trips._table()}`
            ORDER BY created_at DESC
            LIMIT 1
        """
        success, rows, _error = await asyncio.to_thread(
            trips.bq_helper.run_select, query
        )
        trip = rows_to_models(Trip, rows)[0] if success and rows else None
    if not success:
        return None, (
            "I'm having trouble reaching the booking system right now — "
            "give me a second and ask me again."
        )
    if trip is None:
        return None, "I don't see a booked trip for you yet."

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


# How each seed item type is spoken in the booking confirmation — the MVP
# books the fixed seed-trip shape, so the parts are known.
_SPOKEN_PARTS = {
    "flight": "a flight",
    "hotel": "a hotel in Mountain View",
    "ground": "a ride from the airport",
    "dining": "dinner",
    "experience": "a museum visit",
}


def _spoken_date(d) -> str:
    """'July 17th' — dates are read aloud, never ISO."""
    day = d.day
    if 11 <= day % 100 <= 13:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
    return f"{d.strftime('%B')} {day}{suffix}"


async def book_trip_impl(
    session_id: str, destination: str, title: Optional[str] = None
) -> str:
    """Book the complete trip in one shot — the magic utterance. The tool
    body, kept a plain function for tests (the fix_trip_impl pattern).

    Wraps create_seed_trip (blocking BigQuery — off the loop via to_thread)
    with the spoken destination folded into the trip title, then replaces
    the session's pinned trip with the new one: ensure_trip_context caches
    the pin for the session's life, so without replacement the agent would
    keep answering from the old/no-trip context after booking. Failures
    return speakable strings — a tool that raises kills the spoken turn."""
    destination = (destination or "").strip()
    if not destination:
        return "Where would you like to go? Tell me and I'll book the trip."
    trip_title = title or f"Trip to {destination}"
    try:
        result = await asyncio.to_thread(
            create_seed_trip, "demo-traveler", trip_title
        )
    except Exception:  # noqa: BLE001 — the voice turn must survive anything
        return (
            "I couldn't get that trip booked just now — give me a second "
            "and ask me again."
        )

    # The booking is real from here on; replace the pin so this session's
    # remaining turns answer from the new trip, not the old one.
    _SESSION_TRIPS.pop(session_id, None)
    context, _speakable_error = await ensure_trip_context(
        session_id, trip_id=result["trip_id"]
    )
    if context is None:
        # Booked but the read-back failed; the pin isn't cached, so a later
        # turn retries and lands on this (latest) trip.
        return (
            "Your trip is booked! Give me a moment to pull up the details, "
            "then ask me anything about it."
        )

    parts = [_SPOKEN_PARTS.get(item.type, item.type) for item in context.items]
    spoken_parts = (
        ", ".join(parts[:-1]) + f", and {parts[-1]}" if len(parts) > 1 else parts[0]
    )
    trip = context.trip
    dates = (
        f", {_spoken_date(trip.start_date)} through {_spoken_date(trip.end_date)}"
        if trip.start_date and trip.end_date
        else ""
    )
    return (
        f"Your trip to {destination} is booked — {spoken_parts}{dates}. "
        "Ask me anything about it."
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

    async def _book_trip(destination: str) -> str:
        """Book a complete trip to the given destination in one shot —
        flight, hotel, ride, dinner, and an activity. Use only when the
        traveler has no booked trip yet."""
        return await book_trip_impl(session_id, destination)

    trip_line = trip_context.summary if trip_context else _NO_TRIP_LINE
    return Agent(
        name="Concierge",
        model=_llm_model(),
        instructions=BASE_INSTRUCTIONS + trip_line + session_snapshot(session_id),
        tools=[
            function_tool(_fix_trip, name_override="fix_trip"),
            function_tool(_book_trip, name_override="book_trip"),
        ],
    )


async def answer_query(session_name: str, query: str) -> str:
    """One delegated spoken turn — the Phase 8 seam, now the Concierge.

    A plain `await Runner.run(...)` on the same loop as the background
    repairs (the concurrency_core pattern); history replay makes the
    session multi-turn. The trip pin resolves on the session's first turn
    (cached after), and a failed resolution never blocks the turn — the
    agent just lacks trip details until a later turn's retry lands."""
    trip_context, _ = await ensure_trip_context(session_name)
    agent = build_agent(session_name, trip_context)
    history = _HISTORY.get(session_name, [])
    result = await Runner.run(
        agent,
        history + [{"role": "user", "content": query}],
        max_turns=6,
    )
    _HISTORY[session_name] = result.to_input_list()
    return str(result.final_output)
