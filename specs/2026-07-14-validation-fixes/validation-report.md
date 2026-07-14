# Validation Report — Validation Fixes (Phase 26 close-out)
**Branch:** `vb/dev`  **Commit:** `4f83157080b572407e2babd97a2ae558d4e8d573`  **Date:** 2026-07-14

## Summary
PASS. The merged Phase 26 implementation satisfies the amended Phase 25 + 26 criteria: hermetic and credentialed suites pass, cleanup is guaranteed under simulated shape drift and forced success, all 17 sweep targets classify without network errors, probe failure modes return nonzero, notes and scope contracts hold, no PNR or secret was produced, and the merge commit's Cloud Build succeeded. The different-day CERT artifact remains explicitly deferred and non-blocking under Phase 26 validation; this report does not claim that future run has occurred.

## Criterion-by-criterion results

### 1. Hermetic suite and execution contexts
- **Criterion:** The default container suite is green with no raw Sabre credentials; six `cert` tests are deselected, the cleanup test runs, and the docs-contract module skips rather than fails in the bare backend image.
- **Status:** PASS
- **Evidence:** The running backend reported both raw Sabre variables unset. `docker compose exec -T backend pytest` collected 346 tests, deselected 6, and finished `335 passed, 5 skipped, 6 deselected`; `tests/test_sabre_cert_cleanup.py` ran all four tests, while the four repo-root docs tests skipped as specified.
- **Notes:** Seven unrelated warnings were emitted; none changed the exit code.

### 2. Full-checkout docs-contract execution
- **Criterion:** `test_notes_have_required_decision_sections` is collected and passes from a full checkout.
- **Status:** PASS
- **Evidence:** `docker run --rm -v <repo>:/repo -w /repo/backend hackathon-vocal-bridge-backend python -m pytest tests/test_validator_docs_contract.py -v` returned `4 passed`; the required notes test passed.
- **Notes:** This matches the amended full-checkout convention.

### 3. Shape-drift and forced-success cleanup guarantee
- **Criterion:** A drifted success carrying `ORPHAN1` and a clean success carrying `FORCED1` both cancel the confirmation and still fail the tripwire flow.
- **Status:** PASS
- **Evidence:** `tests/test_sabre_cert_cleanup.py::test_shape_drift_after_created_pnr_still_cancels` and `::test_forced_success_still_cancels_via_finally` passed. Inspection shows `_attempt_create_harvesting_confirmation` recovers the raw validation input and `_run_create_booking_tripwire` cancels any harvested ID in `finally`.
- **Notes:** The tests exercise the production-shaped Pydantic validation boundary with a recording fake client; no network is used.

### 4. Entitlement-category tripwire
- **Criterion:** The create-booking tripwire accepts only an `errors[]` payload containing `UNAUTHORIZED_ACCESS` and fails on any other validation payload.
- **Status:** PASS
- **Evidence:** Hermetic `test_documented_entitlement_wall_passes_and_cancels_nothing` passed. Live `tests/test_sabre_cert.py::test_create_booking_unauthorized_tripwire` passed against CERT. A simulated lifecycle payload with `OTHER`/`DRIFT` returned 1, while `UNAUTHORIZED`/`UNAUTHORIZED_ACCESS` returned 0.
- **Notes:** Both `category` and `type` are checked because CERT currently puts the marker in `type`.

### 5. Docs-contract test bites
- **Criterion:** Removing or renaming any required notes heading makes the docs-contract assertion fail.
- **Status:** PASS
- **Evidence:** An in-memory mutation walk-through invoked the actual test function after independently removing each of its five anchors; all five cases raised `AssertionError`. The unmodified document passed in the full-checkout run.
- **Notes:** No spec file was edited during the mutation check.

### 6. Computed future travel dates
- **Criterion:** No probe/test source hard-codes `2026-08-13`; generated travel dates are at least 14 days ahead.
- **Status:** PASS
- **Evidence:** `rg -n '2026-08-13' backend/tests specs/2026-07-13-sabre-cert-exploration/probes` returned no matches. `test_sabre_cert.py`, `sweep.py`, and `booking_lifecycle.py` use `date.today() + timedelta(days=30)` (and +32 for checkout); the live lifecycle run generated 2026-08-13 on 2026-07-14.
- **Notes:** The generated output date is expected; the criterion prohibits a hard-coded source literal.

