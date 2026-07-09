# Validation Report — Live Itinerary UI
**Branch:** vb/feature/live-itinerary-ui    **Commit:** 81d00cc    **Date:** 2026-07-09

## Summary
PARTIAL: automated validation passes in a rebuilt backend container, and source inspection shows the page and JSON endpoints implement the specified read-only itinerary surface. The end-to-end manual walkthrough on local BigQuery data and the post-merge deployed Cloud Run service was not executed from this unmerged feature branch, so those criteria remain UNTESTABLE here.

## Criterion-by-criterion results
- **Criterion:** `cd backend && python -m pytest` passes with no GCP credentials and no `OPENAI_API_KEY`, locally and inside the CI container.
- **Status:** PASS
- **Evidence:** `python -m pytest` failed because `python` is unavailable locally; `python3 -m pytest` failed because local Python has no pytest. Rebuilt the backend image with `docker compose build backend`, then ran `docker run --rm hackathon-vocal-bridge-backend python -m pytest tests/ -v`: `206 passed, 4 skipped, 6 warnings in 6.24s`.
- **Notes:** Containerized result is the CI-relevant one. Warnings are pre-existing coroutine warnings in `tests/test_sabre_tools.py::test_repair_trip_failed_write_surfaces_as_error_event`.

- **Criterion:** `list_recent_trips` returns trips ordered newest-first; empty and helper-error paths covered.
- **Status:** PASS
- **Evidence:** [backend/api/repositories/trips.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/repositories/trips.py:55) orders by `created_at DESC` and parameterizes `LIMIT @limit`; [backend/tests/test_repositories.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/tests/test_repositories.py:109) covers ordered results, empty results, and helper failure.
- **Notes:** No issue found.

- **Criterion:** `GET /v1/itinerary/status/{trip_id}` returns trip, items sorted by `start_ts`, summary counts totaling `len(items)`, correct `all_clear`, 404 unknown trip, and 5xx/error body on repository failure.
- **Status:** PASS
- **Evidence:** [backend/api/itinerary_ui.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/itinerary_ui.py:47) wraps `trips.get_trip_with_items` in `asyncio.to_thread`, returns `trip`, `items`, `summary`, and `fetched_at`; [backend/api/repositories/trips.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/repositories/trips.py:84) orders items by `start_ts`; [backend/tests/test_itinerary_ui.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/tests/test_itinerary_ui.py:66) covers shape, counts, sorting SQL, `all_clear`, 404, and 500 behavior.
- **Notes:** Automated tests assert `all_clear` false for `repairing` and true for `fixed/cancelled`; the implementation also treats `broken` as active.

- **Criterion:** `GET /v1/itinerary/trips` returns 200 with selector fields.
- **Status:** PASS
- **Evidence:** [backend/api/itinerary_ui.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/itinerary_ui.py:68) returns `trip_id`, `title`, `status`, `start_date`, `end_date`; [backend/tests/test_itinerary_ui.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/tests/test_itinerary_ui.py:143) verifies the selector fields and limit pass-through.
- **Notes:** No issue found.

- **Criterion:** `GET /v1/itinerary/` returns 200, `text/html`, page marker present.
- **Status:** PASS
- **Evidence:** [backend/api/itinerary_ui.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/itinerary_ui.py:42) serves the page via `HTMLResponse`; [backend/tests/test_itinerary_ui.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/tests/test_itinerary_ui.py:47) verifies status, content type, and marker.
- **Notes:** Router is mounted in [backend/main.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/main.py:75).

- **Criterion:** No new Python or JS dependencies introduced; page makes no external requests.
- **Status:** PASS
- **Evidence:** `git diff --cached --name-only` shows no requirements-file changes. [backend/tests/test_itinerary_ui.py](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/tests/test_itinerary_ui.py:57) asserts no external `src="http"` or `href="http"`; the page uses same-origin `fetch` calls at [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:444) and [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:494).
- **Notes:** No issue found.

- **Criterion:** Manual walkthrough: seed trip, open page, break flight, repair trip, cards/feed/timer update, statuses match BigQuery, total under 60s.
- **Status:** UNTESTABLE
- **Evidence:** The current branch is unmerged and the report was run without a live local BigQuery walkthrough or post-merge Cloud Run deployment. Static evidence supports the intended behavior: five item types render from API data at [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:255), status transitions feed entries at [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:402), and the recovery timer starts/stops from active summary counts at [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:417).
- **Notes:** Needs real walkthrough evidence after merge/deploy.

- **Criterion:** Manual edge cases: unknown `trip_id`, backend mid-poll recovery, trip switching resets feed/timer, cancelled item muted, readable from projector distance.
- **Status:** PARTIAL
- **Evidence:** Static/code evidence only: unknown trip state at [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:454), stale/retry state at [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:447), trip reset at [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:477), cancelled muted style at [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:146), and projector-oriented sizing/colors at [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:21).
- **Notes:** No browser/device observation was performed.

- **Criterion:** Tone check: traveler-facing copy, calm, present tense, reassuring; no exclamation points or internal jargon.
- **Status:** PASS
- **Evidence:** User-visible feed and banner copy is in [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:263) and [backend/api/assets/itinerary/page.html](/Users/joshuajanzen/zen/dev/hackathon-vocal-bridge/backend/api/assets/itinerary/page.html:347). No user-visible copy uses internal terms like row, DML, poll, or endpoint.
- **Notes:** Code comments contain internal terms, but they are not user-visible.

- **Criterion:** Definition of done: automated assertions pass in CI, manual deployed walkthrough passes, tone check passed, Phase 10 marked complete.
- **Status:** PARTIAL
- **Evidence:** Automated assertions pass in the rebuilt container; tone check passed; `specs/roadmap.md` marks Phase 10 complete. Deployed walkthrough after merge was not run from this branch.
- **Notes:** This remains partial until deployed manual QA is recorded.

## Missing tests
- `backend/tests/test_itinerary_ui.py::test_status_all_clear_false_for_broken_items` — assert a broken item makes `summary.all_clear` false, not only repairing.
- `backend/tests/test_itinerary_ui.py::test_page_contains_all_status_visual_hooks` — assert the HTML contains visual hooks for planned, booked, broken, repairing, fixed, and cancelled.
- Browser-level test, e.g. `backend/tests/test_itinerary_ui_page_behavior.py::test_trip_switch_resets_feed_and_timer` — serve mocked `/trips` and `/status` responses, switch trips, and assert feed/timer reset.
- Browser-level test, e.g. `backend/tests/test_itinerary_ui_page_behavior.py::test_poll_failure_shows_reconnecting_and_recovers` — simulate a failed status fetch followed by a healthy response.
- Browser-level test, e.g. `backend/tests/test_itinerary_ui_page_behavior.py::test_status_transition_feed_and_timer` — simulate booked -> broken -> repairing -> fixed responses and assert cards, feed, and timer behavior.

I did not write validator tests.

## Gaps in validation.md
- Should the validation require a captured local/deployed walkthrough artifact, such as screenshots, curl transcript, or a recorded `trip_id`, before Phase 10 can be marked fully done?
- Should projector readability have a concrete viewport, zoom level, or screenshot standard instead of subjective observation?
- Should `?trip_id=` for a trip outside the recent selector list be an explicit accepted case?

## Risks not covered by validation.md
- The full suite passes with coroutine warnings in the repair failure test path. These warnings are not caused by the itinerary UI, but they point at a repair-path cleanup issue that could obscure future async failures.
