# Validation Report — Phase 31: Phase 23 close-out — the consent flow works live
**Branch:** `vb/dev`  **Commit:** `debf36fda24283af741c90e1adaebca43b477226`  **Date:** 2026-07-15

## Summary
FAIL. The implementation is hermetically healthy: the bare suite and current in-image Cloud Build are green, the two adopted validator tests pass, and the session join, different-flight selection, stale-watcher gate, `fix_trip` deferral, and live-shaped integration contracts all pass. The acceptance package is incomplete: the required two-call live rerun was not authorized, PR #55 still has its placeholder body, Phases 23/31 remain marked manual-QA-pending, and there is no dedicated automated assertion for the required `broken`-status all-clear suppression. The validator remained blind to `plan.md`.

## Criterion-by-criterion results

### 1. Bare suite green, including both adopted validator tests
- **Criterion:** `docker compose exec backend pytest` is green, including both tests in `test_validator_cascade_live_voice_demo.py`.
- **Status:** PASS
- **Evidence:** The canonical command completed with `482 passed, 12 skipped, 11 deselected, 7 warnings in 13.79s`. Both adopted tests passed. A focused rerun of 19 Phase 31 tests also passed (`19 passed in 1.36s`).
- **Notes:** No production code or existing test was changed by this validation.

### 2. No new skips; only the six pre-existing RuntimeWarnings
- **Criterion:** No new skips, and the only `RuntimeWarning`s are the six Phase 24 debt entries.
- **Status:** PASS
- **Evidence:** The bare run reported exactly six `RuntimeWarning`s: one unawaited `sleep` and five unawaited repair coroutines. The seventh warning was a separate `StarletteDeprecationWarning`. `git diff -U0 a88b67e..e20c57a -- backend/tests` contains no added `pytest.skip` or skip decorator.
- **Notes:** “No new” was compared with the feature merge's first parent, `a88b67e`.

### 3. Session join and sanitized call payload
- **Criterion:** `place_call` returns `room_name`; `find_session` joins on a live-shaped `id` + `room_name` row; the watcher grants when call and log IDs differ; secrets stay out of the payload.
- **Status:** PASS
- **Evidence:** `backend/api/vb_cli.py:115-157` returns only `call_id`, `status`, and `room_name`; `backend/api/vb_cli.py:186-206` matches `id`, `session_id`, or `room_name`; `backend/api/demo.py:290-299` keys the watcher on `room_name`. Passing tests: `test_place_call_happy_path_is_sanitized`, `test_find_session_matches_by_room_name_on_live_shaped_rows`, `test_disrupt_keys_the_watcher_on_room_name_when_present`, and `test_full_consent_gated_flow_break_to_results_call` (`backend/tests/test_demo_flow_integration.py:58-173`). The integration fixture deliberately uses `call-1`, a different log `id`, and joins through `room-1`.
- **Notes:** The integration test also asserts that neither the callee number nor API-key identifiers enter the call purposes.

### 4. Different-flight guarantee
- **Criterion:** Voice booking stores flight identity; repair excludes it; identity-less rows exclude equal clocks; an emptied pool warns and falls back.
- **Status:** PASS
- **Evidence:** `backend/api/concierge.py:440-458` writes `details.airline` and `details.flight_number`; `backend/api/sabre_tools.py:173-207` forwards identity and fallback clocks; `backend/api/repair_tools.py:180-234` performs both exclusions and warns before fallback. Passing tests: `test_book_flight_creates_rows_replaces_pin_and_clears_options`, `test_rebook_flight_chooses_a_different_flight_than_the_cancelled_one`, `test_pick_replacement_without_identity_excludes_equal_clocks`, and `test_pick_replacement_equal_clock_exclusion_never_empties`.
- **Notes:** Read-only deployed preparation created fresh trip `b86cc2f9-a2df-486b-8097-4961909cf0ed`; its booked flight is JetBlue 323 and its row carries the expected identity. The live repair itself was not run.

### 5. Re-trigger race closed
- **Criterion:** A re-trigger during stale-watcher classification produces zero repair launches and zero Call 2s; resolve-to-granted precedes launch with no await between them.
- **Status:** PASS
- **Evidence:** Adopted test `test_validator_retrigger_during_classification_stops_the_old_watcher` passes and asserts both launch collections remain empty (`backend/tests/test_validator_cascade_live_voice_demo.py:61-99`). Source order is synchronous `consent.resolve(...)` then `launch_trip_repairs(...)`, with no await between them (`backend/api/demo.py:173-186`).
- **Notes:** The behavior test covers the reproduced classification race; the no-await property is source-inspected, not independently AST-tested.

