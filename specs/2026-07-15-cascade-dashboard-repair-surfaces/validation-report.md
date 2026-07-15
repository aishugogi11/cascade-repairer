# Validation Report — Phase 22 Cascade Dashboard Repair Surfaces

**Branch:** `vb/dev`  
**Commit:** `700324d94a8e252e2773b8cb8aaf89df16691334`  
**Date:** 2026-07-15

## Summary

**FAIL (acceptance package).** The implementation behavior passed the bare suite, the targeted tests, static route/schema checks, and a 24-check headless-browser walkthrough of the real page with intercepted mock API responses. The required pre-merge PR evidence did not pass: PR #53 contains only a one-line summary and the generated placeholder notice, with no surface summary or mock broken-to-fixed evidence. The quota-consuming live-call loop and the BigQuery-backed local walkthrough remain untestable in this environment. Validation ran against the merged integration commit; the merged feature head is `27640e2c8e85fc8316b83a94566840ec02ad0382`.

## Criterion-by-criterion results

### Automated

#### 1. Full bare suite is green

- **Criterion:** The complete non-`cert` suite passes in the backend container.
- **Status:** PASS
- **Evidence:** `docker compose exec -T backend pytest -q` → **428 passed, 12 skipped, 11 deselected** in 5.61 s.
- **Notes:** The run emitted six pre-existing unawaited-coroutine warnings plus one Starlette/httpx deprecation warning.

#### 2. Cascade shell coverage

- **Criterion:** `/v1/cascade/` serves a self-contained HTML shell with access-code/status-poll wiring and both existing demo trigger targets.
- **Status:** PASS
- **Evidence:** All 17 tests in `backend/tests/test_cascade_ui.py` passed. Named coverage includes `test_shell_served_without_code_when_gate_armed`, `test_page_is_self_contained`, `test_page_polls_status_on_the_shared_cadence`, and `test_page_has_the_trigger_controls_wired_to_the_demo_orchestrator`.
- **Notes:** The tests inspect wiring only and do not spend call quota.

#### 3. Access-gate behavior

- **Criterion:** `/v1/cascade/` is a public page shell while gated JSON and trigger APIs remain protected.
- **Status:** PASS
- **Evidence:** `test_access_gate.py::test_allowlisted_gets_stay_public`, `test_access_gate.py::test_pages_contain_header_attach_wiring`, and `test_cascade_ui.py::test_gated_json_endpoints_still_401_without_code` all passed. `backend/api/access_gate.py` adds only `/v1/cascade` to `_PUBLIC_PAGES`.
- **Notes:** The public shell remains inert without authorized API responses.

#### 4. Item-H age expiry

- **Criterion:** Fresh pinned/unpinned search slots still surface; expired slots do not; a fresh slot pinned to another trip remains hidden.
- **Status:** PASS
- **Evidence:** Six named `test_concierge.py` boundary/resolution tests passed, including `test_pending_options_expired_slot_returns_none`, `test_pending_options_slot_just_inside_the_ttl_still_surfaces`, and all three fresh-slot resolution cases. The implementation filters at `backend/api/concierge.py:502` against `_LATEST_SEARCH_TTL` without changing the subsequent pin logic.
- **Notes:** The targeted acceptance run was **25 passed** total, including the shell and gate cases.

#### 5. No new data endpoint or status schema

- **Criterion:** The page uses the three existing GET data endpoints; only the `/v1/cascade/` shell route is new; the itinerary status payload gains no field.
- **Status:** PASS
- **Evidence:** The page has GET fetches only for `/v1/itinerary/status/{trip_id}`, `/v1/itinerary/trips`, and `/v1/sabre_tools/latest_trip_id`, plus POSTs to the two required existing demo triggers. `git diff --exit-code HEAD^1 HEAD -- backend/api/itinerary_ui.py` is clean. Production API changes are limited to `access_gate.py`, the new cascade page/router, `concierge.py`, and router registration in `main.py`.
- **Notes:** `/v1/demo/book` and `/v1/demo/disrupt` predate this feature.

#### 6. Booking page is untouched

- **Criterion:** `backend/api/assets/booking/page.html` and `backend/api/booking_ui.py` do not change.
- **Status:** PASS
- **Evidence:** `git diff --exit-code HEAD^1 HEAD -- backend/api/assets/booking/page.html backend/api/booking_ui.py` is clean.
- **Notes:** None.

### Manual scripted QA

#### 0. Real single-page trigger loop

