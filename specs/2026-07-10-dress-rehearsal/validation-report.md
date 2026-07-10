# Validation Report - Phase 12: Dress Rehearsal
**Branch:** vb/feature/dress-rehearsal    **Commit:** eb76fb22065fc10b12783b7de4f8363202fe219d    **Date:** 2026-07-10

## Summary
PARTIAL / FAIL. The local automated suite passes and the deployed non-call data path can seed, break, repair, and persist all five trip legs in under 60 seconds. The strict deployed two-beat rehearsal fails because Vocal Bridge outbound calls currently return HTTP 502: `Outbound call credit exhausted for this destination`; both `/v1/demo/book` and `/v1/demo/disrupt` are blocked before the phone-call demo can run.

## Criterion-by-criterion results

- **Criterion:** Run the automated suite from the repo root with no GCP/OpenAI/Vocal Bridge credentials; required Phase 12 assertions are covered.
- **Status:** PASS
- **Evidence:** Exact command in validation.md, `docker compose exec vocal-bridge-be pytest`, failed because the compose service is named `backend`, not `vocal-bridge-be`. Equivalent in-repo command `docker compose exec backend pytest` passed: 255 passed, 4 skipped, 6 warnings in 5.38s.
- **Notes:** Command/service-name mismatch belongs under gaps; the test bar itself is green.

- **Criterion:** `/v1/demo/book` and `/v1/demo/disrupt` return 503 naming missing Vocal Bridge env vars.
- **Status:** PASS
- **Evidence:** `backend/tests/test_demo.py::test_book_missing_env_is_503_naming_the_var`; `backend/tests/test_demo.py::test_disrupt_missing_env_is_503_naming_the_var`.
- **Notes:** Deployed service has env present; deployed failures were 502 call-credit errors, not 503 missing env.

- **Criterion:** `/book` happy path places the call before trip write, injects trip narrative, and returns exactly `{trip_id, call_id, call_status}` without phone/API leakage.
- **Status:** PASS
- **Evidence:** `backend/tests/test_demo.py::test_book_places_call_before_seeding_and_returns_exact_shape`; `backend/tests/test_demo.py::test_book_purpose_carries_the_trip_narrative`; implementation in `backend/api/demo.py`.
- **Notes:** Deployed happy path could not be observed because `vb_cli.place_call` failed with exhausted destination credit.

- **Criterion:** `/book` call failure returns 502 with scrubbed error and does not seed a trip.
- **Status:** PASS
- **Evidence:** `backend/tests/test_demo.py::test_book_call_failure_is_502_scrubbed_and_seeds_nothing`; deployed `POST /v1/demo/book` returned HTTP 502 with `[redacted]` and credit-exhausted error. BigQuery query for titles `Validator rehearsal 2026-07-10%` returned `[]`.
- **Notes:** This failure behavior worked correctly on Cloud Run.

- **Criterion:** `/disrupt` happy path breaks flight via `break_trip_flight`, launches repairs via `launch_trip_repairs` without awaiting, and returns `repair_session_id` plus five launched names.
- **Status:** PASS
- **Evidence:** `backend/tests/test_demo.py::test_disrupt_calls_then_breaks_then_launches_repairs`; source shows `launch_trip_repairs(...)` result is returned without awaiting task completion.
- **Notes:** Deployed `/v1/demo/disrupt` happy path was blocked by Vocal Bridge credit failure before the break step.

- **Criterion:** `/disrupt` against a trip with no flight item returns 404.
- **Status:** PASS
- **Evidence:** `backend/tests/test_demo.py::test_disrupt_404_passes_through_when_trip_has_no_flight`.
- **Notes:** No deployed no-flight run attempted; call-credit failure would occur first.

- **Criterion:** `GET /v1/demo/` serves HTML.
- **Status:** PASS
- **Evidence:** Deployed `GET /v1/demo/` returned HTTP 200, `content-type: text/html; charset=utf-8`, `content-length: 22136`; `backend/tests/test_demo.py::test_demo_page_is_served_as_html`.
- **Notes:** Static HTML includes `Trigger call` enabled and `Flight canceled` disabled initially.

