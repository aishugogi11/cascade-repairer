"""Phase 5 concurrency spike endpoints — the two proofs, curl-testable.

Proof A (POST /talk_while_tool_runs): the agent answers a follow-up turn
while a fake 10-second tool call is still in flight — Pallavi's test.

Proof B (POST /cascade): N>=3 fake repairs run concurrently, each writing its
repairing -> fixed transition to itinerary_items as it lands.

Text transport only; the concurrency pattern (concurrency_core) is what the
voice phases reuse, not these endpoints.
"""
import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api import concurrency_agent, concurrency_core as core
from api.concurrency_core import RepairSpec

concurrency_spike = APIRouter()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Proof A: talk while a slow tool call runs -------------------------------

class TalkRequest(BaseModel):
    session_id: Optional[str] = None
    question: str = "While that lookup runs — what should I pack for Mountain View in July?"
    slow_seconds: float = 10.0


@concurrency_spike.post("/talk_while_tool_runs")
async def talk_while_tool_runs(req: TalkRequest):
    """Start the fake slow call in the background, then answer a follow-up
    agent turn while it is still running. The response carries the timing
    evidence; `answered_before_tool_finished` is the acceptance bit."""
    if not concurrency_agent.openai_key_present():
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not set — the follow-up turn needs the "
                   "agent LLM. Set the key and retry; the concurrency core "
                   "itself is proven hermetically in the test suite.",
        )

    session_id = req.session_id or f"spike-{uuid.uuid4().hex[:12]}"
    slow_started_at = _utc_now_iso()
    slow_started_monotonic = time.monotonic()
    slow_task = core.start_background_call(
        session_id, "slow_api_call", concurrency_agent._slow_api_call(req.slow_seconds)
    )

    answer = await concurrency_agent.run_followup_turn(session_id, req.question)

    answered_monotonic = time.monotonic()
    still_running = not slow_task.done()
    session = core.get_session(session_id)
    return {
        "session_id": session_id,
        "followup_answer": answer,
        "followup_answered_at": _utc_now_iso(),
        "followup_latency_seconds": round(answered_monotonic - slow_started_monotonic, 3),
        "slow_call": {
            "seconds": req.slow_seconds,
            "started_at": slow_started_at,
            "state": "running" if still_running else "finished",
        },
        "answered_before_tool_finished": still_running,
        "completed_events": [e.model_dump() for e in session.events],
        "pending_tasks": session.pending(),
    }


# --- Proof B: parallel repair cascade ----------------------------------------

# Default demo cascade: one item per required category, staggered durations so
# overlap (wall time ~= max, not sum) is visible in the completion log.
_DEFAULT_ITEMS = [
    RepairSpec(item_id=f"demo-{category}", name=tool_name, duration_seconds=2.0 + i)
    for i, (category, tool_name) in enumerate(concurrency_agent.REPAIR_TOOL_NAMES.items())
]


class CascadeRequest(BaseModel):
    session_id: Optional[str] = None
    items: Optional[List[RepairSpec]] = None  # default: the five demo categories
    wait: bool = False  # true: return after all repairs land, with the full event log
    fail_one: bool = False  # break the first repair, proving siblings survive


@concurrency_spike.post("/cascade")
async def cascade(req: CascadeRequest):
    """Launch one background repair task per item — all concurrent. With
    wait=false (default) this returns immediately, proving the launch does
    not block; call again with wait=true to see the landed event log."""
    specs = req.items if req.items else _DEFAULT_ITEMS
    if len(specs) < 3:
        raise HTTPException(status_code=422, detail="The cascade proof needs N>=3 items.")

    session_id = req.session_id or f"cascade-{uuid.uuid4().hex[:12]}"
    failing_item = specs[0].item_id if req.fail_one else None

    async def do_repair(spec: RepairSpec):
        if spec.item_id == failing_item:
            return await concurrency_agent.failing_repair(spec)
        return await concurrency_agent.fake_repair(spec)

    launched_at = _utc_now_iso()
    tasks = core.run_repairs(session_id, specs, do_repair)
    if req.wait:
        await asyncio.gather(*tasks)

    session = core.get_session(session_id)
    return {
        "session_id": session_id,
        "launched_at": launched_at,
        "launched": [s.name for s in specs],
        "item_ids": [s.item_id for s in specs],
        "waited_for_completion": req.wait,
        "pending_tasks": session.pending(),
        "completed_events": [e.model_dump() for e in session.events],
    }
