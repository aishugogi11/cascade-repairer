"""Phase 7 tests — the L4 outbound-call router and make_phone_call tool.

Hermetic (the test_vb_test.py pattern): the vb CLI wrapper is mocked at the
function boundary, env via monkeypatch, no network. The load-bearing
invariant is sanitization — the callee phone number and API key must never
appear in any response body.
"""
import asyncio

from agents import FunctionTool
from fastapi.testclient import TestClient

import main
from api import outbound_call as outbound_call_module
from api import vb_cli

client = TestClient(main.app)

FAKE_API_KEY = "vb-secret-key-123"
FAKE_CALLEE = "+15555550123"
FAKE_AGENT_ID = "caller-agent-1"


def _set_env(monkeypatch, api_key=FAKE_API_KEY, agent_id=FAKE_AGENT_ID, callee=FAKE_CALLEE):
    for name, value in (
        ("VOCAL_BRIDGE_API_KEY", api_key),
        ("VOCAL_BRIDGE_CALLER_AGENT_ID", agent_id),
        ("VOCAL_BRIDGE_CALLEE_PHONE", callee),
    ):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


# ── registration ───────────────────────────────────────────────────────


def test_routes_registered_with_l4_summaries():
    paths = main.app.openapi()["paths"]
    assert "/v1/outbound_call/call" in paths
    assert "/v1/outbound_call/status" in paths
    assert "/v1/outbound_call/recording/{session_id}" in paths
    # Lesson labels are the demo's navigation — every endpoint carries [L4].
    assert paths["/v1/outbound_call/call"]["post"]["summary"].startswith("[L4]")
    assert paths["/v1/outbound_call/status"]["get"]["summary"].startswith("[L4]")
    assert paths["/v1/outbound_call/recording/{session_id}"]["get"]["summary"].startswith("[L4]")


# ── POST /call ─────────────────────────────────────────────────────────


def test_call_returns_only_call_id_and_status(monkeypatch):
    _set_env(monkeypatch)
    monkeypatch.setattr(
        vb_cli, "place_call",
        lambda purpose, name=None: (True, {"call_id": "c-42", "status": "initiated"}, None),
    )
    resp = client.post("/v1/outbound_call/call", json={"purpose": "confirm dinner"})
    assert resp.status_code == 200
    assert resp.json() == {"call_id": "c-42", "status": "initiated"}
    assert FAKE_CALLEE not in resp.text
    assert FAKE_API_KEY not in resp.text


def test_call_passes_purpose_and_name_through(monkeypatch):
    _set_env(monkeypatch)
    seen = {}

    def fake_place_call(purpose, name=None):
        seen["purpose"], seen["name"] = purpose, name
        return True, {"call_id": "c", "status": "initiated"}, None

    monkeypatch.setattr(vb_cli, "place_call", fake_place_call)
    client.post("/v1/outbound_call/call", json={"purpose": "say hi", "name": "demo"})
    assert seen == {"purpose": "say hi", "name": "demo"}


def test_call_missing_env_is_503_naming_the_var(monkeypatch):
    for missing in ("VOCAL_BRIDGE_API_KEY", "VOCAL_BRIDGE_CALLER_AGENT_ID",
                    "VOCAL_BRIDGE_CALLEE_PHONE"):
        _set_env(monkeypatch)
        monkeypatch.delenv(missing)
        resp = client.post("/v1/outbound_call/call", json={"purpose": "x"})
        assert resp.status_code == 503
        assert missing in resp.json()["error"]


def test_call_blank_purpose_is_422(monkeypatch):
    _set_env(monkeypatch)
    assert client.post("/v1/outbound_call/call", json={"purpose": "   "}).status_code == 422
    assert client.post("/v1/outbound_call/call", json={}).status_code == 422


def test_call_cli_failure_is_502_and_scrubbed(monkeypatch):
    _set_env(monkeypatch)
    monkeypatch.setattr(
        vb_cli, "place_call",
        lambda purpose, name=None: (False, None, f"vb call {FAKE_CALLEE} failed: key {FAKE_API_KEY} rejected"),
    )
    resp = client.post("/v1/outbound_call/call", json={"purpose": "x"})
    assert resp.status_code == 502
    assert FAKE_CALLEE not in resp.text
    assert FAKE_API_KEY not in resp.text
    assert "[redacted]" in resp.json()["error"]


# ── GET /status ────────────────────────────────────────────────────────


