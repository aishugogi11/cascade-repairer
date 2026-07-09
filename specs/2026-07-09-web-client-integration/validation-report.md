# Validation Report - Vocal Bridge web client integration
**Branch:** vb/feature/web-client-integration    **Commit:** b27f7a428b29f221d15b9fd5243fa4969f7c1a90    **Date:** 2026-07-09

## Summary
Partial pass. The automated validation criteria pass in the backend container (`182 passed, 4 skipped`), and the implementation evidence matches the token, query, memory, page, and logging contracts. The deployed live Vocal Bridge walkthrough criteria remain UNTESTABLE from this branch state because the feature is not merged/deployed to `vb/dev` and no live browser/microphone/BigQuery walkthrough was run.

## Criterion-by-criterion results
- **Criterion:** Full hermetic backend suite passes from `backend/`, with no network, GCP credentials, OpenAI key, or `vb` CLI.
- **Status:** PASS
- **Evidence:** Ran `docker compose build backend` successfully, then `docker run --rm hackathon-vocal-bridge-backend python -m pytest tests/ -v`: `182 passed, 4 skipped, 6 warnings in 3.07s`.
- **Notes:** Local `backend/venv/bin/python -m pytest` was unavailable, `python` was not on PATH, and `python3 -m pytest` lacked pytest; containerized test run matches README/CI shape.

- **Criterion:** `POST /v1/web_call/token` handles missing env, upstream failure, and success aliasing.
- **Status:** PASS
- **Evidence:** Implementation reads `VOCAL_BRIDGE_API_KEY` and `VOCAL_BRIDGE_WEB_AGENT_ID` per request and returns 503 for either missing var, 502 with upstream status/body for failed mint, and `connection_url` / `token` / `session_name` on success in `backend/api/web_call.py:76`. Tests cover these paths in `backend/tests/test_web_call.py:92`, `backend/tests/test_web_call.py:100`, `backend/tests/test_web_call.py:108`, and `backend/tests/test_web_call.py:123`.
- **Notes:** Success path uses `X-Agent-Id: VOCAL_BRIDGE_WEB_AGENT_ID`, keeping the Phase 4 agent separate.

- **Criterion:** `POST /v1/web_call/query` returns 422 on blank query, 503 without `OPENAI_API_KEY`, 200 `{"response": ...}` with `Runner.run` mocked, and 502 on Runner exception.
- **Status:** PASS
- **Evidence:** Pydantic validator rejects blank query/session values in `backend/api/web_call.py:188`; missing OpenAI key and Runner exception handling are in `backend/api/web_call.py:206`. Tests cover the required responses in `backend/tests/test_web_call.py:154`, `backend/tests/test_web_call.py:162`, `backend/tests/test_web_call.py:170`, and `backend/tests/test_web_call.py:180`.
- **Notes:** The endpoint is mounted at `/v1/web_call/query` in `backend/main.py:68`.

- **Criterion:** Multi-turn memory replays prior exchange for the same `session_name`, while different sessions are isolated.
- **Status:** PASS
- **Evidence:** `answer_query` stores Agents SDK input history by `session_name` in `backend/api/web_call.py:128`. Tests assert second-turn replay and cross-session isolation in `backend/tests/test_web_call.py:197` and `backend/tests/test_web_call.py:219`.
- **Notes:** Memory is intentionally in-process, matching the project constitution's single-instance hackathon scope.

- **Criterion:** `GET /v1/web_call/` returns HTML containing `useAIAgent` and `/v1/web_call/query`.
- **Status:** PASS
- **Evidence:** The page template imports `useAIAgent` and posts delegated questions to `/v1/web_call/query` in `backend/api/web_call.py:235`; route returns the template in `backend/api/web_call.py:379`. Test `backend/tests/test_web_call.py:308` verifies 200 HTML plus `useAIAgent`, `/v1/web_call/query`, and `/v1/web_call/token`.
- **Notes:** The page also surfaces token and query errors and returns a spoken fallback string on query failure in `backend/api/web_call.py:295`.

