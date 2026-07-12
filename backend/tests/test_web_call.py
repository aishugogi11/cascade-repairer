"""Phase 8 tests — the Vocal Bridge web client integration router.

Hermetic: the VB token mint is mocked at the requests boundary, the agent at
the Runner boundary, repositories at theirs (no VOCAL_BRIDGE_API_KEY, no
OPENAI_API_KEY, no network). The load-bearing contracts: token minting never
leaks the key and names the broken env var; /query is multi-turn per session
and survives logging failures; the page carries the L3 useAIAgent wiring.
"""
import asyncio
import time

from fastapi.testclient import TestClient

import main
from api import concierge as concierge_module
from api import web_call as web_call_module

client = TestClient(main.app)


class _FakeResult:
    def __init__(self, input_items, reply):
        self._items = list(input_items) + [{"role": "assistant", "content": reply}]
        self.final_output = reply

    def to_input_list(self):
        return self._items


def _mock_agent(monkeypatch, reply="I'm the backend agent on Cloud Run."):
    """Fresh Runner fake + clean per-session state; returns the input log.

    Since Phase 9 the seam delegates to the Concierge, so the Runner and
    history live in the concierge module."""
    calls = []

    class _FakeRunner:
        @classmethod
        async def run(cls, agent, input, max_turns=None):
            calls.append(input)
            return _FakeResult(input, reply)

    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(concierge_module, "Runner", _FakeRunner)
    monkeypatch.setattr(concierge_module, "_HISTORY", {})
    monkeypatch.setattr(concierge_module, "_SESSION_TRIPS", {})
    # The trip pin's read must never reach a real client; empty tables mean
    # the turn proceeds with the no-trip instructions.
    monkeypatch.setattr(
        concierge_module.trips.bq_helper, "run_select",
        lambda query, params=None: (True, [], None),
    )
    monkeypatch.setattr(web_call_module, "_LOGGED_SESSIONS", set())
    return calls


def _mock_persistence(monkeypatch, log=None, fail=False, raise_exc=False):
    log = log if log is not None else []

    def fake_create_session(session):
        if raise_exc:
            raise RuntimeError("bq down")
        log.append(("session", session))
        return (not fail), (None if fail else session), ("boom" if fail else None)

    def fake_create_turn(turn):
        if raise_exc:
            raise RuntimeError("bq down")
        log.append(("turn", turn))
        return (not fail), (None if fail else turn), ("boom" if fail else None)

    monkeypatch.setattr(
        web_call_module.sessions_repo, "create_session", fake_create_session
    )
    monkeypatch.setattr(web_call_module.turns_repo, "create_turn", fake_create_turn)
    return log


class _FakeMintResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


# ── registration ───────────────────────────────────────────────────────


def test_routes_registered_with_lesson_summary():
    paths = main.app.openapi()["paths"]
    assert "/v1/web_call/" in paths
    assert "/v1/web_call/token" in paths
    assert "/v1/web_call/query" in paths
    assert paths["/v1/web_call/query"]["post"]["summary"].startswith("[L3]")


# ── /token ─────────────────────────────────────────────────────────────


def test_token_missing_api_key_is_503_naming_the_var(monkeypatch):
    monkeypatch.delenv("VOCAL_BRIDGE_API_KEY", raising=False)
    monkeypatch.setenv("VOCAL_BRIDGE_WEB_AGENT_ID", "agent-123")
    resp = client.post("/v1/web_call/token")
    assert resp.status_code == 503
    assert "VOCAL_BRIDGE_API_KEY" in resp.json()["error"]


def test_token_missing_web_agent_id_is_503_naming_the_var(monkeypatch):
    monkeypatch.setenv("VOCAL_BRIDGE_API_KEY", "vb-key")
    monkeypatch.delenv("VOCAL_BRIDGE_WEB_AGENT_ID", raising=False)
    resp = client.post("/v1/web_call/token")
    assert resp.status_code == 503
    assert "VOCAL_BRIDGE_WEB_AGENT_ID" in resp.json()["error"]


def test_token_upstream_error_is_502_with_detail(monkeypatch):
    monkeypatch.setenv("VOCAL_BRIDGE_API_KEY", "vb-key")
    monkeypatch.setenv("VOCAL_BRIDGE_WEB_AGENT_ID", "agent-123")
    monkeypatch.setattr(
        web_call_module.requests,
        "post",
        lambda *a, **kw: _FakeMintResponse(status_code=401, text="bad key"),
    )
    resp = client.post("/v1/web_call/token")
    assert resp.status_code == 502
    body = resp.json()
    assert body["upstream_status"] == 401
    assert body["upstream_body"] == "bad key"


