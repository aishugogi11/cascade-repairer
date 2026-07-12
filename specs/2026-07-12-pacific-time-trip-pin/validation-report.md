# Validation Report — Pacific-time discipline & pin the displayed trip
**Branch:** `vb/dev` (`vb/feature/pacific-time-trip-pin` points to the same commit)  
**Commit:** `be3937aee26c00e5d79c3902095aa3ebdf35d431`  
**Date:** 2026-07-12

## Summary
PARTIAL. The implementation and required automated coverage pass: the exact container command completed with 307 passed and 4 repo-root-only skips, those 4 tests passed when rerun with the repository mounted, all 11 focused Phase 19 tests passed, and the iOS simulator build succeeded. The deployed Cloud Run revision `vocal-bridge-be-dev-00073-299` also runs image tag `be3937a`. Acceptance is not complete because the live voice/browser/device, unchanged-binary, legacy-row, and App Store checks could not be observed in this session. One definition-of-done item is a definite FAIL: merged PR #31 has an empty body and no comments, so it does not contain the required iOS no-time-rendering and accepted old-row-skew notes.

## Criterion-by-criterion results

### Automated

- **Criterion:** A `06:15` mock departure written by `_booking_writes` stores the July instant `13:15Z`.
- **Status:** PASS
- **Evidence:** `backend/tests/test_concierge.py::test_booking_writes_declare_pacific_wall_clock` passed. `backend/api/concierge.py` assigns `ZoneInfo("America/Los_Angeles")`; a `google.cloud.bigquery.ScalarQueryParameter("TIMESTAMP", ...)` probe serialized the value as `2026-07-13 13:15:00+00:00`.
- **Notes:** This verifies both the model value and the BigQuery client serialization boundary.

- **Criterion:** `_completion_items` and `_SEED_ITEMS` use the same Pacific-to-UTC conversion.
- **Status:** PASS
- **Evidence:** `backend/tests/test_concierge.py::test_completion_items_declare_pacific_wall_clock` and `backend/tests/test_sabre_tools.py::test_seed_items_declare_pacific_wall_clock` passed.
- **Notes:** The tests cover a 7 PM dinner becoming `02:00Z`, a 10 PM hotel start becoming `05:00Z`, and the seed flight's 8 AM becoming `15:00Z` in July.

- **Criterion:** `answer_query(session, query, trip_id=...)` pins the passed trip and places its summary in agent instructions.
- **Status:** PASS
- **Evidence:** `backend/tests/test_concierge.py::test_answer_query_trip_id_pins_the_displayed_trip` passed; `backend/api/concierge.py::answer_query` forwards the value to cache-first `ensure_trip_context`.
- **Notes:** The test asserts the pinned ID and authoritative trip summary, not merely function-call plumbing.

- **Criterion:** A pinned session queried with a different `trip_id` retains the original pin.
- **Status:** PASS
- **Evidence:** `backend/tests/test_concierge.py::test_answer_query_trip_id_never_clobbers_an_existing_pin` passed and asserts no repository read for the second ID.
- **Notes:** This directly covers pin-only-if-unpinned behavior.

- **Criterion:** Calling `answer_query` without `trip_id` still reaches `search_flights` for a fresh session.
- **Status:** PASS
- **Evidence:** The unchanged Phase 18 test `backend/tests/test_concierge.py::test_fresh_session_booking_reaches_search_flights` passed. `git diff HEAD^1..HEAD` shows no Phase 19 modification to that test.
- **Notes:** The test uses a non-empty trips-table fixture and invokes the real `search_flights` function tool against the mock Sabre client.

- **Criterion:** `POST /v1/web_call/query` forwards `trip_id`; omitting it preserves prior behavior.
- **Status:** PASS
- **Evidence:** `backend/tests/test_web_call.py::test_query_forwards_trip_id_to_the_seam`, `::test_query_without_trip_id_reaches_the_seam_as_none`, and `::test_query_blank_trip_id_normalizes_to_none` passed. The omitted-field response remains `{"response":"seam reply"}` and the seam receives `None`.
- **Notes:** The test compares response shape/content, not a stored pre-Phase-19 raw-byte fixture; see Gaps.

