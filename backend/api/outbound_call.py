"""L4 "Voice as a Tool" — outbound phone calls as an API surface (Phase 7).

Ports the L4 notebook flow (jupyter_notebook/training_course/L4/L4.ipynb) to
demo endpoints: POST /call places a real outbound phone call with a per-call
purpose injected into the caller agent's prompt, GET /status inspects the
resulting session, GET /recording/{session_id} archives the call audio to
GCS. The `make_phone_call` function_tool wraps the same core so Phase 9's
Concierge (and the Phase 12 demo opening beat) can hand it to an agent.

Sanitization invariant (ported from the notebook): nothing returned to an
LLM or API client ever contains the callee phone number, the API key, or
transport-level fields — /call responds with call_id and status only, and
every other payload is scrubbed of secret values before it leaves.
"""
import asyncio
import os
import re
import tempfile
from typing import Any, Optional

from agents import function_tool
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from api import vb_cli
from api.helpers.gcs_helper import gcs_helper

outbound_call = APIRouter()

# Session ids come back as CLI/user input and end up in file names and shell
# args — keep them to a safe charset.
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _secret_values() -> list:
    return [
        v.strip()
        for v in (
            os.environ.get("VOCAL_BRIDGE_API_KEY", ""),
            os.environ.get("VOCAL_BRIDGE_CALLEE_PHONE", ""),
        )
        if v.strip()
    ]


def _scrub(obj: Any) -> Any:
    """Redact secret values (API key, callee number) anywhere in a payload
    before it leaves the service — CLI errors and session logs can echo the
    dialed number back."""
    secrets = _secret_values()
    if isinstance(obj, str):
        for secret in secrets:
            obj = obj.replace(secret, "[redacted]")
        return obj
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    return obj


def _missing_env(*names: str) -> Optional[str]:
    for name in names:
        if not os.environ.get(name, "").strip():
            return name
    return None


class CallRequest(BaseModel):
    purpose: str = Field(..., description="What the caller agent should accomplish on this call.")
    name: Optional[str] = Field(None, description="Optional display name for the call.")

    @field_validator("purpose")
    @classmethod
    def _purpose_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("purpose must not be blank")
        return v.strip()


@outbound_call.post(
    "/call",
    summary="[L4] Place an outbound phone call with an injected purpose",
)
async def place_outbound_call(request: CallRequest):
    missing = _missing_env(
        "VOCAL_BRIDGE_API_KEY",
        "VOCAL_BRIDGE_CALLER_AGENT_ID",
        "VOCAL_BRIDGE_CALLEE_PHONE",
    )
    if missing:
        return JSONResponse(status_code=503, content={"error": f"{missing} not set"})

    # The CLI blocks on the network; keep it off the event loop.
    ok, result, error = await asyncio.to_thread(
        vb_cli.place_call, request.purpose, request.name
    )
    if not ok:
        return JSONResponse(status_code=502, content={"error": _scrub(error)})
    return {"call_id": result["call_id"], "status": result["status"]}


@outbound_call.get(
    "/status",
    summary="[L4] Inspect the latest (or a specific) outbound-call session",
)
async def call_status(session_id: Optional[str] = None):
    missing = _missing_env("VOCAL_BRIDGE_API_KEY", "VOCAL_BRIDGE_CALLER_AGENT_ID")
    if missing:
        return JSONResponse(status_code=503, content={"error": f"{missing} not set"})
    if session_id is not None and not _SESSION_ID_RE.match(session_id):
        return JSONResponse(status_code=422, content={"error": "invalid session_id"})

    if session_id:
        ok, session, error = await asyncio.to_thread(vb_cli.find_session, session_id)
    else:
        ok, session, error = await asyncio.to_thread(vb_cli.latest_session)
    if not ok:
        return JSONResponse(status_code=502, content={"error": _scrub(error)})
    if session is None:
        return JSONResponse(status_code=404, content={"error": "no matching session"})

    # Session log shapes vary by CLI version — pass the (scrubbed) session
    # through and surface the fields the demo needs beside it. Live payloads
    # carry the transcript as one `transcript_text` string (observed
    # 2026-07-08 on the deployed service).
    transcript = (
        session.get("transcript")
        or session.get("messages")
        or session.get("transcript_text")
        or []
    )
    recording_available = bool(
        session.get("recording_url")
        or session.get("has_recording")
        or session.get("status") == "completed"
        or session.get("call_status") == "completed"
    )
    return _scrub(
        {
            "session": session,
            "transcript": transcript,
            "recording_available": recording_available,
        }
    )


@outbound_call.get(
    "/recording/{session_id}",
    summary="[L4] Archive a call recording to GCS and return its URI",
)
async def fetch_recording(session_id: str):
    missing = _missing_env("VOCAL_BRIDGE_API_KEY", "VOCAL_BRIDGE_CALLER_AGENT_ID")
    if missing:
        return JSONResponse(status_code=503, content={"error": f"{missing} not set"})
    if not _SESSION_ID_RE.match(session_id):
        return JSONResponse(status_code=422, content={"error": "invalid session_id"})

    local_path = os.path.join(
        tempfile.gettempdir(), f"vb_recording_{session_id}.mp3"
    )
    ok, _, error = await asyncio.to_thread(
        vb_cli.download_recording, session_id, local_path
    )
    if not ok:
        status = 404 if "not found" in (error or "").lower() else 502
        return JSONResponse(status_code=status, content={"error": _scrub(error)})

    try:
        ok, gcs_uri, error = await asyncio.to_thread(
            gcs_helper.upload_file, local_path, f"audio/outbound/{session_id}.mp3"
        )
    finally:
        try:
            os.unlink(local_path)
        except OSError:
            pass
    if not ok:
        return JSONResponse(
            status_code=502, content={"error": f"GCS upload failed: {_scrub(error)}"}
        )
    return {"gcs_uri": gcs_uri}


async def _make_phone_call(purpose: str, name: Optional[str] = None) -> dict:
    """Place a real outbound phone call to the configured demo callee.

    The purpose is injected into the caller agent's prompt so it knows what
    to accomplish; the call runs asynchronously after this returns. Returns
    only call_id and status.
    """
    ok, result, error = await asyncio.to_thread(vb_cli.place_call, purpose, name)
    if not ok:
        return {"call_id": None, "status": f"error: {_scrub(error)}"}
    return result


# The LLM-visible tool for Phase 9's Concierge and the Phase 12 opening beat
# ("agent notices, agent acts"). The plain function stays callable for tests
# — the hello.py _get_weather pattern.
make_phone_call = function_tool(_make_phone_call)
