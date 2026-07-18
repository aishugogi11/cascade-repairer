"""Hermetic tests for POST /v1/email/test — Phase 39.

Run against the real main.app so the gate middleware and router wiring are
under test. The load-bearing contracts: the endpoint is gated (NOT on the
allowlist), key-less environments answer an honest "disabled", module
failures surface as 200 + status "error" (never a 500), and a non-address
recipient is a 400.
"""

from fastapi.testclient import TestClient

import main
from api import email_api as email_api_module
from api.email_api import TEST_BODY, TEST_SUBJECT

client = TestClient(main.app)

CODE = "demo-code-1234"


def _fake_send(result):
    captured = {}

    async def fake(**kwargs):
        captured.update(kwargs)
        return result

    return fake, captured


# ---------- gate ----------

def test_gated_401_without_code(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_CODE", CODE)
    resp = client.post("/v1/email/test", json={"to": "a@example.com"})
    assert resp.status_code == 401


def test_gated_200_with_code(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_CODE", CODE)
    fake, captured = _fake_send({"status": "sent", "id": "email_1"})
    monkeypatch.setattr(email_api_module, "send_email", fake)

    resp = client.post(
        "/v1/email/test",
        json={"to": "a@example.com"},
        headers={"X-Access-Code": CODE},
    )

    assert resp.status_code == 200
    assert resp.json() == {"status": "sent", "id": "email_1"}
    assert captured["to"] == "a@example.com"
    assert captured["subject"] == TEST_SUBJECT
    assert captured["text"] == TEST_BODY


# ---------- honesty: disabled / error are 200s, never 500s ----------

def test_no_key_returns_disabled(monkeypatch):
    monkeypatch.delenv("DEMO_ACCESS_CODE", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)

    resp = client.post("/v1/email/test", json={"to": "a@example.com"})

    assert resp.status_code == 200
    assert resp.json()["status"] == "disabled"


def test_module_failure_is_200_error_not_500(monkeypatch):
    monkeypatch.delenv("DEMO_ACCESS_CODE", raising=False)
    fake, _ = _fake_send({"status": "error", "reason": "TimeoutException"})
    monkeypatch.setattr(email_api_module, "send_email", fake)

    resp = client.post("/v1/email/test", json={"to": "a@example.com"})

    assert resp.status_code == 200  # asserted NOT 500
    assert resp.json()["status"] == "error"


# ---------- input validation ----------

def test_bad_address_is_400(monkeypatch):
    monkeypatch.delenv("DEMO_ACCESS_CODE", raising=False)
    resp = client.post("/v1/email/test", json={"to": "not-an-address"})
    assert resp.status_code == 400


# ---------- tone: the canned copy is minimal and honest ----------

def test_canned_copy_names_the_test_and_carries_no_links():
    assert "deliverability test" in TEST_BODY
    assert "http" not in TEST_BODY.lower()
    assert "www." not in TEST_BODY.lower()
    assert TEST_SUBJECT == "Cascade test send"
