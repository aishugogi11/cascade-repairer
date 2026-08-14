"""HTTP surface for Optimize My Trip."""
import logging
import os
import re

import requests
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api import optimize
from api.web_call import VB_API_URL

logger = logging.getLogger(__name__)

trip_builder_api = APIRouter()

_AGENT_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _looks_like_agent_id(value: str) -> bool:
    """True for Vocal Bridge agent UUIDs — rejects API keys (vb_…)."""
    text = (value or "").strip()
    if not text or text.startswith("vb_"):
        return False
    return bool(_AGENT_UUID.match(text))


def _build_credentials() -> tuple[str, str]:
    """Resolve Optimize token credentials.

    VOCAL_BRIDGE_BUILD_AGENT_ID is often mis-set to an API key. When that
    happens, fall back to the Cascade web agent + main API key so the orb
    lands in the same AI-Agent delegation path (useAIAgent → /query) instead
    of a cascaded voice agent that answers \"need more info\" itself.
    """
    build_key = os.environ.get("VOCAL_BRIDGE_BUILD_API_KEY", "").strip()
    main_key = os.environ.get("VOCAL_BRIDGE_API_KEY", "").strip()
    build_agent = os.environ.get("VOCAL_BRIDGE_BUILD_AGENT_ID", "").strip()
    web_agent = os.environ.get("VOCAL_BRIDGE_WEB_AGENT_ID", "").strip()

    if _looks_like_agent_id(build_agent):
        return (build_key or main_key), build_agent
    if build_agent:
        logger.warning(
            "VOCAL_BRIDGE_BUILD_AGENT_ID looks like an API key, not an agent "
            "UUID — falling back to VOCAL_BRIDGE_WEB_AGENT_ID"
        )
    return (main_key or build_key), (
        web_agent if _looks_like_agent_id(web_agent) else ""
    )


class ParseRequest(BaseModel):
    session_id: str = "opt-default"
    text: str = ""
    pdf_base64: str = ""
    image_base64: str = ""
    mime: str = "image/png"
    sample: bool = False
    sample_kind: str = ""


class OptimizeRequest(BaseModel):
    session_id: str = "opt-default"
    priority: str = ""
    max_walk_minutes: int | None = None
    min_buffer: int | None = None
    apply: bool = False


class TurnRequest(BaseModel):
    message: str
    session_id: str = "opt-default"


class QueryRequest(BaseModel):
    query: str
    session_name: str = "opt-voice"
    trip_id: str = ""


@trip_builder_api.post("/token")
def mint_token():
    """Mint a Vocal Bridge token for the Optimize My Trip orb."""
    api_key, agent_id = _build_credentials()
    if not api_key:
        return JSONResponse(
            status_code=503,
            content={"error": "VOCAL_BRIDGE_BUILD_API_KEY is not set"},
        )
    if not agent_id:
        return JSONResponse(
            status_code=503,
            content={"error": "VOCAL_BRIDGE_WEB_AGENT_ID is not set"},
        )
    try:
        res = requests.post(
            f"{VB_API_URL}/api/v1/token",
            headers={
                "X-API-Key": api_key,
                "X-Agent-Id": agent_id,
                "Content-Type": "application/json",
            },
            json={"participant_name": "Optimize My Trip"},
            timeout=15,
        )
    except requests.RequestException as exc:
        return JSONResponse(
            status_code=502,
            content={"error": f"Vocal Bridge unreachable: {exc}"},
        )
    if res.status_code >= 400:
        return JSONResponse(
            status_code=502,
            content={
                "error": "Vocal Bridge token mint failed",
                "upstream_status": res.status_code,
                "upstream_body": res.text[:1000],
            },
        )
    data = res.json()
    return {
        "connection_url": data.get("connection_url") or data["livekit_url"],
        "token": data["token"],
        "session_name": data["room_name"],
        "agent_mode": data.get("agent_mode", ""),
    }


@trip_builder_api.post("/parse")
def parse(req: ParseRequest):
    return optimize.ingest(
        req.session_id,
        text=req.text,
        pdf_base64=req.pdf_base64,
        image_base64=req.image_base64,
        mime=req.mime,
        sample=req.sample,
        sample_kind=req.sample_kind,
    )


@trip_builder_api.post("/optimize")
def run_optimize(req: OptimizeRequest):
    sess = optimize._attach(req.session_id)
    prefs = sess["prefs"]
    if req.priority or req.max_walk_minutes is not None or req.min_buffer is not None:
        prefs = optimize.Prefs(
            priority=req.priority or prefs.priority,
            max_walk_minutes=(
                req.max_walk_minutes
                if req.max_walk_minutes is not None
                else prefs.max_walk_minutes
            ),
            min_buffer=(
                req.min_buffer if req.min_buffer is not None else prefs.min_buffer
            ),
            frozen=prefs.frozen,
        )
    out = optimize.reoptimize(req.session_id, prefs)
    if req.apply:
        applied = optimize.apply_recommendations(req.session_id)
        out["applied"] = True
        out["reply"] = out["reply"] + " " + applied["reply"]
        out["stops"] = applied["stops"]
    return out


@trip_builder_api.get("/session/{session_id}")
def session(session_id: str):
    return optimize.session_state(session_id)


@trip_builder_api.post("/undo")
def undo(req: OptimizeRequest):
    return optimize.undo_last(req.session_id)


@trip_builder_api.get("/sample")
def sample():
    return {"text": optimize.sample_text()}


@trip_builder_api.post("/turn")
async def turn(req: TurnRequest):
    return await optimize.apply_turn(req.session_id, req.message)


@trip_builder_api.post("/query")
async def query(req: QueryRequest):
    result = await optimize.apply_turn(
        req.session_name, req.query, trip_id=req.trip_id,
    )
    return {"response": result["reply"], **{k: v for k, v in result.items() if k != "reply"}}
