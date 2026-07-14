# Validation Report — Validation Fixes (Phase 26)

**Branch:** `vb/feature/validation-fixes`

**Commit:** `11a86bc222f4347f9d2565fd19c9e2f43d89347a`

**Date:** 2026-07-14

## Summary

FAIL. The cleanup tripwire, live CERT suite, 17-endpoint sweep, probe exit behavior, notes matrix, PR merge, and Cloud Build all pass. Two explicit acceptance conditions do not: `test_notes_have_required_decision_sections` is skipped rather than passed by the required bare-container suite, and the branch changes `specs/roadmap.md` even though the scope criterion permits spec changes only in the Phase 25 exploration directory and this feature directory. The roadmap is also marked `[x] COMPLETE` before this re-validation has passed.

## Criterion-by-criterion results

### 1. Hermetic suite green with zero Sabre environment variables

- **Criterion:** The bare container suite deselects every `cert` test, attempts no network access, and collects and passes both named new hermetic tests.
- **Status:** FAIL
- **Evidence:** All four Sabre variables were absent in the running backend container. `docker compose exec -T backend pytest` exited 0 with `335 passed, 5 skipped, 6 deselected` in 5.55 seconds. `tests/test_sabre_cert_cleanup.py` ran four passing tests, including the named cleanup test. `tests/test_validator_docs_contract.py` showed `ssss`; the named notes-contract test was skipped by the module-level `README.exists()` guard at `backend/tests/test_validator_docs_contract.py:19` because repo-root files are absent from the backend image.
- **Notes:** The criterion requires the notes-contract test to pass in this run, not merely exist or pass in a separately mounted checkout.

### 2. Shape-drift cleanup guarantee

- **Criterion:** A drifted `ORPHAN1` response and a clean `FORCED1` success both reach cancellation, while the drifted flow still fails.
- **Status:** PASS
- **Evidence:** `backend/tests/test_sabre_cert_cleanup.py::test_shape_drift_after_created_pnr_still_cancels` and `::test_forced_success_still_cancels_via_finally` passed in the bare suite. The tests assert `client.cancelled == ["ORPHAN1"]` and `["FORCED1"]` at `backend/tests/test_sabre_cert_cleanup.py:66` and `:78`. The production-independent tripwire cleanup is in `backend/tests/test_sabre_cert.py:269`–`311`.
- **Notes:** The hermetic file also passed entitlement-wall and root-payload-recovery cases.

### 3. Tripwire asserts the entitlement category

- **Criterion:** `test_create_booking_unauthorized_tripwire` accepts only a raw `errors[]` response containing `UNAUTHORIZED_ACCESS`; other validation-error payloads fail.
- **Status:** PASS
- **Evidence:** The live test passed in the credentialed run. `backend/tests/test_sabre_cert.py:292`–`308` checks both `category` and `type`. An isolated fake-client walkthrough with `type: DIFFERENT_ERROR` raised `pytest.fail.Exception` as required.
- **Notes:** Checking both fields matches the observed CERT payload, where `category` is `UNAUTHORIZED` and `type` is `UNAUTHORIZED_ACCESS`.

### 4. Docs-contract test bites

- **Criterion:** Each of the five required notes headings is enforced.
- **Status:** PASS
- **Evidence:** With the full repository mounted read-only, `tests/test_validator_docs_contract.py::test_notes_have_required_decision_sections` passed. An in-memory mutation walkthrough renamed each required heading independently; all five mutations raised `AssertionError`.
- **Notes:** The assertion behavior is correct, but criterion 1 still fails because this test is skipped in the required default container/CI context.

### 5. No hard-coded travel dates

- **Criterion:** The specified grep finds no `2026-08-13`, and all computed dates are at least 14 days ahead.
- **Status:** PASS
- **Evidence:** `grep -rn "2026-08-13" backend/tests specs/2026-07-13-sabre-cert-exploration/probes` returned no matches (exit 1). Date sites use `timedelta(days=30)` in `backend/tests/test_sabre_cert.py:49`, `probes/sweep.py:77`, and `probes/booking_lifecycle.py:74`; the remaining search probe uses 14 days.
- **Notes:** The live lifecycle happened to resolve its computed date to 2026-08-13 on 2026-07-14; it is not a source literal.

### 6. Credentialed live test run

