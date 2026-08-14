"""Consent machinery for the consent-gated demo flow — Phase 23.

The registry is the dashboard's window into the break → consent → repair
sequence: the disrupt endpoint registers an awaiting entry when Call 1 is
placed, the consent watcher resolves it (granted / declined / timed_out /
error), and the status poll surfaces it as an additive, best-effort
`consent` block. In-process module state keyed by trip_id — the standing
single-instance scope decision; a Cloud Run restart simply forgets the
wait, and the operator re-triggers.

Tokens make re-triggering safe: every registration mints a new token, and
a watcher may only resolve the entry it was born with — a superseded
watcher (the operator clicked Cancel again) stands down silently instead
of flipping the fresh wait.

The classifier is the LLM seam: one small Agents SDK call (the codebase's
standard LLM path) that reads Call 1's transcript_text and answers yes /
no / ambiguous. Only an unambiguous yes launches repairs; everything else
— including a classifier failure — stands down, because repairing without
a read go-ahead is the one wrong answer. Kept a plain function so tests
monkeypatch it and stay hermetic (no OPENAI_API_KEY).
"""
import itertools
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Optional

from agents import Agent, Runner

from api.llm_client import agents_model, configure_agents_sdk
from pydantic import BaseModel

logger = logging.getLogger(__name__)

DEFAULT_CONSENT_MODEL = "gpt-5.4-mini"

AWAITING = "awaiting_consent"
GRANTED = "granted"
DECLINED = "declined"
TIMED_OUT = "timed_out"
ERROR = "error"

# Page-facing copy per state — the dashboard renders these verbatim, so
# they follow the page's voice (sentence case, plain words).
_MESSAGES = {
    AWAITING: "Waiting for the traveler's go-ahead — Cascade is on the "
              "phone asking to repair.",
    GRANTED: "Go-ahead received — repairs are running.",
    DECLINED: "The traveler declined the repair — nothing was changed.",
    TIMED_OUT: "No go-ahead from the call — repairs are standing by. "
               "Trigger the cascade again to retry.",
    ERROR: "Couldn't start the repairs — trigger the cascade again.",
}


class ConsentRecord(BaseModel):
    trip_id: str
    call_id: Optional[str] = None
    state: str
    message: str
    since: datetime
    updated_at: datetime
    token: int


_RECORDS: Dict[str, ConsentRecord] = {}
_TOKENS = itertools.count(1)


def register_awaiting(trip_id: str, call_id: Optional[str]) -> int:
    """Register a fresh consent wait for this trip — replaces any prior
    entry (a re-clicked Cancel supersedes the old watcher, whose token goes
    stale). Returns the token the new watcher must present to resolve."""
    token = next(_TOKENS)
    now = datetime.now(timezone.utc)
    _RECORDS[trip_id] = ConsentRecord(
        trip_id=trip_id, call_id=call_id, state=AWAITING,
        message=_MESSAGES[AWAITING], since=now, updated_at=now, token=token,
    )
    return token


def is_current(trip_id: str, token: int) -> bool:
    record = _RECORDS.get(trip_id)
    return record is not None and record.token == token


def resolve(
    trip_id: str, token: int, state: str, message: Optional[str] = None
) -> bool:
    """Move this trip's consent wait to a new state — only if the token is
    still current. A superseded watcher's resolution is dropped (False), so
    a re-triggered cascade can never be flipped by the previous call."""
    if not is_current(trip_id, token):
        return False
    record = _RECORDS[trip_id]
    _RECORDS[trip_id] = record.model_copy(update={
        "state": state,
        "message": message or _MESSAGES.get(state, ""),
        "updated_at": datetime.now(timezone.utc),
    })
    return True


def current(trip_id: str) -> Optional[ConsentRecord]:
    return _RECORDS.get(trip_id)


def consent_block(trip_id: str) -> Optional[dict]:
    """The additive status-poll block — None when the trip has no consent
    history, so the poll omits the key entirely (the detail/pending_options
    precedent)."""
    record = _RECORDS.get(trip_id)
    if record is None:
        return None
    return {
        "state": record.state,
        "message": record.message,
        "since": record.since.isoformat(),
        "updated_at": record.updated_at.isoformat(),
    }


def reset() -> None:
    """Test hook — the registry is module state."""
    _RECORDS.clear()


# --- the consent classifier (the LLM seam) ------------------------------------

_CLASSIFIER_INSTRUCTIONS = (
    "You judge one phone-call transcript. The AI travel agent told the "
    "traveler their flight was cancelled and asked for permission to "
    "rebook it and recheck the rest of the trip. The transcript "
    "interleaves AGENT: and USER: turns. Judge ONLY what the traveler "
    "(USER) said in answer to that question. Reply with exactly one word "
    "— yes, no, or ambiguous. Say 'yes' only if the traveler clearly "
    "agreed (for example 'yeah', 'sure', 'go ahead', 'please fix it'). "
    "Say 'no' if they clearly declined. Say 'ambiguous' if they never "
    "answered, the answer is unclear, or there are no USER turns."
)


# Phase 40 — the same yes/no/ambiguous seam, pointed at Call 2's email
# offer instead of Call 1's repair consent. Same honesty posture: only an
# unambiguous yes sends anything.
_EMAIL_OFFER_INSTRUCTIONS = (
    "You judge one phone-call transcript. Near the end of the call the AI "
    "travel agent offered to email the traveler a summary of their "
    "repaired trip — for example 'Would you like an email of this?'. The "
    "transcript interleaves AGENT: and USER: turns. Judge ONLY what the "
    "traveler (USER) said in answer to that offer. Reply with exactly one "
    "word — yes, no, or ambiguous. Say 'yes' only if the traveler clearly "
    "wanted the email (for example 'yes please', 'sure', 'send it'). Say "
    "'no' if they clearly declined. Say 'ambiguous' if they never "
    "answered, the answer is unclear, or there are no USER turns."
)


def _consent_model():
    return agents_model()


async def _classify_transcript(
    transcript_text: str, instructions: str, name: str
) -> str:
    """The shared classifier body: yes / no / ambiguous from a transcript.
    Any failure — API error, empty transcript, an off-script answer —
    reads as 'ambiguous', which stands down: never act on an unread
    answer."""
    if not (transcript_text or "").strip():
        return "ambiguous"
    try:
        configure_agents_sdk()
        agent = Agent(
            name=name,
            model=_consent_model(),
            instructions=instructions,
        )
        result = await Runner.run(agent, transcript_text, max_turns=1)
        verdict = str(result.final_output).strip().lower().strip(".!'\"")
        return verdict if verdict in ("yes", "no") else "ambiguous"
    except Exception:  # noqa: BLE001 — a failed read must stand down, not raise
        logger.warning("%s classification failed", name, exc_info=True)
        return "ambiguous"


async def classify_consent(transcript_text: str) -> str:
    """yes / no / ambiguous from Call 1's transcript_text — only an
    unambiguous yes launches repairs."""
    return await _classify_transcript(
        transcript_text, _CLASSIFIER_INSTRUCTIONS, "ConsentClassifier"
    )


async def classify_email_offer(transcript_text: str) -> str:
    """yes / no / ambiguous from Call 2's transcript_text (Phase 40) —
    only an unambiguous yes sends the repair email."""
    return await _classify_transcript(
        transcript_text, _EMAIL_OFFER_INSTRUCTIONS, "EmailOfferClassifier"
    )
