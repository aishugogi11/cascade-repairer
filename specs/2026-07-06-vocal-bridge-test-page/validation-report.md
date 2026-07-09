# Validation Report — Vocal Bridge live-call test page
**Branch:** vb/dev    **Commit:** cb03831    **Date:** 2026-07-07

## Summary
FAIL / partial. The automated Phase 4 checks pass in the same containerized pytest path documented for CI, and the deployed Cloud Run service is running the current image, but the deployed live-call acceptance fails because `VOCAL_BRIDGE_AGENT_ID` is not set on Cloud Run. `POST /v1/vb_test/token` returns 503, so the page cannot connect to Vocal Bridge or prove a live conversation.

## Criterion-by-criterion results
- **Criterion:** `pytest` passes, including `tests/test_vb_test.py`.
- **Status:** PASS
- **Evidence:** Ran `docker compose build backend` then `docker run --rm vocal-bridge-training-backend python -m pytest tests/ -v`: `56 passed, 4 skipped, 1 warning in 1.15s`. `tests/test_vb_test.py` all passed.
- **Notes:** Test command matches README containerized test path.

- **Criterion:** `GET /v1/vb_test/` returns 200 HTML containing "Testing Vocal Bridge" and the esm.sh `@vocalbridgeai/react` import.
- **Status:** PASS
- **Evidence:** `tests/test_vb_test.py::test_page_returns_200_html_with_title` and `test_page_loads_vb_react_sdk_from_esm` passed. Code evidence: `backend/api/vb_test.py` serves `<h1>Testing Vocal Bridge</h1>` and imports `https://esm.sh/@vocalbridgeai/react@0.1.1`.
- **Notes:** Deployed `GET https://vocal-bridge-be-dev-24105435206.us-west1.run.app/v1/vb_test/` returned the expected HTML.

- **Criterion:** `POST /v1/vb_test/token` with both env vars set and mocked upstream returns `connection_url`, `token`, `session_name`, `agent_mode`; mocked call receives `X-API-Key`, `X-Agent-Id`, and the lessons' URL.
- **Status:** PASS
- **Evidence:** `tests/test_vb_test.py::test_token_success_aliases_upstream_fields` passed. Code evidence: `backend/api/vb_test.py` posts to `https://vocalbridgeai.com/api/v1/token` with `X-API-Key` and `X-Agent-Id`, then aliases `connection_url` / `livekit_url`, `token`, `room_name`, and `agent_mode`.
- **Notes:** Automated coverage also verifies `connection_url` is preferred over `livekit_url`.

- **Criterion:** Missing `VOCAL_BRIDGE_API_KEY` returns 503 naming it; missing `VOCAL_BRIDGE_AGENT_ID` returns 503 naming it.
- **Status:** PASS
- **Evidence:** `tests/test_vb_test.py::test_token_missing_api_key_is_503` and `test_token_missing_agent_id_is_503` passed.
- **Notes:** Deployed token endpoint currently exercises the second case: it returns `{"error":"VOCAL_BRIDGE_AGENT_ID not set"}`.

- **Criterion:** Mocked upstream non-2xx returns 502 and the API key value appears nowhere in the response body.
- **Status:** PASS
- **Evidence:** `tests/test_vb_test.py::test_token_upstream_error_is_502_and_never_leaks_key` passed.
- **Notes:** `test_token_upstream_unreachable_is_502` also passed.

- **Criterion:** `GET /v1/hello/` landing page contains the `/v1/vb_test/` link.
- **Status:** PASS
- **Evidence:** `tests/test_vb_test.py::test_landing_page_links_to_vb_test` passed. Deployed `GET /v1/hello/` returned an `<a href="/v1/vb_test/">Testing Vocal Bridge (live-call smoke test)</a>` link.
- **Notes:** None.

- **Criterion:** No new entries in `requirements.txt`; uses pinned `requests`.
- **Status:** PASS
- **Evidence:** `git diff --name-only 2d5ee6d^ 2d5ee6d` does not include `backend/requirements.txt`. Current `backend/requirements.txt` already pins `requests==2.34.2`.
- **Notes:** No dependency churn observed for the feature commit.

- **Criterion:** Merge PR -> Cloud Build trigger runs -> deploy succeeds with pytest-in-container step green.
- **Status:** AMBIGUOUS
- **Evidence:** `git log` shows merge commit `cb03831 Merge pull request #10 from zen-apps/vb/feature/vocal-bridge-test-page`. `gcloud run services describe vocal-bridge-be-dev --region us-west1 --project vocal-bridge-hackathon --format=json` shows the service Ready and image tag `.../vocal-bridge-be:cb03831`.
- **Notes:** I did not inspect Cloud Build logs, so I cannot independently prove the Cloud Build pytest step was green. Local containerized pytest passed.

- **Criterion:** One-time deployed prerequisite confirmed: both `VOCAL_BRIDGE_*` vars set on `vocal-bridge-be-dev`.
- **Status:** FAIL
- **Evidence:** `gcloud run services describe vocal-bridge-be-dev --region us-west1 --project vocal-bridge-hackathon --format=json` shows `VOCAL_BRIDGE_API_KEY` present and `VOCAL_BRIDGE_AGENT_ID` absent. Deployed `POST /v1/vb_test/token` returned HTTP 503 with `{"error":"VOCAL_BRIDGE_AGENT_ID not set"}`.
- **Notes:** This blocks the live conversation acceptance.