- **Criterion:** Run Book → Cancel flight → cascade → fixed from `/v1/cascade/` through the live demo endpoints, without navigation.
- **Status:** UNTESTABLE
- **Evidence:** Headless Chrome verified intercepted 503 responses render inline, intercepted 200 responses pin `trip-1`, both POST targets fire, and the path remains `/v1/cascade/`. The actual success path was not called because it consumes approximately two Vocal Bridge calls. The local BigQuery-backed data path also cannot run: `GET /v1/itinerary/trips` returns 500, “Your default credentials were not found.”
- **Notes:** No outbound-call quota or external data was consumed.

#### 1. Frame renders

- **Criterion:** Header, left rail, current flight, reservations, and right column match the shipped frame/mockup structure.
- **Status:** PASS
- **Evidence:** Chrome 150 at 1440 px rendered a `300px 664px 340px` grid, current traveler, flight card, four reservation cards, recent trips, and the right recovery column. The structure matches `about/ui_ideas/ui_mockup_2026_07_09.png` at the Phase 22 level.
- **Notes:** This is a structural visual check, not pixel-diff approval.

#### 2. Recovery banner

- **Criterion:** The banner reports active recovery and resolves to all-clear.
- **Status:** PASS
- **Evidence:** Observed “repairs are starting now,” then “Cascade is actively repairing your itinerary,” then “All done — your trip is repaired and back on track.”
- **Notes:** Responses were controlled status payloads delivered to the real page JavaScript.

#### 3. Recovery timer

- **Criterion:** Timer starts on the first observed break, counts against 60 seconds, and freezes on all-clear.
- **Status:** PASS
- **Evidence:** Timer became visible at 0.3 s, reached 3.0 s, and remained 3.0 s after the fixed state.
- **Notes:** The full 60-second over-target color transition was not waited out; its threshold wiring is covered statically by `TARGET_S = 60`.

#### 4. Lifecycle status treatments

- **Criterion:** Flight, reservation cards, and timeline visibly move broken → repairing → fixed; all six statuses have hooks.
- **Status:** PASS
- **Evidence:** Chrome observed the flight plus all four reservation cards in each of the three states and five matching timeline legs. `test_page_contains_all_status_visual_hooks` covers planned/booked/broken/repairing/fixed/cancelled markup/CSS hooks.
- **Notes:** None.

#### 5. Disruption score

- **Criterion:** The score is state-derived, higher while broken, and drops toward Minimal as repairs complete.
- **Status:** PASS
- **Evidence:** Observed **100 Severe → 70 → 3 Minimal** across broken, repairing, and fixed payloads.
- **Notes:** The final score retained a small real price-delta contribution, as designed.

#### 6. Downstream-impact panel

- **Criterion:** Render one glanceable row per detailed leg, label OK/Adjusted, and omit legs without detail.
- **Status:** PASS
- **Evidence:** Two detailed legs produced exactly two rows: `Hotel — OK` and `Ride — Adjusted`; three legs without detail were omitted.
- **Notes:** None.

#### 7. Phase 23 voice placeholder

- **Criterion:** The center shows a labeled placeholder with no voice wiring or network activity.
- **Status:** PASS
- **Evidence:** Chrome rendered “Voice / Coming in Phase 23”; the captured request log contained no `/v1/web_call` or token request. `test_page_center_column_is_the_phase_23_voice_placeholder` also passed.
- **Notes:** None.

#### 8. Pinning and trip switching

- **Criterion:** Honor `?trip_id=`, adopt a changed `latest_trip_id`, switch from Recent Trips, and support `window.vbSetTrip`.
- **Status:** PASS
- **Evidence:** Chrome initialized on `trip-1`, adopted `trip-2` after the mocked latest-trip change, switched back to `trip-1` from Recent Trips, and repinned to `trip-2` through `vbSetTrip`, all without reload/navigation.
- **Notes:** The latest-trip interval was shortened only in the validator harness; page logic was unchanged.

#### 9. Abandoned-option expiry

- **Criterion:** `pending_options` disappears after `_LATEST_SEARCH_TTL` and the candidates panel clears.
- **Status:** PASS
- **Evidence:** Server boundary tests prove the 10-minute expiry; Chrome observed the candidates panel clear when the expired block was omitted from the next status response.
- **Notes:** The browser walk simulated the post-TTL response rather than waiting ten minutes.

### Tone and time

#### Traveler-voiced copy

