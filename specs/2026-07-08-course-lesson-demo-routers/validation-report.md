# Validation Report — Course lesson demo routers
**Branch:** vb/feature/course-lesson-demo-routers    **Commit:** fba409b6a7d66371224ebe8d0aac41b155285c88    **Date:** 2026-07-08

## Summary
PARTIAL: the automated Phase 7 criteria pass in the Cloud Build-style Docker test path, and the deployed Cloud Run cascade now works through STT, LLM, TTS, `/converse`, multi-turn headers, BigQuery logging, and GCS audio artifact persistence. The deployed outbound-call env guard is fixed and `/status` plus `/recording/{session_id}` work, but live completion is still blocked because the configured Vocal Bridge caller agent has outbound calling disabled.

## Criterion-by-criterion results
- **Criterion:** Automated suite runs hermetically from `backend/`: `pytest`, no GCP credentials, no `OPENAI_API_KEY`, no network, no `vb` binary.
- **Status:** PASS
- **Evidence:** Host `python -m pytest -v` could not run because `python` is absent; host `python3 -m pytest -v` could not run because pytest is not installed. Docker path succeeded: `docker compose build backend` exited 0; `docker run --rm vocal-bridge-training-backend python -m pytest tests/ -v` exited 0 with `162 passed, 4 skipped, 6 warnings in 3.18s`.
- **Notes:** This matches README/Cloud Build execution more closely than host Python. Warnings are from unrelated Sabre tool tests and are listed under risks.

- **Criterion:** Route registration: OpenAPI contains `/v1/cascade_demo/stt`, `/llm`, `/tts`, `/converse` and `/v1/outbound_call/call`, `/status`, `/recording/{session_id}`.
- **Status:** PASS
- **Evidence:** `backend/main.py` registers both routers. `backend/tests/test_cascade_demo.py::test_routes_registered_with_lesson_summaries` and `backend/tests/test_outbound_call.py::test_routes_registered_with_l4_summaries` passed in Docker.
- **Notes:** Tests also assert Swagger summary lesson labels for these routes.

- **Criterion:** Sanitization: `POST /v1/outbound_call/call` response contains exactly `call_id` and `status`; no outbound-call response body contains `VOCAL_BRIDGE_API_KEY` or `VOCAL_BRIDGE_CALLEE_PHONE` values.
- **Status:** PASS
- **Evidence:** `backend/api/outbound_call.py` scrubs configured API key and callee values recursively and returns only `{"call_id": ..., "status": ...}` from `/call`. Passing tests: `test_call_returns_only_call_id_and_status`, `test_call_cli_failure_is_502_and_scrubbed`, `test_status_defaults_to_latest_session_and_scrubs`, `test_make_phone_call_failure_reports_error_status`.
- **Notes:** `backend/api/vb_cli.py::place_call` also reduces raw CLI call output to `call_id` and `status`; `backend/tests/test_vb_cli.py::test_place_call_happy_path_is_sanitized` passed.

- **Criterion:** Env guards: `/call` returns 503 when required Vocal Bridge env vars are unset; 502 when the mocked CLI wrapper reports failure.
- **Status:** PASS
- **Evidence:** `backend/api/outbound_call.py` checks `VOCAL_BRIDGE_API_KEY`, `VOCAL_BRIDGE_CALLER_AGENT_ID`, and `VOCAL_BRIDGE_CALLEE_PHONE` before calling the CLI wrapper. Passing tests: `test_call_missing_env_is_503_naming_the_var` and `test_call_cli_failure_is_502_and_scrubbed`.
- **Notes:** `/status` and `/recording` also guard their required env vars.

- **Criterion:** Purpose injection: `set_caller_purpose` output contains both prompt base and passed purpose text; mocked `vb prompt set` receives it.
- **Status:** PASS
- **Evidence:** `backend/api/vb_cli.py::set_caller_purpose` reads `tool_caller_prompt_base.md`, appends `PURPOSE OF THIS CALL: {purpose}`, writes a temp prompt file, and calls `vb prompt set -f`. Passing test: `backend/tests/test_vb_cli.py::test_set_caller_purpose_injects_base_and_purpose`.
- **Notes:** The implementation deletes the temp file after the CLI call.

