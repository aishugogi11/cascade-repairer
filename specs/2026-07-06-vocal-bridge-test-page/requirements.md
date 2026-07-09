# Requirements — Vocal Bridge live-call test page (Phase 4)

Promoted from `TODO.md` 2026-07-06, front of the roadmap per Josh. A **smoke test**
for the Vocal Bridge API itself — auth, call shape, latency — before any voice
architecture (Phases 7–9) is built on top of it. This is *not* the Phase 8 web
client integration; nothing here is demo polish.

## Scope

### In scope

A minimal "Testing Vocal Bridge" page served by the existing FastAPI backend,
modeled on the `hello.py` landing/test-page style, that makes a **real Vocal
Bridge call** the same way the training-course lessons do
(`jupyter_notebook/training_course/L2/helpers.py`):

| Piece | What it does |
|-------|--------------|
| `GET /v1/vb_test/` | Serves the **Testing Vocal Bridge** HTML page (inline HTML string, `HTMLResponse`, same pattern as `hello.py`'s landing page). |
| `POST /v1/vb_test/token` | Server-side token mint: `POST https://vocalbridgeai.com/api/v1/token` with `X-API-Key` + `X-Agent-Id` headers, returns the aliased fields the SDK expects (`connection_url`, `token`, `session_name`, `agent_mode`). The API key never reaches the browser. |
| Page widget | Browser voice widget built on `@vocalbridgeai/react` + `@vocalbridgeai/sdk` loaded from esm.sh (exact import pattern from the L2 widget template). Connect/disconnect button, connection state, live transcript pane. Nothing else. |
| Landing-page link | One `<li>` added to the `hello.py` landing page pointing at the new page. |

**Token endpoint response shape** (aliased exactly as `L2/helpers.py:mint_token`
does — the upstream API returns transport-level names):

| Field | Source |
|-------|--------|
| `connection_url` | `connection_url` or fallback `livekit_url` |
| `token` | `token` |
| `session_name` | `room_name` |
| `agent_mode` | `agent_mode` (default `""`) |

**Configuration** (both read from env at request time, never baked in):

| Env var | Where it lives |
|---------|----------------|
| `VOCAL_BRIDGE_API_KEY` | Already set on the Cloud Run service. |
| `VOCAL_BRIDGE_AGENT_ID` | Set once on Cloud Run (agent created via `vb agent create` or the dashboard — a documented manual pre-req, not code). |

If either var is missing, `POST /token` returns a clear 503-style JSON error
naming the missing variable (mirroring `gcp_check`'s "show which side broke and
why" philosophy) — it must not stack-trace.

### Out of scope

- Agent auto-provisioning (`vb agent create` from the backend) — the agent is
  pre-provisioned by hand.
- Conversation logging to `sessions`/`turns`, audio to GCS — that's Phase 7.
- Client actions, tools, tic-tac-toe-style app UI from the lessons — transcript
  and connect state only.
- Any concurrency work (Phase 5) or agent-layer wiring (OpenAI Agents SDK).
- Frontend build tooling, templates, static file mounts — inline HTML only.

## Decisions

- **Existing agent via env var** (Josh, 2026-07-06 interview): simplest path,
  matches the lessons' "pre-provisioned agent" branch
  (`VOCAL_BRIDGE_AGENT_ID_L2` pattern in L2). Backend exposes a small token
  endpoint; no auto-creation, no hardcoded ids.
- **Token minted server-side, fetched by the page's `tokenProvider`**: the L2
  widget pre-mints in Python and inlines the token; our page instead calls
  `POST /v1/vb_test/token` from the browser at connect time. Same trust
  boundary (key stays server-side), but the page works on a plain page-load
  with no per-request server templating.
- **New router module** `backend/api/vb_test.py` mounted at `/v1/vb_test` in
  `main.py` — keeps the smoke test out of `hello.py`, follows the existing
  one-router-per-concern mounting pattern.
- **`requests` for the upstream call** (already pinned in
  `backend/requirements.txt`; it's what the lessons use). No new dependencies.
- **Cloud Run is the primary target** (Josh): the page must work on the
  deployed `vocal-bridge-be-dev` URL where the API key already lives. Local
  works too if the two env vars are exported, but validation happens against
  Cloud Run.

## Context

- **Tone**: throwaway test-page plainness, exactly like `hello.py`'s landing
  page — a heading, a short sentence saying what it is, the widget. No styling
  beyond the minimal inline styles the L2 widget template already carries.
- **Patterns to follow**:
  - `backend/api/hello.py` — router style, inline `HTMLResponse` pages,
    error-reporting philosophy of `gcp_check`.
  - `jupyter_notebook/training_course/L2/helpers.py` — `mint_token()` (lines
    60–86) for the upstream call and field aliasing; `_WIDGET_TEMPLATE`
    (lines 127+) for the esm.sh imports, `tokenProvider` contract,
    `useVocalBridge`/`useTranscript` usage, and connect/disconnect UI.
- **Stack limits**: tests must stay hermetic (CI runs them inside the built
  container with no credentials) — the upstream Vocal Bridge call is mocked at
  the `requests` boundary; the live conversation is validated manually.
- **Reference alignment**: the mission requires backend implementations to
  align with the course notebooks "to a tee" — deviations from the L2 call
  shape need a comment explaining why.