- **Criterion:** Banner, impact, and repair-feed text is short, plain, and traveler-facing.
- **Status:** PASS
- **Evidence:** Browser output and `FEED_COPY` use direct phrases such as “Rebooking your flight…” and “Your pickup moved with the flight”; no API/provider jargon appears in impact rows.
- **Notes:** Tone is necessarily a human judgment.

#### Pacific time labels

- **Criterion:** Render clock times in `America/Los_Angeles`, labeled PT, never PST.
- **Status:** PASS
- **Evidence:** Browser output included `Jul 18, 3:00 AM – Jul 18, 4:00 AM PT` and no `PST`; `test_page_renders_times_pacific_labeled_pt` passed.
- **Notes:** None.

### Definition-of-done package

#### Consolidated live demo

- **Criterion:** The complete real book → cancel → repair → fixed loop succeeds on one page.
- **Status:** UNTESTABLE
- **Evidence:** Client-side success/error contracts and the entire visual lifecycle passed, but the real two-call and BigQuery-backed integration path was not executable under the available quota/credentials.
- **Notes:** This is the same coverage limit as manual criterion 0.

#### Remaining implementation bullets

- **Criterion:** Frame/repair surfaces, controls, placeholder, Item H, gate, unchanged booking page, and tests are complete.
- **Status:** PASS
- **Evidence:** Covered by automated criteria 1–6 and manual criteria 1–9 above.
- **Notes:** The integrated manual walkthrough remains separately untestable.

#### PR evidence before merge

- **Criterion:** The PR description carries the surface summary and mock broken-to-fixed evidence before merge.
- **Status:** FAIL
- **Evidence:** `gh pr view 53 --json body,...` returns only `Phase 22 cascade dashboard` followed by `_Placeholder description generated automatically by git_pull_dev.sh._`; PR #53 merged at 2026-07-15T18:56:39Z.
- **Notes:** Post-merge comments or this report cannot satisfy a pre-merge criterion.

#### Roadmap completion sequencing

- **Criterion:** Mark Phase 22 complete after validation.
- **Status:** AMBIGUOUS
- **Evidence:** `specs/roadmap.md` is already `[x] COMPLETE (implementation; manual QA pending)` in the implementation merge, before this independent report existed.
- **Notes:** The validator is forbidden to edit the roadmap, and the criterion does not identify which validation pass authorizes the state change.

## Missing tests

- **Dynamic browser lifecycle:** No committed test executes the page JavaScript across broken → repairing → fixed. Proposed: `backend/tests/test_cascade_ui_browser_validator.py::test_mock_lifecycle_renders_repair_surfaces` — intercept the three data APIs and assert banner, timer freeze, all card/timeline states, score bands, impact omission, candidates expiry, PT labels, and no voice requests. The validator ran this behavior ephemerally in Chrome but did not add a browser dependency.
- **Trigger client contract:** Proposed: `backend/tests/test_cascade_ui_browser_validator.py::test_trigger_controls_pin_and_surface_errors_without_navigation` — intercept 200/502/503 responses for both demo POSTs and assert immediate pinning, one-page behavior, retry state, and scrubbed inline errors.
- **BigQuery-backed mock walkthrough:** No automated test composes seed → break → repair → status poll with repository-backed state. Proposed: `backend/tests/test_cascade_dashboard_integration.py::test_seed_break_repair_status_lifecycle` — use the existing repository test seam to assert the five-leg lifecycle without real GCP or call quota.
- **PR evidence gate:** No repository workflow/test prevented the placeholder PR body. Proposed: `.github/workflows/pr-evidence-guard.yml`, job `require_phase_evidence` — reject `vb/feature/*` PRs to `vb/dev` whose body is blank/placeholder or lacks the validation evidence headings.

## Gaps in validation.md

- Should manual criterion 0 require quota-consuming live calls when the validation preamble says the walkthrough spends no outbound-call quota, or may a mocked orchestrator/browser contract satisfy it?
- What credentials or local fake repository should validators use for the required seed/break/repair walkthrough when the prescribed container suite is hermetic and has no BigQuery ADC?
- Does “matching the mockup” require a specific viewport and pixel/visual tolerance, or only the named structural surfaces?
- Which validation pass authorizes the roadmap completion edit, and who performs it, given the independent validator may write only this report?

## Risks not covered by validation.md

- The green suite emits six unawaited-coroutine warnings in concierge/repair paths. They are pre-existing and roadmap-tracked, but can hide async cleanup defects in the demo-critical cascade.
- Validation occurred after merge on `vb/dev`, not on the feature branch before merge. The code tree matches the merged feature, but failed acceptance-package evidence can no longer gate deployment.
