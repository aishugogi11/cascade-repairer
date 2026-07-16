# Validation Report — Repaired flight reflected on the cascade page

**Branch:** `vb/dev`  **Commit:** `14b796d8314535eadb66889b12422974015d0ae3`  **Date:** 2026-07-16

## Summary

FAIL. The Phase 32 implementation behavior passes: the full container suite is green, the exact commit deployed successfully, the live cascade and booking pages render the rebooked flight, and a second repair excludes the newly stamped flight. The acceptance package nevertheless fails Definition of Done B because PR #58 merged with all three required evidence sections still containing `_fill in before merge_`; the same feature also removed the PR evidence guard. Definition of Done A is only partially testable because local BigQuery writes are unavailable to the validator, although the deployed walkthrough passed twice.

## Criterion-by-criterion results

### Full bare suite

- **Criterion:** The full bare suite passes with no new failures and no new `RuntimeWarning`s from this phase.
- **Status:** PASS
- **Evidence:** `docker compose exec -T backend python -m pytest` collected 521 tests: **498 passed, 12 skipped, 11 deselected** in 13.75 s. It emitted one Starlette deprecation warning and the same six unawaited-coroutine `RuntimeWarning`s already tracked as Phase 24 debt (one in `test_concierge.py`, five in `test_sabre_tools.py`); no Phase 32 or validator test emitted a new warning.
- **Notes:** The targeted implementer suite also passed: 113 passed, 2 deselected. The two validator-written tests passed separately and in the full run.

### Automated criterion 1

- **Criterion:** `itinerary_items.update_flight_fields` uses parameterized DML, refreshes `updated_at`, and surfaces helper failure and zero rows.
- **Status:** PASS
- **Evidence:** `backend/tests/test_repositories.py::test_update_flight_fields_parameterized_dml_stamps_updated_at`, `::test_update_flight_fields_on_missing_item_reports_zero_rows`, and `::test_update_flight_fields_surfaces_helper_failure` pass. `backend/api/repositories/itinerary_items.py:80` calls `run_dml` with typed query parameters and `updated_at = CURRENT_TIMESTAMP()`.
- **Notes:** No streaming insert path is used.

### Automated criterion 2

- **Criterion:** `_rebook_flight` writes the chosen option's PT timestamps, fare, currency, and replacement identity, including a next-day red-eye.
- **Status:** PASS
- **Evidence:** `backend/tests/test_repair_tools.py::test_rebook_flight_reshops_real_instaflights_and_writes_flight_repair` asserts every rewritten field. `backend/tests/test_flight_options.py::test_option_timestamps_red_eye_lands_next_pt_day` asserts `end_ts > start_ts` on the next PT day. The first live cycle changed the flight row from 08:00–12:05 PT / $385 to AA 926 at 06:15–11:20 PT / $155.
- **Notes:** `option_timestamps` is shared by initial booking and repair, preventing conversion drift between the two paths.

### Automated criterion 3

- **Criterion:** A failed or zero-row field update raises and the cascade records `error` without writing `fixed` over stale fields.
- **Status:** PASS
- **Evidence:** The implementer tests `test_rebook_flight_failed_field_write_raises` and `test_rebook_flight_zero_row_field_write_raises` pass. Validator test `backend/tests/test_validator_repaired_flight_on_page.py::test_validator_field_write_failure_records_error_without_fixed` drives the failure through `launch_trip_repairs`, observes only the `repairing` transition, and asserts an error completion event.
- **Notes:** The validator test was added because the original tests stopped at the tool boundary.

### Automated criterion 4

- **Criterion:** An honest-empty real re-shop falls back to mock data and rewrites the item identically.
- **Status:** PASS
- **Evidence:** `backend/tests/test_repair_tools.py::test_empty_reshop_falls_back_to_mock_and_still_writes` passes. Validator test `backend/tests/test_validator_repaired_flight_on_page.py::test_validator_mock_fallback_rewrites_every_flight_field` additionally asserts start, end, price, currency, identity, and `rebooked_from` against the chosen mock option.
- **Notes:** Both live repair cycles used the honest-empty → mock fallback and completed successfully.