### 6. `trip_status` honesty
- **Criterion:** Cancelled, broken, and repairing legs suppress “Everything is on track”; a pure all-clear trip keeps it.
- **Status:** FAIL
- **Evidence:** The implementation correctly checks all three statuses (`backend/api/concierge.py:725-730`). Passing tests cover cancelled (`test_validator_trip_status_does_not_call_a_cancelled_trip_on_track`), repairing (`test_reads_fresh_statuses_not_the_pinned_cache`), and all-clear (`test_all_clear_trip_reads_on_track_with_grouped_legs`). No test invokes `trip_status_impl` with a live `broken` item and asserts the all-clear is absent.
- **Notes:** Runtime behavior appears correct; the failure is the validation.md requirement that the specific assertion exist and pass.

### 7. `fix_trip` deferral
- **Criterion:** The pinned trip defers during `awaiting_consent`; resolved windows and other trips launch; registry failures do not kill the turn.
- **Status:** PASS
- **Evidence:** `backend/api/concierge.py:206-254` implements the same-trip check, exact deferral line, and best-effort registry read. Passing tests: `test_fix_trip_defers_to_the_phone_during_a_consent_wait`, `test_fix_trip_ignores_another_trips_consent_wait`, and `test_fix_trip_registry_failure_never_kills_the_turn` (`backend/tests/test_concierge.py:349-418`).
- **Notes:** The manual orb behavior remains separately untested below.

### 8. End-to-end mocked flow uses live-shaped session rows
- **Criterion:** The integration test passes through the `room_name` join with live-shaped logs.
- **Status:** PASS
- **Evidence:** `test_full_consent_gated_flow_break_to_results_call` passes. Its call response uses `call_id=call-1`, while its log row has a different `id`, `room_name=room-1`, completed status, and transcript (`backend/tests/test_demo_flow_integration.py:58-90`). It then asserts granted consent, one repair launch, fixed state, and both call purposes (`:135-173`).
- **Notes:** Hermetic; no network or call quota used.

### 9. Live two-call rerun
- **Criterion:** Voice-book JFK→LAX, Cancel, say yes, observe granted consent and timer-anchored repairs, receive Call 2, and see a different rebooked flight.
- **Status:** UNTESTABLE
- **Evidence:** The deployed Concierge/Sabre seam successfully found live JFK→LAX options, booked a fresh identity-bearing flight, and built all five legs. The prepared trip remains untouched with five `booked` items. Triggering `/v1/demo/disrupt` would spend two outbound calls and mutate deployed state; execution was denied pending explicit user approval.
- **Notes:** Preparation used `/v1/web_call/query`, not audible interaction through the browser orb. No call was placed and no quota was spent.

### 10. Mid-wait orb deferral
- **Criterion:** Ask the orb to fix the trip during the wait; hear the deferral and observe no repair.
- **Status:** UNTESTABLE
- **Evidence:** No live wait window was created because Call 1 was not authorized. The same backend path passes hermetically in `test_fix_trip_defers_to_the_phone_during_a_consent_wait`.
- **Notes:** The browser-orb and audible response remain unobserved.