- **Criterion:** Logging writes one `sessions` row (`architecture="concierge"`, `client="vb_web"`) and user+agent `turns` rows per exchange; repository failure does not change `/query` response.
- **Status:** PASS
- **Evidence:** Logging builds the session and turn models in `backend/api/web_call.py:150` and runs repository calls through `asyncio.to_thread`. Tests verify one session row, two turns per exchange, swallowed repository exceptions, and query response survival in `backend/tests/test_web_call.py:238`, `backend/tests/test_web_call.py:263`, and `backend/tests/test_web_call.py:270`.
- **Notes:** Logging is fire-and-forget from the query path at `backend/api/web_call.py:219`, with test coverage in `backend/tests/test_web_call.py:280`.

- **Criterion:** Manual deployed walkthrough: open Cloud Run `/v1/web_call/`, connect microphone, live two-way voice conversation works, backend self-identifies, memory works, latency is conversational, BigQuery logging appears, reconnect is isolated, token/query errors surface, and `/v1/vb_test/` still works.
- **Status:** UNTESTABLE
- **Evidence:** Validation requires the deployed service after PR merge to `vb/dev`; current worktree is still on `vb/feature/web-client-integration` with uncommitted feature files. No live Cloud Run browser session, microphone test, Vocal Bridge connection, or BigQuery console inspection was run.
- **Notes:** Local code and automated tests support the expected behavior, but this criterion is explicitly live/manual and cannot be marked PASS from static inspection.

- **Criterion:** Tone check: page copy is plain and functional, matching the Phase 4 page and avoiding marketing voice.
- **Status:** PASS
- **Evidence:** Page text at `backend/api/web_call.py:238` says what the page is for and tells the user to click Connect, allow the microphone, and say hello. Test coverage verifies the page is served in `backend/tests/test_web_call.py:308`.
- **Notes:** Static validation only; no visual/browser rendering was performed.

- **Criterion:** Definition of done: live browser conversation against Cloud Run, CI green inside built container, deployed via normal PR-to-`vb/dev` flow, and roadmap Phase 8 marked complete.
- **Status:** UNTESTABLE
- **Evidence:** Containerized local suite is green, and `specs/roadmap.md` in the current worktree marks Phase 8 complete. The live Cloud Run conversation, PR merge, Cloud Build CI run, and deployment were not observable from this unmerged branch validation.
- **Notes:** Treat this as blocked on post-merge manual QA, not an implementation failure.

## Missing tests
- `backend/tests/test_web_call.py::test_page_query_failure_returns_spoken_fallback`: assert the served HTML includes the fallback response returned from `useAIAgent` when `/v1/web_call/query` fails, covering the manual "fallback line rather than dead air" edge case.
- `backend/tests/test_web_call.py::test_web_agent_prompt_delegates_identity_questions`: load `backend/api/assets/web_call/prompt.md` and assert identity questions are explicitly delegated to the backend, strengthening the manual proof that self-identification comes from backend code.
- A post-deploy smoke check is still manual by design: browser microphone, real Vocal Bridge media, and BigQuery console verification are not hermetic pytest targets. If automated later, put it outside the hermetic suite, e.g. `backend/promotion_scripts/smoke_web_call.py`, gated by live env vars.

## Gaps in validation.md
- Should the deployed manual walkthrough be allowed to pass on a locally built branch before PR merge, or is post-merge Cloud Run validation strictly required?
- Should the fallback spoken line on `/query` failure be part of the automated criteria, since the manual edge case depends on client-side JavaScript rather than the backend JSON endpoint?
- Should the validation require checking `VOCAL_BRIDGE_WEB_AGENT_ID` is documented in `backend/.env.example` or Cloud Run env setup, or is the provisioning script sufficient?

## Risks not covered by validation.md
- `_LOGGED_SESSIONS` records a session as attempted before `create_session` succeeds. A transient session insert failure means later turns for that session will not retry the session row, though turn inserts can still run.
- The page concatenates Vocal Bridge transcript lines and backend trace lines without timestamp ordering; in a live call, the visual transcript may not reflect exact conversation order.
