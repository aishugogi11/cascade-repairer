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

Session history is an in-process dict (single Cloud Run instance — the
standing scope decision); blocking BigQuery reads go through
asyncio.to_thread.
"""
import asyncio
import os
from typing import Dict, List, Optional, Tuple

from agents import Agent, Runner, function_tool

from api import concurrency_core as core
from api.concurrency_agent import session_snapshot
from api.repositories import itinerary_items, trips
from api.repositories.models import ItineraryItem
from api.sabre_tools import launch_trip_repairs

DEFAULT_LLM_MODEL = "gpt-4.1-mini"

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
    "keep helping. Your replies are spoken aloud: one or two short, "
    "conversational sentences. No markdown, no lists, no stage directions, "
    "and never speak ids or tool names. "
)

# session_name -> Agents SDK input list (multi-turn memory).
_HISTORY: Dict[str, List] = {}


def _llm_model() -> str:
    return os.environ.get("CONCIERGE_LLM_MODEL", DEFAULT_LLM_MODEL)


async def _latest_trip_items() -> Tuple[Optional[List[ItineraryItem]], Optional[str]]:
    """The demo trip's items: most recently created trip, then its items.
    Returns (items, speakable_error) — exactly one is set. A voice flow can
    never ask the traveler for a trip id, so resolution is server-side."""
    query = f"""
        SELECT trip_id
        FROM `{trips._table()}`
        ORDER BY created_at DESC
        LIMIT 1
    """
    success, rows, error = await asyncio.to_thread(trips.bq_helper.run_select, query)
    if not success:
        return None, (
            "I'm having trouble reaching the booking system right now — "
            "give me a second and ask me again."
        )
    if not rows:
        return None, "I don't see a booked trip for you yet."

    trip_id = rows[0]["trip_id"]
    success, items, error = await asyncio.to_thread(
        itinerary_items.list_items_for_trip, trip_id
    )
    if not success:
        return None, (
            "I found your trip but can't read its details right now — "
            "give me a second and ask me again."
        )
    if not items:
        return None, "Your trip doesn't have any bookings on it yet."
    return items, None


async def fix_trip_impl(session_id: str) -> str:
    """Launch the repair cascade for the traveler's trip — the tool body,
    kept a plain function for tests (the hello.py pattern).

    Fires one background repair per itinerary item through the same seam as
    /repair_trip and returns immediately with a speakable summary; the tasks
    report into this session's event log as they land. Failures return
    speakable strings — a tool that raises would kill the spoken turn."""
    try:
        items, speakable_error = await _latest_trip_items()
        if speakable_error:
            return speakable_error
        launched, _tasks = launch_trip_repairs(session_id, items)
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


def build_agent(session_id: str) -> Agent:
    """The foreground agent for one turn. Tools close over session_id so
    background completions report into this voice session's log; the fresh
    snapshot goes into instructions at build time — build per turn, never
    once."""

    async def _fix_trip() -> str:
        """Start repairs for the traveler's booked trip after a disruption.
        Repairs run in the background and this returns immediately — keep
        the conversation going while they work."""
        return await fix_trip_impl(session_id)

    return Agent(
        name="Concierge",
        model=_llm_model(),
        instructions=BASE_INSTRUCTIONS + session_snapshot(session_id),
        tools=[function_tool(_fix_trip, name_override="fix_trip")],
    )


async def answer_query(session_name: str, query: str) -> str:
    """One delegated spoken turn — the Phase 8 seam, now the Concierge.

    A plain `await Runner.run(...)` on the same loop as the background
    repairs (the concurrency_core pattern); history replay makes the
    session multi-turn."""
    agent = build_agent(session_name)
    history = _HISTORY.get(session_name, [])
    result = await Runner.run(
        agent,
        history + [{"role": "user", "content": query}],
        max_turns=6,
    )
    _HISTORY[session_name] = result.to_input_list()
    return str(result.final_output)
