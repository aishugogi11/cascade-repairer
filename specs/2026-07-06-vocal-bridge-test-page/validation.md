# Validation — Vocal Bridge live-call test page (Phase 4)

## Automated

Run from `backend/` (same as CI runs inside the built container — hermetic, no
credentials, no network):

- `pytest` passes, including the new `tests/test_vb_test.py`.
- Specific assertions that must exist and pass:
  - `GET /v1/vb_test/` returns 200 HTML containing **"Testing Vocal Bridge"**
    and the esm.sh `@vocalbridgeai/react` import.
  - `POST /v1/vb_test/token` with both env vars set and a mocked upstream
    returns 200 with `connection_url`, `token`, `session_name`, `agent_mode`;
    the mocked call received `X-API-Key` and `X-Agent-Id` headers and the
    lessons' URL (`https://vocalbridgeai.com/api/v1/token`).
  - Missing `VOCAL_BRIDGE_API_KEY` → 503 naming it; missing
    `VOCAL_BRIDGE_AGENT_ID` → 503 naming it.
  - Mocked upstream non-2xx → 502; the API key value appears nowhere in the
    response body.
  - `GET /v1/hello/` landing page contains the `/v1/vb_test/` link.
- No new entries in `requirements.txt` (uses the pinned `requests`).

## Manual (against the deployed Cloud Run service — the primary target)

1. Merge PR → Cloud Build trigger runs → deploy succeeds (pytest-in-container
   step green).
2. One-time pre-req confirmed: `VOCAL_BRIDGE_AGENT_ID` set on
   `vocal-bridge-be-dev` (`gcloud run services describe vocal-bridge-be-dev
   --region us-west1` shows both `VOCAL_BRIDGE_*` vars).
3. Open `https://<cloud-run-url>/v1/vb_test/` in Chrome:
   - Page renders with the Testing Vocal Bridge heading and a Connect button.
   - Click **Connect** → browser prompts for mic → connection state reaches
     connected.
   - **Have a very simple live conversation**: say hello, get a spoken reply,
     see both sides appear in the transcript pane. This is the acceptance
     moment for the phase.
   - Click **Disconnect** → state returns to disconnected; reconnect works.
4. Edge cases:
   - `POST /v1/vb_test/token` via `/docs` returns a real token payload (no key
     leaked in the response).
   - Temporarily unset scenario (verified locally, not on Cloud Run): with a
     var missing, the page's Connect surfaces the 503 error text instead of
     hanging.
   - Reload mid-conversation → page returns to idle cleanly (no stuck session
     UI).
5. Latency sanity note (this phase exists to de-risk it): roughly how long
   from Connect click to connected, and from end-of-utterance to first spoken
   reply. No hard threshold — record observations in the PR for the voice
   phases.

## Tone check

Page copy is plain and functional, matching `hello.py`: a heading, one sentence
of purpose, no marketing language, no styling beyond the widget's minimal
inline styles.

## Definition of done

- All automated assertions above pass locally and in the Cloud Build
  pytest-in-container step.
- A live voice conversation (connect → speak → hear reply → transcript →
  disconnect) works on the deployed Cloud Run URL.
- Landing page links to the new page.
- Roadmap Phase 4 marked `[x] COMPLETE`; latency observations recorded in the
  PR.
