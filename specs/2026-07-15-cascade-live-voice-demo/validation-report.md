# Validation Report — Phase 23: live voice surfaces + the consent-gated demo flow

**Branch:** `vb/dev`  
**Commit:** `a88b67e9f28353a4777390edf79164fc5d4ae52d`  
**Date:** 2026-07-15

## Summary

FAIL. The implementation's original in-container suite is green and the exact merge commit is deployed, but two validator-written tests expose acceptance failures: a superseded consent watcher can still launch repairs and Call 2, and `trip_status` calls a cancelled trip "on track." The acceptance package is also incomplete: PR #54 contains only a placeholder description, while the roadmap explicitly says manual QA is pending, so the required local and live run evidence is absent.

## Criterion-by-criterion results

### Automated

- **Criterion:** Bare suite green; all new tests pass; no accidental skips or new unawaited-coroutine warnings.
- **Status:** FAIL
- **Evidence:** Before validator tests, `docker compose exec backend pytest` completed with 473 passed, 12 skipped, 11 deselected, and 7 warnings. All 12 skips identify repo-root probe/docs/skill files intentionally absent from the backend image. Six warnings are the pre-Phase-26 unawaited-coroutine debt documented at `specs/roadmap.md:66`; no Phase 23 watcher warning appeared. With `backend/tests/test_validator_cascade_live_voice_demo.py` included, the same command reports 2 failed, 473 passed, 12 skipped, 11 deselected.
- **Notes:** The failure is from validator coverage required by this validation, not from the known warning baseline.

- **Criterion:** Disrupt split: Call 1 precedes the break, no repairs launch at click time, awaiting consent is registered, a watcher is spawned, and call failure writes/spawns nothing.
- **Status:** PASS
- **Evidence:** `backend/tests/test_demo.py::test_disrupt_calls_breaks_and_awaits_consent_without_repairs` and `::test_disrupt_call_failure_is_502_and_breaks_nothing` pass. `backend/api/demo.py:261-283` returns on call failure before the break, registry write, or task creation; the success path calls, breaks, registers, then creates the watcher.
- **Notes:** Reads precede the call only to build the real-trip purpose; the first write remains the break after Call 1.

- **Criterion:** Consent outcomes: yes launches repairs and grants; no/ambiguous/timeout stand down; transcript lag resolves.
- **Status:** PASS
- **Evidence:** Passing tests: `backend/tests/test_demo.py::test_watcher_yes_launches_repairs_then_places_the_results_call`, `::test_watcher_no_stands_down_without_repairs_or_callback`, `::test_watcher_ambiguous_stands_down_with_a_retry_message`, `::test_watcher_times_out_when_the_call_never_completes`, and `::test_watcher_absorbs_transcript_lag`; classifier normalization/failure cases pass in `backend/tests/test_consent.py`.
- **Notes:** Empty transcripts and classifier errors resolve to ambiguous, never yes.

- **Criterion:** Call 2 occurs only after all repair tasks land and uses post-repair detail data.
- **Status:** PASS
- **Evidence:** `backend/tests/test_demo.py::test_watcher_yes_launches_repairs_then_places_the_results_call` gates a repair task and proves it finishes before Call 2. `backend/tests/test_demo_flow_integration.py::test_full_consent_gated_flow_break_to_results_call` proves the resulting purpose includes Delta 1445, a +$23 delta, and downstream re-check copy. Production sequencing is `await asyncio.gather(...)` before repository/detail reads at `backend/api/demo.py:96-123`.
- **Notes:** Failed repair tasks are gathered and the purpose reports unresolved live statuses honestly.

- **Criterion:** Real-data purposes name JFK→LAX, remove the retired MSP→SFO narrative, degrade without detail, and never contain the callee number/API key.
- **Status:** PASS
- **Evidence:** All 12 tests in `backend/tests/test_call_purposes.py` pass; the end-to-end purpose assertions in `backend/tests/test_demo_flow_integration.py:139-155` also pass.
- **Notes:** Builders are pure over trip/item/detail inputs and do not read transport secrets.

