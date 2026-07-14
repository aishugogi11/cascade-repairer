"""Hermetic certification of the cert tripwire's cleanup guarantee (Phase 26).

No `cert` marker, no env skipif, no network: these tests drive the tripwire
flow extracted in test_sabre_cert.py with fake clients, closing the Phase 25
validation report's failing criterion by construction — a create response
that carries a confirmationId but fails shape validation must still be
cancelled before the flow resolves. Importing test_sabre_cert is safe here:
its cert/skipif marks apply at collection, not import.
"""
import pytest

import test_sabre_cert
from api.sabre import shapes


class _RecordingFakeClient:
    """Fake with the client interface the tripwire flow touches.

    create_booking drives the payload through
    shapes.CreateBookingResponse.model_validate — exactly what the real
    client does — so a drifted payload raises a ValidationError whose error
    `input` is realistic. cancel_booking records every confirmationId."""

    def __init__(self, create_payload: dict):
        self._create_payload = create_payload
        self.cancelled: list[str] = []

    async def create_booking(self, request):
        return shapes.CreateBookingResponse.model_validate(self._create_payload)

    async def cancel_booking(self, request):
        self.cancelled.append(request.confirmationId)


# A "success" that drifted: the PNR is there, but the required booking
# section is missing, so shape validation fails after the PNR exists
# server-side — the 2026-07-13 escape path.
_DRIFT_PAYLOAD = {
    "timestamp": "2026-07-14T12:00:00Z",
    "confirmationId": "ORPHAN1",
}

# A clean validated success (the validator's original dry-run case).
_FORCED_SUCCESS_PAYLOAD = {
    "timestamp": "2026-07-14T12:00:00Z",
    "confirmationId": "FORCED1",
    "booking": {"bookingId": "FORCED1"},
}

# The documented entitlement wall as CERT actually shapes it (verified live
# 2026-07-14: the UNAUTHORIZED_ACCESS marker is in `type`; `category` is
# UNAUTHORIZED) — the only payload the tripwire accepts.
_WALL_PAYLOAD = {
    "timestamp": "2026-07-14T12:00:00Z",
    "errors": [
        {
            "category": "UNAUTHORIZED",
            "type": "UNAUTHORIZED_ACCESS",
            "description": "The service PassengerDetailsRQ returned an "
            "authorization failure.",
        }
    ],
}


def test_shape_drift_after_created_pnr_still_cancels():
    client = _RecordingFakeClient(_DRIFT_PAYLOAD)
    with pytest.raises(pytest.fail.Exception):
        test_sabre_cert._run_create_booking_tripwire(
            client, test_sabre_cert._booking_request()
        )
    assert client.cancelled == ["ORPHAN1"], (
        "a created-but-shape-drifted PNR must be cancelled before the "
        "tripwire resolves"
    )


def test_forced_success_still_cancels_via_finally():
    client = _RecordingFakeClient(_FORCED_SUCCESS_PAYLOAD)
    with pytest.raises(pytest.fail.Exception):
        test_sabre_cert._run_create_booking_tripwire(
            client, test_sabre_cert._booking_request()
        )
    assert client.cancelled == ["FORCED1"]


def test_documented_entitlement_wall_passes_and_cancels_nothing():
    client = _RecordingFakeClient(_WALL_PAYLOAD)
    test_sabre_cert._run_create_booking_tripwire(
        client, test_sabre_cert._booking_request()
    )
    assert client.cancelled == []


def test_raw_payload_recovery_prefers_the_root_dict():
    """The recovery helper must hand back the payload model_validate
    received (the shallowest loc), not a nested sub-dict."""
    try:
        shapes.CreateBookingResponse.model_validate(_DRIFT_PAYLOAD)
    except Exception as exc:  # pydantic.ValidationError
        raw = test_sabre_cert._raw_response_from_validation_error(exc)
        assert raw == _DRIFT_PAYLOAD
    else:
        pytest.fail("drift payload unexpectedly validated")
