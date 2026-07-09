"""Cascade demo router — the L2/L3 cascaded architecture over Swagger (Phase 7).

Each stage of the cascade (STT → LLM → TTS) is its own endpoint so every
lesson concept is demoable on its own; POST /converse chains all three and is
the reference implementation. /converse logs to `sessions`/`turns` and
archives both sides' audio to GCS — best-effort: a logging failure degrades
to a warning, never a failed demo response.

Blocking work (OpenAI audio calls, BigQuery DML, GCS uploads) runs through
asyncio.to_thread — the Phase 5 standing rule.
"""
import asyncio
import logging
import os
import time
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, field_validator

from api import cascade_core
from api.helpers.gcs_helper import gcs_helper
from api.repositories import sessions as sessions_repo
from api.repositories import turns as turns_repo
from api.repositories.models import Session, Turn

logger = logging.getLogger(__name__)

cascade_demo = APIRouter()

# What the OpenAI STT endpoint accepts; the extension check catches uploads
# whose content_type is a generic octet-stream.
_AUDIO_EXTENSIONS = {
    ".wav", ".mp3", ".m4a", ".webm", ".ogg", ".oga", ".flac", ".mpga",
    ".mpeg", ".mp4",
}


def _openai_key_missing() -> bool:
    return not os.environ.get("OPENAI_API_KEY", "").strip()


def _looks_like_audio(upload: UploadFile) -> bool:
    content_type = (upload.content_type or "").lower()
    if content_type.startswith("audio/") or content_type in ("video/webm", "video/mp4"):
        return True
    filename = (upload.filename or "").lower()
    return any(filename.endswith(ext) for ext in _AUDIO_EXTENSIONS)


def _header_safe(text: str, limit: int = 400) -> str:
    """HTTP header values must be latin-1; percent-encode the transcript so
    any speech content survives the trip."""
    return quote(text[:limit], safe=" .,!?'-")


class TextRequest(BaseModel):
    text: str = Field(..., description="Text for this stage.")
    session_id: Optional[str] = Field(
        None, description="Continue an existing demo session (multi-turn)."
    )

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be blank")
        return v


@cascade_demo.post(
    "/stt",
    summary="[L2/L3] Cascade stage 1 — speech to text",
)
async def speech_to_text(file: UploadFile = File(...)):
    if _openai_key_missing():
        return JSONResponse(status_code=503, content={"error": "OPENAI_API_KEY not set"})
    if not _looks_like_audio(file):
        return JSONResponse(status_code=400, content={"error": "upload must be an audio file"})
    audio_bytes = await file.read()
    try:
        transcript = await asyncio.to_thread(
            cascade_core.transcribe, audio_bytes, file.filename or "audio.wav"
        )
    except Exception as exc:
        return JSONResponse(status_code=502, content={"error": f"transcription failed: {exc}"})
    return {"transcript": transcript}


@cascade_demo.post(
    "/llm",
    summary="[L3] Cascade stage 2 — agent reply (the L3 query-server pattern)",
)
async def llm_reply(request: TextRequest):
    # This endpoint is the L3 "Voice for your Agent" handler shape: a spoken
    # turn arrives as text, the agent returns text for the platform to speak.
    if _openai_key_missing():
        return JSONResponse(status_code=503, content={"error": "OPENAI_API_KEY not set"})
    try:
        reply = await cascade_core.agent_reply(request.text, request.session_id)
    except Exception as exc:
        return JSONResponse(status_code=502, content={"error": f"agent reply failed: {exc}"})
    return {"reply": reply}


@cascade_demo.post(
    "/tts",
    summary="[L2/L3] Cascade stage 3 — text to speech",
)
async def text_to_speech(request: TextRequest):
    if _openai_key_missing():
        return JSONResponse(status_code=503, content={"error": "OPENAI_API_KEY not set"})
    try:
        mp3_bytes = await asyncio.to_thread(cascade_core.synthesize, request.text)
    except Exception as exc:
        return JSONResponse(status_code=502, content={"error": f"synthesis failed: {exc}"})
    return Response(content=mp3_bytes, media_type="audio/mpeg")


async def _log_converse_turns(
    session: Optional[Session],
    session_id: str,
    user_audio: bytes,
    user_content_type: str,
    transcript: str,
    reply: str,
    reply_mp3: bytes,
    ttfb_ms: int,
    duration_ms: int,
) -> None:
    """Best-effort persistence for one /converse round trip: the session row
    (first turn only), both turns, both audio artifacts. Failures warn and
    return — the demo response must never depend on logging."""
    if session is not None:
        ok, _, error = await asyncio.to_thread(sessions_repo.create_session, session)
        if not ok:
            logger.warning("cascade session insert failed: %s", error)

    user_turn = Turn(session_id=session_id, role="user", transcript=transcript)
    user_turn.audio_gcs_uri = turns_repo.audio_uri_for(session_id, user_turn.turn_id)
    agent_turn = Turn(
        session_id=session_id,
        role="agent",
        transcript=reply,
        ttfb_ms=ttfb_ms,
        duration_ms=duration_ms,
    )
    agent_turn.audio_gcs_uri = turns_repo.audio_uri_for(session_id, agent_turn.turn_id)

    for turn, audio, content_type in (
        (user_turn, user_audio, user_content_type),
        (agent_turn, reply_mp3, "audio/mpeg"),
    ):
        blob_name = f"audio/{session_id}/{turn.turn_id}.wav"
        ok, _, error = await asyncio.to_thread(
            gcs_helper.upload_file_from_bytes, audio, blob_name, content_type
        )
        if not ok:
            logger.warning("cascade audio upload failed (%s): %s", blob_name, error)
        ok, _, error = await asyncio.to_thread(turns_repo.create_turn, turn)
        if not ok:
            logger.warning("cascade turn insert failed (%s): %s", turn.role, error)


@cascade_demo.post(
    "/converse",
    summary="[L2/L3] Full cascade — audio in, spoken reply out",
)
async def converse(
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
):
    if _openai_key_missing():
        return JSONResponse(status_code=503, content={"error": "OPENAI_API_KEY not set"})
    if not _looks_like_audio(file):
        return JSONResponse(status_code=400, content={"error": "upload must be an audio file"})

    new_session: Optional[Session] = None
    if not session_id:
        new_session = Session(architecture="cascaded", client="api_demo")
        session_id = new_session.session_id

    started = time.monotonic()
    audio_bytes = await file.read()
    try:
        transcript = await asyncio.to_thread(
            cascade_core.transcribe, audio_bytes, file.filename or "audio.wav"
        )
        reply = await cascade_core.agent_reply(transcript, session_id)
        ttfb_ms = int((time.monotonic() - started) * 1000)
        reply_mp3 = await asyncio.to_thread(cascade_core.synthesize, reply)
    except Exception as exc:
        return JSONResponse(status_code=502, content={"error": f"cascade failed: {exc}"})
    duration_ms = int((time.monotonic() - started) * 1000)

    try:
        await _log_converse_turns(
            new_session,
            session_id,
            audio_bytes,
            file.content_type or "audio/wav",
            transcript,
            reply,
            reply_mp3,
            ttfb_ms,
            duration_ms,
        )
    except Exception as exc:
        logger.warning("cascade logging failed: %s", exc)

    return Response(
        content=reply_mp3,
        media_type="audio/mpeg",
        headers={
            "X-Session-Id": session_id,
            "X-Transcript": _header_safe(transcript),
            "X-Reply": _header_safe(reply),
        },
    )
