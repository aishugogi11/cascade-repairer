"""Outbound transactional email via Resend — Phase 39.

Guarded send module for `info@talktomytrip.com`: an async httpx POST to the
Resend HTTP API (not SMTP — Cloud Run blocks port 25, and SMTP doesn't fit
request-scoped lifecycles; not the resend SDK — httpx is already pinned).

The kill switch is RESEND_API_KEY, read at call time and whitespace-stripped
(the paypal_client trio precedent): missing/empty means status "disabled",
no HTTP call — which is also what keeps the hermetic suite credential-free.
send_email NEVER raises: a failed email must never kill the calling request
(Phase 40 will call this from the booking flow).
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

log = logging.getLogger(__name__)

RESEND_API_URL = "https://api.resend.com/emails"
FROM_ADDRESS_DEFAULT = "Cascade <info@talktomytrip.com>"
_TIMEOUT_SECONDS = 8.0  # the standing external-call ceiling (Tavily, PayPal)


def _api_key() -> Optional[str]:
    value = os.environ.get("RESEND_API_KEY", "").strip()
    return value or None


def _from_address() -> str:
    """Optional RESEND_FROM override for a verified Resend sender.

    Default stays info@talktomytrip.com. If that domain is unverified on the
    current API key, set RESEND_FROM to a verified address (or Resend's
    onboarding sender) so demo emails can still go out.
    """
    override = os.environ.get("RESEND_FROM", "").strip()
    return override or FROM_ADDRESS_DEFAULT


# Back-compat for tests/importers that read FROM_ADDRESS.
FROM_ADDRESS = FROM_ADDRESS_DEFAULT


async def send_email(
    *,
    to: str,
    subject: str,
    html: Optional[str] = None,
    text: Optional[str] = None,
    reply_to: Optional[str] = None,
) -> dict:
    """Send one email through Resend. NEVER raises.

    Returns {"status": "sent", "id": ...} on success,
    {"status": "disabled", ...} without a key, or
    {"status": "error", "reason": ...} on any failure.
    """
    key = _api_key()
    if not key:
        return {"status": "disabled", "reason": "RESEND_API_KEY not configured"}

    body: dict = {"from": _from_address(), "to": [to], "subject": subject}
    if html:
        body["html"] = html
    if text:
        body["text"] = text
    if reply_to:
        body["reply_to"] = reply_to

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                RESEND_API_URL,
                json=body,
                headers={"Authorization": f"Bearer {key}"},
            )
            if resp.is_success:
                return {"status": "sent", "id": resp.json().get("id")}
            # Surface Resend's own message so ops can see domain/key failures
            # (403 domain-not-verified, 401 bad key) without opening the dashboard.
            detail = ""
            try:
                payload = resp.json()
                if isinstance(payload, dict):
                    err = payload.get("message") or payload.get("name") or ""
                    detail = str(err).strip()
            except Exception:  # noqa: BLE001
                detail = (resp.text or "")[:200].strip()
            reason = f"HTTP {resp.status_code}"
            if detail:
                reason = f"{reason}: {detail}"
            log.warning("resend send failed: %s", reason)
            return {"status": "error", "reason": reason}
    except Exception as exc:  # noqa: BLE001
        log.warning("resend send failed: %s: %s", type(exc).__name__, exc)
        return {"status": "error", "reason": type(exc).__name__}
