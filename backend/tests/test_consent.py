"""Phase 23 tests — the consent registry and the consent classifier.

Hermetic: the registry is pure in-process state; the classifier's Agents
SDK call is monkeypatched (no OPENAI_API_KEY, no network). Load-bearing
invariants: a stale token can never flip a fresh wait, the status block is
additive (None means the poll omits it), and every classifier failure mode
reads as 'ambiguous' — standing down, never launching.
"""
import asyncio

from api import consent


def setup_function():
    consent.reset()


# ── registry ───────────────────────────────────────────────────────────


def test_register_creates_an_awaiting_record_with_page_copy():
    token = consent.register_awaiting("t-1", "c-1")
    record = consent.current("t-1")
    assert record.state == consent.AWAITING
    assert record.call_id == "c-1"
    assert record.token == token
    assert "go-ahead" in record.message

    block = consent.consent_block("t-1")
    assert block["state"] == consent.AWAITING
    assert "go-ahead" in block["message"]
    assert block["since"] and block["updated_at"]


def test_unknown_trip_has_no_block():
    assert consent.consent_block("nope") is None
    assert consent.current("nope") is None


def test_resolve_moves_state_with_default_or_custom_message():
    token = consent.register_awaiting("t-1", "c-1")
    assert consent.resolve("t-1", token, consent.GRANTED) is True
    assert consent.current("t-1").state == consent.GRANTED
    assert "repairs are running" in consent.current("t-1").message

    token = consent.register_awaiting("t-1", "c-2")
    assert consent.resolve("t-1", token, consent.DECLINED, message="custom")
    assert consent.current("t-1").message == "custom"


def test_stale_token_cannot_flip_a_fresh_wait():
    stale = consent.register_awaiting("t-1", "c-1")
    fresh = consent.register_awaiting("t-1", "c-2")
    assert stale != fresh
    assert consent.is_current("t-1", stale) is False

    assert consent.resolve("t-1", stale, consent.GRANTED) is False
    record = consent.current("t-1")
    assert record.state == consent.AWAITING
    assert record.call_id == "c-2"
    assert record.token == fresh


# ── classifier ─────────────────────────────────────────────────────────


class _Result:
    def __init__(self, output):
        self.final_output = output


def _stub_runner(monkeypatch, output, ran=None):
    async def fake_run(agent, run_input, max_turns=1):
        if ran is not None:
            ran.append(run_input)
        return _Result(output)

    monkeypatch.setattr(consent.Runner, "run", fake_run)


def test_classifier_normalizes_the_verdict(monkeypatch):
    for raw, expected in (
        ("yes", "yes"), ("Yes.", "yes"), ("NO", "no"),
        ("absolutely", "ambiguous"), ("maybe?", "ambiguous"),
    ):
        _stub_runner(monkeypatch, raw)
        verdict = asyncio.run(consent.classify_consent("USER: something"))
        assert verdict == expected, raw


def test_classifier_receives_the_transcript(monkeypatch):
    ran = []
    _stub_runner(monkeypatch, "yes", ran)
    asyncio.run(consent.classify_consent("AGENT: hi\n\nUSER: Yeah"))
    assert ran == ["AGENT: hi\n\nUSER: Yeah"]


def test_empty_transcript_is_ambiguous_without_an_llm_call(monkeypatch):
    ran = []
    _stub_runner(monkeypatch, "yes", ran)
    assert asyncio.run(consent.classify_consent("")) == "ambiguous"
    assert asyncio.run(consent.classify_consent("   ")) == "ambiguous"
    assert ran == []


def test_classifier_failure_is_ambiguous_never_a_raise(monkeypatch):
    async def broken_run(agent, run_input, max_turns=1):
        raise RuntimeError("api down")

    monkeypatch.setattr(consent.Runner, "run", broken_run)
    assert asyncio.run(consent.classify_consent("USER: yes")) == "ambiguous"


# ── the status surface (additive consent block) ────────────────────────


from types import SimpleNamespace
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import itinerary_ui as itinerary_ui_mod
from api.helpers.bigquery_helper import bq_helper
from api.itinerary_ui import itinerary_ui

app = FastAPI()
app.include_router(itinerary_ui, prefix="/v1/itinerary")

TRIP_ROW = {
    "trip_id": "t-1", "user_id": "josh", "title": "Trip", "status": "booked",
}
ITEM_ROWS = [
    {"item_id": "i-0", "trip_id": "t-1", "type": "flight", "status": "broken"},
]


def _status(monkeypatch):
    select = MagicMock(side_effect=[
        (True, [TRIP_ROW], None),   # the trip
        (True, ITEM_ROWS, None),    # its items
        (True, [], None),           # bookings (details)
    ])
    monkeypatch.setattr(bq_helper, "run_select", select)
    monkeypatch.setattr(bq_helper, "run_dml", MagicMock(return_value=(True, 1, None)))
    with TestClient(app) as client:
        return client.get("/v1/itinerary/status/t-1")


def test_status_carries_the_consent_block_when_a_wait_exists(monkeypatch):
    consent.register_awaiting("t-1", "c-1")
    resp = _status(monkeypatch)
    assert resp.status_code == 200
    block = resp.json()["consent"]
    assert block["state"] == consent.AWAITING
    assert "go-ahead" in block["message"]
    assert block["since"] and block["updated_at"]


def test_status_omits_the_block_without_a_wait(monkeypatch):
    resp = _status(monkeypatch)
    assert resp.status_code == 200
    assert "consent" not in resp.json()


def test_registry_failure_never_breaks_the_poll(monkeypatch):
    def explode(trip_id):
        raise RuntimeError("registry on fire")

    monkeypatch.setattr(itinerary_ui_mod.consent, "consent_block", explode)
    resp = _status(monkeypatch)
    assert resp.status_code == 200
    assert "consent" not in resp.json()
