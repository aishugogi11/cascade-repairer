"""Helpers for Lesson 3 — Voice for your Agent (AI Agent Integration).

Adds two things to the Lesson 2 toolkit:
  - start_query_server() — FastAPI in a background thread; the widget
                           POSTs spoken queries to it and gets text back.
  - voice_widget()       — uses the VB React SDK's `useAIAgent({ onQuery })`
                           hook to forward every query through that endpoint.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from string import Template
from typing import Any, Callable

import requests
import uvicorn
from dotenv import load_dotenv, find_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


VB_API_URL = "https://vocalbridgeai.com"

VB_REACT_VER = "0.1.1"
VB_SDK_VER = "0.1.1"
REACT_VER = "18"


def load_env():
    load_dotenv(find_dotenv())


@dataclass
class TokenData:
    """Voice session token returned by VB's /api/v1/token endpoint.

    Field names use VB-native vocabulary; the underlying transport details
    are an implementation detail learners don't need to think about.
    """
    connection_url: str       # the wss:// endpoint the SDK connects to
    token: str                # short-lived JWT
    session_name: str         # unique name for this voice session
    agent_mode: str           # e.g. "openai_concierge"

    def as_dict(self) -> dict[str, Any]:
        return {
            "connection_url": self.connection_url,
            "token": self.token,
            "session_name": self.session_name,
            "agent_mode": self.agent_mode,
        }


def mint_token(
    agent_id: str,
    api_key: str | None = None,
    participant_name: str = "Notebook Learner",
) -> TokenData:
    """POST /api/v1/token. Returns a VB voice session token for the widget."""
    api_key = api_key or os.environ["VOCAL_BRIDGE_API_KEY"]
    res = requests.post(
        f"{VB_API_URL}/api/v1/token",
        headers={
            "X-API-Key": api_key,
            "X-Agent-Id": agent_id,
            "Content-Type": "application/json",
        },
        json={"participant_name": participant_name},
        timeout=15,
    )
    res.raise_for_status()
    data = res.json()
    return TokenData(
        # API returns the transport's field name; we expose a neutral
        # `connection_url` to keep the lesson surface transport-agnostic.
        connection_url=data.get("connection_url") or data["livekit_url"],
        token=data["token"],
        session_name=data["room_name"],
        agent_mode=data.get("agent_mode", ""),
    )


def vb(*args: str, json_output: bool = False) -> Any:
    cmd = ["vb", *args]
    if json_output and "--json" not in args:
        cmd.append("--json")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"vb {args} failed:\n{proc.stderr or proc.stdout}")
    out = proc.stdout
    if json_output:
        # The CLI prints a human-readable table first, then a JSON block
        # separated by `--- JSON ---`. Anchor on that marker when present.
        marker = "--- JSON ---"
        if marker in out:
            out = out.split(marker, 1)[1]
        for i, ch in enumerate(out):
            if ch in "{[":
                return json.loads(out[i:])
        raise ValueError(f"no JSON found in output:\n{out}")
    return out


def append_to_env(key: str, value: str, env_path: str | Path = ".env") -> None:
    p = Path(env_path)
    lines = p.read_text().splitlines() if p.exists() else []
    found = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break
    if not found:
        lines.append(f"{key}={value}")
    p.write_text("\n".join(lines) + "\n")
    os.environ[key] = value


# ── FastAPI background server ─────────────────────────────────────────
_server_state: dict[str, Any] = {"server": None, "thread": None}


class _QueryRequest(BaseModel):
    query: str
    turn_id: str | None = None


def start_query_server(
    handler: Callable[[str], str],
    port: int = 8765,
) -> str:
    """Start a FastAPI server with POST /query in a background thread."""
    if _server_state["server"] is not None:
        stop_query_server()

    app = FastAPI()
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    @app.post("/query")
    def query(req: _QueryRequest) -> dict[str, Any]:
        try:
            response = handler(req.query)
        except Exception as exc:
            response = f"(error: {exc})"
        return {"response": response, "turn_id": req.turn_id}

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    # Bind to 0.0.0.0 (not 127.0.0.1) so DLAI's edge can route the
    # per-port subdomain (e.g. <host>p8765.lab-aws-staging.deeplearning.ai)
    # into the container. Locally this also works — the browser still
    # reaches it via localhost.
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)

    def _run() -> None:
        server.run()

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()

    url = f"http://localhost:{port}"
    for _ in range(40):
        try:
            requests.get(f"{url}/health", timeout=0.5).raise_for_status()
            break
        except Exception:
            time.sleep(0.1)
    else:
        raise RuntimeError(f"Query server didn't come up on {url}")

    _server_state["server"] = server
    _server_state["thread"] = thread
    return url


def stop_query_server() -> None:
    server = _server_state.get("server")
    if server is None:
        return
    server.should_exit = True
    thread = _server_state.get("thread")
    if thread is not None:
        thread.join(timeout=3)
    _server_state["server"] = None
    _server_state["thread"] = None


# ── In-notebook voice widget (Vocal Bridge React SDK + AI Agent mode) ─
_WIDGET_TEMPLATE = Template("""
<div id="$root_id" style="font-family: -apple-system, system-ui, sans-serif; max-width: 720px; min-height: ${height}px; padding: 16px; border: 1px solid #ddd; border-radius: 12px; color: #888;">loading Vocal Bridge React SDK…</div>
<script type="module">
import React, { useState, useEffect } from 'https://esm.sh/react@$react_ver';
import ReactDOM from 'https://esm.sh/react-dom@$react_ver/client';
import {
  VocalBridgeProvider, useVocalBridge, useTranscript, useAIAgent,
} from 'https://esm.sh/@vocalbridgeai/react@$vb_react_ver?deps=react@$react_ver,react-dom@$react_ver';
import { ConnectionState } from 'https://esm.sh/@vocalbridgeai/sdk@$vb_sdk_ver';