### 11. Cloud Run maximum instances
- **Criterion:** Confirm the Cloud Run service's max-instances is 1.
- **Status:** PASS
- **Evidence:** `gcloud run services describe vocal-bridge-be-dev` reported service-level annotation `run.googleapis.com/maxScale: '1'` on the latest ready revision. The revision-level `autoscaling.knative.dev/maxScale` remains the default `100`; Google documents service-level and revision-level caps separately and says the service-level setting takes effect immediately: [Cloud Run maximum instances](https://docs.cloud.google.com/run/docs/configuring/max-instances).
- **Notes:** `specs/roadmap.md:28` and `:63-67` currently say the service max is 100. That conflicts with the live service-level value and appears to conflate the revision default with the service cap.

### 12. PR evidence-guard check
- **Criterion:** A draft PR with the placeholder body fails the guard; a complete three-section body passes.
- **Status:** UNTESTABLE
- **Evidence:** Source inspection shows the intended check and exit (`git_pull_dev.sh:159-181`), including the placeholder rejection and three required headings. No disposable draft PR was created or mutated during validation.
- **Notes:** PR #55 was manually merged with the placeholder body, so the script is not a repository-wide enforcement boundary.

### 13. Deferral tone
- **Criterion:** The deferral is short, first person, one clear instruction, and jargon-free.
- **Status:** PASS
- **Evidence:** `backend/api/concierge.py:210-213` exactly contains: “I'm already asking you on the phone — just say yes on the call and I'll get started.” The focused unit test asserts the operative “on the phone” and “say yes” phrases.
- **Notes:** Text verified; audible delivery was not.

### 14. Call 2 speaks the different flight by ear
- **Criterion:** The results callback audibly states the different rebooked flight.
- **Status:** UNTESTABLE
- **Evidence:** The hermetic integration proves Call 2 is composed after repairs and includes the mocked replacement details (`backend/tests/test_demo_flow_integration.py:156-167`), but no real Call 2 was authorized or heard.
- **Notes:** Requires the budgeted live rerun.

### 15. Bare suite and CI in-image run are green
- **Criterion:** All automated checks pass locally and in CI's built image.
- **Status:** PASS
- **Evidence:** Local canonical suite: `482 passed`. Cloud Build `73ae5032-663b-4c99-8a90-1b70fc6ae8f0` succeeded for current commit `debf36f`; `backend/devops/cloudbuild.yaml:40-51` runs pytest inside the built image before deployment.
- **Notes:** Commit `debf36f` changes only `specs/changelog.md` and `specs/roadmap.md` relative to feature merge `e20c57a`; backend code is identical.

### 16. Live rerun completed
- **Criterion:** The deployed-merge live rerun completes with all manual boxes satisfied.
- **Status:** FAIL
- **Evidence:** It did not run. `specs/roadmap.md:23-28` and `specs/changelog.md:11-17` still record Phases 23/31 as implementation-complete with manual QA pending.
- **Notes:** A fresh five-leg trip is prepared for a resumed run after explicit approval.

### 17. PR description contains pre-merge evidence
- **Criterion:** PR #55 contains the pytest tail, dated live-run notes with both call outcomes and the differing flight, and the mock verification summary before merge.
- **Status:** FAIL
- **Evidence:** `gh pr view 55 --json body,mergedAt` shows the merged PR body still contains `_fill in before merge_` under all three headings and the auto-generated placeholder notice. It merged at `2026-07-15T23:21:38Z`.
- **Notes:** Post-merge editing can improve the record but cannot satisfy the expressly pre-merge criterion.

### 18. Roadmap completion and Phase 23 QA closure
- **Criterion:** Phase 31 is complete in the roadmap and Phase 23's manual-QA-pending qualifier is resolved.
- **Status:** FAIL
- **Evidence:** Current `specs/roadmap.md:23-28` archives both phases as implementation-complete but manual-QA-pending and lists the live rerun and PR body as open follow-ups. `specs/changelog.md:11-17` says the same.
- **Notes:** The roadmap's policy moves completed phases to the changelog, so the literal `[x] COMPLETE` wording is structurally stale; the unresolved manual-QA qualifier is unambiguous.

## Missing tests

- Add `backend/tests/test_trip_status_tool.py::test_broken_trip_suppresses_all_clear`: pin a trip, return a fresh `broken` flight, assert the disruption is spoken and “Everything is on track” is absent.
- Add `backend/tests/test_validator_consent_repair_closeout.py::test_granted_gate_has_no_await_before_launch`: AST-inspect `_watch_consent_then_repair` and assert no `Await` appears between the successful `consent.resolve(...GRANTED)` gate and `launch_trip_repairs`.
- Add a non-mutating body-check mode to `git_pull_dev.sh`, then cover it with `backend/tests/test_pr_evidence_guard.py::test_placeholder_fails_and_complete_body_passes`; today the guard can only be exercised as part of a state-changing PR workflow.
- The browser orb, real phone session join, audible deferral, timer anchoring, and audible Call 2 have no automated coverage. Keep the budgeted live rerun as the acceptance test; the existing hermetic integration is the right non-network substitute but cannot prove transport or TTS behavior.

## Gaps in validation.md

- Should “max-instances is 1” mean the service-level cap or the revision-level cap? Cloud Run exposes both; the live values are 1 and 100 respectively.
- Should the `trip_status` bullet require a dedicated `broken` test, as “specific assertions must exist” implies, or is source inspection plus the repairing/cancelled tests sufficient?
- What baseline defines “no new skips”? This report uses the feature merge's first parent (`a88b67e`).
- Should the seven-warning bare-suite output pass the warning criterion when exactly six are `RuntimeWarning`s and the seventh is a separate deprecation warning?
- How should an independent validator satisfy a pre-merge PR-body criterion when validation runs after the merge? Should this remain a historical pass/fail check, as applied here?
- Does archiving a phase to `changelog.md` satisfy the literal “marked `[x] COMPLETE` in roadmap” requirement under the repository's current archive-completed-phases policy?

## Risks not covered by validation.md

- `place_call` treats a successful CLI exit with both `call_id` and `room_name` missing as success; the watcher then times out instead of failing the disrupt request immediately.
- The evidence guard is local workflow logic with an explicit bypass and can also be bypassed by a manual/admin GitHub merge, as PR #55 demonstrates.
- The current deployment is docs-only commit `debf36f`, not literal image `e20c57a` named by the live-rerun criterion. The backend code is identical, but exact-image wording should be updated before the rerun.
- Roadmap scaling notes currently contradict the live Cloud Run service-level cap, creating a risk that an operator changes the wrong scaling control before the event.