- **Criterion:** The documented `pytest -m cert` command passes on the implementation day.
- **Status:** PASS
- **Evidence:** The documented credential-passthrough command ran against Sabre CERT and reported `6 passed in 3.60s`, including the reworked create-booking tripwire.
- **Notes:** No token or credential value was printed or recorded.

### 7. Extended sweep executes clean

- **Criterion:** The original ten endpoints plus all Phase 26 additions each print one classification, with no `NETWORK-ERR`, and the probe exits 0.
- **Status:** PASS
- **Evidence:** The documented live sweep printed 17 classified endpoint lines and exited 0. The added results were: schedules `NOT-FOUND 404`, availability `NOT-FOUND 404`, exchange `NOT-ENTITLED 403`, reshop `SHAPE-400`, car `NOT-FOUND 404`, EnhancedSeatMap `SHAPE-400`, and modifyBooking `WORKS 200`. No line was `NETWORK-ERR`.
- **Notes:** The notes explicitly allow the observed availability 403/404 gateway flap.

### 8. Probe exit codes bite

- **Criterion:** `sweep.py` exits nonzero on `NETWORK-ERR`; `booking_lifecycle.py` exits 0 for the expected wall and nonzero when `UNAUTHORIZED_ACCESS` is absent.
- **Status:** PASS
- **Evidence:** An isolated no-network walkthrough exercised `classify()`'s exception branch and then drove all 17 probes to `NETWORK-ERR`; `main()` returned 1. The live lifecycle probe exited 0 with `UNAUTHORIZED / UNAUTHORIZED_ACCESS`. A simulated `APPLICATION_ERROR / OTHER` create response returned 1.
- **Notes:** These walkthroughs ran from a read-only repository mount and changed no tests or specs.

### 9. modifyBooking executed classification

- **Criterion:** The dummy-PNR modify probe produces a dated, executed clean business error proving authorization.
- **Status:** PASS
- **Evidence:** The live sweep received HTTP 200 for `POST /v1/trip/orders/modifyBooking` with `APPLICATION_ERROR / BOOKING_NOT_FOUND`. The dated `verified-live 2026-07-14` matrix row is at `specs/2026-07-13-sabre-cert-exploration/sabre-cert-notes.md:101`.
- **Notes:** The dummy confirmation was nonexistent; the probe performed no successful write.

### 10. Notes matrix complete

- **Criterion:** Every enumerated domain has an executed classification, and superseded rows remain visibly marked.
- **Status:** PASS
- **Evidence:** The base and extension matrices at `sabre-cert-notes.md:69`–`105` cover air shopping, schedules, availability, exchange/reshop, hotel/lodging, ground/car, utility/content, and booking management. The earlier modifyBooking and EnhancedSeatMap rows are marked superseded at lines 81 and 84.
- **Notes:** No required domain remains labeled inferred or untestable in the active extension rows.

### 11. PNR hygiene

- **Criterion:** No confirmation ID remains after live runs; any harvested ID is cancelled.
- **Status:** PASS
- **Evidence:** The live cert and lifecycle responses contained no `confirmationId`, so the recorded set was empty. `sabre-cert-notes.md:106`–`107` records that result. Hermetic drift and forced-success cases prove harvested IDs reach cancellation.
- **Notes:** No live PNR was created during this validation.

### 12. Scope discipline and credential hygiene

- **Criterion:** No production Sabre-client diff; no spec changes outside the two allowed directories; no credential/token material in the diff.
- **Status:** FAIL
- **Evidence:** `git diff vb/dev -- backend/api/sabre/` was empty. Literal-pattern and exact configured-value scans found no Sabre user ID, secret, composed secret, bearer token, or Basic credential. However, `git diff --name-only vb/dev...HEAD -- specs` includes `specs/roadmap.md`, outside `specs/2026-07-13-sabre-cert-exploration/` and `specs/2026-07-14-validation-fixes/`.
- **Notes:** Requirements clarify that nothing else under `specs/` changes. This failure does not depend on the content of the roadmap edit.

### 13. Notes tone

- **Criterion:** Notes preserve Phase 25's confidence labels, dated rows, trimmed payloads, tables, and credential hygiene.
- **Status:** PASS
- **Evidence:** Confidence labels are defined at `sabre-cert-notes.md:9`; the extension is dated and tabular at lines 86–101; probe output is truncated to 150 characters; both credential scans were clean.
- **Notes:** No user-facing product copy was added.

### 14. Definition of done item 1 — roadmap items 1–5 implemented