const e = React.createElement;
const TOKEN = $token_payload;
const RAW_QUERY_URL = $query_url;

// Resolve the FastAPI URL for the browser. Locally, kernel and browser
// share localhost so the raw URL works. In remote-kernel sandboxes we
// have to route the browser to the container's port via the platform's
// chosen mechanism. Two patterns covered:
//
//   1. Per-port subdomain (DLAI, Coder, Codespaces-style). Hostnames look
//      like `<host>p<JUPYTER_PORT>.<rest>`. We substitute the port to
//      reach the FastAPI on its own subdomain.
//   2. jupyter-server-proxy fallback at `<lab-base>/proxy/<port>/`.
function resolveQueryUrl(raw) {
  const m = raw.match(/^https?:\\/\\/(?:localhost|127\\.0\\.0\\.1):(\\d+)(\\/.*)?$$/);
  if (!m) return raw;
  const loc = window.location;
  if (loc.hostname === 'localhost' || loc.hostname === '127.0.0.1') return raw;
  const port = m[1];
  const path = m[2] || '/';
  const subdomain = loc.hostname.match(/^(.+)p(\\d+)\\.(.+)$$/);
  if (subdomain) {
    const newHost = subdomain[1] + 'p' + port + '.' + subdomain[3];
    return loc.protocol + '//' + newHost + path;
  }
  const baseMatch = loc.pathname.match(/^(.*?)\\/(notebooks|lab|tree|files|edit)\\//);
  const base = baseMatch ? baseMatch[1] : '';
  return loc.origin + base + '/proxy/' + port + path;
}
const QUERY_URL = resolveQueryUrl(RAW_QUERY_URL);

// Pre-minted token; the React SDK consumes it via a custom tokenProvider
// so no API key ever reaches the browser. The SDK's contract uses the
// underlying transport field names; we map our VB-native names to those.
const tokenProvider = async () => ({
  url: TOKEN.connection_url,
  token: TOKEN.token,
  room_name: TOKEN.session_name,
  participant_identity: 'notebook-learner',
  expires_in: 3600,
  agent_mode: TOKEN.agent_mode,
});

const ROLE_COLOR = { user: '#4f46e5', agent: '#10b981', claude: '#f59e0b' };
const styles = {
  row: { display: 'flex', gap: 12, alignItems: 'center', marginBottom: 12 },
  btn: (kind) => ({
    padding: '10px 18px', borderRadius: 8, border: 'none',
    background: kind === 'danger' ? '#ef4444' : '#4f46e5',
    color: 'white', fontWeight: 600, cursor: 'pointer',
  }),
  state: { color: '#666', fontFamily: 'monospace', fontSize: 13 },
  transcript: { height: 320, overflowY: 'auto', padding: 12, background: '#fafafa', borderRadius: 8, fontSize: 14, lineHeight: 1.5 },
  roleTag: (role) => ({
    color: ROLE_COLOR[role] || '#999', fontWeight: 600,
    fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.1em', marginRight: 6,
  }),
  err: { color: '#dc2626', fontSize: 13, marginTop: 6 },
};

function VoiceUI() {
  const { state, connect, disconnect, error } = useVocalBridge();
  const { transcript } = useTranscript();
  const [extra, setExtra] = useState([]);  // claude trace lines

  // The AI Agent hook: every spoken question arrives here. Whatever we
  // return is sent back to VB and spoken to the user.
  useAIAgent({
    onQuery: async (query) => {
      setExtra((prev) => [...prev, { role: 'app', text: 'POST /query → ' + query }]);
      try {
        // When routed through jupyter-server-proxy, the Jupyter server's
        // tornado layer requires an _xsrf token on POST. Forward it from
        // the page's cookie as X-XSRFToken; harmless locally.
        const headers = { 'Content-Type': 'application/json' };
        const xsrf = document.cookie.match(/(?:^|;\\s*)_xsrf=([^;]+)/);
        if (xsrf) headers['X-XSRFToken'] = decodeURIComponent(xsrf[1]);
        const res = await fetch(QUERY_URL, {
          method: 'POST',
          headers,
          credentials: 'same-origin',
          body: JSON.stringify({ query }),
        });
        const data = await res.json();
        setExtra((prev) => [...prev, { role: 'claude', text: data.response }]);
        return data.response;
      } catch (err) {
        setExtra((prev) => [...prev, { role: 'app', text: 'error: ' + err.message }]);
        return "Sorry — I couldn't reach my brain.";
      }
    },
  });

  const isDisconnected = state === ConnectionState.Disconnected;
  const busy = state === ConnectionState.Connecting || state === ConnectionState.WaitingForAgent;

  // Merge transcript and trace into one timeline.
  const lines = [
    ...transcript.map((t) => ({ ...t, _kind: 'transcript' })),
    ...extra.map((t) => ({ ...t, _kind: 'trace' })),
  ];

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
  return e(VocalBridgeProvider,
    { options: { auth: { tokenProvider }, debug: false } },
    e(VoiceUI),
  );
}

const container = document.getElementById('$root_id');
container.style.color = '#222';
container.innerHTML = '';
ReactDOM.createRoot(container).render(e(App));
</script>
""")


def voice_widget(token: TokenData, query_url: str, height: int = 480) -> str:
    """Widget variant for AI Agent mode.

    Uses `useAIAgent({ onQuery })` — every spoken turn calls onQuery,
    which POSTs to `query_url`/query and returns the text VB will speak.
    """
    return _WIDGET_TEMPLATE.substitute(
        root_id=f"vb-root-{int(time.time() * 1000)}",
        height=height,
        react_ver=REACT_VER,
        vb_react_ver=VB_REACT_VER,
        vb_sdk_ver=VB_SDK_VER,
        token_payload=json.dumps(token.as_dict()),
        query_url=json.dumps(query_url + "/query"),
    )