def test_token_success_aliases_transport_fields(monkeypatch):
    monkeypatch.setenv("VOCAL_BRIDGE_API_KEY", "vb-key")
    monkeypatch.setenv("VOCAL_BRIDGE_WEB_AGENT_ID", "agent-123")
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen["url"] = url
        seen["headers"] = headers
        return _FakeMintResponse(payload={
            "livekit_url": "wss://vb.example",
            "token": "jwt-token",
            "room_name": "room-42",
            "agent_mode": "ai_agent",
        })

    monkeypatch.setattr(web_call_module.requests, "post", fake_post)
    resp = client.post("/v1/web_call/token")
    assert resp.status_code == 200
    assert resp.json() == {
        "connection_url": "wss://vb.example",
        "token": "jwt-token",
        "session_name": "room-42",
        "agent_mode": "ai_agent",
    }
    # The web agent id (not the Phase 4 smoke-test agent) is what's minted.
    assert seen["headers"]["X-Agent-Id"] == "agent-123"


# ── /query ─────────────────────────────────────────────────────────────


def test_query_blank_text_is_422(monkeypatch):
    _mock_agent(monkeypatch)
    resp = client.post(
        "/v1/web_call/query", json={"query": "  ", "session_name": "room-1"}
    )
    assert resp.status_code == 422


