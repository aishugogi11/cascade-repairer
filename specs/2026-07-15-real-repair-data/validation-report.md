# Validation Report — Real repair data: the cascade re-shops InstaFlights

**Branch:** `vb/dev` **Commit:** `6c806c0f00cd0cecf50bf24cb6093de6a64881a6` **Date:** 2026-07-15

## Summary

**FAIL (acceptance package; implementation passes).** The Phase 29 implementation now
passes every automated and safely runnable live criterion: the bare-container suite is
green, the mock-PNR regression guard passes, and both credentialed CERT checks report
`pnr_write: mock client`. Definition-of-done B remains failed because original PR #51
and remediation PR #52 contain only generated placeholder descriptions, not the
required pre-merge mock/CERT output snippets. The mock-mode BigQuery walkthrough also
remains untestable with the available local credentials. Re-validation ran at PR #52's
merge commit; its remediation commit is `bfb1cbbeb495aca748960c1770dae0498d033c46`.

## Criterion-by-criterion results

### 1. Suite green, no new warnings

- **Criterion:** All bare-container tests pass with only the allowed one Starlette
  deprecation and six pre-existing unawaited-coroutine warnings.
- **Status:** PASS
- **Evidence:** `docker run --rm hackathon-vocal-bridge-backend python -m pytest tests/
  -q` reports `405 passed, 12 skipped, 11 deselected, 7 warnings`.
- **Notes:** The warning set is exactly the allowed baseline: one Starlette deprecation
  and the six pre-existing unawaited-coroutine warnings.

### 2. Refactor is behavior-neutral

- **Criterion:** Existing InstaFlights/Concierge behavior remains green; the re-export
  identity holds; the extracted module has no cycle-forming import.
- **Status:** PASS
- **Evidence:** The current full suite passed. In particular,
  `test_flight_options.py::test_module_has_no_cycle_forming_import` and
  `test_reexport_identity_holds` passed. `backend/api/flight_options.py` imports only
  datetime, Pydantic, `api.sabre.shapes`, and `api.sabre.airport_tz`; `concierge` directly
  re-exports the same `FlightOption` and parser objects.
- **Notes:** No production behavior change outside the shared extraction was found.

### 3. Real re-shop wires InstaFlights

- **Criterion:** Mock-mode repair writes a parsed `flight_repair` booking with
  alternatives and reaches `fixed`; BFM is absent from the repair path.
- **Status:** PASS
- **Evidence:**
  `test_repair_tools.py::test_rebook_flight_reshops_real_instaflights_and_writes_flight_repair`
  and
  `test_sabre_tools.py::test_repair_trip_flight_writes_flight_repair_and_flips_to_fixed`
  passed. `backend/api/repair_tools.py:253` calls `instaflights_search`; the only
  `flight_search` call in that module is the separate guided initial-booking function.
- **Notes:** The cascade core, not `_rebook_flight`, owns the `repairing -> fixed` writes.

### 4. Selection: different flight, closest arrival

- **Criterion:** Exclude the cancelled flight when possible, choose closest PT arrival,
  and tolerate missing/all-same inputs.
- **Status:** PASS
- **Evidence:** All five focused tests passed:
  `test_pick_replacement_returns_closest_arrival`,
  `test_pick_replacement_excludes_the_cancelled_flight`,
  `test_pick_replacement_none_cancelled_and_none_arrival_takes_first`,
  `test_pick_replacement_all_same_number_falls_back_to_closest_over_all`, and
  `test_pick_replacement_arrival_distance_wraps_the_clock`.
- **Notes:** Live criterion 9 also selected Delta 767 instead of cancelled Delta 773.

### 5. Empty search falls back and never stalls

- **Criterion:** An empty real result logs the route, uses mock options, writes the
  booking, and still reaches `fixed`; failed writes still raise.
- **Status:** PASS
- **Evidence:** Existing tests
  `test_empty_reshop_falls_back_to_mock_and_still_writes` and
  `test_empty_reshop_failed_write_still_raises` passed. Validator-written
  `test_validator_empty_reshop_fallback_flips_fixed` also passed and asserted one
  booking write plus exact `repairing`, `fixed` status writes with
  `from_mock_fallback=True`.