- **Criterion:** Timer/consent surface is additive and best-effort; timer starts on repairing, not broken; waiting treatment is present.
- **Status:** PASS
- **Evidence:** `backend/tests/test_consent.py::test_status_carries_the_consent_block_when_a_wait_exists`, `::test_status_omits_the_block_without_a_wait`, and `::test_registry_failure_never_breaks_the_poll` pass. `backend/tests/test_cascade_ui.py::test_page_timer_anchors_on_repairing_never_on_broken` and `::test_page_renders_the_consent_treatments` pass. The timer condition is at `backend/api/assets/cascade/page.html:875-890`.
- **Notes:** The deployed `/v1/cascade/` returned HTTP 200 and served the same waiting/timer code.

- **Criterion:** Orb wiring uses pinned VB CDN versions and includes token/query wiring, feed, latency/state, and search-log surfaces.
- **Status:** PASS
- **Evidence:** `backend/tests/test_cascade_ui.py::test_page_center_column_is_the_live_voice_orb`, `::test_page_voice_module_uses_the_pinned_web_call_cdn_versions`, and `::test_page_has_the_sabre_live_search_panel` pass. The deployed page returned HTTP 200 with VB React/SDK `0.1.1`, `/v1/web_call/token`, `/v1/web_call/query`, and the waiting treatment.
- **Notes:** This is static/server wiring evidence; actual microphone/CDN behavior remains a manual criterion below.

- **Criterion:** `trip_status` is registered and answers honestly across sessions, with speakable no-pin/no-trip failures.
- **Status:** FAIL
- **Evidence:** Existing tests in `backend/tests/test_trip_status_tool.py` pass for unpinned, repairing, booked, and repository-failure cases. Validator test `backend/tests/test_validator_cascade_live_voice_demo.py::test_validator_trip_status_does_not_call_a_cancelled_trip_on_track` fails: the reply is "your flight is cancelled. Everything is on track." The unconditional all-clear branch is at `backend/api/concierge.py:693-695`.
- **Notes:** The tool is registered through `function_tool(..., name_override="trip_status")`; the failure is semantic honesty for a valid lifecycle status.

- **Criterion:** `/v1/demo/disrupt` and `/v1/sabre_tools/search_log` are access-gated.
- **Status:** PASS
- **Evidence:** `backend/tests/test_access_gate.py::test_other_gated_routes_401_without_code`, `backend/tests/test_cascade_ui.py::test_gated_json_endpoints_still_401_without_code`, and `backend/tests/test_search_log.py::test_endpoint_serves_the_log_and_is_gated` pass.
- **Notes:** Both endpoints return 401 without the configured code.

### Manual — local

- **Criterion:** Mock-mode `/v1/cascade/` walkthrough: connect orb, voice-book, auto-adopt trip, render conversation feed and mock search log.
- **Status:** UNTESTABLE
- **Evidence:** No run artifact or PR note exists; `specs/roadmap.md:23` says "manual QA pending." The shell and automated wiring tests pass.
- **Notes:** This requires a browser, microphone, live VB web session, and human speech; it was not performed by this validator.

- **Criterion:** Mock disrupt UI: waiting/no clock → yes/repairing timer → fixed/all-clear; decline/timeout stand-down and re-arm.
- **Status:** UNTESTABLE
- **Evidence:** Hermetic state-machine and markup tests pass, including `backend/tests/test_demo_flow_integration.py` and `backend/tests/test_cascade_ui.py`, but there is no recorded browser walkthrough.
- **Notes:** No outbound call or quota was consumed during independent validation.

### Manual — live

- **Criterion:** Full deployed JFK→LAX book → Cancel → Call 1 consent → repair animation → Call 2 actual-results contract.
- **Status:** UNTESTABLE
- **Evidence:** Cloud Build deployed commit `a88b67e` successfully, but PR #54 has no live-run notes and the roadmap says manual QA is pending.
- **Notes:** Reproducing this requires a participating callee, live microphone interaction, current Sabre content, and two outbound calls.

- **Criterion:** Ask "how's my trip?" mid-repair and hear current statuses.
- **Status:** UNTESTABLE
- **Evidence:** No live transcript/run note exists. Repository-fresh behavior is covered hermetically by `backend/tests/test_trip_status_tool.py`.
- **Notes:** The cancelled-status validator failure also shows the tool is not honest for every valid state.