### Manual timezone walkthrough

- **Criterion:** A fresh voice-booked flight is spoken and rendered on `/v1/itinerary/` at the same PT wall-clock time.
- **Status:** UNTESTABLE
- **Evidence:** Component evidence is green: the `06:15` write becomes `13:15Z`, `_spoken_clock` says `6:15 AM`, and the itinerary formatter renders `13:15Z` as `6:15 AM PT`. No live Vocal Bridge/OpenAI booking plus itinerary observation was performed.
- **Notes:** The deployed service is on the validated commit, but the gated live workflow requires credentials and creates external records.

- **Criterion:** `/v1/demo/` cards and both pages' repair-feed clocks show Pacific time labeled PT.
- **Status:** UNTESTABLE
- **Evidence:** `backend/tests/test_demo.py::test_demo_page_renders_times_pacific_labeled_pt` and `backend/tests/test_itinerary_ui.py::test_page_renders_times_pacific_labeled_pt` passed. Deployed page source contains fixed `America/Los_Angeles` formatting and `PT` suffixes for cards and feed clocks.
- **Notes:** No live repair feed was triggered, so the full walkthrough was not observed.

- **Criterion:** Changing the viewer OS/browser timezone does not change displayed times.
- **Status:** PASS
- **Evidence:** The page formatter was executed under `TZ=America/Chicago`, `TZ=UTC`, and `TZ=Asia/Tokyo`; all three rendered `2026-07-13T13:15:00Z` as `Jul 13, 6:15 AM PT`. Both deployed pages explicitly set `timeZone: "America/Los_Angeles"`.
- **Notes:** This exercises the ECMAScript `Date`/`Intl` behavior used by the pages without GUI browser automation.

- **Criterion:** A newly seeded trip renders `_SEED_ITEMS` wall clocks, including an 8 AM PT flight, without shifting.
- **Status:** UNTESTABLE
- **Evidence:** The seed conversion test and page formatter tests pass independently.
- **Notes:** No live seed row was created and viewed in this validation session.

- **Criterion:** Existing pre-fix development rows show the accepted approximately seven-hour skew and are left unchanged.
- **Status:** UNTESTABLE
- **Evidence:** `specs/roadmap.md` documents the accepted skew; no authenticated pre-fix row was inspected.
- **Notes:** The criterion depends on retained deployed data, not branch code.

### Manual trip-pin walkthrough

- **Criterion:** Desktop `/v1/web_call/?trip_id=<seed>` answers a first-turn trip question from the selected trip.
- **Status:** UNTESTABLE
- **Evidence:** The full server seam is covered by passing `test_query_forwards_trip_id_to_the_seam` and `test_answer_query_trip_id_pins_the_displayed_trip`; deployed web-call source sends the query-string ID with every delegated query.
- **Notes:** An authenticated live LLM turn against a seeded BigQuery trip was not performed.

- **Criterion:** On iOS simulator/device, asking about the displayed seed trip succeeds and “my flight was cancelled, fix it” launches repairs.
- **Status:** UNTESTABLE
- **Evidence:** The iOS project built successfully with `xcodebuild ... -sdk iphonesimulator ... CODE_SIGNING_ALLOWED=NO ... build`. `APIConfig.mobileVoiceURL`, `VoiceManager.setTrip`, `VoiceWebView`, and `ContentView.onChange` carry displayed-trip changes into `window.vbSetTrip`.
- **Notes:** Build success does not prove a live voice conversation or repair launch.

- **Criterion:** The unchanged pre-Phase-19 app binary gains trip awareness from the backend-only temporary bridge.
- **Status:** UNTESTABLE
- **Evidence:** `backend/tests/test_mobile_voice.py::test_page_temp_bridge_self_resolves_latest_trip` passed. The deployed mobile page fetches `/v1/sabre_tools/latest_trip_id`, gives it lowest precedence, and includes it in `/query` bodies.
- **Notes:** The unchanged installed binary itself was not available to this session.

