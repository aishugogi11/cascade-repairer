"""PayPal sandbox Payouts client for the Cascade Repairer fare refund beat.

PayPal integration: Pallavi G (2026-07-17)."""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Optional

import httpx

log = logging.getLogger(__name__)

_SANDBOX_BASE = "https://api-m.sandbox.paypal.com"
_TIMEOUT_SECONDS = 8.0  # payout must never stall the results callback


@dataclass
class RefundResult:
    status: str  # "sent" | "pending" | "skipped" | "disabled"
    amount: Optional[float] = None
    currency: str = "USD"
    payout_batch_id: Optional[str] = None
    reason: Optional[str] = None

    @property
    def spoken_line(self) -> Optional[str]:
        if self.status == "sent" and self.amount:
            return (
                f"Also tell them their new flight was cheaper and that you "
                f"have already refunded the {self.amount:.2f} dollar "
                f"difference to their PayPal."
            )
        if self.status == "pending" and self.amount:
            return (
                f"Also tell them their new flight was {self.amount:.2f} "
                f"dollars cheaper and the PayPal refund is processing — "
                f"they will see it shortly."
            )
        return None


def _env(name: str) -> Optional[str]:
    value = os.environ.get(name, "").strip()
    return value or None


def compute_refund_delta(
    old_fare: Optional[float], new_fare: Optional[float]
) -> Optional[float]:
    if old_fare is None or new_fare is None:
        return None
    try:
        old_f, new_f = float(old_fare), float(new_fare)
    except (TypeError, ValueError):
        return None
    if old_f <= 0 or new_f < 0:
        return None
    delta = round(old_f - new_f, 2)
    return delta if delta >= 0.01 else None


async def _get_access_token(client: httpx.AsyncClient, base: str) -> Optional[str]:
    resp = await client.post(
        f"{base}/v1/oauth2/token",
        auth=(_env("PAYPAL_CLIENT_ID") or "", _env("PAYPAL_CLIENT_SECRET") or ""),
        data={"grant_type": "client_credentials"},
    )
    resp.raise_for_status()
    return resp.json().get("access_token")


async def refund_fare_difference(
    old_fare: Optional[float],
    new_fare: Optional[float],
    currency: str = "USD",
    note: str = "Cascade Repairer fare difference refund",
) -> RefundResult:
    """Issue a sandbox payout for the fare difference. NEVER raises."""
    delta = compute_refund_delta(old_fare, new_fare)
    if delta is None:
        return RefundResult(status="skipped", reason="no positive fare difference")

    receiver = _env("PAYPAL_RECEIVER_EMAIL")
    if not (_env("PAYPAL_CLIENT_ID") and _env("PAYPAL_CLIENT_SECRET") and receiver):
        return RefundResult(
            status="disabled", amount=delta, currency=currency,
            reason="paypal env vars not configured",
        )

    base = _env("PAYPAL_API_BASE") or _SANDBOX_BASE
    sender_batch_id = f"cascade-{uuid.uuid4().hex[:12]}"
    body = {
        "sender_batch_header": {
            "sender_batch_id": sender_batch_id,
            "email_subject": "Cascade Repairer refund",
            "email_message": note,
        },
        "items": [
            {
                "recipient_type": "EMAIL",
                "receiver": receiver,
                "amount": {"value": f"{delta:.2f}", "currency": currency},
                "note": note,
                "sender_item_id": sender_batch_id + "-1",
            }
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS) as client:
            token = await _get_access_token(client, base)
            if not token:
                raise RuntimeError("empty access token")
            resp = await client.post(
                f"{base}/v1/payments/payouts",
                json=body,
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            batch = resp.json().get("batch_header", {})
            return RefundResult(
                status="sent",
                amount=delta,
                currency=currency,
                payout_batch_id=batch.get("payout_batch_id"),
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("paypal payout failed, reporting pending: %s", type(exc).__name__)
        return RefundResult(
            status="pending", amount=delta, currency=currency,
            reason="payout call failed, will retry outside the demo path",
        )
