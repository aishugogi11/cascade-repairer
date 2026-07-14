# Requirements — Validation Fixes (Phase 26)

Close out the Phase 25 validation report's **FAIL** (`specs/2026-07-13-sabre-cert-exploration/validation-report.md`) so a re-validation against the Phase 25 + 26 criteria passes. Tests, probes, and docs only — no production code changes.

## Scope

### In scope (roadmap items 1–5, confirmed at spec interview)

| # | Item | Where |
|---|------|-------|
| 1 | Rework `test_create_booking_unauthorized_tripwire`: extract the raw response dict from the pydantic `ValidationError` (error `input`), cancel any `confirmationId` found there in `finally` regardless of validation outcome, and assert the `UNAUTHORIZED_ACCESS` error category explicitly | `backend/tests/test_sabre_cert.py` |
| 2 | Add `test_shape_drift_after_created_pnr_still_cancels` — **hermetic** (simulated payload, no `cert` marker): a success payload carrying a `confirmationId` but failing shape validation must still trigger cancel before the test fails | new `backend/tests/test_sabre_cert_cleanup.py` |
| 3 | Extend the sweep with **executed** classifications for the missing domains: air schedules, air availability, exchange/reshop, ground/car, EnhancedSeatMap via POST, and modifyBooking via dummy-PNR probe — and append the executed results to the notes endpoint matrix | `specs/2026-07-13-sabre-cert-exploration/probes/sweep.py` + `sabre-cert-notes.md` |
| 4 | Add `test_notes_have_required_decision_sections` — hermetic docs-contract test asserting the auth-bridge, deltas, rate/reset, Flight Search v1 answer, and demo-recommendation headings exist in `sabre-cert-notes.md` | `backend/tests/test_validator_docs_contract.py` (precedent file) |
| 5 | Replace hard-coded `2026-08-13` travel dates with computed future dates; make `probes/sweep.py` exit nonzero on `NETWORK-ERR`; make `probes/booking_lifecycle.py` assert the `UNAUTHORIZED_ACCESS` category and exit nonzero on drift | `test_sabre_cert.py`, both probes |

### Out of scope

- **Close-out (roadmap item 6)** — the `sdd-validate-feature` re-run happens in a separate agent session after this branch is done, and the different-day `pytest -m cert` re-run lands as a dated artifact whenever the calendar allows (**event-day morning at the latest**, replan decision D4). This branch only makes those steps possible.
- **`backend/api/sabre/` stays untouched** — the frozen-client punch list (dead `POS` field, empty-BFM optional lists, BM errors-as-200 masking) is Phase 24's conditional work.
- **BFM shapes stay untouched**; InstaFlights response models are Phase 27.
- No new dependencies, no pytest-asyncio — async keeps running via `asyncio.run()` inside sync tests (the `test_sabre_client.py` convention).

## Decisions

All four validation-triage decisions were pre-answered at the 2026-07-13 replan interview; the spec interview (2026-07-14) confirmed execution posture:

- **D1 — completeness is the targeted additions, no manifest.** The validator's suggested `test_sweep_manifest_covers_required_domains` is deliberately **not** built; the enumerated domain additions in item 3 *define* sweep completeness. (The docs-contract test in item 4 is the only new docs assertion.)
- **D2 — modifyBooking gets an executed dummy-PNR probe**, not an `UNTESTABLE/inferred` row: expected result is a clean business error (`RESOURCE_NOT_FOUND` family, HTTP 200), proving authorization the same way `cancelBooking` was proven.
- **D3 — empty-set PNR hygiene is sufficient**: when createBooking returns no confirmation references, verifying the empty set (no confirmations recorded → nothing to cancel) satisfies hygiene; no account-level booking list is required.
- **D4 — repeatability evidence is a dated artifact** appended to `sabre-cert-notes.md` (a different-day `pytest -m cert` output), captured at close-out, not on this branch.
- **Live CERT calls run during implementation** (interview): the extended sweep executes against CERT while building this branch, and its classifications land in the notes matrix as part of the phase.
- **Notes edits are authorized** (interview): the roadmap's Phase 26 bullets are the explicit instruction to modify `specs/2026-07-13-sabre-cert-exploration/` — the sweep probe, the notes matrix, and dated appendices. Nothing else under `specs/` changes beyond this phase's own spec directory.
- **Computed dates** follow the probes' existing pattern (`date.today() + timedelta(days=30)`), keeping the suite valid on any run date.

## Context

- **The three validation-report failures this phase repairs**: (a) the tripwire returns on `ValidationError` before any cleanup, so a created-but-shape-drifted PNR would leak (`test_sabre_cert.py:232-233`); (b) the Try-it-Out sweep is incomplete — no schedules/availability/exchange/ground rows, modifyBooking inferred-only, EnhancedSeatMap notes-only GET 404; (c) definition-of-done item 3 fails on (b). Plus three "risks not covered": hard-coded dates, sweep exits 0 on `NETWORK-ERR`, lifecycle probe exits 0 without asserting the entitlement category.
- **The `cert` fence is inviolable**: `pytest.ini` `addopts = -m "not cert"`; hermetic CI runs with no Sabre env vars and must stay green, with all live tests deselected. New hermetic tests (items 2, 4) must run and pass in the default suite with zero credentials.
- **Credential hygiene**: never commit or print the raw user ID, secret, or token material; `config/.env` untouched. Live runs use the documented `docker compose exec -T -e SABRE_API_USER_ID -e SABRE_API_SECRET` passthrough.
- **Notes tone** (validated PASS in Phase 25 — keep it): confidence labels (`verified-live` / `docs-only` / `inferred`), trimmed payloads, tables; new matrix rows dated 2026-07-14 so the Phase 25 record stays legible.
- **Heading caveat for item 4**: the rate-limit/reset evidence currently lives in prose without its own heading — promoting it to a heading in `sabre-cert-notes.md` is an authorized edit if the docs-contract test needs an anchor.
- **Tripwire testability**: the module-level `pytestmark` in `test_sabre_cert.py` applies `cert` + `skipif` to everything in that file, so the hermetic shape-drift test (item 2) lives in its own file and exercises the extracted cleanup logic with a fake client — importing helpers from `test_sabre_cert.py` is safe (marks apply at collection, not import).
