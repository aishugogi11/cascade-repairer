"""Demo orchestrator — Phase 12's "one button, one beat" surface, reworked
by Phase 23 into the consent-gated flow.

Two endpoints compose the Cascade Repairer demo from seams built in earlier
phases; a third serves the operator-facing demo page:

- POST /book — Beat 1: the traveler receives a phone call while the booked
  trip lands. The outbound call (vb_cli, Phase 7) carries the booking
  narrative; the trip itself is seeded server-side (create_seed_trip,
  Phase 6). The hosted Vocal Bridge caller agent cannot invoke our tools
  mid-call, so the call is the narrative and the backend does the booking —
  accepted stagecraft; the purpose derives from the same seed data so voice
  and screen tell the same story.
- POST /disrupt — Beat 2 (Phase 23): does exactly two things — places
  Call 1, which tells the traveler their flight was cancelled and asks for
  their consent to repair, and breaks the flight (break_trip_flight). No
  repairs launch at click time: a background consent watcher polls the VB
  session log for that call, reads the traveler's answer from
  transcript_text, and launches the repair cascade only on an unambiguous
  yes — then awaits the repairs and places Call 2, the results callback,
  composed from the actual post-repair state. Everything else stands down
  and surfaces on the page via the consent registry (api.consent).
- GET / — the demo page (assets/demo/page.html), the projector surface.

In each beat the call fires before the data writes — the phone should ring
while the screen changes, not after (reads may precede the call: the script
is composed from the trip's data). Failure of any leg is an error status,
never a silent partial success. Same invariants as outbound_call.py: nothing
returned ever contains the callee phone number or the API key; blocking work
runs via asyncio.to_thread.
"""
import asyncio
import logging
import uuid
from pathlib import Path
from typing import Optional, Set

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from api import call_purposes, consent, email_content, trip_emails, vb_cli
from api.email_client import send_email
from api.paypal_client import refund_fare_difference
from api.disruption import break_trip_flight
from api.itinerary_ui import _details_for
from api.outbound_call import _missing_env, _scrub
from api.repositories import itinerary_items, trips
from api.sabre_tools import _SEED_ITEMS, create_seed_trip, launch_trip_repairs

logger = logging.getLogger(__name__)

demo = APIRouter()

# Read per request, not at import: uvicorn --reload only watches .py files,
# so an import-time read would serve stale HTML all through local dev.
_PAGE_PATH = Path(__file__).parent / "assets" / "demo" / "page.html"

_REQUIRED_ENV = (
    "VOCAL_BRIDGE_API_KEY",
    "VOCAL_BRIDGE_CALLER_AGENT_ID",
    "VOCAL_BRIDGE_CALLEE_PHONE",
)

# Consent-watcher tuning (Phase 23). place_call blocks ~10–16 s before the
# phone even rings and the consent conversation takes tens of seconds, so
# the watcher polls gently and gives the whole call three minutes before
# standing down as timed_out. Module constants so tests can shrink them.
_CONSENT_POLL_SECONDS = 4.0
_CONSENT_TIMEOUT_SECONDS = 180.0

# Strong refs so the fire-and-forget watcher tasks aren't garbage-collected
# mid-flight (the web_call._LOG_TASKS pattern).
_WATCHER_TASKS: Set[asyncio.Task] = set()


async def _await_call_transcript(session_key: Optional[str]) -> Optional[str]:
    """Poll the VB session log until Call 1 reads completed AND carries a
    transcript, or the timeout lapses (None). transcript_text can land a
    beat after the completed status (post_processing lag — the resolved
    2026-07-15 spike), so both conditions gate together and the poll
    cadence absorbs the lag. session_key is the call's room_name (the log
    join key, Phase 31) with call_id as the legacy fallback; find_session
    matches id, session_id, and room_name."""
    if not session_key:
        return None
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _CONSENT_TIMEOUT_SECONDS
    while loop.time() < deadline:
        ok, session, _error = await asyncio.to_thread(
            vb_cli.find_session, session_key
        )
        if ok and isinstance(session, dict):
            status = session.get("call_status") or session.get("status")
            transcript = session.get("transcript_text") or ""
            if status == "completed" and transcript.strip():
                return transcript
        await asyncio.sleep(_CONSENT_POLL_SECONDS)
    return None


