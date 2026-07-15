"""Phase 7 tests — the vb CLI wrapper (api/vb_cli.py).

Hermetic: subprocess.run is mocked, so no vb binary, no network, no
credentials. The wrapper's job is faithful porting of the L4 notebook
mechanics — JSON-marker parsing, purpose injection, sanitized call results —
so that's what these assert.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock

from api import vb_cli

FAKE_CALLEE = "+15555550123"
FAKE_AGENT_ID = "caller-agent-1"


def _proc(returncode=0, stdout="", stderr=""):
    proc = MagicMock()
    proc.returncode = returncode
    proc.stdout = stdout
    proc.stderr = stderr
    return proc


def _set_call_env(monkeypatch):
    monkeypatch.setenv("VOCAL_BRIDGE_API_KEY", "vb-key")
    monkeypatch.setenv("VOCAL_BRIDGE_CALLER_AGENT_ID", FAKE_AGENT_ID)
    monkeypatch.setenv("VOCAL_BRIDGE_CALLEE_PHONE", FAKE_CALLEE)
    monkeypatch.delenv("VOCAL_BRIDGE_OUTBOUND_GREETING", raising=False)


# ── run_vb ─────────────────────────────────────────────────────────────


def test_run_vb_parses_json_after_marker(monkeypatch):
    out = "table junk\n--- JSON ---\n" + json.dumps({"call_id": "c1"})
    monkeypatch.setattr(vb_cli.subprocess, "run", lambda *a, **k: _proc(stdout=out))
    ok, payload, error = vb_cli.run_vb("call", "x", json_output=True)
    assert ok and error is None
    assert payload == {"call_id": "c1"}


def test_run_vb_parses_bare_json(monkeypatch):
    monkeypatch.setattr(
        vb_cli.subprocess, "run", lambda *a, **k: _proc(stdout='[{"a": 1}]')
    )
    ok, payload, _ = vb_cli.run_vb("logs", "list", json_output=True)
    assert ok and payload == [{"a": 1}]


def test_run_vb_appends_json_flag(monkeypatch):
    seen = {}

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return _proc(stdout="{}")

    monkeypatch.setattr(vb_cli.subprocess, "run", fake_run)
    vb_cli.run_vb("call", "x", json_output=True)
    assert seen["cmd"] == ["vb", "call", "x", "--json"]


def test_run_vb_no_json_in_output_is_error(monkeypatch):
    monkeypatch.setattr(
        vb_cli.subprocess, "run", lambda *a, **k: _proc(stdout="just a table")
    )
    ok, payload, error = vb_cli.run_vb("logs", "list", json_output=True)
    assert not ok and payload is None
    assert "no JSON" in error


def test_run_vb_nonzero_exit_is_error_with_stderr(monkeypatch):
    monkeypatch.setattr(
        vb_cli.subprocess, "run", lambda *a, **k: _proc(returncode=1, stderr="boom")
    )
    ok, _, error = vb_cli.run_vb("call", "x")
    assert not ok
    assert "boom" in error


def test_run_vb_missing_binary_is_error(monkeypatch):
    def raise_fnf(*a, **k):
        raise FileNotFoundError("vb")

    monkeypatch.setattr(vb_cli.subprocess, "run", raise_fnf)
    ok, _, error = vb_cli.run_vb("call", "x")
    assert not ok
    assert "not found" in error


# ── set_caller_purpose ─────────────────────────────────────────────────


def test_set_caller_purpose_injects_base_and_purpose(monkeypatch):
    captured = {}

    def fake_run(cmd, **kwargs):
        if cmd[:3] == ["vb", "prompt", "set"]:
            # Read the temp file while it still exists.
            captured["prompt"] = Path(cmd[cmd.index("-f") + 1]).read_text()
        return _proc(stdout="ok")

    monkeypatch.setattr(vb_cli.subprocess, "run", fake_run)
    ok, full, error = vb_cli.set_caller_purpose("confirm the demo dinner reservation")
    assert ok and error is None
    # The pushed prompt carries both the shipped base and the purpose block.
    base_first_line = vb_cli.CALLER_PROMPT_BASE_PATH.read_text().splitlines()[0]
    assert base_first_line in captured["prompt"]
    assert "PURPOSE OF THIS CALL: confirm the demo dinner reservation" in captured["prompt"]
    assert captured["prompt"] == full


# ── place_call ─────────────────────────────────────────────────────────


def test_place_call_missing_callee_is_error(monkeypatch):
    _set_call_env(monkeypatch)
    monkeypatch.delenv("VOCAL_BRIDGE_CALLEE_PHONE")
    ok, result, error = vb_cli.place_call("purpose")
    assert not ok and result is None
    assert "VOCAL_BRIDGE_CALLEE_PHONE" in error


def test_place_call_happy_path_is_sanitized(monkeypatch):
    _set_call_env(monkeypatch)
    commands = []

    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        if cmd[1] == "call":
            payload = {
                "call_id": "c-42",
                "status": "initiated",
                "room_name": "room-42",
                "livekit_url": "wss://transport-secret",
                "to_number": FAKE_CALLEE,
            }
            return _proc(stdout=f"--- JSON ---\n{json.dumps(payload)}")
        return _proc(stdout="ok")

    monkeypatch.setattr(vb_cli.subprocess, "run", fake_run)
    ok, result, error = vb_cli.place_call("purpose", name="demo")
    assert ok and error is None
    # Sanitized: call_id, status, and the room_name session join key
    # (Phase 31) — nothing transport-level, never the callee number.
    assert result == {
        "call_id": "c-42", "status": "initiated", "room_name": "room-42",
    }
    # Stateless container: the caller agent is pinned before the call.
    assert ["vb", "agent", "use", FAKE_AGENT_ID] in commands
    call_cmd = next(c for c in commands if c[1] == "call")
    assert call_cmd[2] == FAKE_CALLEE
    assert "--name" in call_cmd and "demo" in call_cmd


def test_place_call_sets_greeting_when_env_present(monkeypatch):
    _set_call_env(monkeypatch)
    monkeypatch.setenv("VOCAL_BRIDGE_OUTBOUND_GREETING", "Hello from the demo")
    commands = []

    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        if cmd[1] == "call":
            return _proc(stdout='--- JSON ---\n{"call_id": "c", "status": "initiated"}')
        return _proc(stdout="ok")

    monkeypatch.setattr(vb_cli.subprocess, "run", fake_run)
    ok, _, _ = vb_cli.place_call("purpose")
    assert ok
    assert ["vb", "config", "set", "--outbound-greeting", "Hello from the demo"] in commands


def test_place_call_defaults_status_to_initiated(monkeypatch):
    _set_call_env(monkeypatch)

    def fake_run(cmd, **kwargs):
        if cmd[1] == "call":
            return _proc(stdout='--- JSON ---\n{"call_id": "c-1"}')
        return _proc(stdout="ok")

    monkeypatch.setattr(vb_cli.subprocess, "run", fake_run)
    ok, result, _ = vb_cli.place_call("purpose")
    assert ok and result["status"] == "initiated"


# ── session lookup + recording ─────────────────────────────────────────


def test_latest_session_accepts_list_and_dict_shapes(monkeypatch):
    monkeypatch.setenv("VOCAL_BRIDGE_CALLER_AGENT_ID", FAKE_AGENT_ID)

    def runner_for(payload):
        def fake_run(cmd, **kwargs):
            if cmd[1] == "logs":
                return _proc(stdout=f"--- JSON ---\n{json.dumps(payload)}")
            return _proc(stdout="ok")
        return fake_run

    monkeypatch.setattr(
        vb_cli.subprocess, "run", runner_for([{"session_id": "s1"}])
    )
    ok, session, _ = vb_cli.latest_session()
    assert ok and session == {"session_id": "s1"}

    monkeypatch.setattr(
        vb_cli.subprocess, "run", runner_for({"logs": [{"session_id": "s2"}]})
    )
    ok, session, _ = vb_cli.latest_session(status="completed")
    assert ok and session == {"session_id": "s2"}

    monkeypatch.setattr(vb_cli.subprocess, "run", runner_for([]))
    ok, session, error = vb_cli.latest_session()
    assert ok and session is None and error is None


def test_find_session_matches_live_id_key(monkeypatch):
    # Live CLI sessions key the id as `id` (observed on the deployed
    # service) — find_session must match that shape.
    monkeypatch.setenv("VOCAL_BRIDGE_CALLER_AGENT_ID", FAKE_AGENT_ID)
    payload = [{"id": "s1", "status": "completed"}, {"id": "s2", "status": "completed"}]

    def fake_run(cmd, **kwargs):
        if cmd[1] == "logs":
            return _proc(stdout=f"--- JSON ---\n{json.dumps(payload)}")
        return _proc(stdout="ok")

    monkeypatch.setattr(vb_cli.subprocess, "run", fake_run)
    ok, session, _ = vb_cli.find_session("s2")
    assert ok and session["id"] == "s2"


def test_find_session_matches_by_room_name_on_live_shaped_rows(monkeypatch):
    """Phase 31 (proven live 2026-07-15): the session log rows carry id +
    room_name and NO call_id key — a call joins to its session only through
    room_name. find_session must match it."""
    monkeypatch.setenv("VOCAL_BRIDGE_CALLER_AGENT_ID", FAKE_AGENT_ID)
    payload = [
        {"id": "d0d991f5-3401", "room_name": "room-a",
         "call_status": "completed", "transcript_text": "USER: yes"},
        {"id": "be2b0349-3ab0", "room_name": "room-b",
         "call_status": "completed", "transcript_text": "USER: no"},
    ]

    def fake_run(cmd, **kwargs):
        if cmd[1] == "logs":
            return _proc(stdout=f"--- JSON ---\n{json.dumps(payload)}")
        return _proc(stdout="ok")

    monkeypatch.setattr(vb_cli.subprocess, "run", fake_run)
    ok, session, _ = vb_cli.find_session("room-b")
    assert ok and session["id"] == "be2b0349-3ab0"
    # A call_id that appears nowhere in the rows still finds nothing —
    # the miss is honest, not an exception.
    ok, session, error = vb_cli.find_session("call-xyz")
    assert ok and session is None and error is None


def test_find_session_matches_by_id(monkeypatch):
    monkeypatch.setenv("VOCAL_BRIDGE_CALLER_AGENT_ID", FAKE_AGENT_ID)
    payload = [{"session_id": "s1"}, {"session_id": "s2"}]

    def fake_run(cmd, **kwargs):
        if cmd[1] == "logs":
            return _proc(stdout=f"--- JSON ---\n{json.dumps(payload)}")
        return _proc(stdout="ok")

    monkeypatch.setattr(vb_cli.subprocess, "run", fake_run)
    ok, session, _ = vb_cli.find_session("s2")
    assert ok and session == {"session_id": "s2"}
    ok, session, error = vb_cli.find_session("nope")
    assert ok and session is None and error is None


def test_download_recording_requires_file_to_exist(monkeypatch, tmp_path):
    monkeypatch.setenv("VOCAL_BRIDGE_CALLER_AGENT_ID", FAKE_AGENT_ID)
    out_path = str(tmp_path / "rec.mp3")

    monkeypatch.setattr(vb_cli.subprocess, "run", lambda *a, **k: _proc(stdout="ok"))
    ok, _, error = vb_cli.download_recording("s1", out_path)
    assert not ok and "missing" in error

    def fake_run_writes(cmd, **kwargs):
        if cmd[1] == "logs" and cmd[2] == "download":
            Path(out_path).write_bytes(b"mp3")
        return _proc(stdout="ok")

    monkeypatch.setattr(vb_cli.subprocess, "run", fake_run_writes)
    ok, path, error = vb_cli.download_recording("s1", out_path)
    assert ok and path == out_path and error is None