- **Criterion:** Pre-existing suites still pass, especially seed/break endpoint tests.
- **Status:** PASS
- **Evidence:** `docker compose exec backend pytest`: 255 passed, 4 skipped. Includes `tests/test_sabre_tools.py`, `tests/test_disruption.py`, and `tests/test_itinerary_ui.py`.
- **Notes:** Warnings include existing un-awaited coroutine warnings in one Sabre-tools failure-path test.

- **Criterion:** Deployed page renders with "Trigger call" enabled and "Flight canceled" disabled.
- **Status:** PASS
- **Evidence:** Deployed page HTTP 200; `backend/api/assets/demo/page.html` renders `btn-book` enabled and `btn-cancel` with `disabled`.
- **Notes:** I did not use a browser screenshot; this is HTTP/source evidence.

- **Criterion:** Beat 1 - pressing "Trigger call" rings the operator phone, agent narrates booking, five cards render `booked`, and "Flight canceled" becomes enabled.
- **Status:** FAIL
- **Evidence:** Deployed `POST /v1/demo/book` returned HTTP 502: `vb call [redacted] --name demo-beat1-booking failed: Error: Outbound call credit exhausted for this destination.`
- **Notes:** The error is scrubbed and no trip was seeded for the failed attempts.

- **Criterion:** Beat 2 - pressing "Flight canceled" rings again, agent opens with cancellation/rebooking line, page flips broken -> repairing -> fixed, feed narrates, timer runs.
- **Status:** FAIL
- **Evidence:** Deployed `POST /v1/demo/disrupt` against a valid direct-repair trip returned HTTP 502: `vb call [redacted] --name demo-beat2-disruption failed: Error: Outbound call credit exhausted for this destination.`
- **Notes:** The endpoint calls Vocal Bridge before breaking the trip, so the strict demo beat does not start while credits are exhausted.

- **Criterion:** Hard gate - broken -> all five fixed in under 60 seconds on the page timer.
- **Status:** UNTESTABLE
- **Evidence:** Strict page-timer rehearsal could not run because both call beats fail. Supporting data-path evidence: direct deployed `seed_trip` + `break_flight` + waited `repair_trip` completed in `real 21.30`; status endpoint then showed five `fixed` items and `all_clear: true`.
- **Notes:** Data path is under 60 seconds; strict voice/page run remains unproven.

- **Criterion:** BigQuery spot check shows fresh `updated_at` item flips and repair bookings.
- **Status:** PASS
- **Evidence:** For direct trip `66066e67-411b-487a-8d12-7c2586059696`, BigQuery showed five `fixed` rows with `updated_at` from `2026-07-10 11:49:11` through `11:49:26`; bookings query returned `booking_count=7`, `confirmed_count=7`.
- **Notes:** This validates the non-call deployed repair path, not the blocked `/v1/demo/*` two-beat path.

- **Criterion:** `GET /v1/outbound_call/status` after each beat returns a session transcript without phone/API leakage.
- **Status:** UNTESTABLE
- **Evidence:** No successful deployed beat occurred. Baseline deployed `GET /v1/outbound_call/status` returned a prior completed outbound session with transcript, `caller_phone:null`, and no API key.
- **Notes:** The prior transcript was not a Phase 12 demo call.

- **Criterion:** Pressing "Trigger call" twice does not create a second trip mid-demo.
- **Status:** UNTESTABLE
- **Evidence:** Source disables the button immediately on click and keeps it disabled after success; failed calls re-enable it. No browser/manual success run occurred.
- **Notes:** No automated browser test covers double-click behavior.

- **Criterion:** "Flight canceled" before a trip is live is impossible or safely rejected.
- **Status:** PASS
- **Evidence:** HTML initializes `btn-cancel` as disabled; JS only enables it after a booked trip is observed; `backend/tests/test_demo.py::test_disrupt_requires_trip_id` asserts missing `trip_id` is 422.
- **Notes:** API still requires explicit `trip_id`.

- **Criterion:** A failed beat shows an on-page projector-readable error, never a dead button.
- **Status:** PASS
- **Evidence:** `backend/api/assets/demo/page.html` routes non-OK `/book` and `/disrupt` responses through `showError(...)` and re-enables the relevant button.
- **Notes:** I verified source behavior, not a live browser rendering.

- **Criterion:** `/v1/disruption/break_flight` still works standalone.
- **Status:** PASS
- **Evidence:** Deployed `POST /v1/disruption/break_flight` for trip `66066e67-411b-487a-8d12-7c2586059696` returned HTTP 200 with `previous_status:"booked"`, `status:"broken"`, `affected_rows:1`.
- **Notes:** Follow-up status poll showed `broken:1`.