### Automated criterion 5

- **Criterion:** `_rebook_flight` succeeds with all optional original-flight context omitted and degrades `rebooked_from` gracefully.
- **Status:** PASS
- **Evidence:** `backend/tests/test_repair_tools.py::test_rebook_flight_without_existing_booking_uses_placeholder_ref` passes. The first live seed-trip repair also had no stamped identity and returned `rebooked_from: "Was the 8 AM PT departure · $385"` without error.
- **Notes:** Identity was stamped by that repair for the next cycle.

### Automated criterion 6

- **Criterion:** `_flight_repair_detail` handles full, partial, empty, and malformed `rebooked_from` data without regressing existing detail builders.
- **Status:** PASS
- **Evidence:** The four `test_flight_repair_detail_rebooked_from_*` tests in `backend/tests/test_itinerary_ui.py` pass. Existing `test_status_detail_for_voice_booked_flight` and `test_status_detail_for_repaired_item_and_latest_booking_wins` remain green. The live status payload produced both the identity-less and full-identity forms.
- **Notes:** The cascade page hides the was-line when the additive key is absent, covered by `test_page_has_the_rebooked_from_was_line`.

### Automated criterion 7

- **Criterion:** Phase 31's exclusion guarantee remains green after identity re-stamping.
- **Status:** PASS
- **Evidence:** All seven `_pick_replacement` tests in `backend/tests/test_repair_tools.py` pass. On deployed trip `5c6edb6f-aeea-4093-92a7-2b8db0c6b26d`, cycle 1 selected AA 926; cycle 2 used AA 926 as the cancelled identity and selected AA 912 instead.
- **Notes:** Both cycles returned `status: ok` for the flight repair.

### Local mock walkthrough

- **Criterion:** Seed, break, and repair locally with `SABRE_MODE=mock`, observing the cascade and booking pages.
- **Status:** UNTESTABLE
- **Evidence:** The existing Compose container returned HTTP 500 because no ADC was mounted. A second attempt used a newly built temporary container with the host ADC mounted read-only and `SABRE_MODE=mock`; BigQuery then returned HTTP 403 because that principal lacks `bigquery.jobs.create`. Both failures occurred on `seed_trip` before a local trip row was created.
- **Notes:** Hermetic tests cover the mock repair behavior, but they do not replace the required local browser walkthrough.

### Deployed walkthrough and browser rendering

- **Criterion:** Repeat seed → break → repair on Cloud Run without outbound calls; confirm the corrected row, old → new treatment, fresh timestamps, second-repair exclusion, and booking-page inheritance.
- **Status:** PASS
- **Evidence:** Cloud Build `1371df77-938d-4e55-99f1-9a915752def1` successfully tested and deployed exact revision `14b796d`. The live trip above progressed booked → broken → fixed. Cycle 1 changed 08:00–12:05 PT / $385 to AA 926 at 06:15–11:20 PT / $155. Cycle 2 changed AA 926 to AA 912 at 08:00–10:05 PT / $187.60, with fresh `updated_at` and `rebooked_from: "Was American 926 · departed 6:15 AM PT · $155"`. Headless Chrome visually confirmed the cascade card at rounded $188 with the struck-through was-line, and the booking page showed the same AA 912 time and price.
- **Notes:** No Vocal Bridge call endpoint was used; this consumed zero outbound-call quota.

### Tone check

- **Criterion:** The was-line is plain, glanceable, PT-labeled, rounded, and free of jargon or exclamation marks.
- **Status:** PASS
- **Evidence:** The deployed cascade rendered `Was American 926 · departed 6:15 AM PT · $155` in the struck-through secondary treatment. The first identity-less cycle rendered `Was the 8 AM PT departure · $385`.
- **Notes:** Airline codes are converted to names when known.

