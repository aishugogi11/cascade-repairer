"""Talk-while-work-runs concurrency core (Phase 5 spike).

Plain asyncio — no LLM, no FastAPI — so the pattern the voice phases (7–9)
will reuse is provable without OPENAI_API_KEY or GCP credentials. The agent
layer wraps these primitives; it never re-implements them.

The pattern: background work is fired with `asyncio.create_task` alongside
the active session instead of being awaited inline, and every completion is
recorded to a per-session event log the session can read as results land.

The session registry is a module-level dict — spike-grade, in-memory,
single-process. Fine for the demo (one Cloud Run instance, one conversation);
a real product would need external state.
"""
import asyncio
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from pydantic import BaseModel

from api.repositories import itinerary_items


class CompletionEvent(BaseModel):
    """One finished piece of background work, as reported into the session."""

    name: str
    status: str  # "ok" | "error"
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: str  # wall clock, ISO 8601 UTC — for humans
    finished_at: str
    started_monotonic: float  # time.monotonic() — for overlap assertions
    finished_monotonic: float


class SessionLog(BaseModel):
    """Per-session record of in-flight tasks and landed completions."""

    model_config = {"arbitrary_types_allowed": True}

    session_id: str
    events: List[CompletionEvent] = []
    tasks: List[asyncio.Task] = []

    def pending(self) -> List[str]:
        return [t.get_name() for t in self.tasks if not t.done()]


_SESSIONS: Dict[str, SessionLog] = {}


def get_session(session_id: str) -> SessionLog:
    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = SessionLog(session_id=session_id)
    return _SESSIONS[session_id]


def clear_session(session_id: str) -> None:
    _SESSIONS.pop(session_id, None)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _record(session_id: str, name: str, coro: Awaitable[Any]) -> CompletionEvent:
    """Await `coro`, then append its completion event to the session log.

    Exceptions are captured into the event (status="error") rather than
    propagated — one failed repair must not kill the session or its siblings.
    """
    session = get_session(session_id)
    started_at = _utc_now_iso()
    started_monotonic = time.monotonic()
    try:
        result = await coro
        event = CompletionEvent(
            name=name,
            status="ok",
            result=result,
            started_at=started_at,
            finished_at=_utc_now_iso(),
            started_monotonic=started_monotonic,
            finished_monotonic=time.monotonic(),
        )
    except Exception as exc:  # noqa: BLE001 — the event log is the error surface
        event = CompletionEvent(
            name=name,
            status="error",
            error=f"{type(exc).__name__}: {exc}",
            started_at=started_at,
            finished_at=_utc_now_iso(),
            started_monotonic=started_monotonic,
            finished_monotonic=time.monotonic(),
        )
    session.events.append(event)
    return event


def start_background_call(session_id: str, name: str, coro: Awaitable[Any]) -> asyncio.Task:
    """Fire-and-forget: run `coro` in the background, report completion into
    the session log. Returns the task so callers can await it if they choose;
    the session keeps talking either way."""
    task = asyncio.create_task(_record(session_id, name, coro), name=name)
    get_session(session_id).tasks.append(task)
    return task


class RepairSpec(BaseModel):
    """One fake repair: which itinerary item, what to call it, how long it takes."""

    item_id: str
    name: str  # e.g. "rebook_flight"
    duration_seconds: float


async def _update_status_or_raise(item_id: str, status: str) -> None:
    """Run the status DML in a thread and raise unless it landed on a real row.

    `update_status` returns (success, affected_rows, error); a False success
    or 0 affected rows means the flip never reached the table the UI reads, so
    the repair must surface as an error — never a false `ok`.
    """
    success, affected_rows, error = await asyncio.to_thread(
        itinerary_items.update_status, item_id, status
    )
    if not success:
        raise RuntimeError(
            f"status write failed for item {item_id} -> {status}: {error}"
        )
    if affected_rows == 0:
        raise RuntimeError(
            f"status write for item {item_id} -> {status} matched no rows"
        )


async def _repair_one(
    session_id: str,
    spec: RepairSpec,
    do_repair: Callable[[RepairSpec], Awaitable[Any]],
) -> Any:
    """The cascade unit: flip the item to `repairing`, do the work, flip to
    `fixed`. On failure — including a failed or 0-row status write — the item
    is left as-is (not `fixed`) and the exception surfaces in the completion
    event via _record.

    Repository calls are sync (blocking BigQuery client), so they run in a
    thread — a blocking DML on the event loop would stall the very
    conversation this spike exists to keep alive.
    """
    await _update_status_or_raise(spec.item_id, "repairing")
    result = await do_repair(spec)
    await _update_status_or_raise(spec.item_id, "fixed")
    return result


def run_repairs(
    session_id: str,
    specs: List[RepairSpec],
    do_repair: Callable[[RepairSpec], Awaitable[Any]],
) -> List[asyncio.Task]:
    """Launch one background repair task per spec — all concurrent, each
    reporting its completion into the session log as it lands."""
    return [
        start_background_call(session_id, spec.name, _repair_one(session_id, spec, do_repair))
        for spec in specs
    ]