- **Criterion:** Page copy is traveler-voiced and projector-legible with no debug jargon visible.
- **Status:** PASS
- **Evidence:** `backend/api/assets/demo/page.html` uses traveler-facing copy such as `Your trip is booked and everything looks good`, `Cascade is actively repairing your itinerary`, and red-strip operator errors. Runbook also notes a real projector/browser risk: Dark Reader can invert the intended palette.
- **Notes:** No visual screenshot was captured in this validation.

- **Criterion:** Both call purposes are calm, concrete, and avoid internal IDs/tool names.
- **Status:** PASS
- **Evidence:** `_book_purpose(...)` and `_DISRUPT_PURPOSE` in `backend/api/demo.py`; tests `test_book_purpose_carries_the_trip_narrative` and `test_disrupt_purpose_is_the_cancellation_script`.
- **Notes:** Deployed audio/transcript for these purposes was not produced because calls failed.

- **Criterion:** Automated suite green in CI and locally.
- **Status:** AMBIGUOUS
- **Evidence:** Local container pytest is green. I did not verify a Cloud Build/CI run for commit `eb76fb2`.
- **Notes:** CI status should be attached before merge.

- **Criterion:** One clean uninterrupted two-beat deployed run, under-60 recovery, timings recorded in runbook.
- **Status:** FAIL
- **Evidence:** Both deployed call beats return HTTP 502 due exhausted outbound call credit. `runbook.md` records only a partial data-path run, with calls blocked.
- **Notes:** This is the headline release blocker.

- **Criterion:** Runbook complete: preconditions, script, timings, recovery moves, call-ordering note.
- **Status:** PARTIAL
- **Evidence:** `specs/2026-07-10-dress-rehearsal/runbook.md` contains preconditions, two-beat script, recovery moves, a partial Cloud Run data-path timing, and a call-ordering section.
- **Notes:** The call-ordering note remains unanswered because no successful second call occurred.

- **Criterion:** Phase 12 marked `[x] COMPLETE` in `specs/roadmap.md`.
- **Status:** PASS
- **Evidence:** `specs/roadmap.md` heading reads `Phase 12: Dress rehearsal - the cascade, end to end [x] COMPLETE (implementation; manual QA pending)`.
- **Notes:** The qualifier matches this report: implementation is present, strict manual QA is not passing.

## Missing tests

- `backend/tests/test_demo_page_validator.py::test_failed_demo_call_renders_operator_error` - browser or JS-level test that stubs `/v1/demo/book` to 502 and asserts the red error strip text is visible and the button is re-enabled.
- `backend/tests/test_demo_page_validator.py::test_trigger_call_is_one_shot_after_success` - browser or JS-level test that stubs a successful `/book` response and verifies a second click cannot create another trip while the demo is live.
- `backend/tests/test_demo_page_validator.py::test_cancel_button_arms_only_after_booked_status` - browser or JS-level test that stubs status polling from empty -> booked and asserts `Flight canceled` stays disabled until booked cards render.
- No automated test can fully replace the strict Vocal Bridge phone-call rehearsal; keep that as manual/deployed evidence, but attach the Cloud Build run and call transcript IDs when successful.

## Gaps in validation.md

- Should the automated command be updated from `docker compose exec vocal-bridge-be pytest` to `docker compose exec backend pytest`, matching `docker-compose.yml`?
- What exact CI evidence is required for "automated suite green in CI" - Cloud Build URL, commit SHA, or trigger name?
- Who must confirm phone-ringing/audio transcript quality during independent validation when the callee phone is not controlled by the validator?
- Should the strict manual gate allow a degraded data-path run when Vocal Bridge credits are exhausted, or is any outbound-call 502 an automatic phase failure? Current wording implies automatic failure.

## Risks not covered by validation.md

- Vocal Bridge destination credit is now a hard external demo dependency. The runbook mentions it, but the deployed demo currently fails until credits are topped up or the destination changes.
- `GET /v1/outbound_call/status` returns the latest prior session when no successful beat occurs; an operator could mistake stale transcript/status for the current failed run.
- The exact page timer can restart on refresh per runbook; if that happens during judging, the under-60 evidence should be backed by wall-clock timing or recorded screen capture.
