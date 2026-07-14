# Plan — Validation Fixes (Phase 26)

Task groups are independently implementable; group 4 is the only one that touches the live CERT network and should run after group 3 so the hardened probes are what execute.

## 1. Tripwire rework (`backend/tests/test_sabre_cert.py`)

1. Extract the create-attempt-with-cleanup logic into a module-level helper (e.g. `_attempt_create_harvesting_confirmation(client, request)`): call `client.create_booking(...)`; on pydantic `ValidationError`, recover the raw response dict from the error's `input` (`exc.errors()[0]["input"]` walks back to the payload `model_validate` received) and harvest any `confirmationId` found there; return `(created_model_or_None, raw_dict_or_None, harvested_confirmation_or_None)`. Keep it dependency-injectable (client passed in) so the hermetic test in group 2 can drive it with a fake.
2. Rework `test_create_booking_unauthorized_tripwire` on that helper: the `finally` block cancels **any** harvested `confirmationId` — whether validation succeeded, failed, or the payload drifted — before the test resolves.
3. On the expected entitlement-wall path, stop treating any `ValidationError` as success: assert the raw response's `errors[]` contains category `UNAUTHORIZED_ACCESS` explicitly (the `booking_lifecycle.py` finding). A `ValidationError` whose raw payload lacks that category is drift and must fail the test.
4. Replace both hard-coded `2026-08-13` dates (`_search_request_without_pos`, `_booking_request`) with computed future dates via a module helper mirroring the probes' pattern (`date.today() + timedelta(days=30)`); derive the `departureDate`/`DepartureDateTime` strings from it.

## 2. Hermetic shape-drift-still-cancels test (new `backend/tests/test_sabre_cert_cleanup.py`)

1. New test file **without** the `cert` marker or env skipif: `test_shape_drift_after_created_pnr_still_cancels`.
2. Build a fake client whose `create_booking` raises `ValidationError` constructed from a simulated success payload carrying `{"confirmationId": "ORPHAN1", ...}` but missing other required `CreateBookingResponse` fields (drive it through `shapes.CreateBookingResponse.model_validate` so the error `input` is realistic), and whose `cancel_booking` records the call.
3. Run the group-1 tripwire flow against the fake; assert `cancel_booking` was invoked with `ORPHAN1` **and** the flow still signals failure (the drifted payload is not the documented entitlement wall).
4. Also cover the validator's original dry-run case: a fake *successful* create (`FORCED1`) must reach cancel via `finally`.
5. Confirm the file collects and passes in the bare hermetic run (`pytest` with no Sabre env vars).

## 3. Probe hardening (`specs/2026-07-13-sabre-cert-exploration/probes/`)

1. `sweep.py`: have `classify()` report (return or count) a `NETWORK-ERR` outcome; `main()` returns nonzero if any endpoint hit `NETWORK-ERR`, so a partially failed sweep can no longer look successful to shell automation.
2. `booking_lifecycle.py`: on the create-error path, assert the `errors[]` categories include `UNAUTHORIZED_ACCESS` — print the mismatch and return nonzero on drift (any other category set, or an empty `errors[]` without a `confirmationId`).
3. Keep both probes stdlib-only, credential-hygienic (no token/secret printing), and runnable via the documented `docker compose exec` stdin command.

## 4. Sweep extension + executed classifications (live CERT)

1. Extend `sweep.py` with one classified call per missing domain (paths per Sabre's Try-it-Out REST set; keep the existing `classify` output format):
   - **Air schedules** (e.g. `GET /v1/shop/flights/schedules` family)
   - **Air availability** (the availability endpoint the Try-it-Out set exposes)
   - **Exchange/reshop** (e.g. Exchange Shop `POST /v3/exchange/shop`)
   - **Ground/car** (e.g. Car Availability / ground transportation lookup)
   - **EnhancedSeatMap via POST** (replacing the notes-only GET 404 row)
   - **modifyBooking via dummy PNR** (`POST /v1/trip/orders/modifyBooking`, `confirmationId: "ABCDEF"` — expected clean business error proving authorization, per D2)
2. Run the extended sweep live against CERT with the documented credential passthrough; expect exit 0 (no `NETWORK-ERR`).
3. Append the executed classifications to the endpoint matrix in `sabre-cert-notes.md` as rows dated **2026-07-14** with `verified-live` labels; replace/supersede the inferred modifyBooking row and the GET-404 EnhancedSeatMap row, noting the supersession inline so the 2026-07-13 record stays legible.

## 5. Docs-contract test (`backend/tests/test_validator_docs_contract.py`)

1. Add `test_notes_have_required_decision_sections`: read `specs/2026-07-13-sabre-cert-exploration/sabre-cert-notes.md` (path-from-repo-root per the file's existing convention) and assert headings exist covering: auth bridge (`Phase 24 env bridge`), deltas (`Deltas vs. mock shapes`), rate limits/reset, Flight Search API v1 answer, and demo recommendations (`What this unlocks for the demo`). Match on stable substrings, not exact strings.
2. If the rate/reset evidence has no heading anchor, promote it to one in `sabre-cert-notes.md` (authorized edit) rather than weakening the test to prose-matching.

## 6. Verification pass

1. Bare hermetic suite green with no Sabre env vars: all `cert` tests deselected, the two new hermetic tests collected and passing.
2. Credentialed `pytest -m cert` green (documented command); confirm the reworked tripwire passes against live CERT.
3. `grep -r "2026-08-13"` over `backend/tests/` and the probes returns nothing.
4. Commit; PR to `vb/dev` per branch strategy.

> **Close-out (not on this branch, per interview):** re-run `sdd-validate-feature` against the Phase 25 + 26 criteria in a separate session, and capture the different-day `pytest -m cert` output as a dated artifact appended to `sabre-cert-notes.md` — event-day morning at the latest (D4). This may ride with the Phase 24 event-day smoke.