async def _maybe_refund_line(items) -> Optional[str]:
    """PayPal fare-difference refund (sponsor award beat) — Pallavi G. When the repair
    landed a cheaper flight, send the difference via sandbox Payouts and
    return the one sentence Call 2 appends. Never raises (the client
    guarantees it); returns None whenever there is nothing to say — no
    flight, not fixed, no original fare, refund skipped/disabled."""
    flight = next((i for i in items if i.type == "flight"), None)
    if flight is None or flight.status != "fixed":
        return None
    original = (flight.details or {}).get("rebooked_from") or {}
    refund = await refund_fare_difference(
        old_fare=original.get("price"),
        new_fare=flight.price,
        currency=flight.currency or "USD",
    )
    return refund.spoken_line


# The Call 2 email-offer beat (Phase 40) — appended to the results purpose
# only when an address is on file for the trip (the booking-call beat
# stored it). No address means no offer sentence and no watcher: Call 2 is
# byte-identical to the pre-40 callback.
_EMAIL_OFFER_PURPOSE = (
    "Before you wrap up, offer exactly once: you can email them this "
    "summary — ask 'Would you like an email of this?'. If they say yes, "
    "tell them it's on its way to the address they gave when they booked; "
    "if they decline, move on warmly without pushing."
)


async def _watch_email_offer(
    trip_id: str,
    session_key: Optional[str],
    address: str,
    trip,
    items,
    details,
    refund_line: Optional[str],
) -> None:
    """The Phase 40 email watcher, one background task per Call 2 placed
    with an address on file: wait for the call's transcript (the consent
    watcher's machinery), classify the traveler's answer to the email
    offer, and send the repair email only on an unambiguous yes. Every
    other outcome — no, ambiguous, timeout, missing session key — sends
    nothing (the consent honesty posture). Never raises, and by
    construction never touches Call 2 itself, the cascade, or consent
    state: the call is already placed when this task is born, and the
    email content is the same loaded data the call's purpose spoke."""
    try:
        transcript = await _await_call_transcript(session_key)
        if transcript is None:
            return
        verdict = await consent.classify_email_offer(transcript)
        if verdict != "yes":
            return
        content = email_content.build_repair_email(
            trip, items, details, refund_line
        )
        result = await send_email(
            to=address,
            subject=content.subject,
            html=content.html,
            text=content.text,
        )
        logger.info(
            "repair email %s for trip %s", result.get("status"), trip_id
        )
    except Exception:  # noqa: BLE001 — background task must never propagate
        logger.warning(
            "email offer watcher failed for trip %s", trip_id, exc_info=True
        )


