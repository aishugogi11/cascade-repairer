# Validation Report — Live Itinerary UI
**Branch:** vb/feature/live-itinerary-ui    **Commit:** 0bf4348    **Date:** 2026-07-09

## Summary
PARTIAL/PASS: the automated suite passes in the backend container, and the deployed Cloud Run walkthrough proves the itinerary API and backing BigQuery rows move booked -> broken -> repairing -> fixed in under 60 seconds. Remaining partial items are browser-visual observations only: this environment has no Chrome/Playwright/Selenium, so I could not directly observe rendered cards, feed animations, timer behavior, or projector readability in a real browser.

## Criterion-by-criterion results
- **Criterion:** `cd backend && python -m pytest` passes with no GCP credentials and no `OPENAI_API_KEY`, locally and inside the CI container.
- **Status:** PASS
- **Evidence:** `docker run --rm hackathon-vocal-bridge-backend python -m pytest tests/ -v`: `206 passed, 4 skipped, 6 warnings in 4.85s`.
- **Notes:** Local `python` is unavailable and local `python3` lacks pytest, so the containerized CI-style command is the relevant evidence. Warnings are in `tests/test_sabre_tools.py::test_repair_trip_failed_write_surfaces_as_error_event`.

- **Criterion:** `list_recent_trips` returns trips ordered newest-first; empty and helper-error paths covered.
- **Status:** PASS
- **Evidence:** [backend/api/repositories/trips.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/repositories/trips.py:55) orders by `created_at DESC` and parameterizes `LIMIT @limit`; [backend/tests/test_repositories.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/tests/test_repositories.py:109) covers ordered results, empty results, and helper failure. Deployed `GET /v1/itinerary/trips` returned 200 and listed the seeded trip `0f584313-f3e8-4546-82e7-ad2c1e44f674` first with selector fields.
- **Notes:** No issue found.

- **Criterion:** `GET /v1/itinerary/status/{trip_id}` returns trip, items sorted by `start_ts`, summary counts totaling `len(items)`, correct `all_clear`, 404 unknown trip, and 5xx/error body on repository failure.
- **Status:** PASS
- **Evidence:** [backend/api/itinerary_ui.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/itinerary_ui.py:47) wraps `trips.get_trip_with_items` in `asyncio.to_thread`, returns `trip`, `items`, `summary`, and `fetched_at`; [backend/api/repositories/trips.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/repositories/trips.py:84) orders items by `start_ts`; [backend/tests/test_itinerary_ui.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/tests/test_itinerary_ui.py:66) covers shape, counts, sorting SQL, `all_clear`, 404, and 500 behavior. Deployed unknown trip returned `404 application/json` with `trip not-a-real-trip-id-validator not found`.
- **Notes:** Deployed status payloads during the walkthrough showed `all_clear: true` for five booked items, `false` for one broken item, `false` for four repairing/one fixed, and `true` for five fixed.

- **Criterion:** `GET /v1/itinerary/trips` returns 200 with selector fields.
- **Status:** PASS
- **Evidence:** [backend/api/itinerary_ui.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/itinerary_ui.py:68) returns `trip_id`, `title`, `status`, `start_date`, `end_date`; [backend/tests/test_itinerary_ui.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/tests/test_itinerary_ui.py:143) verifies selector fields and limit pass-through. Deployed `GET https://vocal-bridge-be-dev-qqboibtzpq-uw.a.run.app/v1/itinerary/trips` returned `200 application/json`; first trip was `0f584313-f3e8-4546-82e7-ad2c1e44f674` with those fields.
- **Notes:** No issue found.

- **Criterion:** `GET /v1/itinerary/` returns 200, `text/html`, page marker present.
- **Status:** PASS
- **Evidence:** [backend/api/itinerary_ui.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/itinerary_ui.py:42) serves the page via `HTMLResponse`; [backend/tests/test_itinerary_ui.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/tests/test_itinerary_ui.py:47) verifies status, content type, and marker. Deployed `GET /v1/itinerary/` and `GET /v1/itinerary/?trip_id=0f584313-f3e8-4546-82e7-ad2c1e44f674` both returned `200 text/html; charset=utf-8`; title marker `Live Itinerary — Cascade Repairer` was present.
- **Notes:** Router is mounted in [backend/main.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/main.py:75).

- **Criterion:** No new Python or JS dependencies introduced; page makes no external requests.
- **Status:** PASS
- **Evidence:** No requirements file changes in the clean worktree. [backend/tests/test_itinerary_ui.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/tests/test_itinerary_ui.py:57) asserts no external `src="http"` or `href="http"`; the page uses same-origin `fetch` calls at [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:444) and [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:494).
- **Notes:** No issue found.

