"""Hermetic tests for the Resend send module — Phase 39. No network, no key."""

import asyncio

import httpx
import pytest

from api import email_client
from api.email_client import FROM_ADDRESS, send_email

KEY = "re_test_key_123"


def _install_transport(monkeypatch, handler):
    """Route email_client's AsyncClient through a MockTransport."""
    real_client = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(email_client.httpx, "AsyncClient", factory)


def _counting_handler(calls):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"id": "email_123"})

    return handler


# ---------- kill switch: no key means disabled, and no HTTP call ----------

@pytest.mark.parametrize("key_value", [None, "", "   "])
def test_disabled_without_key_and_no_http_call(monkeypatch, key_value):
    if key_value is None:
        monkeypatch.delenv("RESEND_API_KEY", raising=False)
    else:
        monkeypatch.setenv("RESEND_API_KEY", key_value)
    calls = []
    _install_transport(monkeypatch, _counting_handler(calls))

    result = asyncio.run(send_email(to="a@example.com", subject="s", text="t"))

    assert result["status"] == "disabled"
    assert calls == []  # zero requests


# ---------- payload shape on a mocked success ----------

def test_sent_payload_shape_and_auth_header(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", KEY)
    calls = []
    _install_transport(monkeypatch, _counting_handler(calls))

    result = asyncio.run(
        send_email(to="josh@example.com", subject="Cascade test send", text="hello")
    )

    assert result == {"status": "sent", "id": "email_123"}
    assert KEY not in str(result)  # key never leaks into the status dict
    (request,) = calls
    assert request.url == email_client.RESEND_API_URL
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    import json

    body = json.loads(request.content)
    assert body["from"] == FROM_ADDRESS
    assert body["to"] == ["josh@example.com"]
    assert body["subject"] == "Cascade test send"
    assert body["text"] == "hello"
    assert "reply_to" not in body  # only present when passed
    assert "html" not in body


def test_reply_to_passthrough_when_given(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", KEY)
    calls = []
    _install_transport(monkeypatch, _counting_handler(calls))

    asyncio.run(
        send_email(
            to="a@example.com", subject="s", html="<p>hi</p>",
            reply_to="reply@example.com",
        )
    )

    import json

    body = json.loads(calls[0].content)
    assert body["reply_to"] == "reply@example.com"
    assert body["html"] == "<p>hi</p>"


# ---------- never raises: non-2xx, timeout, transport error ----------

def test_non_2xx_returns_error_without_raising(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", KEY)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"message": "invalid"})

    _install_transport(monkeypatch, handler)
    result = asyncio.run(send_email(to="a@example.com", subject="s", text="t"))
    assert result["status"] == "error"


def test_timeout_returns_error_without_raising(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", KEY)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("too slow")

    _install_transport(monkeypatch, handler)
    result = asyncio.run(send_email(to="a@example.com", subject="s", text="t"))
    assert result["status"] == "error"
    assert result["reason"] == "TimeoutException"


def test_transport_error_returns_error_without_raising(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", KEY)

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no network")

    _install_transport(monkeypatch, handler)
    result = asyncio.run(send_email(to="a@example.com", subject="s", text="t"))
    assert result["status"] == "error"