async def _call_back_with_results(trip_id: str, tasks) -> None:
    """The completion watcher → Call 2: wait for the repair tasks this
    backend launched, then place the results callback with a purpose
    composed from the actual post-repair state — the phone agent speaks
    the true fixed state because its script *is* the live data. Best-effort
    end to end: a failed read degrades the script, a failed call logs — a
    background task must never take down the loop holding the conversation.
    With an address on file (Phase 40) the purpose gains the email offer
    and an email watcher follows the call; a failed email path can never
    affect the call itself."""
    if tasks:
        # Repair tasks capture their own failures into completion events
        # (concurrency_core._record); return_exceptions is belt and braces.
        await asyncio.gather(*tasks, return_exceptions=True)

    success, trip, error = await asyncio.to_thread(trips.get_trip, trip_id)
    if not success or trip is None:
        logger.warning(
            "results callback skipped: could not load trip %s: %s", trip_id, error
        )
        return
    success, items, error = await asyncio.to_thread(
        itinerary_items.list_items_for_trip, trip_id
    )
    if not success:
        items = []
    details = await _details_for(trip_id, items)
    purpose = call_purposes.build_results_purpose(trip, items, details)
    refund_line = await _maybe_refund_line(items)
    if refund_line:
        purpose = purpose + " " + refund_line
    email_address = trip_emails.get(trip_id)
    if email_address:
        purpose = purpose + " " + _EMAIL_OFFER_PURPOSE
    ok, call, error = await asyncio.to_thread(
        vb_cli.place_call, purpose, "demo-beat3-results"
    )
    if not ok:
        logger.warning("results callback call failed: %s", _scrub(error))
        return
    if email_address:
        # The same session-log join key as the consent watcher (Phase 31):
        # room_name first, call_id as the legacy fallback. A payload with
        # neither spawns a watcher that times out quietly — no email, and
        # never a failed callback.
        session_key = None
        if isinstance(call, dict):
            session_key = call.get("room_name") or call.get("call_id")
        task = asyncio.create_task(
            _watch_email_offer(
                trip_id, session_key, email_address,
                trip, items, details, refund_line,
            )
        )
        _WATCHER_TASKS.add(task)
        task.add_done_callback(_WATCHER_TASKS.discard)


async def _watch_consent_then_repair(
    trip_id: str, session_key: Optional[str], token: int
) -> None:
    """The Phase 23 consent watcher, one background task per disrupt: wait
    for Call 1's transcript, classify the traveler's answer, launch the
    repair cascade only on an unambiguous yes — then hand off to the
    completion watcher for Call 2. Every other outcome (no, ambiguous,
    timeout, failure) stands down and resolves the registry so the page
    always learns how the wait ended. Never raises — background task."""
    try:
        transcript = await _await_call_transcript(session_key)
        if not consent.is_current(trip_id, token):
            return  # superseded by a re-triggered cascade — stand down
        if transcript is None:
            consent.resolve(trip_id, token, consent.TIMED_OUT)
            return

        verdict = await consent.classify_consent(transcript)
        if verdict == "no":
            consent.resolve(trip_id, token, consent.DECLINED)
            return
        if verdict != "yes":
            consent.resolve(
                trip_id, token, consent.DECLINED,
                message="The traveler's answer wasn't a clear yes — "
                        "repairs are standing by. Trigger the cascade "
                        "again to retry.",
            )
            return

        success, items, error = await asyncio.to_thread(
            itinerary_items.list_items_for_trip, trip_id
        )
        if not success or not items:
            logger.warning(
                "consent granted but items unreadable for trip %s: %s",
                trip_id, error,
            )
            consent.resolve(trip_id, token, consent.ERROR)
            return

        # The atomic gate (Phase 31, the validator's race): claim the wait
        # BEFORE launching, with no awaits in between — resolve is
        # synchronous module state on this single event loop, so a fresh
        # Cancel registered during the classifier/repository awaits above
        # makes this return False and the stale watcher stands down without
        # launching anything. Only then is it the go-ahead moment: repairs
        # launch, and the page's recovery timer anchors on the first
        # `repairing` status these flips produce.
        if not consent.resolve(trip_id, token, consent.GRANTED):
            return
        repair_session_id = f"demo-{uuid.uuid4().hex[:12]}"
        _launched, tasks = launch_trip_repairs(repair_session_id, items)

        await _call_back_with_results(trip_id, tasks)
    except Exception:  # noqa: BLE001 — background task must never propagate
        logger.warning("consent watcher failed for trip %s", trip_id, exc_info=True)
        consent.resolve(trip_id, token, consent.ERROR)


# Both call scripts are composed from real trip data at placement time
# (call_purposes, Phase 23) — the Phase 12 hardcoded narratives described
# the wrong trip the moment booking went voice-first.


class BookRequest(BaseModel):
    user_id: str = "demo-traveler"
    title: str = "The Complete Trip — hackathon demo"


class DisruptRequest(BaseModel):
    trip_id: str


