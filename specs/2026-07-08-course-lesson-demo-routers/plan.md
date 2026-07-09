# Plan — Course lesson demo routers (L2/L3/L4 ports)

Task groups are independently implementable in roughly this order; groups 2–3 (L4) and
groups 4–5 (cascade) are parallelizable.

## 1. Config & dependencies

1. Add `vocal-bridge>=0.16` to `backend/requirements.txt` (the `vb` CLI, from the
   course notebooks' requirements).
2. Document the new env vars in `.env.example` (or the repo's equivalent):
   `VOCAL_BRIDGE_CALLER_AGENT_ID`, `VOCAL_BRIDGE_OUTBOUND_GREETING` (optional,
   has default), `VOCAL_BRIDGE_CALLEE_PHONE`. `VOCAL_BRIDGE_API_KEY` and
   `OPENAI_API_KEY` already exist.
3. Verify the Docker image build still succeeds with the new dependency (`make build`).

## 2. Vocal Bridge CLI wrapper — `api/vb_cli.py`

1. Port `vb()` from `L4/helpers.py`: run `vb <args> --json` via `subprocess.run`,
   parse JSON after the `--- JSON ---` marker, return `(success, payload, error)`
   in the helper-tuple style used by `bigquery_helper`/`gcs_helper`.
2. Port `set_caller_purpose(purpose)`: load the caller prompt base (store
   `agents/tool-caller/prompt_base.md` content as a backend asset under
   `backend/api/assets/` or inline constant), append the "CONTEXT FOR THIS CALL /
   PURPOSE" block, write to a temp file, push with `vb prompt set -f <file>`
   targeting `VOCAL_BRIDGE_CALLER_AGENT_ID`.
3. Port `place_call(purpose, name?)`: assert `VOCAL_BRIDGE_CALLEE_PHONE`, set purpose,
   `vb call <callee> --json [--name <name>]`, return sanitized `{call_id, status}`.
4. Port `latest_session(status?)` (`vb logs list -n 1 --json`) and
   `download_recording(session_id, out_path)` (`vb logs download`).
5. All functions read env per-call; no import-time env access, no module-level CLI runs.

## 3. Outbound-call router — `api/outbound_call.py`

1. `POST /call`: body `{purpose: str, name: str | None}` → `place_call` in
   `asyncio.to_thread` → 200 `{call_id, status}`; 503 if required env missing,
   502 if the CLI fails.
2. `GET /status`: optional `session_id` query param (default: latest completed/any
   session via `latest_session`) → session metadata + transcript/debug lines +
   whether a recording exists. Sanitize: no API key, no callee number.
3. `GET /recording/{session_id}`: download the mp3 to a temp path, upload via
   `gcs_helper.upload_file` to `audio/outbound/<session_id>.mp3`, return `{gcs_uri}`.
4. Define the OpenAI Agents SDK `function_tool` `make_phone_call(purpose, name?)`
   in the same module (pattern: `api/repair_tools.py`), delegating to `place_call`
   and returning the sanitized dict.
5. Register the router in `main.py`: prefix `/v1/outbound_call`, tag `outbound_call`.

## 4. Cascade pipeline core — `api/cascade_core.py`

1. `transcribe(audio_bytes, filename) -> str` via OpenAI `audio.transcriptions`
   (client created lazily per the existing helper style).
2. `agent_reply(text, history?) -> str` via OpenAI Agents SDK `Runner.run` with a
   minimal travel-assistant agent (pattern: `hello.py`).
3. `synthesize(text) -> bytes` (mp3) via OpenAI `audio.speech`.
4. Model names for STT/TTS/LLM come from module constants overridable by env —
   no hardcoded scatter.

## 5. Cascade demo router — `api/cascade_demo.py`

1. `POST /stt` (UploadFile) → `{transcript}`.
2. `POST /llm` (`{text, session_id?}`) → `{reply}`.
3. `POST /tts` (`{text}`) → `Response(content=mp3, media_type="audio/mpeg")`.
4. `POST /converse` (UploadFile + optional `session_id` form field):
   - create session row if no `session_id` (architecture `cascaded`, client `api_demo`)
     via `repositories.sessions` in `asyncio.to_thread`;
   - STT → LLM → TTS; measure per-stage timings for `ttfb_ms`/`duration_ms`;
   - write a user turn (transcript + uploaded audio to GCS at
     `turns.audio_uri_for(session_id, turn_id)`) and an agent turn (reply text +
     synthesized mp3 to GCS), DML via `asyncio.to_thread`;
   - return the mp3 with `X-Session-Id` and `X-Transcript` headers.
   - GCS/BigQuery failures log a warning and degrade gracefully (the audio reply
     still returns) — demo endpoints must not 500 on logging problems.
5. Register in `main.py`: prefix `/v1/cascade_demo`, tag `cascade_demo`.
6. Every endpoint in groups 3 and 5 sets a Swagger `summary` prefixed with its lesson
   label per the requirements mapping table — `[L2/L3]` for the stage endpoints and
   `/converse`, `[L3]` additionally noted on `/llm` (query-server pattern), `[L4]` for
   all outbound-call endpoints.

## 6. Landing page

1. Add a "Course lesson demos" section to `hello.py` `landing_page()` with one link
   per lesson, labeled by lesson: L2 → `/v1/vb_test/` (existing Phase 4 page),
   L2/L3 cascade → `/docs#/cascade_demo`, L4 → `/docs#/outbound_call`, each with a
   one-line description of what the lesson demonstrates.

## 7. Tests — `backend/tests/`

1. `test_vb_cli.py`: JSON-marker parsing, sanitization of `place_call` output,
   missing-env assertion, purpose-injection prompt content (mock `subprocess.run`).
2. `test_outbound_call.py` (pattern: `test_vb_test.py`): route registration in
   `main.app.openapi()`; `/call` happy path returns only `call_id`/`status`;
   503 on missing env; 502 on CLI failure; `/status` and `/recording` with the
   wrapper mocked; assert the callee phone number and API key never appear in any
   response body.
3. `test_cascade_demo.py`: route registration; each stage endpoint with
   `cascade_core` functions monkeypatched; `/converse` writes one session + two
   turns (repositories mocked) and returns audio with the session-id header;
   logging failure still returns 200 audio.
4. `test_outbound_call_tool.py` (or within test 2): `make_phone_call` function_tool
   is invocable and returns the sanitized shape.
5. Full suite green: `cd backend && pytest` with no credentials/network.
