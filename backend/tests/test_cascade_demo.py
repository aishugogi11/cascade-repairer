"""Phase 7 tests — the L2/L3 cascade demo router.

Hermetic: the three cascade stages are mocked at the cascade_core boundary
(no OPENAI_API_KEY, no network), repositories and GCS at theirs. /converse's
contract — one session row, two turns, audio at the convention path, and a
response that survives logging failures — is the load-bearing part.
"""
import io

from fastapi.testclient import TestClient

import main
from api import cascade_core, cascade_demo as cascade_demo_module
from api.repositories import turns as turns_repo

client = TestClient(main.app)


def _wav_upload(name="question.wav", content=b"RIFF-fake-audio"):
    return {"file": (name, io.BytesIO(content), "audio/wav")}


def _mock_stages(monkeypatch, transcript="what time is my flight", reply="Your flight is at noon."):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(
        cascade_core, "transcribe", lambda audio, filename="audio.wav": transcript
    )

    async def fake_agent_reply(text, session_id=None):
        return reply

    monkeypatch.setattr(cascade_core, "agent_reply", fake_agent_reply)
    monkeypatch.setattr(cascade_core, "synthesize", lambda text: b"MP3-BYTES")


def _mock_persistence(monkeypatch, log=None, fail=False):
    log = log if log is not None else []

    def fake_create_session(session):
        log.append(("session", session))
        return (not fail), (None if fail else session), ("boom" if fail else None)

    def fake_create_turn(turn):
        log.append(("turn", turn))
        return (not fail), (None if fail else turn), ("boom" if fail else None)

    def fake_upload(content, blob_name, content_type="application/octet-stream"):
        log.append(("upload", blob_name, content_type))
        if fail:
            return False, None, "boom"
        return True, f"gs://test-bucket/{blob_name}", None

    monkeypatch.setattr(
        cascade_demo_module.sessions_repo, "create_session", fake_create_session
    )
    monkeypatch.setattr(cascade_demo_module.turns_repo, "create_turn", fake_create_turn)
    monkeypatch.setattr(
        cascade_demo_module.gcs_helper, "upload_file_from_bytes", fake_upload
    )
    return log


# ── registration & lesson labels ───────────────────────────────────────


def test_routes_registered_with_lesson_summaries():
    paths = main.app.openapi()["paths"]
    for path in ("/v1/cascade_demo/stt", "/v1/cascade_demo/llm",
                 "/v1/cascade_demo/tts", "/v1/cascade_demo/converse"):
        assert path in paths
    assert paths["/v1/cascade_demo/stt"]["post"]["summary"].startswith("[L2/L3]")
    assert paths["/v1/cascade_demo/tts"]["post"]["summary"].startswith("[L2/L3]")
    assert paths["/v1/cascade_demo/converse"]["post"]["summary"].startswith("[L2/L3]")
    # /llm is the L3 query-server pattern and is labeled as such.
    assert paths["/v1/cascade_demo/llm"]["post"]["summary"].startswith("[L3]")


def test_landing_page_links_lessons():
    body = client.get("/v1/hello/").text
    assert "Course lessons" in body
    assert "/v1/vb_test/" in body            # L2
    assert "/docs#/cascade_demo" in body      # L2/L3
    assert "/docs#/outbound_call" in body     # L4


# ── stage endpoints ────────────────────────────────────────────────────


def test_stt_returns_transcript(monkeypatch):
    _mock_stages(monkeypatch)
    resp = client.post("/v1/cascade_demo/stt", files=_wav_upload())
    assert resp.status_code == 200
    assert resp.json() == {"transcript": "what time is my flight"}


def test_stt_missing_openai_key_is_503(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    resp = client.post("/v1/cascade_demo/stt", files=_wav_upload())
    assert resp.status_code == 503


def test_stt_non_audio_upload_is_400(monkeypatch):
    _mock_stages(monkeypatch)
    files = {"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")}
    assert client.post("/v1/cascade_demo/stt", files=files).status_code == 400


