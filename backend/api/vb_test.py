"""Testing Vocal Bridge — Phase 4 smoke-test page.

Proves the backend can make a real Vocal Bridge call (auth, call shape,
latency) before any voice architecture is built on top. The call pattern
mirrors the training-course lessons to a tee
(jupyter_notebook/training_course/L2/helpers.py): the token is minted
server-side with the API key, and the browser widget consumes it through a
tokenProvider so the key never reaches the browser. One deliberate deviation
from L2: the notebook pre-mints the token in Python and inlines it into the
widget; this page fetches POST /v1/vb_test/token at connect time instead, so
a plain page-load needs no per-request templating — the trust boundary is
the same.
"""
import os
from string import Template

import requests
from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

vb_test = APIRouter()

VB_API_URL = "https://vocalbridgeai.com"

# Pinned versions for CDN imports, matching the L2 lesson widget. Bump when
# newer VB SDKs ship.
VB_REACT_VER = "0.1.1"
VB_SDK_VER = "0.1.1"
REACT_VER = "18"


@vb_test.post("/token")
def mint_token():
    # Env is read per-request (not at import) so vars set on the Cloud Run
    # service — or monkeypatched in tests — apply without a reload. Missing
    # config reports which var broke, mirroring gcp_check's philosophy.
    api_key = os.environ.get("VOCAL_BRIDGE_API_KEY", "").strip()
    agent_id = os.environ.get("VOCAL_BRIDGE_AGENT_ID", "").strip()
    if not api_key:
        return JSONResponse(status_code=503,
                            content={"error": "VOCAL_BRIDGE_API_KEY not set"})
    if not agent_id:
        return JSONResponse(status_code=503,
                            content={"error": "VOCAL_BRIDGE_AGENT_ID not set"})

    try:
        res = requests.post(
            f"{VB_API_URL}/api/v1/token",
            headers={
                "X-API-Key": api_key,
                "X-Agent-Id": agent_id,
                "Content-Type": "application/json",
            },
            json={"participant_name": "VB Test Page"},
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
    # transport-agnostic names the SDK exposes (same mapping as L2 helpers).
    return {
        "connection_url": data.get("connection_url") or data["livekit_url"],
        "token": data["token"],
        "session_name": data["room_name"],
        "agent_mode": data.get("agent_mode", ""),
    }


# The widget is the L2 lesson template trimmed to the smoke test: connect /
# disconnect, connection state, transcript. No client actions, no app UI.
_PAGE = Template("""<html>
  <head><title>Testing Vocal Bridge</title></head>
  <body style="font-family: -apple-system, system-ui, sans-serif; max-width: 720px; margin: 24px auto; padding: 0 16px;">
    <h1>Testing Vocal Bridge</h1>
    <p>Smoke test: live conversation against the Vocal Bridge API. Click Connect, allow the microphone, and say hello.</p>
    <div id="vb-root" style="min-height: 320px; padding: 16px; border: 1px solid #ddd; border-radius: 12px; color: #888;">loading Vocal Bridge React SDK&hellip;</div>
    <p><a href="/v1/hello/">Back to API home</a></p>
    <script type="module">
import React, { useState, useCallback, useMemo } from 'https://esm.sh/react@$react_ver';
import ReactDOM from 'https://esm.sh/react-dom@$react_ver/client';
import {
  VocalBridgeProvider, useVocalBridge, useTranscript,
} from 'https://esm.sh/@vocalbridgeai/react@$vb_react_ver?deps=react@$react_ver,react-dom@$react_ver';
import { ConnectionState } from 'https://esm.sh/@vocalbridgeai/sdk@$vb_sdk_ver';

const e = React.createElement;

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
    color: role === 'user' ? '#4f46e5' : '#10b981', fontWeight: 600,
    fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.1em', marginRight: 6,
  }),
  err: { color: '#dc2626', fontSize: 13, marginTop: 6 },
};

function VoiceUI({ tokenError }) {
  const { state, connect, disconnect, error } = useVocalBridge();
  const { transcript } = useTranscript();

  const isDisconnected = state === ConnectionState.Disconnected;
  const busy = state === ConnectionState.Connecting || state === ConnectionState.WaitingForAgent;

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
    e('div', { style: styles.transcript },
      transcript.length === 0
        ? e('div', { style: { color: '#aaa', fontStyle: 'italic' } }, 'transcript will appear here…')
        : transcript.map((t, i) => e('div', { key: i },
            e('span', { style: styles.roleTag(t.role) }, t.role),
            t.text,
          ))
    ),
  );
}

function App() {
  const [tokenError, setTokenError] = useState(null);

  // Token is minted server-side; a failed mint surfaces its JSON body here
  // so a missing env var is diagnosable from the page itself.
  const tokenProvider = useCallback(async () => {
    setTokenError(null);
    const res = await fetch('/v1/vb_test/token', { method: 'POST' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = 'token mint failed (HTTP ' + res.status + '): ' + JSON.stringify(data);
      setTokenError(msg);
      throw new Error(msg);
    }
    return {
      url: data.connection_url,
      token: data.token,
      room_name: data.session_name,
      participant_identity: 'vb-test-page',
      expires_in: 3600,
      agent_mode: data.agent_mode,
    };
  }, []);

  const options = useMemo(() => ({ auth: { tokenProvider }, debug: false }), [tokenProvider]);

  return e(VocalBridgeProvider, { options },
    e(VoiceUI, { tokenError }),
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


@vb_test.get("/", response_class=HTMLResponse)
def testing_vocal_bridge_page():
    return _PAGE