- **Criterion:** Orb latency and connection states reflect reality, including an optional network-error state.
- **Status:** UNTESTABLE
- **Evidence:** Static state/latency/error wiring tests pass; no browser/network observation was recorded.
- **Notes:** Requires browser-level runtime validation.

- **Criterion:** Optional second live run with "no" launches no repairs and no Call 2.
- **Status:** UNTESTABLE
- **Evidence:** The hermetic no path passes in `backend/tests/test_demo.py::test_watcher_no_stands_down_without_repairs_or_callback`; no live run was recorded.
- **Notes:** This optional run was not attempted.

### Edge cases

- **Criterion:** Clicking Cancel twice supersedes the first watcher with no double repairs or double Call 2.
- **Status:** FAIL
- **Evidence:** The existing `backend/tests/test_demo.py::test_watcher_stands_down_when_superseded_by_a_retrigger` passes only when the token is stale before the old watcher starts. Validator test `backend/tests/test_validator_cascade_live_voice_demo.py::test_validator_retrigger_during_classification_stops_the_old_watcher` fails: registration of a fresh wait during the old watcher's classifier still produces one repair launch and one callback. `backend/api/demo.py:139-175` checks currency before classification but not again before launch.
- **Notes:** This is a real timing race across the classifier/repository awaits.

- **Criterion:** An unanswered phone reaches `timed_out` and surfaces on the page.
- **Status:** PASS
- **Evidence:** `backend/tests/test_demo.py::test_watcher_times_out_when_the_call_never_completes` and `backend/tests/test_cascade_ui.py::test_page_renders_the_consent_treatments` pass.
- **Notes:** No live unanswered-call run was performed.

- **Criterion:** A status poll with no consent entry remains additive-only/compatible.
- **Status:** PASS
- **Evidence:** `backend/tests/test_consent.py::test_status_omits_the_block_without_a_wait` passes, and the production diff adds `consent` only when `_consent_block` returns data at `backend/api/itinerary_ui.py:252-258`.
- **Notes:** Existing response fields are unchanged.

### Tone check

- **Criterion:** Call 1 is calm, concrete, first-person, asks one clear consent question, and avoids jargon/codes.
- **Status:** PASS
- **Evidence:** `backend/tests/test_call_purposes.py::test_disrupt_purpose_asks_consent_and_claims_no_running_repairs`, `::test_disrupt_purpose_names_the_real_route_never_the_old_narrative`, and `::test_disrupt_purpose_speaks_the_flight_date_and_only_real_legs` pass; builder text is at `backend/api/call_purposes.py:105-133`.
- **Notes:** This validates the generated instruction string, not a live agent's audio delivery.

- **Criterion:** Call 2 plainly reports the real rebooked flight, price delta, and downstream re-check.
- **Status:** PASS
- **Evidence:** `backend/tests/test_call_purposes.py::test_results_purpose_speaks_the_actual_rebooked_flight_and_delta` and the full integration test pass.
- **Notes:** Missing detail and unresolved-leg fallbacks are also covered.

- **Criterion:** Page copy matches the dashboard voice, uses sentence case, and says PT rather than PST.
- **Status:** PASS
- **Evidence:** `backend/tests/test_cascade_ui.py::test_page_renders_the_consent_treatments` and `::test_page_renders_times_pacific_labeled_pt` pass.
- **Notes:** The deployed page contains the same waiting copy.

### Definition of done

- **Criterion:** All automated checks are green in the bare suite and CI image run.
- **Status:** FAIL
- **Evidence:** Cloud Build's original in-image pytest step succeeded, but the independent suite now reports 2 failed, 473 passed, 12 skipped, 11 deselected.
- **Notes:** Both failures are acceptance regressions exposed by validator-written tests.

- **Criterion:** Local mock walkthrough and at least one full live run are completed and noted.
- **Status:** FAIL
- **Evidence:** PR #54 has no walkthrough/live notes; `specs/roadmap.md:23` explicitly says manual QA is pending.
- **Notes:** Absence of required completion evidence is a failure, distinct from the individual manual checks being untestable in this unattended session.