- **Criterion:** Cascade logging: `/converse` creates one `sessions` row and two `turns` rows with roles `user` and `agent`, architecture `cascaded`, and GCS audio URIs under `audio/<session_id>/<turn_id>.wav`.
- **Status:** PASS
- **Evidence:** `backend/api/cascade_demo.py::_log_converse_turns` creates the session on first turn, creates user/agent `Turn` models, sets audio URIs via `turns_repo.audio_uri_for`, uploads both blobs, and writes both turns. Passing test: `backend/tests/test_cascade_demo.py::test_converse_returns_audio_and_logs_session_and_turns`.
- **Notes:** `test_converse_with_session_id_skips_session_insert` confirms continuing an existing session skips a duplicate session insert.

- **Criterion:** Graceful degradation: `/converse` still returns 200 with audio when mocked BigQuery/GCS writes fail.
- **Status:** PASS
- **Evidence:** `_log_converse_turns` logs warnings for failed session, turn, and upload writes without raising; outer `/converse` catches logging exceptions. Passing test: `backend/tests/test_cascade_demo.py::test_converse_still_returns_audio_when_logging_fails`.
- **Notes:** Cascade stage failures still return 502, covered separately by `test_converse_cascade_failure_is_502`.

- **Criterion:** Tool shape: `make_phone_call` exists, is an OpenAI Agents SDK tool, and returns sanitized `{call_id, status}`.
- **Status:** PASS
- **Evidence:** `backend/api/outbound_call.py` keeps `_make_phone_call` callable and wraps it with `function_tool`. Passing tests: `test_make_phone_call_is_a_function_tool`, `test_make_phone_call_plain_function_returns_sanitized_shape`, and `test_make_phone_call_failure_reports_error_status`.
- **Notes:** This follows the repo's `hello.py` function-tool pattern.

- **Criterion:** Existing suite stays green; no regressions in existing routers.
- **Status:** PASS
- **Evidence:** Full Docker suite passed: `162 passed, 4 skipped`. Existing router tests for hello, vb_test, concurrency_spike, disruption, sabre_tools, gcp_check, weather, repositories, and helpers all passed.
- **Notes:** Skipped validator-doc tests are conditional on source directories not copied into the image.

- **Criterion:** Typecheck/lint matches CI; green local suite plus successful `make build` is the bar.
- **Status:** PASS
- **Evidence:** No separate typecheck/lint target is declared in validation.md or Cloud Build. Cloud Build runs pytest inside the built image; the Docker image build and in-image pytest both passed.
- **Notes:** I did not run an additional lint command because none is specified in CI.

- **Criterion:** Manual local Swagger check: `/docs` shows `cascade_demo` and `outbound_call`; endpoint summaries carry lesson labels; landing page shows labeled links.
- **Status:** PASS
- **Evidence:** Automated OpenAPI and landing-page tests passed: `test_routes_registered_with_lesson_summaries`, `test_routes_registered_with_l4_summaries`, and `test_landing_page_links_lessons`. Deployed `GET https://vocal-bridge-be-dev-24105435206.us-west1.run.app/openapi.json` includes `cascade_demo` and `outbound_call` tags plus `[L2/L3]`, `[L3]`, and `[L4]` summaries. Deployed `GET /v1/hello/` shows the Phase 7 lesson links.
- **Notes:** I verified the deployed OpenAPI JSON and landing page, not the rendered Swagger UI in a browser.

- **Criterion:** Manual cascade walkthrough: `/stt` readable transcript, `/llm` sensible reply, `/tts` playable mp3, `/converse` returns playable audio and supports multi-turn via `X-Session-Id`.
- **Status:** PASS
- **Evidence:** Retry after GCS fix: deployed `POST /v1/cascade_demo/llm` returned `{"reply":"Hello from the deployed Phase 7 GCS retry validator!"}`. Deployed `POST /v1/cascade_demo/tts` returned HTTP 200 `audio/mpeg` with 34,560 bytes. Feeding that mp3 to deployed `POST /v1/cascade_demo/stt` returned `{"transcript":"What is my next travel step?"}`. First deployed `POST /v1/cascade_demo/converse` returned HTTP 200 `audio/mpeg`, `X-Session-Id: a2d0c88a-34b3-4b00-9f79-c901011399da`, `X-Transcript: What is my next travel step?`, `X-Reply: Where are you traveling to next? That will help me guide you on your next steps.`, and a 72,960-byte audio body. A second `/converse` with the same `X-Session-Id` returned HTTP 200 `audio/mpeg`, same session id, and a 108,288-byte audio body.
- **Notes:** This was verified against Cloud Run, not local `make up`.

