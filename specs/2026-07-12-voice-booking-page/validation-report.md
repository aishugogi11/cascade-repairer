# Validation Report — Voice Booking Page (Phase 21)
**Branch:** `vb/feature/voice-booking-page`  
**Commit:** `a4382dbf9566f4100f3acffbed561a516bb06bed`  
**Date:** 2026-07-12

## Summary

PARTIAL. All automated criteria pass: the full container suite reports 331 passed and 4 skipped, the 27 focused acceptance tests pass, and the full suite also passes with OpenAI and GCP credentials explicitly removed. A live request through `POST /v1/web_call/query` returned the three deterministic mock options in speakable form. Definition of done is not established because the required browser walkthrough and rendered side-by-side design/tone checks were not completed: the local backend has no GCP ADC for trip reads/writes, and Safari WebDriver is disabled in Safari settings. No production or test code was changed.

## Criterion-by-criterion results

### Automated

- **Criterion:** All tests pass with no regressions.
- **Status:** PASS
- **Evidence:** `docker compose exec -T backend python -m pytest tests/ -q` → `331 passed, 4 skipped, 7 warnings in 5.45s`.
- **Notes:** The four skipped tests were not part of the required Phase 21 assertions; warnings are listed under risks.

- **Criterion:** `search_flights_impl` records the latest-search slot; `book_flight_impl` clears it on success.
- **Status:** PASS
- **Evidence:** `backend/tests/test_concierge.py::test_search_flights_records_the_latest_search_slot`, `::test_second_search_replaces_the_latest_search_slot`, `::test_book_flight_clears_the_latest_search_slot`, and `::test_book_flight_leaves_another_sessions_slot_alone` all pass.
- **Notes:** The slot is stamped with an aware UTC `recorded_at`; a booking clears only its own session's slot.

- **Criterion:** Status carries `pending_options` for a session pinned to the requested trip and for an unpinned session.
- **Status:** PASS
- **Evidence:** `backend/tests/test_itinerary_ui.py::test_status_pending_options_for_unpinned_session` and `::test_status_pending_options_for_session_pinned_to_this_trip` pass.
- **Notes:** The payload assertions cover option numbers, route, speakable times, stops, rounded prices, and absence of airline codes.

- **Criterion:** `pending_options` is omitted for an empty slot, a differently pinned session, or a slot-read failure; failure does not break the poll.
- **Status:** PASS
- **Evidence:** `backend/tests/test_itinerary_ui.py::test_status_omits_pending_options_when_slot_empty`, `::test_status_omits_pending_options_pinned_to_a_different_trip`, and `::test_status_pending_options_read_failure_never_breaks_the_poll` pass.
- **Notes:** The failure case returns HTTP 200 with the normal trip payload intact.

- **Criterion:** Existing status consumers remain unchanged; the contract is additive-only.
- **Status:** PASS
- **Evidence:** The full 331-test suite passes. Focused regressions `test_status_detail_for_voice_booked_flight` and `test_status_detail_read_failure_never_breaks_the_poll` pass, and `trip_status` adds `pending_options` only when the best-effort helper returns a non-empty block.
- **Notes:** Existing `trip`, `items`, `summary`, `fetched_at`, and `detail` assertions remain green.

- **Criterion:** `GET /v1/booking/` is public as a page shell while gated JSON APIs still return 401 without the access header.
- **Status:** PASS
- **Evidence:** `backend/tests/test_booking_ui.py::test_shell_served_without_code_when_gate_armed`, `::test_gated_json_endpoints_still_401_without_code`, `backend/tests/test_access_gate.py::test_allowlisted_gets_stay_public`, and `::test_other_gated_routes_401_without_code` pass.
- **Notes:** The router is mounted in `backend/main.py`; the shell is added to `_PUBLIC_PAGES` only.

- **Criterion:** Tests are hermetic and require neither GCP credentials nor `OPENAI_API_KEY`.
- **Status:** PASS
- **Evidence:** `docker compose exec -T -e OPENAI_API_KEY= -e GOOGLE_APPLICATION_CREDENTIALS= backend python -m pytest tests/ -q` → `331 passed, 4 skipped`.
- **Notes:** A live local trip-list request separately failed for missing ADC, confirming the runtime did not silently have GCP credentials available.

### Manual walkthrough

