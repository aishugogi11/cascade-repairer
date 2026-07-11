# Validation Report — Talk to My Trip: full voice demo experience (Phase 17)
**Branch:** `vb/feature/full-voice-demo`  
**Commit:** `50f3a1de441e550cb0507c1ae4f9fe3bf3d62ca8`  
**Date:** 2026-07-11

## Summary
FAIL. The implementation passes its full container test suite (289 passed, 4 skipped), and the iOS target compiles for a generic physical iPhone. The deployed service is nevertheless fail-open because `DEMO_ACCESS_CODE` is absent, and its Cloud Run revision has `maxScale=100` with no `minScale`, violating the required single-instance configuration. Physical-iPhone, live Vocal Bridge, BigQuery-write, outbound-call, and App Store checks remain unverified.

## Criterion-by-criterion results

### Automated — access gate
- **Criterion:** Fail-open when `DEMO_ACCESS_CODE` is unset; enforce missing/wrong/correct `X-Access-Code` behavior when set; preserve the public allowlist; validate codes through `POST /v1/auth/validate`; wire all four HTML pages through `?code=`, `localStorage`, and request headers.
- **Status:** PASS
- **Evidence:** `docker compose exec backend pytest` passed `backend/tests/test_access_gate.py` (10 tests). Implementation is in `backend/api/access_gate.py`, `backend/api/auth.py`, `backend/main.py`, and the four page sources.
- **Notes:** This is an implementation/test pass only. The deployed gate is not armed; see the deployed gate criterion below.

### Automated — guided booking
- **Criterion:** Search and retain 2–3 spoken flight options; fail speakably; reject missing/bad selections without writes; persist a valid selection and replace the session pin; build the remaining four items with ~1.5-second spacing; expose the new guided tools and retain disruption instructions.
- **Status:** PASS
- **Evidence:** `docker compose exec backend pytest` passed all 21 tests in `backend/tests/test_concierge.py`, including `test_search_flights_stores_options_and_speaks_them`, `test_search_flights_failure_is_speakable_never_raises`, `test_book_flight_without_search_is_speakable_and_writes_nothing`, `test_book_flight_bad_option_number_is_speakable_and_writes_nothing`, `test_book_flight_creates_rows_replaces_pin_and_clears_options`, `test_complete_trip_spaces_items_and_returns_immediately`, and `test_instructions_carry_the_guided_script`. Tool exposure is asserted in the same file.
- **Notes:** Repository boundaries are mocked, as required for hermetic CI.

### Automated — detail payload
- **Criterion:** Include `detail` for items with bookings, omit it for items without bookings, and preserve the existing status contract.
- **Status:** PASS
- **Evidence:** `backend/tests/test_itinerary_ui.py::test_status_detail_for_voice_booked_flight`, `::test_status_detail_for_repaired_item_and_latest_booking_wins`, and `::test_status_detail_read_failure_never_breaks_the_poll` passed with the full pre-existing itinerary tests.
- **Notes:** Detail is additive and a failed booking-detail read does not break polling.

### Automated — hermeticity and buildability
- **Criterion:** Run without GCP credentials or `OPENAI_API_KEY`, with pytest gating deployment.
- **Status:** PASS
- **Evidence:** The mandated container command completed with 289 passed and 4 skipped in 5.39 seconds. A separate unsigned device build also completed with `** BUILD SUCCEEDED **`: `xcodebuild -project ios/TalkToMyTrip/TalkToMyTrip.xcodeproj -scheme TalkToMyTrip -configuration Debug -sdk iphoneos -destination generic/platform=iOS -derivedDataPath /private/tmp/TalkToMyTripDerivedData CODE_SIGNING_ALLOWED=NO build`.
- **Notes:** The pytest run emitted six warnings, including five un-awaited repair coroutine warnings; see Risks.

### Manual 1 — deployed gate walkthrough
- **Criterion:** With `DEMO_ACCESS_CODE` set on Cloud Run, protected calls reject missing credentials and a correct code persists across page reloads.
- **Status:** FAIL
- **Evidence:** Against revision `vocal-bridge-be-dev-00063-s86`, unauthenticated `GET /v1/hello/gcp_check` returned 200, and `POST /v1/auth/validate` with `validator-deliberately-wrong` returned `200 {"valid":true}`. `gcloud run services describe ... --format=value(spec.template.spec.containers[0].env.name)` listed no `DEMO_ACCESS_CODE` variable.
- **Notes:** The public privacy and web-call pages correctly returned 200. Correct-code behavior cannot be exercised until the env var is configured.

### Manual 2 — Act 1 browser booking
- **Criterion:** Complete guided voice booking in the deployed browser, observe staggered cards, and confirm `trips`, `itinerary_items`, and `bookings` rows.
- **Status:** UNTESTABLE
- **Evidence:** Automated tool and persistence-boundary tests pass, but no live Vocal Bridge session, correct access code, or BigQuery write walkthrough was available in this validation session.
- **Notes:** Requires operator voice input and deployed credentials.

### Manual 3 — Act 2 browser repair
- **Criterion:** Disrupt a trip, repair all five cards in under 60 seconds, and receive a specific agent progress answer mid-repair.
- **Status:** UNTESTABLE
- **Evidence:** Existing concurrency tests passed, including `backend/tests/test_concierge.py::test_talk_while_repairing_acceptance_shape`; no deployed end-to-end disruption was run.
- **Notes:** The manual latency and spoken-answer claim remains open.

