# Plan — Vocal Bridge live-call test page (Phase 4)

Task groups are independently implementable in order. Reference files:
`backend/api/hello.py` (style), `jupyter_notebook/training_course/L2/helpers.py`
(`mint_token` lines 60–86, `_WIDGET_TEMPLATE` lines 127+).

## 1. Token endpoint

1.1 Create `backend/api/vb_test.py` with a new `APIRouter` named `vb_test`.
1.2 Add module constant `VB_API_URL = "https://vocalbridgeai.com"` (same as the
    lessons' helpers).
1.3 Implement `POST /token`: read `VOCAL_BRIDGE_API_KEY` and
    `VOCAL_BRIDGE_AGENT_ID` from env **inside the handler** (so tests can
    monkeypatch env without reimporting). If either is missing, return
    `JSONResponse(status_code=503, content={"error": "<VAR> not set"})`.
1.4 Call `requests.post(f"{VB_API_URL}/api/v1/token", headers={"X-API-Key": ...,
    "X-Agent-Id": ..., "Content-Type": "application/json"},
    json={"participant_name": "VB Test Page"}, timeout=15)` — mirroring
    `mint_token()` in `L2/helpers.py`.
1.5 On success, return the aliased shape: `connection_url` (falling back to
    `livekit_url`), `token`, `session_name` (from `room_name`), `agent_mode`
    (default `""`).
1.6 On upstream failure (non-2xx or `requests` exception), return a 502 JSON
    body with the upstream status and response text — never the API key, and
    never a bare stack trace.

## 2. Testing Vocal Bridge page

2.1 In the same router, implement `GET /` returning an inline-HTML
    `HTMLResponse` titled **Testing Vocal Bridge** — heading, one sentence
    ("Smoke test: live conversation against the Vocal Bridge API"), and the
    widget root div.
2.2 Port the L2 widget script, trimmed to the smoke test: esm.sh module imports
    of `react`, `react-dom`, `@vocalbridgeai/react`, `@vocalbridgeai/sdk`
    (pin the same versions the L2 template pins), `VocalBridgeProvider`,
    `useVocalBridge` (state/connect/disconnect/error), `useTranscript`.
2.3 Replace the L2 pre-minted-token pattern with a `tokenProvider` that
    `fetch`es `POST /v1/vb_test/token` and maps the response to the SDK
    contract (`url`, `token`, `room_name`, `participant_identity`,
    `expires_in`, `agent_mode`) — the same mapping the L2 template does from
    its inlined `TOKEN`.
2.4 UI: Connect/Disconnect button, connection-state line, scrolling transcript
    pane with role tags, error line (reuse the L2 template's minimal inline
    styles for these; drop the tic-tac-toe board, client actions, and
    everything else).
2.5 If `tokenProvider`'s fetch returns non-200, render the JSON error body in
    the error line so a missing env var is diagnosable from the page itself.

## 3. Route mounting & navigation

3.1 Mount the router in `backend/main.py`:
    `app.include_router(vb_test, prefix="/v1/vb_test", tags=["vb_test"])`.
3.2 Add a landing-page link in `hello.py`:
    `<li><a href="/v1/vb_test/">Testing Vocal Bridge (live-call smoke test)</a></li>`.

## 4. Tests

4.1 Create `backend/tests/test_vb_test.py` using the same FastAPI TestClient
    pattern as the existing tests. All tests hermetic — no real env vars, no
    network: mock `requests.post` at the `api.vb_test` module boundary.
4.2 Page test: `GET /v1/vb_test/` → 200, body contains "Testing Vocal Bridge"
    and the esm.sh `@vocalbridgeai/react` import.
4.3 Token success test: env vars set via monkeypatch, `requests.post` mocked to
    return a lesson-shaped payload (`livekit_url`/`token`/`room_name`) → 200
    with the aliased fields; assert the upstream call carried the
    `X-API-Key`/`X-Agent-Id` headers.
4.4 Missing-env tests: each var absent → 503 naming that variable.
4.5 Upstream-failure test: mocked non-2xx → 502, body includes upstream status,
    and the API key does not appear anywhere in the response.
4.6 Landing-page test: extend the existing hello landing-page assertions to
    include the new link.

## 5. Deploy pre-req (manual, documented)

5.1 Verify/provision the Vocal Bridge agent once (`vb agent create` per the L2
    notebook, or dashboard) and set `VOCAL_BRIDGE_AGENT_ID` on the
    `vocal-bridge-be-dev` Cloud Run service (env vars merge across deploys, so
    this is one-time). `VOCAL_BRIDGE_API_KEY` is already set.
5.2 Record the exact command used in the PR description so the team can
    reproduce it.
