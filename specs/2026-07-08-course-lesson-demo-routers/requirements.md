# Requirements — Course lesson demo routers (L2/L3/L4 ports)

Phase 7 of the roadmap: port the cascaded STT → LLM → TTS pipeline (L2/L3) and the
"Voice as a Tool" outbound-call pattern (L4) from `jupyter_notebook/training_course/`
into the backend as API-driven reference implementations, each with its own FastAPI
router, Swagger-visible tag, and landing-page link.

## Scope

### Lesson → route mapping (the demo story)

Every endpoint carries its lesson label in its Swagger `summary` (e.g. `[L3] …`) so the
team can walk `/docs` lesson by lesson:

| Lesson | What the lesson teaches | Demo route(s) |
|---|---|---|
| **L2 — Voice in your App** | Token minting + managed web widget | `/v1/vb_test/` — already ported in Phase 4; the landing page labels it as the L2 demo. Nothing new to build. |
| **L2/L3 — cascaded architecture** | The STT → LLM → TTS pipeline as individually inspectable stages | `/v1/cascade_demo/stt`, `/llm`, `/tts`, and `/converse` (full chain) |
| **L3 — Voice for your Agent** | The query-server pattern: a spoken turn arrives as text, your agent returns text to speak | `/v1/cascade_demo/llm` — this endpoint *is* the L3 `/query` handler shape (OpenAI agent instead of Claude) |
| **L4 — Voice as a Tool** | An LLM-visible tool places a real outbound phone call with an injected purpose | `/v1/outbound_call/call`, `/status`, `/recording/{session_id}` + the `make_phone_call` function_tool |

### In scope

**Cascade demo router** — `api/cascade_demo.py`, registered at `/v1/cascade_demo`, tag `cascade_demo`:

| Endpoint | Method | In | Out |
|---|---|---|---|
| `/stt` | POST | audio file upload (wav/mp3/webm) | JSON `{transcript}` |
| `/llm` | POST | JSON `{text, session_id?}` | JSON `{reply}` |
| `/tts` | POST | JSON `{text}` | audio response (mp3) |
| `/converse` | POST | audio file upload + optional `session_id` | audio reply (mp3) + `X-Session-Id` / `X-Transcript` metadata |

- Per-stage endpoints exist so each lesson concept is demoable on its own in Swagger;
  `/converse` chains all three stages and is the L2/L3 reference implementation.
- `/converse` logs conversation turns to `sessions`/`turns` (architecture `cascaded`)
  and uploads both user and agent audio to GCS at `audio/<session_id>/<turn_id>.wav`
  per the existing `turns.audio_uri_for()` convention. Passing `session_id` continues
  an existing session (multi-turn); omitting it creates one.

**Outbound-call router (L4)** — `api/outbound_call.py`, registered at `/v1/outbound_call`, tag `outbound_call`:

| Endpoint | Method | In | Out |
|---|---|---|---|
| `/call` | POST | JSON `{purpose, name?}` | JSON `{call_id, status}` (sanitized — no transport fields) |
| `/status` | GET | query `session_id?` (default: latest session) | JSON: session metadata, transcript lines, recording availability |
| `/recording/{session_id}` | GET | path param | JSON `{gcs_uri}` after downloading the mp3 via `vb logs download` and uploading to GCS |

- `POST /call` ports `place_call()` from `L4/helpers.py`: inject the per-call purpose
  into the caller agent's prompt (`vb prompt set`), place the call to the configured
  callee (`vb call <VOCAL_BRIDGE_CALLEE_PHONE> --json`), return only `{call_id, status}`.
- An OpenAI Agents SDK `function_tool` named `make_phone_call(purpose, name?)` wraps the
  same core function, so later phases (Concierge, dress-rehearsal opening beat) can hand
  the tool to an agent. Phase 7 ships the tool definition and a unit test for it; wiring
  it into a live agent conversation is Phase 9 work.

**Shared plumbing**

- Landing page (`hello.py` `GET /v1/hello/`) gains links to both routers' demo surfaces
  (Swagger tag anchors are sufficient; the cascade has no HTML page in this phase).
- A thin `vb` CLI wrapper module in the backend (subprocess + `--json` parsing, ported
  from `L4/helpers.py` `vb()`), so router code never shells out directly.

### Out of scope

- The Vocal Bridge web client / WebRTC integration (Phase 8) — the cascade demo is
  Swagger/HTTP-driven only in this phase.
