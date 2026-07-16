# Validation Report — Rich flight fields (Phase 33)
**Branch:** `vb/dev`  **Commit:** `2759a2c3f3575dbb9513fec4afd039c68444003c`  **Date:** 2026-07-16

## Summary
PARTIAL. All automated Phase 33 criteria pass on the merged commit: the full suite is green, the feature-focused slice is green, PR #60 merged, its Cloud Build succeeded, and the deployed service serves the rich-field page. The required interactive mock-mode voice/repair walkthrough was not executable in this headless validator context and no walkthrough notes or screenshots were present, so the manual criteria remain unverified and the manual-artifact Definition of Done item fails. No implementation defect was found in the exercised criteria.

## Criterion-by-criterion results

### A1 — Bare suite green; warning count does not grow
- **Criterion:** The container suite has no failures and retains exactly the six documented pre-existing unawaited-coroutine warnings.
- **Status:** PASS
- **Evidence:** `docker compose exec -T backend python -m pytest tests/ -q` → `518 passed, 12 skipped, 11 deselected, 7 warnings in 13.60s`.
- **Notes:** The seven total warnings are one Starlette dependency deprecation plus exactly six `RuntimeWarning: coroutine ... was never awaited` warnings, matching the criterion's baseline.

### A2 — Parser fills rich fields from mock data
- **Criterion:** Mock results populate airline name, cabin, duration, layovers, and next-day state, including a connection and a non-economy cabin.
- **Status:** PASS
- **Evidence:** `test_parser_fills_rich_fields`, `test_mock_instaflights_carries_rich_fields_deterministically`, `test_mock_connection_hub_swaps_when_dfw_is_an_endpoint`, and `test_parser_red_eye_sets_arrives_next_day` passed. The mock asserts elapsed minutes `[125, 130, 305]`, cabins `[Y, J, Y]`, and a two-segment DFW connection.
- **Notes:** The focused run passed all 40 selected tests.

### A3 — Missing rich fields degrade without skipping
- **Criterion:** Missing `ElapsedTime` and cabin-chain data preserve the option with duration `0` and cabin `""`.
- **Status:** PASS
- **Evidence:** `test_shapes_parse_without_rich_fields` and `test_parser_missing_rich_fields_degrade_never_skip` passed; the latter asserts one option remains offered with the required defaults.
- **Notes:** The parser only skips correctness failures such as unmappable airport timezones, not missing garnish fields.

### A4 — Pre-33 payload compatibility
- **Criterion:** Stored `FlightOption` payloads without rich fields still validate using defaults.
- **Status:** PASS
- **Evidence:** `test_pre_33_stored_payload_still_validates` and `test_arrive_date_defaults_to_depart_date` passed.
- **Notes:** Every Phase 33 field has an additive default.

### A5 — Spoken option clause
- **Criterion:** The option clause uses the airline name, not a known carrier code or fare-class letter; number words and prior stops/time/rounded-price content remain.
- **Status:** PASS
- **Evidence:** `test_spoken_clause_names_the_airline_never_codes`, `test_parser_spoken_contract_no_codes_rounded_prices`, and `test_search_result_reference_block_carries_rich_facts` passed.
- **Notes:** Cabin, duration, and layover details remain in the bracketed on-request reference block, outside the default read-back.

### A6 — Booking/repair stamping parity
- **Criterion:** Initial booking and repair write the same rich-field key set; repair preserves `rebooked_from` including the original airline name and stamps the replacement's values.
- **Status:** PASS
- **Evidence:** `test_book_flight_creates_rows_replaces_pin_and_clears_options`, `test_flight_writeback_matches_the_booking_stamp_key_set`, `test_rebook_flight_chooses_a_different_flight_than_the_cancelled_one`, and `test_rebooked_from_names_the_old_carrier` passed. Both production paths call `flight_options.details_from_option`; repair adds only `rebooked_from`.
- **Notes:** Coverage is compositional; there is no single automated book → break → repair → second-repair lifecycle test.

### A7 — Exclusion identity unchanged
- **Criterion:** `details.airline` and `details.flight_number` continue to drive replacement exclusion exactly as before.
- **Status:** PASS
- **Evidence:** `test_rebook_flight_chooses_a_different_flight_than_the_cancelled_one` and `test_pick_replacement_excludes_the_cancelled_flight` passed. The full suite also passed the remaining Phase 31 exclusion tests.
- **Notes:** `git diff --unified=0 HEAD^1 HEAD` shows no edits to the existing `test_pick_replacement_*` bodies.

### A8 — One airline table
- **Criterion:** `itinerary_ui.py` reuses the carrier table in `flight_options.py`; no duplicate production dictionary remains.
- **Status:** PASS
- **Evidence:** `test_airline_table_has_exactly_one_copy` passed and asserts object identity. Repository search found the dictionary definition only in `backend/api/flight_options.py`; `itinerary_ui._AIRLINE_NAMES` is an alias to it.
- **Notes:** Unknown carriers deliberately fall back to their code.