- **Criterion:** Open deployed `/v1/vb_test/` in Chrome; page renders with Testing Vocal Bridge heading and Connect button.
- **Status:** UNTESTABLE
- **Evidence:** Deployed HTML contains the heading and React code that renders a `Connect` button. I did not run a real browser session in Chrome.
- **Notes:** Static page delivery is working; browser runtime rendering was not directly observed.

- **Criterion:** Click Connect -> browser prompts for mic -> connection state reaches connected.
- **Status:** FAIL
- **Evidence:** Deployed `POST /v1/vb_test/token` returns 503 due missing `VOCAL_BRIDGE_AGENT_ID`; the page's token provider throws on non-2xx responses before a WebRTC connection can be established.
- **Notes:** This cannot pass until Cloud Run has a valid `VOCAL_BRIDGE_AGENT_ID`.

- **Criterion:** Have a very simple live conversation: speak, get a spoken reply, see both sides in transcript.
- **Status:** FAIL
- **Evidence:** Token mint fails on the deployed service with HTTP 503, so the browser cannot connect to Vocal Bridge.
- **Notes:** This is the primary phase acceptance moment and was not achieved.

- **Criterion:** Click Disconnect -> state returns to disconnected; reconnect works.
- **Status:** FAIL
- **Evidence:** Connection cannot be established because token mint fails with missing `VOCAL_BRIDGE_AGENT_ID`.
- **Notes:** Reconnect behavior remains unproven.

- **Criterion:** `POST /v1/vb_test/token` via `/docs` returns a real token payload and no key leaked in the response.
- **Status:** FAIL
- **Evidence:** Direct deployed `curl -sS -X POST .../v1/vb_test/token` returned HTTP 503 and `{"error":"VOCAL_BRIDGE_AGENT_ID not set"}`.
- **Notes:** No key leaked in this error response, but the required real token payload was not returned.

- **Criterion:** Temporarily unset scenario verified locally: with a var missing, the page's Connect surfaces the 503 error text instead of hanging.
- **Status:** PASS
- **Evidence:** Existing tests verify missing-var 503 responses. Code evidence: `backend/api/vb_test.py` token provider sets `tokenError` from the JSON response and throws a visible error string on non-2xx.
- **Notes:** I did not add a browser test for the rendered error text.

- **Criterion:** Reload mid-conversation -> page returns to idle cleanly.
- **Status:** UNTESTABLE
- **Evidence:** No live browser conversation was possible because deployed token mint fails.
- **Notes:** Needs manual browser validation after `VOCAL_BRIDGE_AGENT_ID` is configured.

- **Criterion:** Latency sanity observations recorded in the PR.
- **Status:** UNTESTABLE
- **Evidence:** No live connection or spoken reply occurred; no latency numbers can be recorded from this validation run.
- **Notes:** Needs manual validation after token mint succeeds.

- **Criterion:** Tone check: page copy is plain and functional, matching `hello.py`.
- **Status:** PASS
- **Evidence:** `backend/api/vb_test.py` page copy is a heading, one purpose sentence, widget container, and back link; no marketing content.
- **Notes:** Styling is minimal inline widget styling.

- **Criterion:** Definition of done: all automated assertions pass locally and in Cloud Build; live voice conversation works on deployed Cloud Run; landing page links to new page; roadmap marked complete; latency observations recorded in PR.
- **Status:** FAIL
- **Evidence:** Local automated assertions pass and deployed landing page links to the page. The deployed live voice conversation cannot work because token mint returns 503 missing `VOCAL_BRIDGE_AGENT_ID`. Cloud Build pytest logs and latency PR notes were not independently checked.
- **Notes:** Roadmap marks Phase 4 `[x] COMPLETE (implementation; manual QA pending)`, which matches this result better than full completion.

## Missing tests
- No automated browser test proves that Connect renders the 503 text in the UI. Proposed: `backend/tests/test_vb_test.py::test_page_token_provider_surfaces_missing_config` is not practical with the current FastAPI-only test stack; it would require a browser/JS test harness.
- No automated deployment/config test proves `VOCAL_BRIDGE_AGENT_ID` is set on Cloud Run before manual QA. Proposed: a CI or release validation script, outside hermetic pytest, that runs `gcloud run services describe vocal-bridge-be-dev --region us-west1 --project vocal-bridge-hackathon` and asserts both `VOCAL_BRIDGE_API_KEY` and `VOCAL_BRIDGE_AGENT_ID` names are present.
- No automated end-to-end voice test proves connect -> spoken reply -> transcript -> disconnect. Proposed: keep this manual unless the repo adds a browser automation and real Vocal Bridge test lane; path/name could be `backend/tests/e2e/test_vb_live_call_manual.py` only if a non-hermetic e2e suite is introduced.

## Gaps in validation.md
- Should validation be run from the merged `vb/dev` branch after PR merge, or strictly from `vb/feature/vocal-bridge-test-page` before merge? The current validator run is on `vb/dev`, while the skill expects a current feature branch.
- What exact artifact should contain the latency observations: PR comment, validation report, README note, or another file?
- Is `VOCAL_BRIDGE_AGENT_ID` expected to be set manually before marking Phase 4 complete, or is "implementation complete; manual QA pending" an allowed intermediate state?
- Should the validation require checking Cloud Build logs directly, or is deployed Cloud Run image readiness at the current commit sufficient evidence that the PR pipeline completed?

## Risks not covered by validation.md
- Cloud Run service description currently exposes API keys as literal environment variable values to anyone with permission to describe the service. Consider Secret Manager env refs for `OPENAI_API_KEY` and `VOCAL_BRIDGE_API_KEY`.
- `mint_token()` calls `res.json()` without guarding malformed upstream JSON; a bad 200 response would raise a 500 instead of returning a controlled 502.