### Manual 4 — iOS gate
- **Criterion:** Exercise fresh-install gate, rejection, persistence, and server-side rotation behavior on device.
- **Status:** UNTESTABLE
- **Evidence:** The iOS target compiles. Static inspection found the gate-first root view, Keychain persistence, friendly error copy, header attachment, and 401-triggered relock in `TalkToMyTripApp.swift`, `AccessManager.swift`, `KeychainHelper.swift`, and `APIService.swift`.
- **Notes:** Fresh-install and relaunch behavior requires a physical device; rotation also requires an armed deployed gate.

### Manual 5 — three acts on device
- **Criterion:** Book by voice, render the repair cascade under 60 seconds while conversing, receive the outbound recovery call, and archive the recording.
- **Status:** UNTESTABLE
- **Evidence:** The app compiles and the relevant backend tests pass; no physical-device/Vocal Bridge run or recording retrieval occurred.
- **Notes:** One run consumes two calls from the daily quota.

### Manual 6 — sheet and hidden gestures
- **Criterion:** Show recommendation detail or fallback on card tap, open recent-trip selection by long press, disrupt by triple tap, and expose no visible demo buttons.
- **Status:** UNTESTABLE
- **Evidence:** Static implementation exists in `RecommendationSheet.swift`, `TripSelectorSheet.swift`, `TripTimelineView.swift`, and `ContentView.swift`; all compile in the device build.
- **Notes:** Gesture precedence, presentation, and stage readability require device observation.

### Manual 7 — edge cases
- **Criterion:** Handle invalid options, pinned-trip rebooking, backend restart, and desktop loading of the headless webview.
- **Status:** UNTESTABLE
- **Evidence:** Invalid-option behavior and pinned-trip instructions have passing automated tests. The page contains the desktop no-op event seam. Backend restart recovery and actual agent adherence were not observed.
- **Notes:** This criterion combines automated and live behavioral claims; the live portion prevents a PASS.

### Manual 8 — deployment health and scaling
- **Criterion:** Return green GCP health and run with `min-instances=1` and `max-instances=1`.
- **Status:** FAIL
- **Evidence:** Deployed `GET /v1/hello/gcp_check` returned BigQuery `ok` and GCS `ok`. Cloud Run revision annotations report `autoscaling.knative.dev/maxScale=100` and no `minScale`.
- **Notes:** In-process session state is unsafe under the deployed scaling configuration.

### Tone check
- **Criterion:** Keep new spoken copy concise and speakable; use demo-honest gate copy and glanceable recommendation copy.
- **Status:** PASS
- **Evidence:** Spoken-option tests reject codes/markdown and assert rounded prices; all tested tool failure paths return strings. `AccessGateView.swift` uses “Enter the access code from your demo invitation” and friendly rejection copy. Recommendation detail is one sentence per field in backend mappings and Swift fallbacks.
- **Notes:** Live model adherence remains part of the untested voice walkthroughs.

### Definition of done
- **Criterion:** Green local/CI automation; armed deployed gate; physical-device Acts 1–3; shipped sheet/gestures/polish; archived/uploaded update with review code; Phase 17 marked complete.
- **Status:** FAIL
- **Evidence:** Local automation, compilation, implementation files, and the roadmap completion marker are present. The deployed gate and scaling checks fail. Physical-device verification and App Store Connect archive/upload were not evidenced in this session.
- **Notes:** A completed PR/deploy does not satisfy the explicit runtime configuration and device-release requirements.

## Missing tests
- No automated deployed-config check asserts that `DEMO_ACCESS_CODE` exists or that Cloud Run is pinned to `minScale=1`/`maxScale=1`. Add a post-deploy smoke step in `backend/devops/cloudbuild.yaml` (or a read-only release-check script) that asserts both configuration contracts and verifies a protected endpoint returns 401 without a header.
- No iOS test target covers gate persistence or 401 relocking. Add `TalkToMyTripTests/AccessManagerTests.swift` with injected Keychain/API seams to assert wrong-code rejection, successful unlock, persisted relaunch, and rotation relock.
- No iOS UI test covers triple-tap versus single-tap precedence, long-press trip selection, card-sheet presentation, or absence of visible demo controls. Add `TalkToMyTripUITests/DemoGesturesTests.swift` against a stub backend.
- The live voice, BigQuery row, under-60-second repair, outbound-call, recording, restart-recovery, and App Store upload criteria are intentionally manual and have no automated coverage.

## Gaps in validation.md
- What durable artifact should prove the physical-iPhone run: a dated checklist, screen recording, or captured logs?
- What artifact should prove the App Store archive/upload and App Review notes without exposing the shared code?
- Should “CI is green” require a specific Cloud Build ID/revision in the report?
- Manual edge case 7 combines independently passable automated and live claims; should it be split so invalid-option coverage can receive a definitive PASS?

## Risks not covered by validation.md
- The passing pytest run emitted five `RuntimeWarning: coroutine ... was never awaited` warnings from `backend/api/concurrency_core.py:89` during `test_repair_trip_failed_write_surfaces_as_error_event`. These can hide leaked repair work or misleading test behavior.
- `complete_trip` reports success immediately, while background write failures only log and stop. A partial four-item build can therefore be spoken as underway without a later user-visible error state.