- **Criterion:** When `latest_trip_id` is empty or fails, the unchanged binary still connects and guided booking remains unpinned.
- **Status:** UNTESTABLE
- **Evidence:** `backend/api/mobile_voice.py` maps non-OK responses to `null`, catches fetch failures, and omits `trip_id` when no pin exists. The server's fresh-session booking regression passes.
- **Notes:** There is no runtime JS test or unchanged-binary walkthrough covering this combined failure path.

- **Criterion:** Voice-booking a new trip does not let the previously displayed trip clobber the new booking pin.
- **Status:** UNTESTABLE
- **Evidence:** Server tests separately prove booking replaces a stale pin (`test_book_flight_creates_rows_replaces_pin_and_clears_options`) and later caller IDs cannot clobber a pin (`test_answer_query_trip_id_never_clobbers_an_existing_pin`).
- **Notes:** The combined behavior was not exercised through the iOS bridge on a device.

- **Criterion:** A session with neither `trip_id` nor a pin retains the Phase 18 guided-booking path.
- **Status:** PASS
- **Evidence:** `backend/tests/test_concierge.py::test_fresh_session_booking_reaches_search_flights` passed with a non-empty trips table. Deployed desktop page source has no `latest_trip_id` fallback.
- **Notes:** This covers the regression at the agent/tool seam; the live Vocal Bridge surface was not exercised.

### Tone check

- **Criterion:** Every rendered time uses “PT” or “Pacific time”; no rendered time uses “PST” or lacks a zone label.
- **Status:** PASS
- **Evidence:** Both page tests passed; source and deployed-page scans found two fixed-zone formatters and two PT suffixes on each page, with no `PST`. The iOS UI has no timestamp formatter or rendered timestamp field.
- **Notes:** Trip date ranges are dates rather than times and therefore do not require a time-zone label.

- **Criterion:** Every new agent-facing failure string is speakable.
- **Status:** PASS
- **Evidence:** The Phase 19 production diff adds no agent-spoken failure string. The temporary latest-trip fetch fails silently by design.
- **Notes:** Existing HTTP error strings were not introduced by this feature.

### Definition of done

- **Criterion:** Container suite is green and all six required automated assertions exist and pass.
- **Status:** PASS
- **Evidence:** `docker compose exec -T backend python -m pytest tests/ -q` reported `307 passed, 4 skipped, 7 warnings`. The four skips were repo-root contract tests unavailable inside the backend-only image; rerunning them in the same image with the repository mounted reported `4 passed`. The focused Phase 19 command reported `11 passed`.
- **Notes:** No failing test was hidden by the skips.

- **Criterion:** Both manual walkthroughs pass end to end in `SABRE_MODE=mock`.
- **Status:** UNTESTABLE
- **Evidence:** Static, unit, integration-seam, deployed-page, timezone-runtime, and build checks pass, but no live voice/browser/device walkthrough was completed.
- **Notes:** Human/external evidence is still required.

- **Criterion:** Spoken, stored-as-UTC, and displayed times agree for a fresh booking.
- **Status:** UNTESTABLE
- **Evidence:** Each component agrees for the `06:15` fixture, but no single fresh live booking traversed all three boundaries in this session.
- **Notes:** Component agreement is necessary but does not substitute for the specified end-to-end observation.

- **Criterion:** No build was archived/uploaded to App Store Connect and the in-review binary remained untouched.
- **Status:** UNTESTABLE
- **Evidence:** This validator ran only an unsigned simulator build and did not archive, sign, upload, or access App Store Connect.
- **Notes:** Repository and GitHub state cannot prove what occurred in App Store Connect before this session.

- **Criterion:** The temporary bridge is commented with its v1.0.1 removal condition and a removal reminder exists in `TODO.md`.
- **Status:** PASS
- **Evidence:** `backend/api/mobile_voice.py:74` labels the `TEMP bridge` and names v1.0.1; `TODO.md:3` contains the matching removal reminder. `test_page_temp_bridge_self_resolves_latest_trip` passes.
- **Notes:** The code, reminder, and test agree on removal timing.

