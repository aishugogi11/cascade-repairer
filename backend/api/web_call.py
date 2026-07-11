"""Vocal Bridge web client integration — Phase 8.

The browser surface for the backend agent: the L3 "Voice for your Agent"
pattern (jupyter_notebook/training_course/L3/L3.ipynb) as production routes.
A VB agent in AI Agent mode owns STT, TTS, and turn-taking, and delegates
every spoken query to the page's `useAIAgent` hook, which POSTs it
same-origin to /query; whatever text comes back, VB speaks. /query is a thin
seam (`answer_query`) — since Phase 9 it runs the Concierge hybrid
(concierge.py): a fast foreground agent that launches background repairs and
keeps talking while they run.

Token minting follows vb_test.py verbatim (server-side, the API key never
reaches the browser) but against a separate AI-Agent-mode VB agent
(VOCAL_BRIDGE_WEB_AGENT_ID): AI Agent mode and Background System are
mutually exclusive in VB, so the Phase 4 smoke-test agent stays untouched.

Turn logging to sessions/turns is fire-and-forget off the response path —
the spoken reply must never wait on BigQuery — and DML runs through
asyncio.to_thread (the Phase 5 standing rule). Session history is an
in-process dict, the same deliberate single-instance scope as cascade_core.
"""
import asyncio
import logging
import os
import time
from string import Template
from typing import Set

import requests
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

from api import concierge
from api.repositories import sessions as sessions_repo
from api.repositories import turns as turns_repo
from api.repositories.models import Session, Turn

logger = logging.getLogger(__name__)

web_call = APIRouter()

VB_API_URL = "https://vocalbridgeai.com"

# Pinned versions for CDN imports, matching the L3 lesson widget. Bump when
# newer VB SDKs ship.
VB_REACT_VER = "0.1.1"
VB_SDK_VER = "0.1.1"
REACT_VER = "18"

# Sessions whose row insert has been attempted (attempted, not confirmed —
# a failed insert warns rather than retrying every turn).
_LOGGED_SESSIONS: Set[str] = set()
# Strong refs so fire-and-forget logging tasks aren't garbage-collected.
_LOG_TASKS: Set[asyncio.Task] = set()