### 7. Credentialed real-client CERT suite
- **Criterion:** Auth, BFM search findings, create-booking entitlement behavior, and cancel authorization are reproducible through the unmodified real client.
- **Status:** PASS
- **Evidence:** The documented credential-passthrough command for `pytest -m cert tests/test_sabre_cert.py -v` returned `6 passed in 5.69s`. It minted a token, reproduced the missing-POS 400 and empty-BFM response, confirmed `UNAUTHORIZED_ACCESS` on create, and confirmed cancel-side authorization.
- **Notes:** The two search outcomes are explicitly accepted documented findings, not unexplained errors.

### 8. Standalone auth recipe
- **Criterion:** The documented raw-credential recipe mints a CERT token and records the Phase 24 environment bridge without exposing secrets.
- **Status:** PASS
- **Evidence:** `probes/auth_check.py` exited 0 with `token_type: bearer` and `expires_in: 604800`; token metadata was redacted. `sabre-cert-notes.md` contains the v2 construction recipe and the `SABRE_BASE_URL` / `SABRE_CLIENT_SECRET` bridge heading required by the docs-contract test.
- **Notes:** No cached state is used by the probe.

### 9. Extended live entitlement sweep
- **Criterion:** The original ten targets plus schedules, availability, exchange/reshop, ground/car, EnhancedSeatMap POST, and modifyBooking each emit one classified line; none is `NETWORK-ERR`; exit code is 0.
- **Status:** PASS
- **Evidence:** `sweep.py` contains 17 `probe(...)` calls. The live command emitted 17 classified lines and exited 0: the added rows resolved to schedules 404, availability 403, exchange 404, reshop 400, car 404, seat map 400, and modifyBooking HTTP 200 business error; no network error occurred.
- **Notes:** The 403/404 availability and exchange gateway flap is documented as an equivalent denial.

### 10. Probe exit codes bite
- **Criterion:** Sweep network failures return nonzero, and lifecycle returns nonzero when the expected entitlement marker is absent.
- **Status:** PASS
- **Evidence:** With `mint_token` stubbed and the sweep host forced unreachable in memory, all 17 calls classified `NETWORK-ERR` and `main()` returned 1. With a simulated lifecycle response, entitlement drift returned 1 and the documented wall returned 0. The live lifecycle probe exited 0.
- **Notes:** These checks executed the checked-in probe functions without editing them.

### 11. modifyBooking and matrix completeness
- **Criterion:** modifyBooking has an executed dummy-PNR classification, every enumerated domain has an executed row, and superseded rows remain visibly marked.
- **Status:** PASS
- **Evidence:** The live sweep returned HTTP 200 with `BOOKING_NOT_FOUND` for modifyBooking. `sabre-cert-notes.md` records it as `verified-live 2026-07-14`, covers all eight named domains, and labels the original modifyBooking and EnhancedSeatMap rows as superseded.
- **Notes:** HTTP 200 plus the clean business error proves request authorization without writing a booking.

### 12. Notes completeness and tone
- **Criterion:** Notes contain the auth bridge, endpoint classifications, mock-shape deltas, rate/reset evidence, a definite Flight Search v1 answer, and demo recommendations using the established confidence-label style.
- **Status:** PASS
- **Evidence:** The full-checkout heading contract passed for all five decision anchors. Manual inspection confirmed the endpoint tables, `verified-live` / `docs-only` / `inferred` labels, dated extension rows, trimmed payload descriptions, and the explicit “real shopping, mock booking” recommendation.
- **Notes:** No user-facing product copy was introduced.

### 13. PNR hygiene
- **Criterion:** No live run leaves a confirmation ID behind; an empty set is sufficient when createBooking never succeeds.
- **Status:** PASS
- **Evidence:** The live CERT suite and lifecycle probe returned the expected create-side entitlement error with no confirmation ID. The sweep used only dummy `ABCDEF` reads/modifications and received not-found business errors. Hermetic forced-confirmation cases prove both harvested IDs are cancelled.
- **Notes:** Recorded live confirmation-ID set: empty; therefore no final cancel/read target existed.

