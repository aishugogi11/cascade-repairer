"""Phase 4 tests — Testing Vocal Bridge page + token endpoint.

Hermetic like the rest of the suite (these run inside the built container in
Cloud Build with no credentials and no network): the upstream Vocal Bridge
call is mocked at the requests boundary, env vars via monkeypatch. The live
conversation itself is validated manually per validation.md.
"""
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

import main
from api import vb_test as vb_test_module

client = TestClient(main.app)

FAKE_API_KEY = "vb-secret-key-123"
FAKE_AGENT_ID = "agent-abc"


def _set_env(monkeypatch, api_key=FAKE_API_KEY, agent_id=FAKE_AGENT_ID):
    if api_key is None:
        monkeypatch.delenv("VOCAL_BRIDGE_API_KEY", raising=False)
    else:
        monkeypatch.setenv("VOCAL_BRIDGE_API_KEY", api_key)
    if agent_id is None:
        monkeypatch.delenv("VOCAL_BRIDGE_AGENT_ID", raising=False)
    else:
        monkeypatch.setenv("VOCAL_BRIDGE_AGENT_ID", agent_id)


def _upstream_response(status_code=200, payload=None, text=""):
    res = MagicMock()
    res.status_code = status_code
    res.json.return_value = payload or {}
    res.text = text
    return res


# ── Page ───────────────────────────────────────────────────────────────


def test_page_returns_200_html_with_title():
    resp = client.get("/v1/vb_test/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Testing Vocal Bridge" in resp.text


def test_page_loads_vb_react_sdk_from_esm():
    body = client.get("/v1/vb_test/").text
    assert "esm.sh/@vocalbridgeai/react" in body
    assert "esm.sh/@vocalbridgeai/sdk" in body
    # The page mints through the backend, never with an inlined key.
    assert "/v1/vb_test/token" in body


def test_routes_registered():
    paths = main.app.openapi()["paths"]
    assert "/v1/vb_test/" in paths
    assert "/v1/vb_test/token" in paths


def test_landing_page_links_to_vb_test():
    body = client.get("/v1/hello/").text
    assert "/v1/vb_test/" in body


# ── Token endpoint ─────────────────────────────────────────────────────


def test_token_success_aliases_upstream_fields(monkeypatch):
    _set_env(monkeypatch)
    calls = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        calls["url"] = url
        calls["headers"] = headers
        calls["json"] = json
        return _upstream_response(payload={
            "livekit_url": "wss://example.vocalbridge",
            "token": "jwt-token",
            "room_name": "room-42",
            "agent_mode": "openai_concierge",
        })

    monkeypatch.setattr(vb_test_module.requests, "post", fake_post)

    resp = client.post("/v1/vb_test/token")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "connection_url": "wss://example.vocalbridge",
        "token": "jwt-token",
        "session_name": "room-42",
        "agent_mode": "openai_concierge",
    }
    # The upstream call must match the lessons' shape exactly.
    assert calls["url"] == "https://vocalbridgeai.com/api/v1/token"
    assert calls["headers"]["X-API-Key"] == FAKE_API_KEY
    assert calls["headers"]["X-Agent-Id"] == FAKE_AGENT_ID
    assert calls["json"] == {"participant_name": "VB Test Page"}


def test_token_prefers_connection_url_over_livekit_url(monkeypatch):
    _set_env(monkeypatch)
    monkeypatch.setattr(
        vb_test_module.requests, "post",
        lambda *a, **k: _upstream_response(payload={
            "connection_url": "wss://preferred",
            "livekit_url": "wss://fallback",
            "token": "jwt",
            "room_name": "room-1",
        }),
    )
    body = client.post("/v1/vb_test/token").json()
    assert body["connection_url"] == "wss://preferred"
    assert body["agent_mode"] == ""  # defaulted when upstream omits it


def test_token_missing_api_key_is_503(monkeypatch):
    _set_env(monkeypatch, api_key=None)
    resp = client.post("/v1/vb_test/token")
    assert resp.status_code == 503
    assert "VOCAL_BRIDGE_API_KEY" in resp.json()["error"]


def test_token_missing_agent_id_is_503(monkeypatch):
    _set_env(monkeypatch, agent_id=None)
    resp = client.post("/v1/vb_test/token")
    assert resp.status_code == 503
    assert "VOCAL_BRIDGE_AGENT_ID" in resp.json()["error"]


def test_token_upstream_error_is_502_and_never_leaks_key(monkeypatch):
    _set_env(monkeypatch)
    monkeypatch.setattr(
        vb_test_module.requests, "post",
        lambda *a, **k: _upstream_response(status_code=401, text="bad key"),
    )
    resp = client.post("/v1/vb_test/token")
    assert resp.status_code == 502
    body = resp.json()
    assert body["upstream_status"] == 401
    assert "bad key" in body["upstream_body"]
    assert FAKE_API_KEY not in resp.text


def test_token_upstream_unreachable_is_502(monkeypatch):
    _set_env(monkeypatch)

    def raise_connection_error(*a, **k):
        raise vb_test_module.requests.ConnectionError("boom")

    monkeypatch.setattr(vb_test_module.requests, "post", raise_connection_error)
    resp = client.post("/v1/vb_test/token")
    assert resp.status_code == 502
    assert "unreachable" in resp.json()["error"]
    assert FAKE_API_KEY not in resp.text