@web_call.post("/token")
def mint_token():
    # Env is read per-request (not at import) so vars set on the Cloud Run
    # service — or monkeypatched in tests — apply without a reload. Missing
    # config reports which var broke, mirroring vb_test's philosophy.
    api_key = os.environ.get("VOCAL_BRIDGE_API_KEY", "").strip()
    agent_id = os.environ.get("VOCAL_BRIDGE_WEB_AGENT_ID", "").strip()
    if not api_key:
        return JSONResponse(status_code=503,
                            content={"error": "VOCAL_BRIDGE_API_KEY not set"})
    if not agent_id:
        return JSONResponse(status_code=503,
                            content={"error": "VOCAL_BRIDGE_WEB_AGENT_ID not set"})

    try:
        res = requests.post(
            f"{VB_API_URL}/api/v1/token",
            headers={
                "X-API-Key": api_key,
                "X-Agent-Id": agent_id,
                "Content-Type": "application/json",
            },
            json={"participant_name": "Web Call Page"},
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
    # The API returns transport-level field names; alias them to the neutral,
    # transport-agnostic names the SDK exposes (same mapping as L3 helpers).
    return {
        "connection_url": data.get("connection_url") or data["livekit_url"],
        "token": data["token"],
        "session_name": data["room_name"],
        "agent_mode": data.get("agent_mode", ""),
    }


async def answer_query(session_name: str, query: str) -> str:
    """One delegated spoken turn. Kept as the stable seam (tests patch here,
    rollback is this one line); since Phase 9 the implementation is the
    Concierge hybrid."""
    return await concierge.answer_query(session_name, query)


async def _log_query_turns(
    session_name: str,
    query: str,
    reply: str,
    ttfb_ms: int,
    duration_ms: int,
) -> None:
    """Best-effort persistence for one delegated turn: the session row (first
    turn only), then user and agent turns. Failures warn and return — the
    spoken reply never depends on logging."""
    try:
        if session_name not in _LOGGED_SESSIONS:
            _LOGGED_SESSIONS.add(session_name)
            session = Session(
                session_id=session_name, architecture="concierge", client="vb_web"
            )
            ok, _, error = await asyncio.to_thread(
                sessions_repo.create_session, session
            )
            if not ok:
                logger.warning("web_call session insert failed: %s", error)

        user_turn = Turn(session_id=session_name, role="user", transcript=query)
        agent_turn = Turn(
            session_id=session_name,
            role="agent",
            transcript=reply,
            ttfb_ms=ttfb_ms,
            duration_ms=duration_ms,
        )
        for turn in (user_turn, agent_turn):
            ok, _, error = await asyncio.to_thread(turns_repo.create_turn, turn)
            if not ok:
                logger.warning("web_call turn insert failed (%s): %s", turn.role, error)
    except Exception as exc:
        logger.warning("web_call logging failed: %s", exc)


class QueryRequest(BaseModel):
    query: str = Field(..., description="The delegated spoken question.")
    session_name: str = Field(
        ..., description="The VB session name from the token response."
    )

    @field_validator("query", "session_name")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v.strip()


@web_call.post(
    "/query",
    summary="[L3] Delegated spoken query → backend agent reply",
)
async def delegated_query(request: QueryRequest):
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        return JSONResponse(status_code=503, content={"error": "OPENAI_API_KEY not set"})

    started = time.monotonic()
    try:
        reply = await answer_query(request.session_name, request.query)
    except Exception as exc:
        return JSONResponse(
            status_code=502, content={"error": f"agent query failed: {exc}"}
        )
    elapsed_ms = int((time.monotonic() - started) * 1000)

    # Fire-and-forget: VB is waiting to speak the reply; BigQuery can't be
    # allowed to add latency. ttfb == duration here — text out is the last
    # byte (no synthesis stage; VB owns TTS).
    task = asyncio.create_task(
        _log_query_turns(
            request.session_name, request.query, reply, elapsed_ms, elapsed_ms
        )
    )
    _LOG_TASKS.add(task)
    task.add_done_callback(_LOG_TASKS.discard)

    return {"response": reply}


# The page is the Phase 4 widget template plus the L3 delta: useAIAgent
# forwards every delegated query same-origin to /v1/web_call/query.
_PAGE = Template("""<html>
  <head><title>Web Call</title></head>
  <body style="font-family: -apple-system, system-ui, sans-serif; max-width: 720px; margin: 24px auto; padding: 0 16px;">
    <h1>Web Call</h1>
    <p>Live voice conversation with the backend agent. Click Connect, allow the microphone, and say hello — spoken questions are answered by the agent running on this backend.</p>
    <div id="vb-root" style="min-height: 320px; padding: 16px; border: 1px solid #ddd; border-radius: 12px; color: #888;">loading Vocal Bridge React SDK&hellip;</div>
    <p><a href="/v1/hello/">Back to API home</a></p>
    <script type="module">
import React, { useState, useCallback, useMemo, useRef } from 'https://esm.sh/react@$react_ver';
import ReactDOM from 'https://esm.sh/react-dom@$react_ver/client';
import {
  VocalBridgeProvider, useVocalBridge, useTranscript, useAIAgent,
} from 'https://esm.sh/@vocalbridgeai/react@$vb_react_ver?deps=react@$react_ver,react-dom@$react_ver';
import { ConnectionState } from 'https://esm.sh/@vocalbridgeai/sdk@$vb_sdk_ver';

const e = React.createElement;

// Access-code pass-through (Phase 17): ?code= wins and is persisted, so a
// reload without the param keeps working; with no code the page still
// renders and its API calls 401 cleanly.
const codeFromUrl = new URL(window.location).searchParams.get('code');
if (codeFromUrl) localStorage.setItem('vb_access_code', codeFromUrl);
const ACCESS_CODE = codeFromUrl || localStorage.getItem('vb_access_code') || '';
function codeHeaders(extra) {
  const headers = Object.assign({}, extra);
  if (ACCESS_CODE) headers['X-Access-Code'] = ACCESS_CODE;
  return headers;
}

const ROLE_COLOR = { user: '#4f46e5', agent: '#10b981', backend: '#f59e0b' };
const styles = {
  row: { display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12 },
  btn: (kind) => ({
    padding: '10px 18px', borderRadius: 8, border: 'none',
    background: kind === 'danger' ? '#ef4444' : '#4f46e5',
    color: 'white', fontWeight: 600, cursor: 'pointer',
  }),
  state: { color: '#666', fontFamily: 'monospace', fontSize: 13 },
  transcript: { height: 260, overflowY: 'auto', padding: 12, background: '#fafafa', borderRadius: 8, fontSize: 14, lineHeight: 1.5, marginTop: 12 },
  roleTag: (role) => ({
    color: ROLE_COLOR[role] || '#999', fontWeight: 600,
    fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.1em', marginRight: 6,
  }),
  err: { color: '#dc2626', fontSize: 13, marginTop: 6 },
};

function VoiceUI({ tokenError, sessionRef }) {
  const { state, connect, disconnect, error } = useVocalBridge();
  const { transcript } = useTranscript();
  const [backendLines, setBackendLines] = useState([]);  // delegated-query trace
  const [queryError, setQueryError] = useState(null);

  // The AI Agent hook (the L3 pattern): every delegated spoken question
  // arrives here; whatever string we return, VB speaks to the user.
  useAIAgent({
    onQuery: async (query) => {
      setQueryError(null);
      try {
        const res = await fetch('/v1/web_call/query', {
          method: 'POST',
          headers: codeHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify({
            query,
            session_name: sessionRef.current || 'unknown-session',
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          throw new Error('HTTP ' + res.status + ': ' + JSON.stringify(data));
        }
        setBackendLines((prev) => [...prev, { role: 'backend', text: data.response }]);
        return data.response;
      } catch (err) {
        setQueryError('query failed: ' + err.message);
        return "Sorry — I couldn't reach my backend brain. Try that again in a moment.";
      }
    },
  });

  const isDisconnected = state === ConnectionState.Disconnected;
  const busy = state === ConnectionState.Connecting || state === ConnectionState.WaitingForAgent;

  // Merge VB's transcript with the backend trace into one timeline.
  const lines = [...transcript, ...backendLines];

  return e('div', null,
    e('div', { style: styles.row },
      e('button', {
        style: styles.btn(isDisconnected ? 'primary' : 'danger'),
        onClick: isDisconnected ? connect : disconnect,
        disabled: busy,
      }, isDisconnected ? 'Connect' : 'Disconnect'),
      e('span', { style: styles.state }, state),
    ),
    error && e('div', { style: styles.err }, error.message),
    tokenError && e('div', { style: styles.err }, tokenError),
    queryError && e('div', { style: styles.err }, queryError),
    e('div', { style: styles.transcript },
      lines.length === 0
        ? e('div', { style: { color: '#aaa', fontStyle: 'italic' } }, 'transcript will appear here…')
        : lines.map((t, i) => e('div', { key: i },
            e('span', { style: styles.roleTag(t.role) }, t.role),
            t.text,
          ))
    ),
  );
}

function App() {
  const [tokenError, setTokenError] = useState(null);
  // The VB session name from the token response, so /query calls can be
  // tied to the same session for memory and turn logging.
  const sessionRef = useRef(null);

  // Token is minted server-side; a failed mint surfaces its JSON body here
  // so a missing env var is diagnosable from the page itself.
  const tokenProvider = useCallback(async () => {
    setTokenError(null);
    const res = await fetch('/v1/web_call/token', { method: 'POST', headers: codeHeaders() });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = 'token mint failed (HTTP ' + res.status + '): ' + JSON.stringify(data);
      setTokenError(msg);
      throw new Error(msg);
    }
    sessionRef.current = data.session_name;
    return {
      url: data.connection_url,
      token: data.token,
      room_name: data.session_name,
      participant_identity: 'web-call-page',
      expires_in: 3600,
      agent_mode: data.agent_mode,
    };
  }, []);

  const options = useMemo(() => ({ auth: { tokenProvider }, debug: false }), [tokenProvider]);

  return e(VocalBridgeProvider, { options },
    e(VoiceUI, { tokenError, sessionRef }),
  );
}

const container = document.getElementById('vb-root');
container.style.color = '#222';
container.innerHTML = '';
ReactDOM.createRoot(container).render(e(App));
    </script>
  </body>
</html>""").substitute(
    react_ver=REACT_VER,
    vb_react_ver=VB_REACT_VER,
    vb_sdk_ver=VB_SDK_VER,
)


@web_call.get("/", response_class=HTMLResponse)
def web_call_page():
    return _PAGE
