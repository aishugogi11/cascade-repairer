"""HTTP surface for Optimize My Trip."""
import os

import requests
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api import optimize
from api.web_call import VB_API_URL

trip_builder_api = APIRouter()


class ParseRequest(BaseModel):
    session_id: str = "opt-default"
    text: str = ""
    pdf_base64: str = ""
    image_base64: str = ""
    mime: str = "image/png"
    sample: bool = False


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


@trip_builder_api.post("/token")
def mint_token():
    """Mint a Vocal Bridge token for the Optimize My Trip orb."""
    api_key = (
        os.environ.get("VOCAL_BRIDGE_BUILD_API_KEY", "").strip()
        or os.environ.get("VOCAL_BRIDGE_API_KEY", "").strip()
    )
    agent_id = (
        os.environ.get("VOCAL_BRIDGE_BUILD_AGENT_ID", "").strip()
        or os.environ.get("VOCAL_BRIDGE_WEB_AGENT_ID", "").strip()
    )
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
    result = await optimize.apply_turn(req.session_name, req.query)
    return {"response": result["reply"], **{k: v for k, v in result.items() if k != "reply"}}