### Definition of done A

- **Criterion:** The old → new treatment is verified locally in mock mode and on the deployed service.
- **Status:** UNTESTABLE
- **Evidence:** Deployed behavior passed, including visual browser evidence and two repair cycles. The required local half could not get past BigQuery authentication/authorization.
- **Notes:** This is an environment gap, not a deployed behavior failure.

### Definition of done B

- **Criterion:** The PR into `vb/dev` carries completed pre-merge Mock walkthrough, Live run, and Pytest evidence sections.
- **Status:** FAIL
- **Evidence:** [PR #58](https://github.com/zen-apps/hackathon-vocal-bridge/pull/58) is merged, but its `### Mock walkthrough`, `### Live run`, and `### Pytest` sections each still say `_fill in before merge_`. Commit `933f8e8` removed the evidence-section and placeholder checks from `git_pull_dev.sh` before the PR merged.
- **Notes:** Post-merge validation cannot make pre-merge evidence exist retroactively.

### Definition of done C

- **Criterion:** Full bare suite green and all seven automated assertions exist.
- **Status:** PASS
- **Evidence:** Full suite result above. The two validator tests close the only missing assertion depth: field-write failure through the cascade and all-field equality on mock fallback.
- **Notes:** The validator tests are a deliverable of this independent validation.

### Definition of done D

- **Criterion:** No change to consent flow, repair guarantee, voice scripts, trip model/schema, or dependencies.
- **Status:** PASS
- **Evidence:** Feature diff inspection found no changes to `consent.py`, `call_purposes.py`, repository models/schema, or dependency manifests. The `concierge.py` change only reuses the extracted timestamp helper; Phase 31 exclusion tests and the live second repair pass.
- **Notes:** The unrelated workflow-script regression is recorded under Risks because it is outside the criterion's enumerated runtime surfaces.

### Definition of done E

- **Criterion:** Phase 32 is marked complete in `specs/roadmap.md`.
- **Status:** PASS
- **Evidence:** The roadmap heading is `Phase 32: Repaired flight reflected on the cascade page [x] COMPLETE (implementation; manual QA pending)`.
- **Notes:** The parenthetical accurately preserves the unresolved local/manual acceptance state.

## Missing tests

- Added `backend/tests/test_validator_repaired_flight_on_page.py::test_validator_field_write_failure_records_error_without_fixed`: injects a Phase 32 field-write failure through the real cascade wrapper and asserts an error event with no `fixed` transition.
- Added `backend/tests/test_validator_repaired_flight_on_page.py::test_validator_mock_fallback_rewrites_every_flight_field`: forces an empty real search and asserts all item-row fields equal the chosen mock option.
- No automated item among criteria 1–7 remains uncovered. The browser walkthrough remains manual by contract and by the project's standing no-browser-test-dependency decision.

## Gaps in validation.md

- What credential/bootstrap path should an independent validator use for the required local BigQuery-backed walkthrough? `make up` alone provides neither mounted ADC nor a principal with `bigquery.jobs.create`.
- Should Definition of Done B explicitly require preservation/execution of the repository's PR evidence guard? This phase satisfied neither the evidence body nor the guard, yet the validation text only names the desired PR sections.
- Should the item-field write be required to preserve unrelated keys already present in `details`, or is wholesale replacement intentional before Phase 33 adds richer flight metadata?

## Risks not covered by validation.md

- `git_pull_dev.sh` no longer enforces evidence sections or rejects placeholders, contradicting the documented PR-evidence workflow and allowing the same acceptance failure on future phases.
- New `DEMO_FLOW.md:41` says Phase 32 is still unimplemented and the headline flight remains stale, although the same commit implements and deploys the fix.
- `_rebook_flight` persists the new booking before updating the item row; a field-write failure leaves a repair booking behind while the item remains non-fixed. The error is honest, but the partial write is not rolled back.
