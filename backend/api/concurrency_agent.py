"""Fake tools + agent wiring for the Phase 5 concurrency spike.

The fakes are plain async functions (callable directly by tests, per the
`_get_weather` pattern in hello.py); the agent gets them wrapped with
`function_tool`. The agent's tools *launch* background work via
concurrency_core and answer immediately — never `await` the slow work inline.
That inversion is the whole spike.
"""
import asyncio
import os

from agents import Agent, Runner, function_tool
from dotenv import load_dotenv

from api import concurrency_core as core
from api.concurrency_core import RepairSpec

load_dotenv()

# One fake repair tool name per required trip category (see tech-stack.md).
REPAIR_TOOL_NAMES = {
    "flight": "rebook_flight",
    "hotel": "shift_hotel",
    "ground": "reschedule_ground",
    "dining": "move_dining",
    "experience": "rebook_experience",
}


async def _slow_api_call(seconds: float = 10.0) -> dict:
    """The fake 10-second API call from Pallavi's test — nothing but time."""
    await asyncio.sleep(seconds)
    return {"status": "done", "detail": f"fake API call finished after {seconds:.1f}s"}


async def fake_repair(spec: RepairSpec) -> dict:
    """Fake category repair: wait the injected duration, return a canned
    'rebooked' payload shaped like a provider confirmation."""
    await asyncio.sleep(spec.duration_seconds)
    return {
        "item_id": spec.item_id,
        "repair": spec.name,
        "status": "rebooked",
        "confirmation_ref": f"FAKE-{spec.name.upper()}-{spec.item_id[:8]}",
        "duration_seconds": spec.duration_seconds,
    }


async def failing_repair(spec: RepairSpec) -> dict:
    """Fake repair that breaks mid-flight — for the edge-case proof that one
    failure neither kills the siblings nor flips its item to fixed."""
    await asyncio.sleep(spec.duration_seconds)
    raise RuntimeError(f"provider rejected {spec.name} for {spec.item_id}")


def session_snapshot(session_id: str) -> str:
    """One-line summary of the session's background work, for the agent's
    instructions — so a follow-up like "how are the repairs coming?" gets a
    grounded answer instead of a clarifying question."""
    session = core.get_session(session_id)
    pending = session.pending()
    landed = [f"{e.name}: {'done' if e.status == 'ok' else 'FAILED'}" for e in session.events]
    if not pending and not landed:
        return "No background work is currently running for this traveler."
    parts = []
    if pending:
        parts.append(f"still in progress: {', '.join(pending)}")
    if landed:
        parts.append(f"finished: {', '.join(landed)}")
    return (
        "LIVE STATUS of this traveler's background work (authoritative — "
        f"this list is what 'the repairs' means): {'; '.join(parts)}. "
        "When asked about progress, summarize this list directly; never ask "
        "which repairs are meant."
    )


def build_agent(session_id: str) -> Agent:
    """Agent whose slow tool starts background work and returns immediately.

    Tools close over session_id so completions report into the right session
    log — the id must not leak into the LLM-facing tool schema. Instructions
    carry a snapshot of the session's background work, taken at build time —
    build the agent per turn, not once.
    """

    async def _start_slow_api_lookup(seconds: float = 10.0) -> str:
        """Start a slow travel-API lookup. It runs in the background; you get
        the result later, so keep helping the traveler in the meantime."""
        core.start_background_call(session_id, "slow_api_call", _slow_api_call(seconds))
        return (
            f"Lookup started in the background (about {seconds:.0f}s). "
            "Keep the conversation going; results will arrive when ready."
        )

    return Agent(
        name="Concurrency Spike Agent",
        model="gpt-5.4-mini",
        instructions=(
            "You are a travel assistant in a live conversation. Slow "
            "operations run in the background via your tools — never wait "
            "for them silently. Answer follow-up questions promptly and "
            "concisely while background work is in flight. "
            + session_snapshot(session_id)
        ),
        tools=[function_tool(_start_slow_api_lookup)],
    )


def openai_key_present() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


async def run_followup_turn(session_id: str, question: str) -> str:
    """One agent turn (`Runner.run` is a classmethod, per hello.py) — awaited
    while background tasks run on the same loop. The router stubs this in
    hermetic tests."""
    result = await Runner.run(build_agent(session_id), question, max_turns=10)
    return result.final_output
