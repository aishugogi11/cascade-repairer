"""Hermetic tests for the PayPal refund client. No network, no credentials.

PayPal integration: Pallavi G (2026-07-17).
"""

import asyncio
import json

import httpx
import pytest

from api import paypal_client
from api.paypal_client import (
    RefundResult,
    compute_refund_delta,
    refund_fare_difference,
)


# ---------- compute_refund_delta: the money math is conservative ----------

def test_delta_positive_when_new_flight_cheaper():
    assert compute_refund_delta(326.40, 242.10) == 84.30


def test_delta_none_when_new_flight_more_expensive():
    assert compute_refund_delta(242.10, 326.40) is None


def test_delta_none_on_missing_or_garbage_fares():
    assert compute_refund_delta(None, 200.0) is None
    assert compute_refund_delta(200.0, None) is None
    assert compute_refund_delta("abc", 200.0) is None
    assert compute_refund_delta(0, 0) is None


def test_delta_ignores_sub_cent_noise():
    assert compute_refund_delta(200.004, 200.0) is None


# ---------- env gating ----------

def test_disabled_without_env(monkeypatch):
    for var in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_RECEIVER_EMAIL"):
        monkeypatch.delenv(var, raising=False)
    result = asyncio.run(refund_fare_difference(300.0, 200.0))
    assert result.status == "disabled"
    assert result.amount == 100.0
    assert result.spoken_line is None  # unconfigured => agent says nothing


def test_skipped_when_no_savings():
    result = asyncio.run(refund_fare_difference(200.0, 300.0))
    assert result.status == "skipped"
    assert result.spoken_line is None


# ---------- payout path via MockTransport ----------

def _install_transport(monkeypatch, handler):
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(paypal_client.httpx, "AsyncClient", factory)


def _set_env(monkeypatch):
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "test-id")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("PAYPAL_RECEIVER_EMAIL", "traveler@example.com")


def test_successful_payout_returns_sent_with_batch_id(monkeypatch):
    _set_env(monkeypatch)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "tok"})
        if request.url.path == "/v1/payments/payouts":
            seen["body"] = json.loads(request.content)
            return httpx.Response(
                201, json={"batch_header": {"payout_batch_id": "BATCH123"}}
            )
        return httpx.Response(404)

    _install_transport(monkeypatch, handler)
    result = asyncio.run(refund_fare_difference(326.40, 242.10))

    assert result.status == "sent"
    assert result.payout_batch_id == "BATCH123"
    assert result.amount == 84.30
    item = seen["body"]["items"][0]
    assert item["amount"]["value"] == "84.30"
    assert item["receiver"] == "traveler@example.com"
    assert "refunded" in result.spoken_line


def test_paypal_failure_never_raises_and_reports_pending(monkeypatch):
    _set_env(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    _install_transport(monkeypatch, handler)
    result = asyncio.run(refund_fare_difference(326.40, 242.10))  # must not raise

    assert result.status == "pending"
    assert result.amount == 84.30
    assert "processing" in result.spoken_line


def test_network_error_never_raises(monkeypatch):
    _set_env(monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network")

    _install_transport(monkeypatch, handler)
    result = asyncio.run(refund_fare_difference(300.0, 250.0))
    assert result.status == "pending"


# ---------- the spoken line contract ----------

def test_spoken_line_shapes():
    assert "refunded" in RefundResult(status="sent", amount=84.30).spoken_line
    assert "processing" in RefundResult(status="pending", amount=84.30).spoken_line
    assert RefundResult(status="skipped").spoken_line is None
    assert RefundResult(status="disabled", amount=10.0).spoken_line is None


# ---------- demo.py seam: _maybe_refund_line ----------

from types import SimpleNamespace

from api import demo


def _flight(status="fixed", price=242.10, currency="USD", original_price=326.40):
    details = {"rebooked_from": {"price": original_price, "currency": currency}}
    return SimpleNamespace(
        type="flight", status=status, price=price, currency=currency, details=details
    )


def test_refund_line_appended_for_cheaper_fixed_flight(monkeypatch):
    async def fake_refund(old_fare, new_fare, currency="USD", note=""):
        assert old_fare == 326.40 and new_fare == 242.10
        return RefundResult(status="sent", amount=84.30)

    monkeypatch.setattr(demo, "refund_fare_difference", fake_refund)
    line = asyncio.run(demo._maybe_refund_line([_flight()]))
    assert "refunded" in line


def test_no_refund_line_when_flight_not_fixed(monkeypatch):
    called = {"n": 0}

    async def fake_refund(*a, **k):
        called["n"] += 1
        return RefundResult(status="sent", amount=1.0)

    monkeypatch.setattr(demo, "refund_fare_difference", fake_refund)
    line = asyncio.run(demo._maybe_refund_line([_flight(status="repairing")]))
    assert line is None and called["n"] == 0


def test_no_refund_line_without_original_fare():
    flight = _flight()
    flight.details = {}  # seed trips: no rebooked_from block
    line = asyncio.run(demo._maybe_refund_line([flight]))
    assert line is None  # client returns skipped => silent