### A9 — Status and pending-options payloads
- **Criterion:** Stored rich fields and candidate carrier/duration data reach the status endpoint, while detail and pending-option failures remain best-effort.
- **Status:** PASS
- **Evidence:** `test_status_carries_rich_flight_details`, `test_pending_options_payload_is_the_phase_21_contract_plus_rich_keys`, `test_status_pending_options_for_unpinned_session`, `test_status_detail_read_failure_never_breaks_the_poll`, and `test_status_pending_options_read_failure_never_breaks_the_poll` passed.
- **Notes:** The deployed page also returned HTTP 200 and contained all rich-item and rich-candidate render markers.

### A10 — Timezone and dedup regressions
- **Criterion:** Existing timezone skipping/conversion and byte-identical dedup behavior remain unchanged.
- **Status:** PASS
- **Evidence:** `test_parser_converts_airport_local_to_pacific`, `test_parser_skips_itinerary_with_unmapped_connection_airport`, and `test_parser_dedupes_identical_itineraries` passed in the focused run; the full suite passed all related tests.
- **Notes:** The feature diff does not modify these existing test bodies.

### M1 — Voice booking shows rich pending candidates
- **Criterion:** A mock-mode voice search on `/v1/cascade/` shows airline names and durations, without carrier codes.
- **Status:** UNTESTABLE
- **Evidence:** Static/API coverage passed (`test_page_renders_pending_options_as_the_candidates_panel`, pending-options payload tests), and the deployed page contains `o.airline_name`/`o.duration` render logic.
- **Notes:** No interactive browser/microphone voice session or saved walkthrough artifact was available.

### M2 — Agent reads the concise option clause
- **Criterion:** The live agent says “Option one on <Airline>” without codes and without adding duration/cabin to the default clause.
- **Status:** UNTESTABLE
- **Evidence:** Deterministic tool-output tests pass, including `test_spoken_clause_names_the_airline_never_codes` and `test_search_result_reference_block_carries_rich_facts`.
- **Notes:** Actual model/Vocal Bridge delivery was not observed.

### M3 — Agent answers duration/cabin follow-ups without re-searching
- **Criterion:** Mid-conversation follow-ups are answered from the prior tool result.
- **Status:** UNTESTABLE
- **Evidence:** `test_search_result_reference_block_carries_rich_facts` and `test_instructions_carry_the_reference_block_clause` prove the facts and instruction are supplied.
- **Notes:** No live transcript or Sabre-call trace proves model compliance or absence of a second search.

### M4 — Booked flight card renders all rich facts
- **Criterion:** The booked card shows carrier/flight headline, cabin, stop/via state, duration, and conditional next-day text.
- **Status:** UNTESTABLE
- **Evidence:** `test_status_carries_rich_flight_details` and `test_page_has_the_rich_flight_fields` passed; deployed HTML contains every render branch.
- **Notes:** Dynamic rendering with a freshly booked trip was not observed in a browser.

### M5 — First break/consent/repair updates rich fields
- **Criterion:** After consent and repair, the card shows the replacement's rich fields and a struck-through old-carrier line.
- **Status:** UNTESTABLE
- **Evidence:** Repair/write-back and old-carrier unit tests pass, and `test_flight_repair_detail_prefers_stamped_airline_names` passed.
- **Notes:** The end-to-end flow requires an interactive consent call and consumes external Vocal Bridge quota; it was not run by this validator.

### M6 — Second repair preserves fields and excludes the current flight
- **Criterion:** A second break/repair retains rich fields and excludes the newly current flight.
- **Status:** UNTESTABLE
- **Evidence:** Shared-stamp parity and exclusion unit tests pass.
- **Notes:** No two-cycle walkthrough or integrated two-cycle automated test was present.

### M7 — Pre-33 trip renders without artifacts
- **Criterion:** A legacy trip renders as before, with no `undefined` text or empty facts row.
- **Status:** UNTESTABLE
- **Evidence:** Additive payload validation passes, and `renderFlight` hides the carrier and facts elements when fields are absent; `test_page_has_the_rich_flight_fields` statically guards those branches.
- **Notes:** No legacy trip was rendered in a browser during validation.

### E1 — Connecting mock option
- **Criterion:** Booking the connecting option yields “1 stop via <code>,” and the agent can identify the layover on request.
- **Status:** UNTESTABLE
- **Evidence:** Parser/mock tests prove the option has one stop and `layover_airports == ["DFW"]`; page/source tests prove the `via` branch exists.
- **Notes:** The booked DOM and live agent response were not observed.

### E2 — Unknown airline fallback
- **Criterion:** An unknown carrier code displays/speaks as the bare code without breaking the flow.
- **Status:** PASS
- **Evidence:** `test_airline_name_falls_back_to_the_code` passed, including `ZZ → ZZ`; parser construction uses that function for both display and spoken carrier text.
- **Notes:** This is the explicit exception to the known-carrier “never codes” rule.