- Wiring `make_phone_call` into a live voice conversation (Phase 9 Concierge).
- Real-time voice-to-voice architecture (stretch).
- Any HTML demo page beyond landing-page links.
- Caller/callee agent *provisioning* (`vb agent create`, outbound TOS acceptance) — done
  once manually per the L4 notebook; the backend assumes a provisioned caller agent id.

## Decisions

1. **LLM = OpenAI Agents SDK, not Anthropic.** The notebooks use `claude-sonnet-4-6`,
   but the mission explicitly standardizes the agent layer on the OpenAI Agents SDK
   (non-goal: "Using Anthropic/Claude as the agent LLM"). The `/llm` stage and the
   `/converse` cascade run a plain `await Runner.run(...)` per the `hello.py` /
   `concurrency_core.py` pattern.
2. **STT/TTS = OpenAI audio APIs.** The L2/L3 notebooks never call STT/TTS SDKs — the
   Vocal Bridge platform manages transport. To make the *cascaded architecture* a
   working, individually-demoable reference (the point of the lesson), the stage
   endpoints use the OpenAI `audio.transcriptions` (STT) and `audio.speech` (TTS) APIs:
   the `openai` package is already a backend dependency (pulled in by `openai-agents`)
   and `OPENAI_API_KEY` is already set on Cloud Run. No new vendor.
3. **L4 transport = `vb` CLI via subprocess**, exactly as the notebook does it
   (`vb prompt set`, `vb call --json`, `vb logs list/download`). This requires adding
   `vocal-bridge>=0.16` to `backend/requirements.txt` — it comes from the course
   notebooks' own requirements, so it stays within the course stack, but it is the one
   dependency addition in this phase (approved via this spec). REST calls via `requests`
   remain the fallback if the CLI misbehaves in the container; the wrapper module keeps
   that swap localized.
4. **Two-endpoint place + status** for L4 (user decision): `POST /call` returns
   immediately with `{call_id, status}`; `GET /status` polls. No blocking endpoint —
   a phone call can run minutes and would tie up the request.
5. **Sanitized call results** (ported invariant from the notebook): whatever the tool or
   `/call` returns to an LLM or API client contains only `call_id` and `status` — never
   raw transport fields, credentials, or the callee phone number.
6. **All call configuration from env, none in code** (roadmap requirement):
   `VOCAL_BRIDGE_API_KEY` (already on Cloud Run), `VOCAL_BRIDGE_CALLER_AGENT_ID`,
   `VOCAL_BRIDGE_OUTBOUND_GREETING` (default provided), `VOCAL_BRIDGE_CALLEE_PHONE`
   (the verified demo cell phone — set in `.env` locally and via `--update-env-vars`
   on Cloud Run; never hardcoded in source or specs). Env is read per-request like
   `vb_test.py`, so a missing var yields a clean 503, not an import-time crash.
7. **BigQuery writes stay off the event loop**: session/turn DML inside async handlers
   goes through `asyncio.to_thread` (standing rule from the Phase 5 spike).

## Context

- **Router conventions**: `APIRouter()` at module top, registered in `main.py` with
  `app.include_router(x, prefix="/v1/<name>", tags=["<name>"])` — follow the five
  existing routers. Secrets read per-request from `os.environ` (see `vb_test.py:37`).
- **Persistence**: use the typed repositories (`api/repositories/sessions.py`,
  `turns.py`) and the `gcs_helper` singleton — never raw SQL or raw storage clients in
  router code. DML only, never streaming inserts.
- **Reference sources**: `jupyter_notebook/training_course/L2/helpers.py` (token/widget),
  `L3/helpers.py` (query-server turn loop), `L4/helpers.py` + `L4.ipynb` cells 10–15
  (tool schema, `place_call`, `set_caller_purpose`, `latest_session`,
  `download_recording`). Backend implementations must align with these "to a tee",
  modulo the LLM-provider decision above.
- **Tone**: landing-page copy is plain and functional, matching the existing page —
  short link text, no marketing language.
- **Tests are hermetic**: no GCP credentials, no `OPENAI_API_KEY`, no network, no real
  `vb` binary — mock at the wrapper/helper boundary (`monkeypatch`), following
  `tests/test_vb_test.py`.
- **Deadline pressure**: hackathon is July 18; this phase feeds Phases 9 (Concierge) and
  12 (demo opening beat — "the traveler receives a call"). Keep the surface minimal and
  the core functions importable by later phases.
