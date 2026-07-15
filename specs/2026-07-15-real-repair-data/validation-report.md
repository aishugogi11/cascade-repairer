# Validation Report — Real repair data: the cascade re-shops InstaFlights

**Branch:** `vb/dev`  
**Commit:** `107d40dddef7d1d1ec666665bc4b0e5be301f61a`  
**Date:** 2026-07-15

## Summary

**FAIL.** The InstaFlights re-shop, selection, fallback, detail rendering, and live
CERT behaviors pass, but the feature violates the permanent mock-PNR boundary:
`_rebook_flight` calls the mode-dispatching `sabre_client.rebook_flight`, so real mode
attempts the real cancel/create path. A validator-written test proves the real PNR
client is awaited. Definition-of-done B also fails because merged PR #51 contains only
the generated placeholder description, not the required pre-merge mock/CERT output.
The feature was already merged when validation began; `vb/dev` HEAD is PR #51's merge
commit, and the implementation commit is `e53e097d7e9eac37ffadb46c30b83a806b3d104c`.

## Criterion-by-criterion results

### 1. Suite green, no new warnings

- **Criterion:** All bare-container tests pass with only the allowed one Starlette
  deprecation and six pre-existing unawaited-coroutine warnings.
- **Status:** FAIL
- **Evidence:** Before adding validator coverage, `docker run --rm
  hackathon-vocal-bridge-backend python -m pytest tests/ -q` reported `403 passed, 12
  skipped, 9 deselected, 7 warnings`. With the validator tests included, the same
  command reports `1 failed, 404 passed, 12 skipped, 11 deselected, 7 warnings`.
- **Notes:** The warning set is exactly the allowed baseline. The sole failure is
  `test_validator_real_mode_uses_mock_pnr_client_only`, which exposes criterion C's
  production defect.

### 2. Refactor is behavior-neutral

- **Criterion:** Existing InstaFlights/Concierge behavior remains green; the re-export
  identity holds; the extracted module has no cycle-forming import.
- **Status:** PASS
- **Evidence:** The pre-validator full suite passed. In particular,
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
  prior walkthrough capture. Automated endpoint/detail tests pass but are not the
  required live repository walkthrough.
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
- **Notes:** The PNR operation was deliberately intercepted to the mock client. This
  safely validates the live search/selection/detail behavior; the unmodified production
  PNR routing separately fails criterion C.

### 10. Empty-route fallback observed live

- **Criterion:** A live cache-empty route still completes with a warning and
  `from_mock_fallback=True`.
- **Status:** PASS
- **Evidence:** Credentialed validator test
  `test_validator_live_empty_route_falls_back_without_stall` observed SFO-MIA empty on
  computed date `2026-07-17`, then asserted one booking write, the route warning,
  `from_mock_fallback=true`, and exact `repairing -> fixed` transitions.
- **Notes:** The live empty response was replayed immediately into the repair to avoid a
  second network response drifting between probe and assertion; PNR was intercepted to
  the mock client.

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
- **Status:** FAIL
- **Evidence:** The current bare-container run has one failure: the validator-added
  real-mode mock-PNR boundary test.
- **Notes:** Criteria 2-7 pass; A fails through criterion 1 and the criterion C defect.

### Definition of done B

- **Criterion:** Mock walkthrough and live CERT output snippets were present in the PR
  description before merge.
- **Status:** FAIL
- **Evidence:** `gh pr view 51` reports a merged PR whose entire body is the phase title
  plus `_Placeholder description generated automatically by git_pull_dev.sh._`.
- **Notes:** Post-merge validator output cannot retroactively satisfy a pre-merge gate.

### Definition of done C

- **Criterion:** PNR cancel/create remains mock; only search is real.
- **Status:** FAIL
- **Evidence:** `backend/api/repair_tools.py:277` calls the mode-dispatching
  `sabre_client.rebook_flight`; `backend/api/sabre/client.py:97-100` routes that operation
  through `_dispatch`; in real mode `_dispatch` awaits `_real`; and
  `backend/api/sabre/real_client.py:185-192` performs real cancel followed by real
  `create_booking`. Validator-written
  `test_validator_real_mode_uses_mock_pnr_client_only` fails because the real PNR client
  was awaited once.
- **Notes:** This is more than an entitlement fallback: real cancel can run before the
  unauthorized create fails, so the current flow can mutate the old CERT PNR before
  falling back to a mock rebook.

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
  the code and PR-evidence failures.

## Missing tests

- **Mock-PNR boundary:** Previously absent. The validator added
  `backend/tests/test_validator_real_repair_data.py::test_validator_real_mode_uses_mock_pnr_client_only`;
  it fails and is the direct regression guard for definition-of-done C.
- **Empty fallback through the cascade:** Previously split across two tests. The validator
  added `test_validator_empty_reshop_fallback_flips_fixed`; it passes and asserts the
  combined fallback/write/status contract.
- **Live criteria:** The validator added cert-marked
  `test_validator_live_anchor_repair_uses_real_fares` and
  `test_validator_live_empty_route_falls_back_without_stall`; both passed with PNR safely
  intercepted to mock.
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
- Does a live CERT search passed through the production repair with PNR intercepted to
  mock count for criterion 9, or must the criterion wait for a deployed end-to-end run
  after the mock-PNR routing defect is fixed?
- What credential mechanism and project role should an ephemeral mock-mode container use
  for criterion 8's BigQuery-backed walkthrough?
- What immutable source establishes that PR evidence existed before merge if a PR body
  can later be edited, and should a generated placeholder be explicitly rejected?

## Risks not covered by validation.md

- `_flight_repair_detail` falls back to displaying an unknown airline's raw code; the
  current tests cover only mapped AA/DL names.
- Price delta subtracts fares without checking that the chosen and original currencies
  match; `original_currency` is stored but not used by the detail builder.