@demo.get("/", response_class=HTMLResponse)
def demo_page():
    return _PAGE_PATH.read_text()


@demo.post(
    "/book",
    summary="[Phase 12] Beat 1 — call the traveler while their trip books",
)
async def book(request: BookRequest):
    missing = _missing_env(*_REQUIRED_ENV)
    if missing:
        return JSONResponse(status_code=503, content={"error": f"{missing} not set"})

    # Call first: place_call returns as soon as the call is queued, so the
    # phone rings while the trip writes land. The purpose derives from the
    # same seed data the writes are about to use — voice and screen agree
    # by construction.
    ok, call, error = await asyncio.to_thread(
        vb_cli.place_call,
        call_purposes.build_book_purpose(request.title, _SEED_ITEMS),
        "demo-beat1-booking",
    )
    if not ok:
        return JSONResponse(status_code=502, content={"error": _scrub(error)})

    seeded = await asyncio.to_thread(
        create_seed_trip, request.user_id, request.title
    )
    return {
        "trip_id": seeded["trip_id"],
        "call_id": call["call_id"],
        "call_status": call["status"],
    }


@demo.post(
    "/disrupt",
    summary="[Phase 23] Beat 2 — cancellation call asking consent, broken "
    "flight; repairs wait for the traveler's spoken yes",
)
async def disrupt(request: DisruptRequest):
    missing = _missing_env(*_REQUIRED_ENV)
    if missing:
        return JSONResponse(status_code=503, content={"error": f"{missing} not set"})

    # Read the real trip first (reads, not writes — the call-before-write
    # invariant is untouched) so the call script describes the trip that is
    # actually breaking, and a trip that can't break (unknown, or no flight
    # item) 404s before any quota is spent on a call.
    success, trip, error = await asyncio.to_thread(trips.get_trip, request.trip_id)
    if not success:
        raise HTTPException(status_code=500, detail=f"could not load trip: {error}")
    if trip is None:
        raise HTTPException(status_code=404, detail=f"trip {request.trip_id} not found")
    success, items, error = await asyncio.to_thread(
        itinerary_items.list_items_for_trip, request.trip_id
    )
    if not success:
        raise HTTPException(status_code=500, detail=f"could not list items: {error}")
    if not any(item.type == "flight" for item in items):
        raise HTTPException(
            status_code=404,
            detail=f"trip {request.trip_id} has no flight item to break",
        )

    ok, call, error = await asyncio.to_thread(
        vb_cli.place_call,
        call_purposes.build_disrupt_purpose(trip, items),
        "demo-beat2-disruption",
    )
    if not ok:
        return JSONResponse(status_code=502, content={"error": _scrub(error)})

    # break_trip_flight's 404 (no flight item / unknown trip) and 500
    # (failed or 0-row write) pass through untouched.
    broken = await asyncio.to_thread(break_trip_flight, request.trip_id)

    # No repairs at click time (Phase 23): register the consent wait and
    # hand off to the watcher, which launches the cascade only on the
    # traveler's spoken yes. A re-clicked Cancel supersedes the previous
    # wait — register_awaiting mints a fresh token and the old watcher
    # stands down on its next resolution attempt.
    #
    # The watcher is keyed on room_name (Phase 31): the session logs carry
    # id + room_name but never call_id, so a call_id-keyed watcher polls to
    # its timeout while the completed session sits in the log — the exact
    # live failure of 2026-07-15. call_id remains the fallback for older
    # CLI shapes; find_session matches every key.
    session_key = call.get("room_name") or call["call_id"]
    token = consent.register_awaiting(request.trip_id, session_key)
    task = asyncio.create_task(
        _watch_consent_then_repair(request.trip_id, session_key, token)
    )
    _WATCHER_TASKS.add(task)
    task.add_done_callback(_WATCHER_TASKS.discard)

    return {
        "trip_id": request.trip_id,
        "item_id": broken["item_id"],
        "call_id": call["call_id"],
        "call_status": call["status"],
        "consent": consent.AWAITING,
    }