- **Notes:** This validator test closes the prior gap where fallback and cascade status
  completion were asserted only in separate tests.

### 6. Real, signed price delta

- **Criterion:** Render costlier, near-zero, and cheaper deltas correctly and route
  `flight_repair` through the repair-specific builder.
- **Status:** PASS
- **Evidence:**
  `test_flight_repair_detail_names_flight_and_signs_a_cheaper_delta`,
  `test_flight_repair_detail_signed_delta_costlier_and_zero`, and
  `test_status_routes_flight_repair_booking_to_the_real_builder` passed.
- **Notes:** The live JFK-LAX probe rendered `$0` for the equal-fare replacement and the
  warm Delta 767 arrival copy.

### 7. Computed dates only

- **Criterion:** No literal travel date appears in a test or fixture added by Phase 29.
- **Status:** PASS
- **Evidence:** The feature diff shows Phase 29's new/changed repair tests use
  `(date.today() + timedelta(...)).isoformat()` via `_DAY`; the added itinerary-detail
  tests contain no travel date. Validator tests also compute all dates.
- **Notes:** Literal dates in pre-existing tests are outside this criterion's stated
  phase-diff scope.

### 8. Mock-mode cascade walkthrough

- **Criterion:** Run seed -> break -> repair in an ephemeral mock-mode container and
  capture final status JSON with dynamic why-chosen and numeric price delta.
- **Status:** UNTESTABLE
- **Evidence:** The container had no default GCP credentials. Mounting the host ADC
  credential read-only progressed to BigQuery but returned `403 ... User does not have
  bigquery.jobs.create permission in project vocal-bridge-hackathon`. PR #51 contains no
  prior walkthrough capture; remediation PR #52 also contains only a placeholder.
  Automated endpoint/detail tests pass but are not the required live repository
  walkthrough.
- **Notes:** No Cloud Run mode change was attempted; changing the deployed service from
  real to mock would be an external deployment mutation, not an independent read-only
  validation step.

### 9. Live CERT repair on the demo anchor

- **Criterion:** Repair JFK-LAX from live CERT data, choose a real alternative, keep
  fallback false, and derive the detail delta from live fares.
- **Status:** PASS
- **Evidence:** Credentialed validator test
  `test_validator_live_anchor_repair_uses_real_fares` passed on computed date
  `2026-07-17`: three offers; cancelled Delta 773; chosen Delta 767 at USD 336.40;
  `from_mock_fallback=false`; detail was `Rebooked on Delta 767, nonstop, landing 1:49
  PM` with `$0` delta.
- **Notes:** The test spies on both PNR clients. Output reported `pnr_write: mock client`;
  the real PNR spy was never awaited.

### 10. Empty-route fallback observed live

- **Criterion:** A live cache-empty route still completes with a warning and
  `from_mock_fallback=True`.
- **Status:** PASS
- **Evidence:** Credentialed validator test
  `test_validator_live_empty_route_falls_back_without_stall` observed SFO-MIA empty on
  computed date `2026-07-17`, then asserted one booking write, the route warning,
  `from_mock_fallback=true`, and exact `repairing -> fixed` transitions.
- **Notes:** The live empty response was replayed immediately into the repair to avoid a
  second network response drifting between probe and assertion. Output reported
  `pnr_write: mock client`; the real PNR spy was never awaited.

### 11. Tone check

- **Criterion:** Repair copy is warm and speakable, names airline/flight/arrival, contains
  no API/mock/sandbox jargon, and no other user-facing copy changes.
- **Status:** PASS
- **Evidence:** `test_flight_repair_detail_names_flight_and_signs_a_cheaper_delta` passed
  its copy and jargon assertions. The production diff adds only the repair-specific
  detail copy; UI assets and other user-facing surfaces are unchanged. The live output
  named Delta 767 and its 1:49 PM arrival without technical jargon.
- **Notes:** Unknown airline-code handling remains a risk below.

### Definition of done A

