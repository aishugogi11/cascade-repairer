# Validation — Validation Fixes (Phase 26)

This phase exists to flip the Phase 25 validation report from FAIL to PASS, so its own validation restates those criteria precisely. The final re-validation (`sdd-validate-feature` against Phase 25 + 26 criteria) is the close-out step and runs in a **separate agent session** after this branch merges.

> **Amended 2026-07-14** (authorized, after the first independent re-validation — report in this directory): two criteria were clarified to say what was intended all along — the notes-contract test's execution context (full checkout, per its module's standing convention) and the sanctioned `specs/roadmap.md` phase-status edit. Dated markers sit inline at each amended criterion. No acceptance bar was lowered; the underlying behaviors were already validated PASS.

## Automated

Run inside the container (`docker compose exec -T backend pytest`, the standing local-testing path).

- **Hermetic suite green with zero Sabre env vars.** All `cert`-marked tests deselected by `pytest.ini` `addopts`; no collected test attempts network access. The new hermetic tests are collected and pass as follows *(amended 2026-07-14 — execution contexts clarified)*:
  - `tests/test_sabre_cert_cleanup.py::test_shape_drift_after_created_pnr_still_cancels` — collected and passes **in this bare container run**.
  - `tests/test_validator_docs_contract.py::test_notes_have_required_decision_sections` — lives in the docs-contract module, which by standing convention (Phase 2, TODO.md D4 Option A) skips inside the backend image because repo-root files sit outside the build context/mount. The criterion is that it is collected and **passes from a full checkout** — e.g. `docker run --rm -v "$PWD":/repo -w /repo/backend <backend-image> python -m pytest tests/test_validator_docs_contract.py` — and **skips (never fails or errors)** in the bare container/CI run.
- **Shape-drift cleanup guarantee (the report's failing criterion, now hermetic):** a simulated create response carrying `confirmationId` `ORPHAN1` but failing `CreateBookingResponse` validation must invoke cancel with `ORPHAN1` **and** still fail the flow; a simulated clean success (`FORCED1`) must also reach cancel via `finally`. The 2026-07-13 escape — `ValidationError` caught and returned before cleanup — must be impossible by construction.
- **Tripwire asserts the entitlement category:** `test_create_booking_unauthorized_tripwire` passes only when the raw response's `errors[]` contains `UNAUTHORIZED_ACCESS`; any other `ValidationError` payload fails the test.
- **Docs-contract test bites:** temporarily removing (or renaming) any required heading in `sabre-cert-notes.md` — auth bridge, deltas, rate/reset, Flight Search v1 answer, demo recommendations — makes `test_notes_have_required_decision_sections` fail; restored, it passes.
- **No hard-coded travel dates:** `grep -rn "2026-08-13" backend/tests specs/2026-07-13-sabre-cert-exploration/probes` returns nothing; the computed dates land ≥ 14 days in the future on any run date.
- **Credentialed live run:** the documented `pytest -m cert` command (credential passthrough via `docker compose exec -e`) passes all tests including the reworked tripwire, on the implementation day.

## Manual

- **Extended sweep executes clean:** run `probes/sweep.py` with the documented command; every endpoint — the original ten **plus** air schedules, air availability, exchange/reshop, ground/car, EnhancedSeatMap (POST), and modifyBooking (dummy PNR) — prints exactly one classified line, none `NETWORK-ERR`, exit code 0.
- **Probe exit codes bite:** sever credentials/network (e.g. run without the env vars past token mint, or point at an unroutable host) and confirm `sweep.py` exits nonzero on `NETWORK-ERR`; confirm `booking_lifecycle.py` exits 0 when createBooking answers `UNAUTHORIZED_ACCESS` and would exit nonzero if that category were absent (verify by inspection of the drift branch plus a simulated payload walk-through).
- **modifyBooking classification (D2):** the dummy-PNR probe result is an executed classification — expected clean business error (RESOURCE_NOT_FOUND family, HTTP 200) proving create-side-only entitlement walls; the result (whatever it is) lands in the matrix as `verified-live`, dated.
- **Notes matrix complete:** every domain the Phase 25 requirements enumerate (air shopping, schedules, availability, exchange/reshop, hotel/lodging, ground/car, utility/content, booking management) now has executed, classified rows; no row for these domains remains `inferred`/`UNTESTABLE`; superseded 2026-07-13 rows (modifyBooking, EnhancedSeatMap GET) are visibly marked as superseded, not silently deleted.
- **PNR hygiene (D3):** after all live runs, the set of recorded confirmation IDs is empty (no createBooking success observed) — the empty set satisfies hygiene; if any confirmation was harvested, its cancel is evidenced in output.
- **Scope discipline:** `git diff vb/dev -- backend/api/sabre/` is empty; no changes under `specs/` outside `specs/2026-07-13-sabre-cert-exploration/` (probes + notes) and this spec directory — **with one sanctioned exception** *(amended 2026-07-14)*: the phase-status edit to `specs/roadmap.md` that the implementation workflow requires at completion (heading marking only, no re-scoping); no raw credential or token material in the diff (`git diff vb/dev...HEAD` scan).

## Tone check

No user-facing product copy in this phase. Notes additions follow the Phase 25 style that validated PASS: confidence labels (`verified-live` / `docs-only` / `inferred`), dated rows, trimmed payloads, tables — and never a credential or token value.

## Definition of done

1. Roadmap items 1–5 implemented: tripwire reworked with category assertion and unconditional-cancel `finally`, hermetic shape-drift test, extended sweep with executed classifications appended to the notes matrix, docs-contract headings test, computed dates + nonzero probe exit codes.
2. Bare hermetic suite and credentialed `pytest -m cert` both green; extended sweep exits 0 with full classification coverage.
3. All three "risks not covered by validation.md" from the Phase 25 report are closed (dates, sweep exit code, lifecycle assertion).
4. Branch merged to `vb/dev` via PR; CI (pytest inside the built image) green.
5. **Deferred, tracked, not blocking this branch:** the close-out re-validation session against Phase 25 + 26 criteria, and the different-day dated `pytest -m cert` artifact appended to `sabre-cert-notes.md` (event-day morning at the latest, D4). *(Amended 2026-07-14:)* the interim `[x] COMPLETE (implementation; manual QA pending)` annotation is the sanctioned pre-close-out roadmap state and does **not** count as complete; the heading flips to plain `[x] COMPLETE` — and the phase moves to the changelog — only when the re-validation passes.
