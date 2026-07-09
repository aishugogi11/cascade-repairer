# Plan — Vocal Bridge web client integration (Phase 8)

Task groups are independently implementable in order; each leaves the repo green.
Reference implementation: `jupyter_notebook/training_course/L3/L3.ipynb` and its
`helpers.py`.

## 1. VB agent provisioning (AI Agent mode)

1. Author the web agent assets under `backend/api/assets/web_call/`:
   `prompt.md` (voice persona + the L3 bridge-line instruction: say "hang on —
   checking…" when delegating) and `ai-agent.json` (`enabled: true`, a
   `description` of what the backend agent is good at, `verbatim: false`).
2. Add `backend/devops/scripts/create_web_call_agent.sh`: runs
   `vb agent create --name vocal-bridge-web-call --prompt-file … --ai-agent-file …
   --background-enabled false --greeting "" --deploy-targets web --json` (the L3
   recipe verbatim) and prints the new agent id. Safe to re-run (creates a new
   agent; never mutates existing ones).
3. Document in the script header the one-time follow-up: set
   `VOCAL_BRIDGE_WEB_AGENT_ID=<id>` on the Cloud Run service with
   `gcloud run services update vocal-bridge-be-dev --update-env-vars …`
   (merge semantics — survives redeploys), and in local `.env` for dev.

## 2. Backend query path (`backend/api/web_call.py`)

1. Router skeleton `web_call = APIRouter()`; mount in `backend/main.py` at
   `prefix="/v1/web_call"`, `tags=["web_call"]`.
2. `POST /token` — copy the `vb_test.py` mint verbatim, reading
   `VOCAL_BRIDGE_API_KEY` + `VOCAL_BRIDGE_WEB_AGENT_ID` per request: 503 naming
   the missing var, 502 with upstream status/body on mint failure, alias
   transport fields to the neutral names (`connection_url`, `token`,
   `session_name`, `agent_mode`).
3. Backend agent module-level wiring (`hello.py` pattern): a plain
   `Agent(name=…, instructions=…)` — no tools yet — with the distinctive
   self-identification in its instructions. Keep an
   `async def answer_query(session_name: str, query: str) -> str` **plain
   function** (callable by tests, and the exact seam Phase 9 replaces): appends
   the user turn to an in-process per-session history dict, runs
   `Runner.run(...)` with that history, appends and returns the agent's reply.
4. `POST /query` — pydantic body (`query` non-blank via `field_validator`,
   `session_name` non-blank); 503 if `OPENAI_API_KEY` unset (the
   `cascade_demo.py` check); calls `answer_query`; returns `{"response": text}`;
   502 with a scrubbed message on agent failure.

## 3. Page (`GET /v1/web_call/`)

1. Start from the Phase 4 `_PAGE` template (`string.Template`, pinned esm.sh CDN
   versions, React 18): Connect/Disconnect button, connection state, transcript,
   token-error surfacing — token provider fetches `POST /v1/web_call/token`.
2. Add the L3 delta: `useAIAgent({ onQuery })` — on each delegated query, POST
   same-origin `/v1/web_call/query` with `{query, session_name}` (session name
   from the token response), return `data.response`; surface a query error in
   the page's error area and return a spoken fallback line so the call never
   dead-airs.

## 4. Turn logging (sessions/turns)

1. On a session's first query, insert a `sessions` row (session_id =
   `session_name`, architecture `concierge`, client `vb_web`, `started_at`);
   per query/response, insert `turns` rows (role user/agent, transcript,
   `ttfb_ms`/`duration_ms` from wall-clock around the Runner call) through the
   existing repositories.
2. All BigQuery writes via `asyncio.to_thread`, fired with
   `asyncio.create_task` off the response path (the `cascade_demo.py`
   `_log_converse_turns` pattern); failures are logged, never raised, and never
   delay the spoken reply.

## 5. Tests (`backend/tests/test_web_call.py`, hermetic)

1. Token endpoint: missing `VOCAL_BRIDGE_API_KEY` / `VOCAL_BRIDGE_WEB_AGENT_ID`
   → 503 naming the var; upstream 4xx/5xx → 502 with upstream detail; success →
   aliased field names (mock `requests.post`).
2. Query endpoint: blank `query` → 422; missing `OPENAI_API_KEY` → 503; mocked
   `Runner.run` → 200 `{"response": …}`; two calls with the same `session_name`
   → second `Runner.run` input contains the first exchange (memory); distinct
   `session_name`s don't share history; Runner exception → 502.
3. Page: `GET /v1/web_call/` returns 200 HTML containing `useAIAgent` and
   `/v1/web_call/query`.
4. Logging: with mocked repositories, one `sessions` row per session and
   user+agent `turns` rows per exchange; a repository exception does not fail
   the `/query` response.