- **Criterion:** Cold start shows awaiting state and a populated, newest-first, PT-labeled recent-trip selector; selecting a trip renders its cards.
- **Status:** AMBIGUOUS
- **Evidence:** Static tests `test_page_has_an_awaiting_state` and `test_page_recent_trips_sorted_newest_first_with_created_labels` pass. In `backend/api/assets/booking/page.html`, `init()` renders awaiting, then the first successful `checkLatest()` immediately adopts the latest trip when no `?trip_id=` is present.
- **Notes:** It is unclear whether a brief awaiting state before automatic latest-trip adoption satisfies “shows the awaiting state,” or whether the page must remain awaiting until the operator selects a trip.

- **Criterion:** A search through `/v1/web_call/query` makes three matching candidates appear within about 1.5 seconds.
- **Status:** UNTESTABLE
- **Evidence:** A live local query in `SABRE_MODE=mock` returned three spoken options with times and rounded prices: $188, $242, and $155. Backend/presentation tests for `pending_options`, the 1.5-second poll, and candidate rendering all pass.
- **Notes:** The candidate panel itself was not browser-observed, so timing and rendered agreement with the spoken reply remain unverified.

- **Criterion:** Booking option N clears candidates and shows the chosen current-flight card without a reload, including `detail` when present.
- **Status:** UNTESTABLE
- **Evidence:** Unit tests prove successful booking clears the slot; page tests prove disappearing `pending_options` clears the panel; status tests prove voice-booking `detail`; static code re-resolves `latest_trip_id` every four seconds.
- **Notes:** The end-to-end booking write requires a functioning trip repository; the local app has no GCP ADC.

- **Criterion:** `complete_trip` materializes hotel, ground, dining, and experience cards over successive polls.
- **Status:** UNTESTABLE
- **Evidence:** The full suite covers `complete_trip` item construction/background behavior, and the page renders every non-flight item returned by status.
- **Notes:** Successive browser-visible materialization was not observed against a live repository.

- **Criterion:** `?trip_id=` seeds the displayed trip and `window.vbSetTrip('<id>')` repoints polling.
- **Status:** UNTESTABLE
- **Evidence:** `backend/tests/test_booking_ui.py::test_page_honors_the_trip_pinning_contract` passes; static code reads `searchParams.get("trip_id")` and exposes `window.vbSetTrip` through `resetForTrip`.
- **Notes:** The console interaction and subsequent network polling were not browser-observed.

- **Criterion:** Unknown trips, missing access code, a second search, and backend interruption/recovery behave gracefully.
- **Status:** UNTESTABLE
- **Evidence:** Static code handles 404, non-OK responses, and fetch exceptions without stopping either interval. Tests cover shell-without-code, gated JSON, second-search replacement, and awaiting/candidate-clear states.
- **Notes:** The complete scripted edge-case sequence, especially kill/restart recovery without reload, was not executed in a browser.

### Design check

- **Criterion:** The page reads as the same product as the mockup: header, left rail, traveler context, timeline, recent trips, and card/pill/color language.
- **Status:** UNTESTABLE
- **Evidence:** The source image `about/ui_ideas/ui_mockup_2026_07_09.png` was inspected. `test_page_carries_the_mockup_frame` passes, and the HTML/CSS contains all named surfaces and the blue/white card/pill treatment.
- **Notes:** Safari could not be automated because “Allow remote automation” is disabled, so the rendered page was not inspected side-by-side.

- **Criterion:** The candidate panel visually matches the mockup's “AI Recommended” treatment.
- **Status:** UNTESTABLE
- **Evidence:** Static markup/CSS uses a blue `AI Recommended` header, bordered option cards, prominent arrival/price copy, and option pills; `test_page_renders_pending_options_as_the_candidates_panel` passes.
- **Notes:** Visual matching remains subjective until rendered side-by-side.

- **Criterion:** Voice and repair surfaces are absent without leaving broken-looking gaps.
- **Status:** UNTESTABLE
- **Evidence:** Source inspection finds none of the orb, conversation feed, Sabre log, recovery timer/banner, or downstream-impact panel. The base grid is two columns and adds the candidates column only when populated.
- **Notes:** Absence is verified statically; whether the remaining space looks intentional requires rendered inspection.

### Tone check

- **Criterion:** Times are Pacific and labeled “PT,” never “PST” or browser-local.
- **Status:** PASS
- **Evidence:** `test_page_renders_times_pacific_labeled_pt` and pending-option payload tests pass. Both page date formatters explicitly set `timeZone: "America/Los_Angeles"`; candidate labels append `PT`; `PST` is absent.
- **Notes:** Backend options are Pacific wall-clock strings by the Phase 19 contract.

