"""Per-trip email addresses — Phase 40.

The in-memory registry behind both email offers: the booking-call beat
stores the traveler's confirmed address keyed by trip_id, and the repair
callback (Call 2) reuses it — no re-ask when one is on file. In-process
module state (the consent.py precedent, interview decision): the standing
single-instance scope decision protects it, a Cloud Run restart simply
forgets the address, and the operator re-confirms on the next booking.
Deliberately no repository writes — the Phase 32 wholesale-`details`
write-back contract is untouched, and nothing here persists.

Only a voice-confirmed address may reach store() (the BASE_INSTRUCTIONS
confirmation contract, with the tool's validity check as the code
backstop) — this module just keeps what it is given, normalized.
"""
from typing import Dict, Optional

_ADDRESSES: Dict[str, str] = {}


def _normalize(address: str) -> str:
    """Whitespace and case never matter to a mailbox; spoken capture adds
    both. Everything else (validity) is the caller's contract."""
    return (address or "").strip().lower()


def store(trip_id: str, address: str) -> None:
    """Remember this trip's confirmed address — replaces any prior one."""
    _ADDRESSES[trip_id] = _normalize(address)


def get(trip_id: str) -> Optional[str]:
    """The stored address for this trip, or None — None means Call 2
    carries no email offer at all (never a guessed address)."""
    return _ADDRESSES.get(trip_id)


def clear(trip_id: str) -> None:
    _ADDRESSES.pop(trip_id, None)


def _reset() -> None:
    """Test hook — the registry is module state."""
    _ADDRESSES.clear()