### T1 — Spoken-copy tone
- **Criterion:** Known airline names only, no fare-class letters or numeric option labels, and durations only on request.
- **Status:** PASS
- **Evidence:** `test_spoken_clause_names_the_airline_never_codes`, `test_parser_spoken_contract_no_codes_rounded_prices`, `test_search_result_reference_block_carries_rich_facts`, and `test_instructions_carry_the_reference_block_clause` passed.
- **Notes:** This validates deterministic copy and agent instructions; actual live model delivery remains M2/M3's untested portion.

### T2 — Page-copy tone
- **Criterion:** PT labels remain explicit; facts are terse; next-day text says “arrives next day,” not `+1`.
- **Status:** PASS
- **Evidence:** `test_page_renders_times_pacific_labeled_pt` and `test_page_has_the_rich_flight_fields` passed. The deployed page returned HTTP 200 with the same render markers.
- **Notes:** No browser screenshot was available for visual-layout judgment.

### D1 — Automated Definition of Done
- **Criterion:** All automated assertions pass and the suite is green.
- **Status:** PASS
- **Evidence:** Full suite: 518 passed. Feature-focused suite: 40 passed in 1.52s.
- **Notes:** None.

### D2 — Manual walkthrough artifact
- **Criterion:** Mock-mode walkthrough is complete and notes/screenshots are saved in the feature directory.
- **Status:** FAIL
- **Evidence:** Before this report, `specs/2026-07-16-rich-flight-fields/` contained only `plan.md`, `requirements.md`, and `validation.md`; no notes or screenshots were present.
- **Notes:** The roadmap independently labels Phase 33 “manual QA pending.”

### D3 — Merge, Cloud Build, and deployed spot-check
- **Criterion:** Merge to `vb/dev`, successful Cloud Build, and deployed `/v1/cascade/` spot-check.
- **Status:** PASS
- **Evidence:** GitHub PR #60 is merged to `vb/dev` at commit `2759a2c`; Cloud Build `29e7c6bb-b5c6-4829-b344-5ee270273802` completed `SUCCESS`; Cloud Run revision `vocal-bridge-be-dev-00121-gzt` uses image tag `2759a2c`; deployed `/v1/cascade/` returned HTTP 200 and contains the rich-field render paths.
- **Notes:** GitHub reported no separate status-check rollup; the project Cloud Build record is the CI/deploy evidence.

### D4 — Roadmap completion marker
- **Criterion:** Phase 33 is marked complete in `specs/roadmap.md`.
- **Status:** PASS
- **Evidence:** The heading is `Phase 33 ... [x] COMPLETE (implementation; manual QA pending)`.
- **Notes:** The qualifier is material to overall validation status.

## Missing tests
- No single lifecycle test proves book → break → repair → second break → second repair over one item. Proposed: `backend/tests/test_rich_flight_lifecycle.py::test_two_repairs_preserve_rich_fields_and_advance_exclusion_identity`, asserting each wholesale details write carries the selected replacement's full shared stamp and preserves the immediately prior flight under `rebooked_from`.
- No automated test observes actual model behavior for M2/M3/E1. Proposed as a non-hermetic eval-marked test: `backend/tests/test_rich_flight_voice_eval.py::test_agent_reads_names_and_answers_followups_without_research`, asserting the transcript, tool-call count, and absence of codes/fare letters in the default read-back.
- No browser-level test exercises M1/M4/M7. Proposed: `backend/tests/test_rich_flight_browser.py::test_pending_booked_repaired_and_legacy_card_states`. The constitution currently keeps browser automation out of the project, so adopting this proposal requires an explicit test-strategy decision; until then, the saved manual walkthrough is the intended evidence.
- No test enforces the D2 artifact. Proposed: `backend/tests/test_validator_docs_contract.py::test_phase33_manual_qa_artifact_exists`, checking for a dated walkthrough note; this would prove presence, not the quality of the observation.

No validator-authored test files were added.

## Gaps in validation.md
- Should “never the code” explicitly mean “for carriers in the static table,” given the required unknown-carrier edge case says the bare code must be spoken and displayed?
- Is Phase 33 allowed to be roadmap-complete while its Definition of Done still requires missing manual walkthrough evidence, or should the completion marker wait for that artifact?
- What exact artifact filename/content is required for the manual walkthrough, and may a headless independent validator rely on operator-supplied notes rather than spend Vocal Bridge call quota?
- For the deployed spot-check, is serving the commit-tagged rich-field page sufficient, or must a real deployed trip be booked and repaired through the gated APIs?

## Risks not covered by validation.md
- A connecting itinerary is summarized from the first segment's marketing carrier/flight number and the first fare-info cabin. A codeshare or mixed-cabin connection could therefore present one carrier/cabin as if it described the whole journey.
- The optional live CERT rich-field parse was not run; real response variance beyond the captured/mock shapes remains unverified.