def test_stt_stage_failure_is_502(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def boom(audio, filename="audio.wav"):
        raise RuntimeError("stt down")

    monkeypatch.setattr(cascade_core, "transcribe", boom)
    assert client.post("/v1/cascade_demo/stt", files=_wav_upload()).status_code == 502


def test_llm_returns_reply(monkeypatch):
    _mock_stages(monkeypatch, reply="Hi there.")
    resp = client.post("/v1/cascade_demo/llm", json={"text": "hello"})
    assert resp.status_code == 200
    assert resp.json() == {"reply": "Hi there."}


def test_llm_blank_text_is_422(monkeypatch):
    _mock_stages(monkeypatch)
    assert client.post("/v1/cascade_demo/llm", json={"text": "  "}).status_code == 422


def test_tts_returns_mp3(monkeypatch):
    _mock_stages(monkeypatch)
    resp = client.post("/v1/cascade_demo/tts", json={"text": "hello"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("audio/mpeg")
    assert resp.content == b"MP3-BYTES"


# ── /converse ──────────────────────────────────────────────────────────


def test_converse_returns_audio_and_logs_session_and_turns(monkeypatch):
    _mock_stages(monkeypatch)
    log = _mock_persistence(monkeypatch)

    resp = client.post("/v1/cascade_demo/converse", files=_wav_upload())
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("audio/mpeg")
    assert resp.content == b"MP3-BYTES"

    session_id = resp.headers["X-Session-Id"]
    assert session_id

    sessions = [entry[1] for entry in log if entry[0] == "session"]
    assert len(sessions) == 1
    assert sessions[0].session_id == session_id
    assert sessions[0].architecture == "cascaded"
    assert sessions[0].client == "api_demo"

    turns = [entry[1] for entry in log if entry[0] == "turn"]
    assert [t.role for t in turns] == ["user", "agent"]
    assert turns[0].transcript == "what time is my flight"
    assert turns[1].transcript == "Your flight is at noon."
    assert turns[1].ttfb_ms is not None and turns[1].duration_ms is not None
    # Audio artifacts follow the convention path, uri and blob agreeing.
    for turn in turns:
        assert turn.audio_gcs_uri == turns_repo.audio_uri_for(session_id, turn.turn_id)
    uploads = [entry[1] for entry in log if entry[0] == "upload"]
    assert uploads == [f"audio/{session_id}/{t.turn_id}.wav" for t in turns]


def test_converse_with_session_id_skips_session_insert(monkeypatch):
    _mock_stages(monkeypatch)
    log = _mock_persistence(monkeypatch)
    resp = client.post(
        "/v1/cascade_demo/converse",
        files=_wav_upload(),
        data={"session_id": "existing-session"},
    )
    assert resp.status_code == 200
    assert resp.headers["X-Session-Id"] == "existing-session"
    assert not [entry for entry in log if entry[0] == "session"]
    assert len([entry for entry in log if entry[0] == "turn"]) == 2


def test_converse_still_returns_audio_when_logging_fails(monkeypatch):
    _mock_stages(monkeypatch)
    _mock_persistence(monkeypatch, fail=True)
    resp = client.post("/v1/cascade_demo/converse", files=_wav_upload())
    assert resp.status_code == 200
    assert resp.content == b"MP3-BYTES"


def test_converse_cascade_failure_is_502(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    def boom(audio, filename="audio.wav"):
        raise RuntimeError("stt down")

    monkeypatch.setattr(cascade_core, "transcribe", boom)
    _mock_persistence(monkeypatch)
    assert client.post("/v1/cascade_demo/converse", files=_wav_upload()).status_code == 502


def test_converse_non_audio_is_400_not_500(monkeypatch):
    _mock_stages(monkeypatch)
    files = {"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")}
    assert client.post("/v1/cascade_demo/converse", files=files).status_code == 400
