# Requirements — Vocal Bridge web client integration (Phase 8)

## What this phase proves

A live voice conversation in the **browser** works against the deployed Cloud Run
backend end-to-end — and the words the agent speaks are produced by **our backend
agent code**, not by a Vocal Bridge dashboard-configured prompt. This page becomes
the test surface for Phases 9–12.

The gap it closes: Phase 4's `/v1/vb_test/` page holds a live conversation, but the
agent answering is a VB platform agent (`VOCAL_BRIDGE_AGENT_ID`) — the backend only
mints the token. Phase 7's `/v1/outbound_call/call` proves the backend can drive a
*phone* call. Phase 8 is the browser equivalent: web client in, backend agent
answering.

## Mechanism (from the L3 course notebook — the reference, "to a tee")

`jupyter_notebook/training_course/L3/L3.ipynb` — "Voice for your Agent":

1. A VB agent is created in **AI Agent mode** (`ai-agent.json`, `--background-enabled
   false`, empty greeting, deploy target `web`). VB owns STT, TTS, turn-taking, and
   filler noises; it **delegates each spoken query** to our agent.
2. The browser widget uses the **`useAIAgent({ onQuery })`** React hook: every spoken
   question arrives as `query`; the widget POSTs it to our backend; whatever string
   comes back, VB speaks.
3. The backend exposes a plain HTTP endpoint that turns `query` text into `response`
   text — "in production this is just another route in your existing backend."

## Scope

### In scope

A new router `backend/api/web_call.py`, mounted at `/v1/web_call`:

| Surface | Method | Behaviour |
| --- | --- | --- |
| `/v1/web_call/` | GET | FastAPI-served static page (Phase 4 widget template + `useAIAgent` hook): Connect/Disconnect, connection state, transcript, visible errors |
| `/v1/web_call/token` | POST | Server-side token mint against the AI-Agent-mode VB agent (`VOCAL_BRIDGE_WEB_AGENT_ID`) — the `vb_test.py` pattern verbatim (per-request env, 503 naming the missing var, 502 with upstream detail, field aliasing) |
| `/v1/web_call/query` | POST | `{query, session_name}` → run the backend agent → `{response}`. **This is the seam Phase 9 replaces with the Concierge.** |

Plus:

- **Backend agent**: a plain OpenAI Agents SDK agent (`hello.py` pattern — no Sabre or
  repair tools yet) with **per-session multi-turn memory** keyed by `session_name`,
  held in process. Its instructions include a distinctive self-identification (e.g.
  it knows it is "the Cascade Repairer backend running on Cloud Run") so manual
  validation can prove answers come from our code, not a VB prompt.
- **One-time VB agent provisioning**: checked-in prompt + `ai-agent.json` assets and a
  script that runs `vb agent create` per the L3 recipe and prints the id; the id is
  set once on Cloud Run via `--update-env-vars` (merge semantics — survives deploys).
- **Turn logging**: a `sessions` row (client `vb_web`) and a `turns` row per
  query/response through the existing repositories — fire-and-forget, off the hot
  path, failures logged never raised.

### Out of scope

- The Concierge hybrid (fillers, bridge lines from a foreground agent, background
  repair tools) — Phase 9 swaps the `/query` seam.
- The live itinerary UI (Phase 10), evaluation harness (Phase 11).
- Agent picker, latency/debug readouts beyond connection state, interruption polish.
- Any change to the Phase 4 smoke-test page or its VB agent.

## Decisions

- **FastAPI-served static page** (user decision): same origin as the API — no CORS, no
  separate deploy, matching the Phase 4 page and the planned Phase 10 itinerary UI.
- **Browser-mediated delegation** (`useAIAgent` → same-origin POST) rather than any
  server-to-server integration: it is the course-verbatim L3 pattern, and the
  tech stack requires backend implementations to align with the notebooks "to a tee."
- **Talk to the existing deployed agent code** (user decision): a simple Agents SDK
  agent now; Concierge wiring waits for Phase 9. The `/query` endpoint is a thin seam
  so that swap is one function.
- **New env var `VOCAL_BRIDGE_WEB_AGENT_ID`**, a new VB agent: AI Agent mode and
  Background System are mutually exclusive in VB, so repurposing the Phase 4
  smoke-test agent would change its behaviour. The smoke test stays intact.
- **In-process session memory** — the standing Phase 5 rule: single Cloud Run
  instance, external session state out of scope for the hackathon.
- **`sessions.architecture = 'concierge'`** for rows this page writes: the L3
  delegation (VB foreground voice + backend reasoning) is the shape the Phase 9
  Concierge formalizes; keeping one value keeps one session lineage for the demo
  surface through Phase 11 evals.
- **Bridge-line prompting** (from L3): the VB agent prompt instructs a short spoken
  bridge line ("hang on — checking…") when a query is delegated, since a backend
  answer takes 1–6 s.

## Context

- **Patterns to follow**: `vb_test.py` (token mint, `string.Template` page,
  per-request env reads, pinned CDN versions); `cascade_demo.py` (`_log_converse_turns`
  for sessions/turns logging, 503 on missing `OPENAI_API_KEY`); `hello.py` (agent +
  plain-function-kept-callable-for-tests); helper tuple convention `(ok, payload,
  error)`; **BigQuery DML inside async paths goes through `asyncio.to_thread`**.
- **Tests stay hermetic**: no `OPENAI_API_KEY`, no GCP credentials — mock `Runner.run`
  and the repositories, monkeypatch env.
- **Tone**: page copy plain and functional, matching the Phase 4 page ("click Connect,
  allow the microphone, and say hello").
- **No new dependencies**: `@vocalbridgeai/react` CDN imports and the `vocal-bridge`
  Python package are already in use.
