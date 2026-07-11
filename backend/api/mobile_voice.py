"""Headless mobile voice page — Phase 16, the iOS webview bridge (IOS_PLAN A2).

The web_call page's VB wiring with no visible DOM: the native SwiftUI app
loads this page in a hidden WKWebView, drives it with window.vbConnect() /
window.vbDisconnect() via evaluateJavaScript, and receives JSON events
through window.webkit.messageHandlers.vb.postMessage. All visible UI stays
native — this page is invisible plumbing.

The VB stack is identical to /v1/web_call/ (same pinned CDN versions,
imported from web_call so they can never drift apart; same server-minted
token via POST /v1/web_call/token; same useAIAgent delegation to
POST /v1/web_call/query, same-origin) — so the Concierge, session memory,
and turn logging behave exactly as the browser surface proved.

postNative guards every event: when window.webkit is absent (a desktop
browser), events console.log instead — the page stays smoke-testable
outside the app shell.
"""
from string import Template

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from api.web_call import REACT_VER, VB_REACT_VER

mobile_voice = APIRouter()

_PAGE = Template("""<html>
  <head><title>Mobile Voice Bridge</title></head>
  <body>
    <div id="vb-root" style="display:none"></div>
    <script type="module">
import React, { useEffect, useRef, useCallback, useMemo } from 'https://esm.sh/react@$react_ver';
import ReactDOM from 'https://esm.sh/react-dom@$react_ver/client';
import {
  VocalBridgeProvider, useVocalBridge, useTranscript, useAIAgent,
} from 'https://esm.sh/@vocalbridgeai/react@$vb_react_ver?deps=react@$react_ver,react-dom@$react_ver';

// Webview -> native. No-ops to the console when the webkit handler is
// absent (desktop browser) so the page is smoke-testable outside the app.
function postNative(msg) {
  if (window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.vb) {
    window.webkit.messageHandlers.vb.postMessage(msg);
  } else {
    console.log('[vb-event]', JSON.stringify(msg));
  }
}

// Access-code pass-through (Phase 17): the app loads this page as
// /v1/mobile_voice/?code=… so the token/query fetches carry the gate
// header; localStorage keeps a reload inside the webview working.
const codeFromUrl = new URL(window.location).searchParams.get('code');
if (codeFromUrl) localStorage.setItem('vb_access_code', codeFromUrl);
const ACCESS_CODE = codeFromUrl || localStorage.getItem('vb_access_code') || '';
function codeHeaders(extra) {
  const headers = Object.assign({}, extra);
  if (ACCESS_CODE) headers['X-Access-Code'] = ACCESS_CODE;
  return headers;
}

const e = React.createElement;

function Bridge({ sessionRef }) {
  const { state, connect, disconnect, error } = useVocalBridge();
  const { transcript } = useTranscript();
  const sentLines = useRef(0);

  // Native -> webview controls, live once the SDK is mounted.
  useEffect(() => {
    window.vbConnect = () => { connect(); };
    window.vbDisconnect = () => { disconnect(); };
    return () => { delete window.vbConnect; delete window.vbDisconnect; };
  }, [connect, disconnect]);

  useEffect(() => { postNative({ type: 'state', value: String(state) }); }, [state]);

  useEffect(() => {
    if (error) postNative({ type: 'error', message: String(error.message || error) });
  }, [error]);

  useEffect(() => {
    for (let i = sentLines.current; i < transcript.length; i++) {
      postNative({ type: 'transcript', role: transcript[i].role, text: transcript[i].text });
    }
    sentLines.current = transcript.length;
  }, [transcript]);

  // The L3 delegation, unchanged from web_call: VB speaks whatever string
  // this returns; the reply event lets native react (e.g. re-poll trips).
  useAIAgent({
    onQuery: async (query) => {
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
        postNative({ type: 'reply', text: data.response });
        return data.response;
      } catch (err) {
        postNative({ type: 'error', message: 'query failed: ' + err.message });
        return "Sorry — I couldn't reach my backend brain. Try that again in a moment.";
      }
    },
  });

  return null;  // headless: nothing to render
}

function App() {
  const sessionRef = useRef(null);

  const tokenProvider = useCallback(async () => {
    const res = await fetch('/v1/web_call/token', { method: 'POST', headers: codeHeaders() });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const msg = 'token mint failed (HTTP ' + res.status + '): ' + JSON.stringify(data);
      postNative({ type: 'error', message: msg });
      throw new Error(msg);
    }
    sessionRef.current = data.session_name;
    return {
      url: data.connection_url,
      token: data.token,
      room_name: data.session_name,
      participant_identity: 'mobile-voice-bridge',
      expires_in: 3600,
      agent_mode: data.agent_mode,
    };
  }, []);

  const options = useMemo(() => ({ auth: { tokenProvider }, debug: false }), [tokenProvider]);

  return e(VocalBridgeProvider, { options }, e(Bridge, { sessionRef }));
}

ReactDOM.createRoot(document.getElementById('vb-root')).render(e(App));
    </script>
  </body>
</html>""").substitute(
    react_ver=REACT_VER,
    vb_react_ver=VB_REACT_VER,
)


@mobile_voice.get("/", response_class=HTMLResponse)
def mobile_voice_page():
    return _PAGE