### 14. Scope and credential discipline
- **Criterion:** No production Sabre client changes, only authorized tests/probes/notes/spec/status edits, and no credential or captured token material in the feature diff.
- **Status:** PASS
- **Evidence:** Diffing pre-Phase-26 `39ab348` to HEAD shows no file under `backend/api/sabre/` or `config/.env`; changed paths are the three test files, two probes, notes, this spec directory, and the single sanctioned roadmap heading line. Raw user ID, raw secret, and captured-token pattern scans all returned clean; `git diff --check 39ab348..HEAD` returned no findings.
- **Notes:** The same production-client check is empty across Phase 25 + 26 from Phase 25's merge base.

### 15. Merge, CI, and definitions of done
- **Criterion:** Roadmap items 1–5 are implemented, the branch merged through a PR, containerized CI pytest is green, and this independent session performs close-out validation.
- **Status:** PASS
- **Evidence:** Items 1–5 map to the passing tests, probes, and notes above. GitHub PR #41 merged `vb/feature/validation-fixes` into `vb/dev` as `4f83157`. Cloud Build `f217d0cf-95da-481f-9282-a37961e64ac3` finished `SUCCESS` for that exact revision; its `run-pytest` step and deployment step both succeeded.
- **Notes:** The roadmap correctly remains at “implementation; manual QA pending” until this report is consumed by the close-out workflow.

### 16. Different-day repeatability artifact
- **Criterion:** A different-day `pytest -m cert` artifact is tracked for later capture and is explicitly non-blocking for this branch/re-validation.
- **Status:** PASS
- **Evidence:** Phase 26 validation Definition of Done item 5 and `specs/roadmap.md` track the event-day-morning rerun. A fresh current-day credentialed rerun passed all six tests in this session.
- **Notes:** PASS reflects the amended criterion's explicit deferral. No different-day artifact exists yet, and this report does not represent one.

## Missing tests

- Live sweep coverage, expected classifications, and `NETWORK-ERR` exit behavior have no automated test. Proposed: `backend/tests/test_sabre_probe_contracts_validator.py::test_sweep_network_error_returns_nonzero` and `::test_sweep_required_domains_emit_once`; the latter would require the spec author to reverse D1's explicit no-manifest decision.
- Lifecycle probe drift handling has only this session's simulated walk-through. Proposed: `backend/tests/test_sabre_probe_contracts_validator.py::test_booking_lifecycle_rejects_non_unauthorized_access`, with `mint_token` and `call` replaced by fakes.
- Semantic notes-matrix completeness is manual beyond the five heading anchors. Proposed: `backend/tests/test_sabre_notes_matrix_validator.py::test_required_domains_have_executed_classifications`, asserting each named domain has a dated non-inferred row and superseded rows remain labeled.
- Diff scope, raw-secret scanning, PR/Cloud Build state, live PNR hygiene, and different-day repeatability are process/external-state checks. Proposed full-checkout test: `backend/tests/test_phase26_git_scope_validator.py::test_feature_diff_is_tests_probes_docs_only`, parameterized by an immutable base commit; retain manual/live evidence for the external-state portions.

## Gaps in validation.md

- Should post-merge scope checks name an immutable base commit or merge-base instead of `git diff vb/dev`? On `vb/dev` after merge, the documented command is vacuous; this report used `39ab348` for Phase 26 and Phase 25's first parent for the combined production-client check.
- When the deferred different-day artifact is appended, should it amend this report, generate a follow-up report, or remain notes-only?
- Should a live sweep exit nonzero on unexpected entitlement/classification drift, or only on `NETWORK-ERR` as currently specified?

## Risks not covered by validation.md

- `sweep.py` labels every HTTP 200 as `WORKS`, including `getBooking` and `modifyBooking` responses whose bodies contain business errors; readers must inspect the body/notes to understand the result.
- The sweep exits 0 for unexpected HTTP classifications (`SERVER-ERR`, new 401/403, or changed 400/404), so automation catches transport failure but not semantic entitlement drift.
- The green hermetic suite emitted seven warnings, including unawaited-coroutine warnings in unrelated Concierge/concurrency tests; these could mask future async lifecycle defects.