- **Criterion:** Manual walkthrough: seed trip, open page, break flight, repair trip, cards/feed/timer update, statuses match BigQuery, total under 60s.
- **Status:** PASS
- **Evidence:** Deployed URL resolved from Cloud Run: `https://vocal-bridge-be-dev-qqboibtzpq-uw.a.run.app`. `POST /v1/sabre_tools/seed_trip` with `{}` returned 200 and trip `0f584313-f3e8-4546-82e7-ad2c1e44f674` with five booked items. Initial `GET /v1/itinerary/status/{trip_id}` returned five booked items and `all_clear: true`. `POST /v1/disruption/break_flight` returned 200, flight item `01818e6d-387f-418d-83bf-c41d600142aa`, `previous_status: booked`, `status: broken`, `affected_rows: 1`; next status payload returned one broken and four booked with `all_clear: false`. `POST /v1/sabre_tools/repair_trip` with `wait:false` returned 200 with all five tasks pending; sampled status returned `flight:repairing`, `ground:fixed`, `dining:repairing`, `hotel:repairing`, `experience:repairing`, `all_clear: false`. Final status returned all five `fixed`, `all_clear: true`. `POST /v1/sabre_tools/repair_trip` with `wait:true` completed all five events in about 15.2s from first task start to last finish. BigQuery read-back for the same trip returned five `fixed` rows with fresh `updated_at` timestamps from `2026-07-09T19:50:12` through `2026-07-09T19:50:21`.
- **Notes:** API and persistence behavior passed. Rendered browser cards/feed/timer were not directly observed; see separate edge-case criterion.

- **Criterion:** Manual edge cases: unknown `?trip_id`, backend mid-poll recovery, trip switching resets feed/timer, cancelled item muted, readable from projector distance.
- **Status:** PARTIAL
- **Evidence:** Deployed unknown status request returned 404 JSON; page source contains friendly unknown-trip copy at [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:454), stale/retry copy at [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:447), trip reset logic at [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:477), cancelled muted style at [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:146), and six status color hooks at [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:129).
- **Notes:** No browser automation was available (`playwright`/`selenium` absent, no Chrome binary), so I did not observe actual DOM-rendered states, backend-kill recovery, trip-switch behavior, cancelled rendering, or projector readability.

- **Criterion:** Tone check: traveler-facing copy, calm, present tense, reassuring; no exclamation points or internal jargon.
- **Status:** PASS
- **Evidence:** User-visible feed and banner copy is in [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:263) and [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:347). No user-visible copy uses internal terms like row, DML, poll, or endpoint.
- **Notes:** Code comments contain internal terms, but they are not user-visible.

- **Criterion:** Definition of done: automated assertions pass in CI, manual deployed walkthrough passes, tone check passed, Phase 10 marked complete.
- **Status:** PARTIAL
- **Evidence:** Automated assertions pass in the rebuilt container; deployed API/data walkthrough passes; tone check passes; `specs/roadmap.md` marks Phase 10 complete.
- **Notes:** The only remaining gap is browser-visual manual QA.

## Missing tests
- `backend/tests/test_itinerary_ui.py::test_status_all_clear_false_for_broken_items` — assert a broken item makes `summary.all_clear` false, not only repairing.
- `backend/tests/test_itinerary_ui.py::test_page_contains_all_status_visual_hooks` — assert the HTML contains visual hooks for planned, booked, broken, repairing, fixed, and cancelled.
- Browser-level test, e.g. `backend/tests/test_itinerary_ui_page_behavior.py::test_trip_switch_resets_feed_and_timer` — serve mocked `/trips` and `/status` responses, switch trips, and assert feed/timer reset.
- Browser-level test, e.g. `backend/tests/test_itinerary_ui_page_behavior.py::test_poll_failure_shows_reconnecting_and_recovers` — simulate a failed status fetch followed by a healthy response.
- Browser-level test, e.g. `backend/tests/test_itinerary_ui_page_behavior.py::test_status_transition_feed_and_timer` — simulate booked -> broken -> repairing -> fixed responses and assert cards, feed, and timer behavior.

I did not write validator tests.

## Gaps in validation.md
- Should browser-visual manual QA require a screenshot or short screen recording as evidence?
- Should projector readability have a concrete viewport, zoom level, or screenshot standard instead of subjective observation?
- Should `?trip_id=` for a trip outside the recent selector list be an explicit accepted case?

## Risks not covered by validation.md
- The full suite passes with coroutine warnings in the repair failure test path. These warnings are not caused by the itinerary UI, but they point at a repair-path cleanup issue that could obscure future async failures.
