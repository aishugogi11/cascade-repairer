# Validation — Vocal Bridge web client integration (Phase 8)

## Automated

From `backend/`: `python -m pytest` passes **hermetically** — no `OPENAI_API_KEY`, no
GCP credentials, no `vb` CLI, no network (same bar CI enforces inside the built
container). Specific assertions that must exist and pass:

- `POST /v1/web_call/token` returns 503 naming the missing var when
  `VOCAL_BRIDGE_API_KEY` or `VOCAL_BRIDGE_WEB_AGENT_ID` is unset; 502 carrying
  upstream status/body on a failed mint; 200 with `connection_url` / `token` /
  `session_name` aliasing on success.
- `POST /v1/web_call/query` returns 422 on a blank query, 503 without
  `OPENAI_API_KEY`, 200 `{"response": …}` with `Runner.run` mocked, 502 on a Runner
  exception.
- Multi-turn memory: a second query with the same `session_name` reaches
  `Runner.run` with the first exchange in its input; different `session_name`s are
  isolated.
- `GET /v1/web_call/` returns 200 HTML containing `useAIAgent` and
  `/v1/web_call/query`.
- Logging: mocked repositories receive one `sessions` row (architecture
  `concierge`, client `vb_web`) and user+agent `turns` rows per exchange; a
  repository failure does not change the `/query` response.
- No existing tests regress (the full suite, not just the new file).

## Manual (on the deployed service, after PR merge to `vb/dev` builds and deploys)

Prereqs once: run `create_web_call_agent.sh`, set `VOCAL_BRIDGE_WEB_AGENT_ID` on
`vocal-bridge-be-dev` via `--update-env-vars`.

1. **Walkthrough**: open `https://vocal-bridge-be-dev-….run.app/v1/web_call/`, click
   Connect, allow the microphone, say hello. A live two-way voice conversation
   happens; connection state and transcript update on the page.
2. **Prove the backend is answering**: ask "who are you, and where are you
   running?" — the spoken answer must include the distinctive self-identification
   from the backend agent's instructions (something no VB dashboard prompt knows).
3. **Multi-turn memory**: ask a question, then "what did I just ask you?" — the
   agent recalls it within the same session.
4. **Latency feel**: delegated answers land within a conversational pause (the L3
   1–6 s window), with the bridge line covering the wait. Note rough
   time-to-first-word; this page is the Phase 9–12 test surface, so record what
   "normal" feels like.
5. **Logging**: after the call, `sessions` has a `vb_web` row and `turns` has the
   exchange, with fresh timestamps, in the BigQuery console.
6. **Edge cases**: Disconnect and reconnect — a fresh session works (new
   `session_name`, no leaked history). With `VOCAL_BRIDGE_WEB_AGENT_ID` unset
   locally, the page surfaces the token-mint error text instead of failing
   silently. Kill the query path (e.g. unset `OPENAI_API_KEY` locally) — the call
   speaks the fallback line rather than dead-airing.
7. **Phase 4 untouched**: `/v1/vb_test/` still connects and converses as before.

## Tone check

Page copy is plain and functional, matching the Phase 4 page: says what the page
is for, tells the user to click Connect and allow the microphone, no marketing
voice.

## Definition of done

- A live voice conversation works in the browser against the Cloud Run instance
  end-to-end, with the spoken answers produced by the backend agent (manual steps
  1–2 pass live) — the roadmap Phase 8 acceptance.
- Automated suite green in CI inside the built container; deploy completed via the
  normal PR-to-`vb/dev` flow.
- `specs/roadmap.md` Phase 8 marked `[x] COMPLETE` (done by the implement step, not
  this spec).