- **Criterion:** PR description carries mock walkthrough, live run, and pytest evidence before merge.
- **Status:** FAIL
- **Evidence:** [PR #54](https://github.com/zen-apps/hackathon-vocal-bridge/pull/54) was merged at 2026-07-15T21:21:19Z with body: `cascade-live-voice-demo` followed by the generated-placeholder notice. It contains none of the three required evidence sections.
- **Notes:** A non-empty-only guard does not reject this placeholder.

- **Criterion:** Merge deployed through Cloud Build and the live run used that deploy.
- **Status:** FAIL
- **Evidence:** Deployment half passes: Cloud Build `baa03de4-eb8c-432f-8143-56a0e630de02` succeeded for revision `a88b67e`, including pytest and deploy steps; Cloud Run is ready and serves image tag `a88b67e`. No live run against that deploy is recorded.
- **Notes:** The combined criterion fails on the missing live-run half.

- **Criterion:** Phase 23 is marked complete and the promoted TODO contract is removed.
- **Status:** PASS
- **Evidence:** `specs/roadmap.md:23` marks Phase 23 `[x] COMPLETE`; `TODO.md:7-11` states the contract was promoted into the feature requirements and removed.
- **Notes:** The roadmap separately retains "manual QA pending," which drives the manual/DoD failures above.

## Missing tests

- Written by the validator: `backend/tests/test_validator_cascade_live_voice_demo.py::test_validator_trip_status_does_not_call_a_cancelled_trip_on_track`. It asserts a valid `cancelled` status is spoken without an all-clear claim. It fails.
- Written by the validator: `backend/tests/test_validator_cascade_live_voice_demo.py::test_validator_retrigger_during_classification_stops_the_old_watcher`. It registers a fresh Cancel while the old watcher is classifying and asserts the old watcher launches neither repairs nor Call 2. It fails.
- Runtime orb/feed/latency behavior has no automated browser test. Proposed: `backend/tests/e2e/test_validator_cascade_dashboard.py::test_orb_connects_and_renders_delegated_turn`, with fake VB token/query seams, asserting connecting → live/error state, traveler/Cascade feed entries, and latency rendering.
- Consent UI animation/re-arm behavior has no automated browser test. Proposed: `backend/tests/e2e/test_validator_cascade_dashboard.py::test_consent_sequence_controls_timer_and_rearms_cancel`, feeding awaiting → repairing → fixed and declined/timeout response sequences.
- The deployed phone contract has no automated live smoke. Proposed: `backend/tests/live/test_validator_cascade_live_flow.py::test_deployed_consent_repair_callback`, explicitly marked live/quota-consuming and requiring a controlled callee; assert two call sessions, transcript consent, status transitions, and Call 2 ordering/details.
- The PR evidence guard has no substantive-placeholder test. Proposed: a workflow-unit test named `test_pr_evidence_rejects_placeholder_body` that requires the mock, live, and pytest sections rather than merely a non-empty body.

## Gaps in validation.md

- Should post-merge validation on the exact merge commit in `vb/dev` be allowed, or must the validator stop until a `vb/feature/*` branch is checked out?
- Which exact skip IDs and warning signatures form the accepted baseline for "none skipped accidentally" and "no new `RuntimeWarning` entries"?
- Where should manual/live evidence be stored if validation happens after merge and the PR can no longer supply pre-merge evidence?
- Should "byte-compatible" be replaced with an explicit response-key/schema assertion, since timestamps make literal byte equality impossible?
- How should an unattended validator obtain callee participation and authorization for the quota-consuming live run?

## Risks not covered by validation.md

- Consent and search-log state are process-local, while the deployed Cloud Run revision permits scaling beyond one instance. A status poll routed to another instance can lose the consent/search-log view.
- Call 1 is deliberately placed before the break write. If that write fails after a successful dial, the traveler can be asked for consent while no watcher/registry entry is created.
- The deployed service configuration carries external credentials as literal environment values rather than secret references. No values are reproduced here; use Secret Manager-backed references to reduce exposure.