- **Criterion:** Every automated assertion in criteria 1-7 exists and passes in the bare
  container.
- **Status:** PASS
- **Evidence:** The current bare-container run reports `405 passed`; every assertion in
  criteria 1-7, including both validator regression tests, passes.
- **Notes:** The seven warnings are the explicitly allowed baseline.

### Definition of done B

- **Criterion:** Mock walkthrough and live CERT output snippets were present in the PR
  description before merge.
- **Status:** FAIL
- **Evidence:** `gh pr view 51` reports a merged PR whose entire body is the phase title
  plus `_Placeholder description generated automatically by git_pull_dev.sh._`.
  Remediation PR #52 has the same generated placeholder and no mock/CERT output.
- **Notes:** Post-merge validator output cannot retroactively satisfy a pre-merge gate.

### Definition of done C

- **Criterion:** PNR cancel/create remains mock; only search is real.
- **Status:** PASS
- **Evidence:** `backend/api/repair_tools.py:281` now calls
  `sabre_client._mock.rebook_flight` directly. Focused command
  `pytest tests/test_validator_real_repair_data.py -m 'not cert' -q` reports `2 passed`;
  `test_validator_real_mode_uses_mock_pnr_client_only` asserts the real PNR client is
  never awaited and the mock client is awaited once. Both live CERT tests also printed
  `pnr_write: mock client`.
- **Notes:** Real-mode shopping remains live; only cancel/create bypasses the dispatcher.

### Definition of done D

- **Criterion:** Other repair categories and guided booking remain behaviorally
  unchanged.
- **Status:** PASS
- **Evidence:** The feature diff changes only `_rebook_flight` within
  `repair_tools.py`, adds flight-context helpers/arguments in `sabre_tools.py`, extracts
  the shared parser, and adds flight detail routing. Existing hotel, ground, dining,
  experience, and Concierge suites pass.
- **Notes:** No affected UI asset or non-flight category implementation was found.

### Definition of done E

- **Criterion:** Phase 29 is marked complete in the roadmap.
- **Status:** PASS
- **Evidence:** `specs/roadmap.md:19` says `Phase 29 ... [x] COMPLETE (implementation;
  manual QA pending)`.
- **Notes:** The manual-QA qualifier accurately reflects criterion 8, but does not cure
  the failed pre-merge PR-evidence gate.

## Missing tests

- No automated gap remains for criteria 1-7 or 9-11. The committed validator suite now
  covers the mock-PNR boundary, combined empty-fallback/write/status behavior, live
  anchor repair, and live cache-empty fallback; all four tests pass.
- **Mock walkthrough status payload:** Still lacks an automated equivalent. Proposed:
  `backend/tests/test_validator_real_repair_data.py::test_validator_mock_walkthrough_status_payload`
  with stateful repository fakes, exercising seed, break, waited repair, and status GET;
  assert the flight status history and returned dynamic detail object.
- **Pre-merge evidence gate:** No unit test can prove historical PR-body timing. Proposed:
  `backend/tests/test_git_pull_dev.py::test_required_evidence_replaces_placeholder_before_merge`
  with a stubbed `gh` command; assert a PR cannot merge while its body is the generated
  placeholder when the feature validation requires evidence snippets.

## Gaps in validation.md

- Should criteria 3 and 5 explicitly say the cascade core—not `_rebook_flight`—owns the
  `fixed` transition, so the required test seam is unambiguous?
- Does a credentialed live search passed through the production repair, with spies
  proving mock-only PNR routing, count for criterion 9, or is a deployed BigQuery-backed
  end-to-end run required?
- What credential mechanism and project role should an ephemeral mock-mode container use
  for criterion 8's BigQuery-backed walkthrough?
- What immutable source establishes that PR evidence existed before merge if a PR body
  can later be edited, and should a generated placeholder be explicitly rejected?

## Risks not covered by validation.md

- `_flight_repair_detail` falls back to displaying an unknown airline's raw code; the
  current tests cover only mapped AA/DL names.
- Price delta subtracts fares without checking that the chosen and original currencies
  match; `original_currency` is stored but not used by the detail builder.