def test_status_defaults_to_latest_session_and_scrubs(monkeypatch):
    _set_env(monkeypatch)
    session = {
        "session_id": "s-1",
        "status": "completed",
        "to_number": FAKE_CALLEE,
        "transcript": [{"role": "agent", "text": f"calling {FAKE_CALLEE} now"}],
    }
    monkeypatch.setattr(vb_cli, "latest_session", lambda status=None: (True, session, None))
    resp = client.get("/v1/outbound_call/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["session"]["session_id"] == "s-1"
    assert body["recording_available"] is True
    assert len(body["transcript"]) == 1
    assert FAKE_CALLEE not in resp.text


def test_status_surfaces_live_session_shape(monkeypatch):
    # The deployed CLI returns `transcript_text` (a string) and
    # `call_status` — the status endpoint must surface both.
    _set_env(monkeypatch)
    session = {
        "id": "s-live",
        "call_status": "completed",
        "status": "completed",
        "transcript_text": "USER: hello\n\nAGENT: hi there",
        "caller_phone": FAKE_CALLEE,
    }
    monkeypatch.setattr(vb_cli, "latest_session", lambda status=None: (True, session, None))
    resp = client.get("/v1/outbound_call/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["transcript"] == "USER: hello\n\nAGENT: hi there"
    assert body["recording_available"] is True
    assert FAKE_CALLEE not in resp.text


def test_status_with_session_id_uses_find_session(monkeypatch):
    _set_env(monkeypatch)
    seen = {}

    def fake_find(session_id):
        seen["session_id"] = session_id
        return True, {"session_id": session_id, "status": "in_progress"}, None

    monkeypatch.setattr(vb_cli, "find_session", fake_find)
    resp = client.get("/v1/outbound_call/status", params={"session_id": "s-9"})
    assert resp.status_code == 200
    assert seen["session_id"] == "s-9"
    assert resp.json()["recording_available"] is False


def test_status_unknown_session_is_404(monkeypatch):
    _set_env(monkeypatch)
    monkeypatch.setattr(vb_cli, "find_session", lambda sid: (True, None, None))
    assert client.get("/v1/outbound_call/status", params={"session_id": "nope"}).status_code == 404


def test_status_invalid_session_id_is_422(monkeypatch):
    _set_env(monkeypatch)
    resp = client.get("/v1/outbound_call/status", params={"session_id": "../etc"})
    assert resp.status_code == 422


def test_status_missing_env_is_503(monkeypatch):
    _set_env(monkeypatch, api_key=None)
    assert client.get("/v1/outbound_call/status").status_code == 503


# ── GET /recording/{session_id} ────────────────────────────────────────


def test_recording_uploads_to_gcs_and_returns_uri(monkeypatch):
    _set_env(monkeypatch)
    seen = {}
    monkeypatch.setattr(
        vb_cli, "download_recording", lambda sid, path: (True, path, None)
    )

    def fake_upload(local_path, blob_name):
        seen["blob_name"] = blob_name
        return True, f"gs://test-bucket/{blob_name}", None

    monkeypatch.setattr(outbound_call_module.gcs_helper, "upload_file", fake_upload)
    resp = client.get("/v1/outbound_call/recording/s-1")
    assert resp.status_code == 200
    assert resp.json() == {"gcs_uri": "gs://test-bucket/audio/outbound/s-1.mp3"}
    assert seen["blob_name"] == "audio/outbound/s-1.mp3"


def test_recording_not_found_is_404(monkeypatch):
    _set_env(monkeypatch)
    monkeypatch.setattr(
        vb_cli, "download_recording",
        lambda sid, path: (False, None, "vb logs download failed: session not found"),
    )
    assert client.get("/v1/outbound_call/recording/s-1").status_code == 404


def test_recording_cli_failure_is_502(monkeypatch):
    _set_env(monkeypatch)
    monkeypatch.setattr(
        vb_cli, "download_recording", lambda sid, path: (False, None, "timeout")
    )
    assert client.get("/v1/outbound_call/recording/s-1").status_code == 502


def test_recording_invalid_session_id_is_422(monkeypatch):
    # The id lands in file names and CLI args — anything outside the safe
    # charset is rejected before either. (Encoded slashes never reach the
    # route: the client normalizes them away.)
    _set_env(monkeypatch)
    assert client.get("/v1/outbound_call/recording/bad!id").status_code == 422


# ── make_phone_call tool ───────────────────────────────────────────────


def test_make_phone_call_is_a_function_tool():
    assert isinstance(outbound_call_module.make_phone_call, FunctionTool)


def test_make_phone_call_plain_function_returns_sanitized_shape(monkeypatch):
    monkeypatch.setattr(
        vb_cli, "place_call",
        lambda purpose, name=None: (True, {"call_id": "c-7", "status": "initiated"}, None),
    )
    result = asyncio.run(outbound_call_module._make_phone_call("confirm hotel"))
    assert result == {"call_id": "c-7", "status": "initiated"}


def test_make_phone_call_failure_reports_error_status(monkeypatch):
    monkeypatch.setenv("VOCAL_BRIDGE_CALLEE_PHONE", FAKE_CALLEE)
    monkeypatch.setattr(
        vb_cli, "place_call",
        lambda purpose, name=None: (False, None, f"could not dial {FAKE_CALLEE}"),
    )
    result = asyncio.run(outbound_call_module._make_phone_call("x"))
    assert result["call_id"] is None
    assert result["status"].startswith("error:")
    assert FAKE_CALLEE not in result["status"]