def test_query_missing_openai_key_is_503(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    resp = client.post(
        "/v1/web_call/query", json={"query": "hello", "session_name": "room-1"}
    )
    assert resp.status_code == 503


def test_query_returns_agent_reply(monkeypatch):
    _mock_agent(monkeypatch, reply="Hi from the backend.")
    _mock_persistence(monkeypatch)
    resp = client.post(
        "/v1/web_call/query", json={"query": "who are you?", "session_name": "room-1"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"response": "Hi from the backend."}


def test_query_agent_failure_is_502(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(concierge_module, "_HISTORY", {})
    monkeypatch.setattr(concierge_module, "_SESSION_TRIPS", {})
    monkeypatch.setattr(
        concierge_module.trips.bq_helper, "run_select",
        lambda query, params=None: (True, [], None),
    )

    class _BoomRunner:
        @classmethod
        async def run(cls, agent, input, max_turns=None):
            raise RuntimeError("agent down")

    monkeypatch.setattr(concierge_module, "Runner", _BoomRunner)
    _mock_persistence(monkeypatch)
    resp = client.post(
        "/v1/web_call/query", json={"query": "hello", "session_name": "room-1"}
    )
    assert resp.status_code == 502


def test_query_replays_session_history(monkeypatch):
    calls = _mock_agent(monkeypatch)
    _mock_persistence(monkeypatch)

    client.post(
        "/v1/web_call/query",
        json={"query": "first question", "session_name": "room-1"},
    )
    client.post(
        "/v1/web_call/query",
        json={"query": "second question", "session_name": "room-1"},
    )

    assert len(calls) == 2
    # The second run's input carries the whole first exchange.
    second_input = calls[1]
    contents = [item.get("content") for item in second_input]
    assert "first question" in contents
    assert "second question" in contents
    assert any(item.get("role") == "assistant" for item in second_input)


def test_query_sessions_are_isolated(monkeypatch):
    calls = _mock_agent(monkeypatch)
    _mock_persistence(monkeypatch)

    client.post(
        "/v1/web_call/query", json={"query": "room one question", "session_name": "room-1"}
    )
    client.post(
        "/v1/web_call/query", json={"query": "room two question", "session_name": "room-2"}
    )

    # The second session starts fresh: just its own user turn.
    assert len(calls[1]) == 1
    assert calls[1][0]["content"] == "room two question"


# ── trip pin (Phase 19) ────────────────────────────────────────────────


def _capture_seam(monkeypatch):
    """Patch the answer_query seam (the single stable patch point) and
    record exactly what /query hands it."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    _mock_persistence(monkeypatch)
    seen = []

    async def fake_answer(session_name, query, trip_id=None):
        seen.append((session_name, query, trip_id))
        return "seam reply"

    monkeypatch.setattr(web_call_module, "answer_query", fake_answer)
    return seen


def test_query_forwards_trip_id_to_the_seam(monkeypatch):
    seen = _capture_seam(monkeypatch)
    resp = client.post(
        "/v1/web_call/query",
        json={"query": "where am I staying?", "session_name": "room-1",
              "trip_id": "t-42"},
    )
    assert resp.status_code == 200
    assert seen == [("room-1", "where am I staying?", "t-42")]


def test_query_without_trip_id_reaches_the_seam_as_none(monkeypatch):
    """A body without trip_id behaves exactly as before Phase 19: the seam
    sees None and the response shape is unchanged."""
    seen = _capture_seam(monkeypatch)
    resp = client.post(
        "/v1/web_call/query", json={"query": "hello", "session_name": "room-1"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"response": "seam reply"}
    assert seen == [("room-1", "hello", None)]


def test_query_blank_trip_id_normalizes_to_none(monkeypatch):
    seen = _capture_seam(monkeypatch)
    resp = client.post(
        "/v1/web_call/query",
        json={"query": "hello", "session_name": "room-1", "trip_id": "  "},
    )
    assert resp.status_code == 200
    assert seen == [("room-1", "hello", None)]


# ── turn logging ───────────────────────────────────────────────────────


def test_log_query_turns_writes_session_once_and_both_turns(monkeypatch):
    monkeypatch.setattr(web_call_module, "_LOGGED_SESSIONS", set())
    log = _mock_persistence(monkeypatch)

    asyncio.run(
        web_call_module._log_query_turns("room-1", "hi", "hello there", 1200, 1200)
    )
    asyncio.run(
        web_call_module._log_query_turns("room-1", "again", "yes again", 900, 900)
    )

    sessions = [entry[1] for entry in log if entry[0] == "session"]
    assert len(sessions) == 1
    assert sessions[0].session_id == "room-1"
    assert sessions[0].architecture == "concierge"
    assert sessions[0].client == "vb_web"

    turns = [entry[1] for entry in log if entry[0] == "turn"]
    assert [t.role for t in turns] == ["user", "agent", "user", "agent"]
    assert turns[0].transcript == "hi"
    assert turns[1].transcript == "hello there"
    assert turns[1].ttfb_ms == 1200 and turns[1].duration_ms == 1200
    assert turns[0].ttfb_ms is None


def test_log_query_turns_swallows_repository_exceptions(monkeypatch):
    monkeypatch.setattr(web_call_module, "_LOGGED_SESSIONS", set())
    _mock_persistence(monkeypatch, raise_exc=True)
    # Must not raise.
    asyncio.run(web_call_module._log_query_turns("room-1", "hi", "hello", 1, 1))


def test_query_response_survives_logging_failure(monkeypatch):
    _mock_agent(monkeypatch, reply="Still talking.")
    _mock_persistence(monkeypatch, raise_exc=True)
    resp = client.post(
        "/v1/web_call/query", json={"query": "hello", "session_name": "room-1"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"response": "Still talking."}


def test_query_schedules_turn_logging_off_the_response_path(monkeypatch):
    _mock_agent(monkeypatch, reply="Logged reply.")
    recorded = []

    async def fake_log(session_name, query, reply, ttfb_ms, duration_ms):
        recorded.append((session_name, query, reply))

    monkeypatch.setattr(web_call_module, "_log_query_turns", fake_log)

    # A context-managed client keeps the event loop alive after the response
    # so the fire-and-forget task actually runs.
    with TestClient(main.app) as ctx_client:
        resp = ctx_client.post(
            "/v1/web_call/query",
            json={"query": "log me", "session_name": "room-9"},
        )
        assert resp.status_code == 200
        for _ in range(100):
            if recorded:
                break
            time.sleep(0.01)

    assert recorded == [("room-9", "log me", "Logged reply.")]


# ── page ───────────────────────────────────────────────────────────────


def test_page_serves_l3_widget_wiring():
    resp = client.get("/v1/web_call/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    assert "useAIAgent" in resp.text
    assert "/v1/web_call/query" in resp.text
    assert "/v1/web_call/token" in resp.text


def test_page_carries_the_trip_pin_wiring_without_the_bridge():
    """Phase 19: ?trip_id= and window.vbSetTrip feed trip_id into the /query
    POST. Desktop stays explicit-only — no latest-trip bridge here, so Act 1
    rehearsals keep a clean unpinned default."""
    text = client.get("/v1/web_call/").text
    assert "vbSetTrip" in text
    assert "trip_id" in text
    assert "latest_trip_id" not in text