- **Criterion:** All five implementation items exist.
- **Status:** PASS
- **Evidence:** The diff contains the reworked tripwire, hermetic cleanup tests, extended probes and executed notes rows, heading contract, computed dates, and nonzero drift/network exits.
- **Notes:** Implementation presence passes; execution of the heading contract in the default suite fails separately under criterion 1.

### 15. Definition of done item 2 — all required commands green

- **Criterion:** Bare suite, credentialed cert suite, and extended sweep exit successfully.
- **Status:** PASS
- **Evidence:** Exit codes were 0 for all three: bare suite `335 passed`, live cert `6 passed`, and sweep 17/17 classified with no network errors.
- **Notes:** A green bare-suite exit does not cure the explicit skipped-test failure in criterion 1.

### 16. Definition of done item 3 — Phase 25 risks closed

- **Criterion:** Hard-coded dates, sweep network exit, and lifecycle entitlement assertion are closed.
- **Status:** PASS
- **Evidence:** Criteria 5 and 8 passed, including live and simulated drift evidence.
- **Notes:** None.

### 17. Definition of done item 4 — merge and CI

- **Criterion:** The feature is merged to `vb/dev` by PR and Cloud Build pytest is green.
- **Status:** PASS
- **Evidence:** GitHub PR 40 merged `11a86bc` into merge commit `281a9dc9ff8fa680e739bfeea2e4dc1a3931b9a1` at 2026-07-14T13:25:49Z. Cloud Build `7c3d0f9b-ebc9-4812-b30f-397975888502` built that merge commit; status was `SUCCESS`, including the `run-pytest` step.
- **Notes:** The local `vb/dev` ref is stale, so merge/CI evidence came from GitHub and Cloud Build rather than the local ancestry check.

### 18. Definition of done item 5 — deferred close-out state

- **Criterion:** Different-day evidence is deferred and tracked; Phase 26 is marked complete only after re-validation passes.
- **Status:** FAIL
- **Evidence:** The different-day artifact is explicitly deferred, which is nonblocking. However, `specs/roadmap.md` already marks Phase 26 `[x] COMPLETE (implementation; manual QA pending)`, while this independent re-validation result is FAIL.
- **Notes:** The `[x]` state also causes criterion 12's out-of-scope spec diff.

## Missing tests

- The default container has no active notes-heading contract. Proposed: `backend/tests/test_sabre_cert_notes_contract.py::test_notes_have_required_decision_sections`, with `sabre-cert-notes.md` made available in the CI test context and no module-wide repo-root skip.
- Probe failure behavior is covered only by manual walkthroughs. Proposed: `backend/tests/test_sabre_probe_contracts.py::test_sweep_network_error_exits_nonzero` and `::test_booking_lifecycle_rejects_missing_unauthorized_access`, loading the scripts with patched network calls and asserting exit codes.
- Exact endpoint/domain coverage is manual by deliberate decision D1. If that decision changes, add `backend/tests/test_sabre_probe_contracts.py::test_sweep_classifies_required_endpoints_once` and `backend/tests/test_validator_docs_contract.py::test_notes_matrix_covers_required_domains_and_superseded_rows`.
- Git scope, credential-diff scanning, PR merge, and Cloud Build state have no automated repository check; this validation gathered them directly.

## Gaps in validation.md

- Should `specs/roadmap.md` be an allowed scope exception, or should the roadmap remain untouched until the independent report passes? The scope rule forbids the edit while definition-of-done item 5 discusses making it.
- Is the “bare container” for the notes-contract criterion intended to contain the repository root? The standing backend image cannot see `sabre-cert-notes.md`, and the chosen precedent module skips all tests when `README.md` is absent.
- Does `[x] COMPLETE (implementation; manual QA pending)` count as complete for the “only when re-validation passes” rule?
- Should the close-out validator produce one Phase 26 report using the restated criteria, as done here, or separately re-run and report every criterion from both the Phase 25 and Phase 26 `validation.md` files?

## Risks not covered by validation.md

- `sweep.py` returns 0 for `SERVER-ERR` and for unexpected classification drift; only `NETWORK-ERR` affects its exit code. A complete but materially changed sweep can therefore look successful to shell automation.
- The bare suite emitted six unawaited-coroutine `RuntimeWarning`s across concierge/repair tests. They predate this phase but can conceal async cleanup defects.
- The required different-day `pytest -m cert` artifact is still pending; today's live run proves current behavior, not repeatability on a later date.