- **Criterion:** Manual BigQuery/GCS check after `/converse`: `sessions` and `turns` rows exist and GCS objects play.
- **Status:** PASS
- **Evidence:** `GET /v1/hello/gcp_check` on Cloud Run reported BigQuery and GCS both `ok`. `bq query` for deployed session `a2d0c88a-34b3-4b00-9f79-c901011399da` found one `sessions` row with `architecture=cascaded`, `client=api_demo`, and four `turns` rows for the two `/converse` calls. The turn rows contain `audio_gcs_uri` values under `gs://vocal-bridge-hackathon-audio/audio/a2d0c88a-34b3-4b00-9f79-c901011399da/...`. `gsutil ls -l 'gs://vocal-bridge-hackathon-audio/audio/a2d0c88a-34b3-4b00-9f79-c901011399da/*'` returned 4 objects totaling 250,368 bytes.
- **Notes:** The earlier deployed session `43ff4e12-c780-4480-a2b8-4f7598e92bce` had missing GCS objects; the retry after Josh's GCS fix passed.

- **Criterion:** Manual L4 walkthrough: real outbound phone call rings, injected purpose appears in conversation, `/status` returns transcript, `/recording/{session_id}` returns playable mp3 GCS URI.
- **Status:** FAIL
- **Evidence:** After `VOCAL_BRIDGE_CALLER_AGENT_ID` was added, deployed `GET /v1/outbound_call/status` returned HTTP 200 with a completed Vocal Bridge session (`id: a0b42db9-99b3-4530-91f5-d27c127cf9e4`, `status: completed`, `recording_available: true`). Deployed `GET /v1/outbound_call/recording/a0b42db9-99b3-4530-91f5-d27c127cf9e4` returned `{"gcs_uri":"gs://vocal-bridge-hackathon-audio/audio/outbound/a0b42db9-99b3-4530-91f5-d27c127cf9e4.mp3"}`, and `gsutil ls -l` found that object at 234,285 bytes. Deployed `POST /v1/outbound_call/call` with a validation purpose failed before dialing with `vb call [redacted] --name phase7-outbound-validator failed: Error: Outbound calling is not enabled for this agent. Enable it in agent settings or via: vb config set --outbound-enabled true`.
- **Notes:** Status and recording endpoints now work live; the real outbound call and purpose-injection part cannot pass until outbound calling is enabled for the configured caller agent.

- **Criterion:** Manual edge cases: empty purpose 422; unknown status 404; recording before call completion 404; non-audio `/converse` 4xx not 500.
- **Status:** PASS
- **Evidence:** Passing tests: `test_call_blank_purpose_is_422`, `test_status_unknown_session_is_404`, `test_recording_not_found_is_404`, and `test_converse_non_audio_is_400_not_500`.
- **Notes:** These edge cases are automated, not only manual.

- **Criterion:** Manual Cloud Run: repeat `/converse` and one real outbound call against deployed service after merge to `vb/dev`.
- **Status:** FAIL
- **Evidence:** Cloud Run `/converse` passed twice with real audio, a stable session id, BigQuery rows, and GCS objects for session `a2d0c88a-34b3-4b00-9f79-c901011399da`. Cloud Run outbound status and recording retrieval work. Cloud Run outbound call failed before dialing because outbound calling is disabled for the configured caller agent.
- **Notes:** This criterion requires both cascade and a real outbound call; only cascade/status/recording pass.

- **Criterion:** Tone check: landing-page additions are short, factual link text with no exclamation points or marketing copy.
- **Status:** PASS
- **Evidence:** `backend/api/hello.py` landing page uses factual labels: `L2 — Voice in your App`, `L2/L3 — Cascaded architecture`, and `L4 — Voice as a Tool`; `backend/tests/test_cascade_demo.py::test_landing_page_links_lessons` passed.
- **Notes:** No exclamation points observed in the added lesson-link copy.

- **Criterion:** Definition of done: all automated assertions pass in hermetic environment and Cloud Build container.
- **Status:** PASS
- **Evidence:** Docker build and in-container pytest passed: `162 passed, 4 skipped`.
- **Notes:** This validates the local Cloud Build-style container path, not an actual Cloud Build run.

- **Criterion:** Definition of done: manual walkthroughs 1-5 pass locally; walkthrough 6 passes on Cloud Run.
- **Status:** FAIL
- **Evidence:** Deployed walkthrough evidence covers Swagger/landing page and cascade, including BigQuery rows and GCS audio objects. Deployed `/status` and `/recording/{session_id}` work. Deployed outbound-call walkthrough fails at `/call` because outbound calling is disabled for the configured caller agent.
- **Notes:** Local `make up` walkthrough was not run; the deployed outbound-call failure is enough to block this definition-of-done item.