- **Criterion:** Prices match the Concierge's rounded speech and headline copy contains no airline codes.
- **Status:** PASS
- **Evidence:** The live `/query` response spoke rounded prices; `pending_options_for_trip` applies Python `round`, the page uses `fmtPrice`, and `test_status_pending_options_for_unpinned_session` asserts airline fields/codes are absent.
- **Notes:** Candidate copy uses route, times, stops, price, and option number only.

- **Criterion:** Copy is traveler-voiced and stage-readable with large type and high contrast.
- **Status:** UNTESTABLE
- **Evidence:** Static copy is traveler-facing, and CSS specifies prominent 19–28 px candidate/flight headlines on white/blue surfaces.
- **Notes:** Projector readability and effective contrast were not observed on a rendered page.

### Definition of done

- **Criterion:** Automated suite is green with all required assertions.
- **Status:** PASS
- **Evidence:** 331 passed, 4 skipped; focused acceptance run → 27 passed.
- **Notes:** Credential-free rerun also passed.

- **Criterion:** Manual walkthrough steps 1–6 pass in local `SABRE_MODE=mock`.
- **Status:** UNTESTABLE
- **Evidence:** The local shell runs and the live mock search succeeds, but trip endpoints return HTTP 500 because local GCP ADC is unavailable; browser automation is disabled.
- **Notes:** This criterion remains open.

- **Criterion:** The pre-disruption beat works end to end on one screen before disruption.
- **Status:** UNTESTABLE
- **Evidence:** Component and integration tests pass, but the candidate-to-five-item browser sequence was not observed end to end.
- **Notes:** This criterion remains open.

- **Criterion:** `specs/tech-stack.md` is updated and Phase 21 is marked complete in `specs/roadmap.md`.
- **Status:** PASS
- **Evidence:** `specs/tech-stack.md` documents the booking page and `pending_options`; `specs/roadmap.md` marks Phase 21 `[x] COMPLETE (implementation; manual QA pending)`.
- **Notes:** The roadmap accurately preserves the outstanding manual QA.

## Missing tests

- The manual candidate → booking → five-item sequence has no executable browser test, by the standing no-browser-automation decision. If that decision changes, add `backend/tests/browser/test_booking_walkthrough_validator.py::test_mock_booking_walkthrough`: stub the repository/API boundary, advance polling time, and assert awaiting, candidate display, candidate clear, latest-trip adoption, and four successive reservation additions.
- Pinning and recovery are only static/unit-tested. If browser coverage is allowed, add `backend/tests/browser/test_booking_walkthrough_validator.py::test_pin_unknown_trip_and_recover`: assert `?trip_id=`, `vbSetTrip`, 404 awaiting behavior, fetch failure, and recovery without reload.
- Visual fidelity and projector readability have no automated coverage. If visual regression testing is adopted, add `backend/tests/browser/test_booking_visual_validator.py::test_booking_mockup_frame` with fixed viewport/data and an approved baseline; separately run an accessibility contrast/font-size audit.
- No validator-written tests were added because `validation.md` explicitly keeps these checks manual and rejects a browser-automation dependency.

## Gaps in validation.md

- Must cold start remain on the awaiting state until the operator selects a recent trip, or does the current brief awaiting state followed by first-run `latest_trip_id` adoption satisfy step 1? `requirements.md` requires both awaiting and latest-trip re-resolution but does not define precedence or dwell time.
- What is the canonical credential/data setup for the required local walkthrough? The local app boots without credentials, but the trip repository cannot serve or write walkthrough data without GCP ADC.
- What viewport, projector resolution, minimum font size, and contrast threshold define “stage-readable” and “high contrast” for an objective pass/fail design check?
- Is the “within ~1.5 s” candidate requirement measured from the `/query` response, from latest-search recording, or to the next completed status poll? The current polling phase can add nearly a full interval before network/render time.

## Risks not covered by validation.md

- The full suite emits runtime warnings for unawaited coroutines in concurrency tests. Tests pass, but these warnings can hide task cleanup defects.
- `_LATEST_SEARCH` has no expiry. An abandoned or failed-to-book conversation can leave stale candidates visible indefinitely until another search or a successful booking replaces/clears the slot.
