# Validation — Course lesson demo routers (L2/L3/L4 ports)

## Automated

Run from `backend/`: `pytest` (hermetic — must pass with no GCP credentials, no
`OPENAI_API_KEY`, no network, no `vb` binary installed).

Required assertions (present and passing):

1. **Route registration**: `main.app.openapi()["paths"]` contains
   `/v1/cascade_demo/stt`, `/llm`, `/tts`, `/converse` and
   `/v1/outbound_call/call`, `/status`, `/recording/{session_id}`.
2. **Sanitization**: `POST /v1/outbound_call/call` response contains exactly
   `call_id` and `status`; no response body from any outbound-call endpoint contains
   `VOCAL_BRIDGE_API_KEY`'s value or `VOCAL_BRIDGE_CALLEE_PHONE`'s value.
3. **Env guards**: `/call` returns 503 when `VOCAL_BRIDGE_API_KEY`,
   `VOCAL_BRIDGE_CALLER_AGENT_ID`, or `VOCAL_BRIDGE_CALLEE_PHONE` is unset;
   502 when the mocked CLI wrapper reports failure.
4. **Purpose injection**: `set_caller_purpose` output contains both the prompt base
   and the passed purpose text (mocked `vb prompt set` receives it).
5. **Cascade logging**: `/converse` creates one `sessions` row (architecture
   `cascaded`) and two `turns` rows (roles `user` and `agent`) with GCS audio URIs
   following `audio/<session_id>/<turn_id>.wav` — repositories/gcs mocked and
   call args asserted.
6. **Graceful degradation**: `/converse` still returns 200 with audio when the mocked
   BigQuery/GCS writes fail.
7. **Tool shape**: the `make_phone_call` function_tool exists, is an OpenAI Agents SDK
   tool, and returns the sanitized `{call_id, status}` dict.
8. Existing suite stays green (no regressions in the five existing routers).

Typecheck/lint: match whatever the repo already runs in CI (Cloud Build runs pytest
inside the built image — a green local suite plus a successful `make build` is the bar).

## Manual

Local (`make up`, backend on :1019) with a real `.env`:

1. Swagger (`/docs`) shows two new tags, `cascade_demo` and `outbound_call`, each with
   its endpoints documented, and every new endpoint's summary carries its lesson label
   (`[L2/L3]`, `[L3]`, `[L4]`) per the requirements mapping table. The landing page
   shows one labeled demo link per lesson (L2 → `/v1/vb_test/`, L2/L3 cascade, L4).
2. **Cascade walkthrough**: upload a short voice clip to `/stt` → readable transcript;
   send that text to `/llm` → sensible reply; send the reply to `/tts` → playable mp3;
   then one `/converse` round-trip returns a playable audio answer to a spoken
   question, and a second `/converse` call with the returned `X-Session-Id` continues
   the conversation.
3. **BigQuery check**: after the `/converse` calls, `sessions` has the new session and
   `turns` has matching user/agent rows with `audio_gcs_uri` values; the GCS objects
   exist and play.
4. **L4 walkthrough** (uses the verified demo cell phone from
   `VOCAL_BRIDGE_CALLEE_PHONE`): `POST /call` with a distinctive purpose → phone rings,
   the caller agent's conversation reflects the injected purpose → `GET /status` shows
   the session and transcript lines → after hangup, `GET /recording/{session_id}`
   returns a GCS URI whose object is a playable mp3 of the call.
5. **Edge cases**: `/call` with empty purpose → 422; `/status` with unknown session_id
   → 404; `/recording` before any call completes → 404; `/converse` with a non-audio
   file → 4xx, not a 500.
6. **Cloud Run**: after merge to `vb/dev` deploys, repeat the `/converse` round-trip
   and one real outbound call against the deployed service (callee phone set via
   `--update-env-vars`).

## Tone check

Landing-page additions read like the existing page: short, factual link text
("Cascaded voice demo (L2/L3)", "Outbound call tool (L4)"), no exclamation points,
no marketing copy.

## Definition of done

- All automated assertions above pass in a hermetic environment and in the Cloud Build
  container.
- Manual walkthroughs 1–5 pass locally; walkthrough 6 passes on Cloud Run.
- A real phone call was placed end-to-end through the deployed backend with the purpose
  audibly injected, and its transcript/status/recording were retrieved via the API.
- `sessions`/`turns` rows and GCS audio artifacts exist for a real cascade conversation.
- No credentials, phone numbers, or agent transport internals appear in any API
  response, log line committed to the repo, or spec file.
- Phase 7 marked `[x] COMPLETE` in `specs/roadmap.md`.