- **Criterion:** Definition of done: a real phone call was placed end-to-end through deployed backend with purpose injected, transcript/status/recording retrieved.
- **Status:** FAIL
- **Evidence:** Deployed `/v1/outbound_call/call` reached the CLI but returned `Outbound calling is not enabled for this agent` before placing a call.
- **Notes:** Enable outbound calling for the configured Vocal Bridge caller agent, then re-run `/call`, `/status`, and `/recording/{session_id}`.

- **Criterion:** Definition of done: `sessions`/`turns` rows and GCS audio artifacts exist for a real cascade conversation.
- **Status:** PASS
- **Evidence:** BigQuery rows exist for deployed session `a2d0c88a-34b3-4b00-9f79-c901011399da`, including four turn rows with audio URIs. `gsutil ls -l 'gs://vocal-bridge-hackathon-audio/audio/a2d0c88a-34b3-4b00-9f79-c901011399da/*'` returned four matching GCS objects totaling 250,368 bytes.
- **Notes:** This criterion passed on the retry after the GCS fix deployment.

- **Criterion:** Definition of done: no credentials, phone numbers, or agent transport internals appear in API response, committed log line, or spec file.
- **Status:** PASS
- **Evidence:** Response sanitization tests passed. Secret scan found env var names and fake test numbers only; implementation reads callee/API key from environment and scrubs response payloads. `backend/api/vb_cli.py::place_call` returns only `call_id` and `status`.
- **Notes:** Specs intentionally name env vars, not values.

- **Criterion:** Definition of done: Phase 7 marked `[x] COMPLETE` in `specs/roadmap.md`.
- **Status:** PASS
- **Evidence:** `specs/roadmap.md` heading reads `Phase 7: Course lesson demo routers — cascaded voice + outbound phone tool (L2/L3/L4 ports) [x] COMPLETE (implementation; manual QA pending)`.
- **Notes:** The parenthetical correctly matches this validation result: implementation passes; manual QA remains.

## Missing tests
- Manual real OpenAI cascade smoke test: add an opt-in integration test, e.g. `backend/tests/integration/test_phase7_live_cascade.py::test_live_converse_writes_bq_and_gcs`, skipped unless `RUN_LIVE_PHASE7=1`, `OPENAI_API_KEY`, and GCP env are set. It should POST a real short audio file to `/v1/cascade_demo/converse`, assert playable mp3, assert `X-Session-Id`, then verify `sessions`/`turns` rows and GCS objects.
- Manual real Vocal Bridge outbound-call smoke test: add an opt-in integration test, e.g. `backend/tests/integration/test_phase7_live_outbound.py::test_live_outbound_call_status_and_recording`, skipped unless `RUN_LIVE_PHASE7=1` and Vocal Bridge env vars are set. It should place a call with a distinctive purpose, poll `/status`, and fetch `/recording/{session_id}` after completion.
- Cloud Run acceptance: add an external smoke script or opt-in test, e.g. `backend/tests/integration/test_phase7_cloudrun.py::test_deployed_phase7_cascade_and_outbound`, skipped unless `PHASE7_CLOUDRUN_BASE_URL` is set. It should exercise the deployed `/converse` and `/outbound_call/call` surfaces.

## Gaps in validation.md
- Should manual/live criteria block completion, or is `[x] COMPLETE (implementation; manual QA pending)` the intended state until credentials and Cloud Run are available?
- Should the validation require an actual Cloud Build run, or is the local Docker image path (`docker compose build backend` plus `docker run ... pytest`) sufficient evidence?
- Should the "no credentials, phone numbers, or agent transport internals" check explicitly exclude fake test data and env var names?

## Risks not covered by validation.md
- The full Docker suite emits coroutine-not-awaited warnings in `tests/test_sabre_tools.py::test_repair_trip_failed_write_surfaces_as_error_event`. Tests pass, but async cleanup in the Sabre repair path may need a later cleanup phase.
- Cloud Run has `VOCAL_BRIDGE_CALLER_AGENT_ID`, but the configured Vocal Bridge caller agent has outbound calling disabled; `/call` cannot pass live validation until agent settings allow outbound dialing.
- Validator process note: while scanning for committed secret values, `rg` returned three env-var-name matches from this feature's `plan.md`. I did not intentionally read the plan and did not use it as pass/fail evidence.