- **Criterion:** PR into `vb/dev` records the iOS no-time-rendering verification and accepted legacy-row skew.
- **Status:** FAIL
- **Evidence:** GitHub PR #31 (`pacific pin`, merged as this commit) has an empty body and zero comments.
- **Notes:** Neither required note is present.

- **Criterion:** Phase 19 is marked complete in `specs/roadmap.md` after merge.
- **Status:** PASS
- **Evidence:** `specs/roadmap.md:121` says `Phase 19 ... [x] COMPLETE`; the checked-out commit is merge commit `be3937a` on `vb/dev`.
- **Notes:** The heading also accurately retains `manual QA pending`.

## Missing tests

No validator tests were added.

- `backend/tests/e2e/test_phase19_timezone_walkthrough.py::test_fresh_mock_booking_spoken_stored_and_rendered_pt_match` — drive a deterministic mock-mode booking through `/query`, capture the stored timestamp, and assert itinerary/demo rendering and spoken text agree.
- `backend/tests/e2e/test_phase19_pages.py::test_card_and_feed_times_are_identical_across_browser_timezones` — render both pages under at least Chicago, UTC, and Tokyo browser contexts and assert card/feed text is unchanged and suffixed PT. This conflicts with the current no-browser-automation standing decision and would require explicit approval.
- `backend/tests/e2e/test_phase19_trip_pin.py::test_seeded_trip_question_and_fix_use_explicit_pin` — seed a hermetic repository, run the real query seam with a deterministic agent, and assert the selected trip summary and repair launch.
- `backend/tests/browser/test_mobile_voice_trip_pin.py::test_latest_bridge_precedence_and_empty_failure` — execute the mobile-page JS with successful, 404, 500, and rejected latest-trip fetches; assert `vbSetTrip > query string > latest`, and assert empty/failure omits `trip_id` without breaking query delegation.
- `ios/TalkToMyTripUITests/TripPinVoiceUITests.swift::testDisplayedTripPinsVoiceAndNewBookingIsNotClobbered` — use a stub voice page/backend to verify initial URL pinning, post-load `vbSetTrip`, trip-question routing, repair launch, and just-booked-trip retention.
- The unchanged-binary and App Store non-upload criteria have no credible hermetic code test. They need a release artifact identifier plus App Store Connect/human attestation.
- The pre-fix-row skew criterion has no automated fixture. A disposable deployed legacy row with a known old timestamp would make it reproducible without inspecting arbitrary development data.
- PR-note compliance has no guard. A PR workflow should require the two release-note attestations before merge; a post-merge repository test cannot reconstruct missing PR prose.

## Gaps in validation.md

- What artifact is required for each live walkthrough: transcript, trip ID, screenshot/video, deployed revision, or a signed human checklist?
- Can the required iOS verification be stated directly here instead of referring to `plan.md` §4.3, which the independent-validator skill forbids reading?
- Does “byte-identical” require an assertion over raw `response.content` against a frozen pre-Phase-19 fixture, rather than the current JSON-content assertion?
- Is real Sabre mode required to convert offset-bearing schedule times to Pacific before speaking and storage? The validation walkthrough is mock-only and does not settle this.
- Who supplies evidence that App Store Connect was untouched and identifies the unchanged installed binary used for the bridge check?
- Should the legacy-row item be informational rather than pass/fail? Its observable result depends on whether any pre-fix rows still exist.

## Risks not covered by validation.md

- Real Sabre schedule offsets are discarded: `backend/api/concierge.py:272-278` reads only the first five characters for speech, and lines 316-317 store only `HH:MM`. A real `06:15:00-05:00` departure is therefore spoken and persisted as 6:15 Pacific rather than converted to Pacific, even though mock-mode tests pass.
- The temporary mobile bridge selects the globally newest trip (`backend/api/sabre_tools.py:268-284`), not a user-scoped trip. Until native v1.0.1 removes it, concurrent users can pin the wrong traveler's itinerary.
- The green suite emits six unawaited-coroutine warnings around concurrency cleanup/error tests, plus one dependency deprecation warning. They are pre-existing and outside Phase 19 criteria, but can conceal async lifecycle defects.
