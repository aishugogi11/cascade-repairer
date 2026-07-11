"""Access-gate tests — Phase 17, hermetic (no GCP, no OPENAI_API_KEY, no
network; the query seam and repositories are patched at their boundaries).

Run against the real main.app so the middleware wiring itself is under
test. The load-bearing contracts: fail-open with DEMO_ACCESS_CODE unset,
401 on missing/wrong header with it set, the public allowlist stays public,
/v1/auth/validate answers 200/401, and every rehearsal page carries the
?code= / localStorage / header-attach wiring.
"""
import logging

from fastapi.testclient import TestClient

import main
from api import access_gate as access_gate_module
from api import web_call as web_call_module

client = TestClient(main.app)

CODE = "demo-code-1234"

PUBLIC_GETS = (
    "/v1/legal/privacy",
    "/v1/legal/support",
    "/v1/web_call/",
    "/v1/mobile_voice/",
    "/v1/itinerary/",
    "/v1/demo/",
)

PAGE_PATHS = (
    "/v1/web_call/",
    "/v1/mobile_voice/",
    "/v1/itinerary/",
    "/v1/demo/",
)


def _mock_query_seam(monkeypatch, reply="hi from the agent"):
    """Make POST /v1/web_call/query answer hermetically behind the gate."""

    async def fake_answer(session_name, query):
        return reply

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(web_call_module, "answer_query", fake_answer)
    monkeypatch.setattr(web_call_module, "_LOGGED_SESSIONS", set())
    monkeypatch.setattr(
        web_call_module.sessions_repo, "create_session", lambda s: (True, s, None)
    )
    monkeypatch.setattr(
        web_call_module.turns_repo, "create_turn", lambda t: (True, t, None)
    )


def _query(headers=None):
    return client.post(
        "/v1/web_call/query",
        json={"query": "hello", "session_name": "gate-test-session"},
        headers=headers or {},
    )


# ---- fail-open (DEMO_ACCESS_CODE unset) ----


def test_unset_env_gated_route_fail_open(monkeypatch):
    monkeypatch.delenv("DEMO_ACCESS_CODE", raising=False)
    _mock_query_seam(monkeypatch)

    resp = _query()

    assert resp.status_code == 200
    assert resp.json() == {"response": "hi from the agent"}


def test_unset_env_warns_once(monkeypatch, caplog):
    monkeypatch.delenv("DEMO_ACCESS_CODE", raising=False)
    monkeypatch.setattr(access_gate_module, "_warned_open", False)
    _mock_query_seam(monkeypatch)

    with caplog.at_level(logging.WARNING, logger="api.access_gate"):
        _query()
        _query()

    warnings = [r for r in caplog.records if "DEMO_ACCESS_CODE" in r.message]
    assert len(warnings) == 1


# ---- gate enforced (DEMO_ACCESS_CODE set) ----


def test_missing_header_401(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_CODE", CODE)

    resp = _query()

    assert resp.status_code == 401
    assert "access code" in resp.json()["error"]


def test_wrong_code_401(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_CODE", CODE)

    resp = _query(headers={"X-Access-Code": "not-the-code"})

    assert resp.status_code == 401


def test_correct_code_passes(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_CODE", CODE)
    _mock_query_seam(monkeypatch)

    resp = _query(headers={"X-Access-Code": CODE})

    assert resp.status_code == 200
    assert resp.json() == {"response": "hi from the agent"}


def test_other_gated_routes_401_without_code(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_CODE", CODE)

    for method, path in (
        ("post", "/v1/web_call/token"),
        ("get", "/v1/itinerary/trips"),
        ("get", "/v1/itinerary/status/some-trip"),
        ("post", "/v1/demo/disrupt"),
    ):
        resp = getattr(client, method)(path)
        assert resp.status_code == 401, path


# ---- public allowlist stays public with the gate armed ----


def test_allowlisted_gets_stay_public(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_CODE", CODE)

    for path in PUBLIC_GETS:
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert resp.headers["content-type"].startswith("text/html"), path


def test_validate_is_public_and_checks_the_code(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_CODE", CODE)

    ok = client.post("/v1/auth/validate", json={"code": CODE})
    assert ok.status_code == 200
    assert ok.json() == {"valid": True}

    bad = client.post("/v1/auth/validate", json={"code": "not-the-code"})
    assert bad.status_code == 401
    assert bad.json()["valid"] is False


def test_validate_fail_open_when_unset(monkeypatch):
    monkeypatch.delenv("DEMO_ACCESS_CODE", raising=False)

    resp = client.post("/v1/auth/validate", json={"code": "anything"})

    assert resp.status_code == 200
    assert resp.json() == {"valid": True}


# ---- pages carry the pass-through wiring ----


def test_pages_contain_header_attach_wiring():
    for path in PAGE_PATHS:
        text = client.get(path).text
        assert "X-Access-Code" in text, path
        assert "vb_access_code" in text, path  # localStorage persistence
        assert 'searchParams.get("code")' in text or "searchParams.get('code')" in text, path
