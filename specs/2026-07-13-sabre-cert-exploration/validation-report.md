# Validation Report — Sabre CERT Exploration (Phase 25)
**Branch:** `vb/feature/sabre-cert-exploration`  
**Commit:** `2fd016339686f7a34363b7e6d909083ab298f4ac`  
**Date:** 2026-07-13

## Summary

**FAIL.** The no-credential suite is green (331 passed), the six live CERT tests pass,
the documented auth bridge works, the current credentials provide real read-side air
shopping, and no production Sabre code or credential material changed. Two acceptance
criteria fail: the create test can silently pass without cleanup when a created PNR's
success payload fails Pydantic validation, and the required cross-domain Try-it-Out sweep
is incomplete. Different-day/post-reset repeatability is untestable from the evidence
available on 2026-07-13.

## Criterion-by-criterion results

### Automated — hermetic suite and CI safety

- **Criterion:** Full hermetic suite stays green with no Sabre environment variables;
  CERT tests are deselected and no collected test attempts network access.
- **Status:** PASS
- **Evidence:** The running backend container reported both `SABRE_API_USER_ID` and
  `SABRE_API_SECRET` unset. `docker compose exec -T backend pytest` collected 341 tests,
  deselected all 6 CERT tests, and finished `331 passed, 4 skipped, 6 deselected` in
  5.18 s. `backend/pytest.ini:7-9` applies `-m "not cert"` by default and registers the
  marker.
- **Notes:** Seven warnings were emitted by pre-existing tests; none involved CERT or
  network access.

### Automated — live CERT suite

- **Criterion:** Credentialed `pytest -m cert` covers auth, BFM v5 search,
  createBooking, and cancelBooking through the unmodified real client; shape or
  entitlement failures must be precisely documented.
- **Status:** PASS
- **Evidence:** The documented credentialed command ran
  `tests/test_sabre_cert.py` against CERT and finished `6 passed in 3.53s`:
  `test_auth_token_mints_via_real_client`, `test_shapes_pos_field_is_dead`,
  `test_flight_search_via_client_lacks_pos_and_gets_400`,
  `test_bfm_empty_response_omits_sections_shapes_require`,
  `test_create_booking_unauthorized_tripwire`, and
  `test_cancel_booking_is_authorized`. The accepted shape/entitlement findings are
  documented in `sabre-cert-notes.md:65-108` as Phase 24 work items.
- **Notes:** Search and create do not succeed functionally with these credentials: BFM
  is empty after a raw POS workaround and createBooking is unauthorized. This is an
  allowed documented finding under the criterion, not an unexplained test error.

### Automated — cancel guarantee

- **Criterion:** A create test failure cannot leave a PNR behind; the finally path must
  be covered by inspection and a forced-failure dry run.
- **Status:** FAIL
- **Evidence:** The ordinary forced-success dry run passed: a fake successful create
  returned confirmation `FORCED1`, `pytest.fail` fired, and the `finally` block called
  cancel. However, `backend/tests/test_sabre_cert.py:232-233` catches every Pydantic
  `ValidationError` and returns before any cleanup. A second dry run simulated a success
  payload containing confirmation `ORPHAN1` but missing other required
  `CreateBookingResponse` fields. The test returned PASS and never invoked cancel.
- **Notes:** If CERT creates a PNR but its success payload drifts from the current shape,
  the real client raises during validation and the test misclassifies that as the known
  unauthorized response. The `finally` block at `backend/tests/test_sabre_cert.py:238-245`
  only has a confirmation when model validation already succeeded.

### Automated — frozen production client

- **Criterion:** `git diff vb/dev -- backend/api/sabre/` is empty.
- **Status:** PASS
- **Evidence:** The command produced no output at commit
  `2fd016339686f7a34363b7e6d909083ab298f4ac`.
- **Notes:** Branch changes are confined to pytest configuration, a new CERT test,
  specs/docs, and probes.

### Automated — credential hygiene

- **Criterion:** No raw user ID, secret, or captured token is committed; `config/.env`
  is untouched.
- **Status:** PASS
- **Evidence:** A fixed-string scan of `git diff vb/dev...HEAD` for the two values loaded
  from `config/.env` returned zero matches. A token-prefix pattern scan returned zero
  matches. `git diff --quiet vb/dev...HEAD -- config/.env` passed.
- **Notes:** Values and token material were not printed during validation.

### Manual — auth recipe and Phase 24 environment bridge

- **Criterion:** `probes/auth_check.py` authenticates against CERT from scratch, and the
  notes document the working grant and exact environment bridge for the unmodified real
  client.
- **Status:** PASS
- **Evidence:** The documented probe ran in a fresh process and reported a bearer token
  with `expires_in: 604800`; token metadata was redacted. `sabre-cert-notes.md:12-63`
  records the working v2 client-credentials recipe, states that v3 was not needed, and
  derives `SABRE_BASE_URL` plus `SABRE_CLIENT_SECRET` from the raw pair.
- **Notes:** The probe is stateless, so no local token cache existed to preserve between
  runs.

### Manual — notes: auth subsection

- **Criterion:** Notes identify the grant that worked and any attempted grant that did
  not.
- **Status:** PASS
- **Evidence:** `sabre-cert-notes.md:12-39` identifies v2 client credentials as
  verified-live and says v3 was not attempted because v2 worked.
- **Notes:** This matches the criterion's “if tried” qualification.

### Manual — notes: endpoint/entitlement matrix and Try-it-Out sweep

- **Criterion:** Matrix covers all modeled endpoints and the Try-it-Out sweep, with each
  row classified as works, not entitled, or errored.
- **Status:** FAIL
- **Evidence:** The live `probes/sweep.py` run reproduced the ten endpoints implemented
  at `probes/sweep.py:70-105`: eight HTTP-200 results and two schema HTTP-400 results.
  The requirements clarify the full sweep as air schedules, availability,
  exchange/reshop, hotel/lodging, ground/car, and utility/content
  (`requirements.md:29-31`). The probe and matrix contain no schedules, availability,
  exchange/reshop, or ground/car rows. `modifyBooking` is marked untestable/inferred at
  `sabre-cert-notes.md:82`, not classified from an executed probe. EnhancedSeatMap is a
  notes-only GET 404 even though the notes identify it as POST-only.
- **Notes:** The endpoints that are present match the live 2026-07-13 results; the
  failure is completeness, not drift in those findings.

### Manual — notes: request/response deltas

- **Criterion:** Every mock-shape delta is tagged as a Phase 24 item or explicitly
  harmless.
- **Status:** PASS
- **Evidence:** `sabre-cert-notes.md:90-120` records five deltas under the heading
  “all Phase 24 work items,” including dead POS typing, empty BFM response fields,
  HTTP-200 Booking Management errors, request extensions, and missing InstaFlights
  shapes.
- **Notes:** The live CERT tests directly exercise the first three.

### Manual — notes: rate limits and credential reset

- **Criterion:** Notes record observed rate limits plus the reset caveat and
  re-bootstrap steps.
- **Status:** PASS
- **Evidence:** `sabre-cert-notes.md:86-88` records no 429s or rate-limit headers over
  roughly 40 calls. `sabre-cert-notes.md:157-160` gives the auth/sweep rerun steps and
  reset warning; the auth section supplies the bootstrap recipe.
- **Notes:** The limit is correctly labeled inferred rather than claimed as a measured
  quota.

### Manual — notes: Flight Search API v1 answer

- **Criterion:** Flight Search API v1 entitlement has a definite yes/no/blocked answer.
- **Status:** PASS
- **Evidence:** `sabre-cert-notes.md:122-128` answers **YES** for
  `GET /v1/shop/flights`. The validator's sweep reproduced HTTP 200 with real priced
  itineraries.
- **Notes:** The documented `onlineitinerariesonly=N` caveat remains relevant.

### Manual — notes: demo implications

- **Criterion:** Notes end with concrete demo-unlock recommendations, a deal-engine
  decision, and Phase 24 risks.
- **Status:** PASS
- **Evidence:** `sabre-cert-notes.md:130-160` concludes “real shopping, mock booking” and
  gives six ordered recommendations, including a deal-engine go, Phase 24 shape/error
  work, and an event-day entitlement ask.
- **Notes:** The section is actionable without re-reading the raw probe history.

### Manual — PNR hygiene after validation

- **Criterion:** No lingering test booking remains; every recorded confirmation is read
  or cancelled again after probe/test sessions.
- **Status:** PASS
- **Evidence:** The live CERT test and guarded `booking_lifecycle.py` probe both received
  HTTP 200 `UNAUTHORIZED_ACCESS` from createBooking and no confirmation ID. Therefore
  the set of recorded confirmation references was empty. The probe's unexpected-success
  path has a `finally` cancellation at `probes/booking_lifecycle.py:112-119`.
- **Notes:** No PNR existed to read or cancel in the observed sessions. This does not
  repair the separate automated cleanup-guarantee failure above.

### Manual — repeatability across a different day or credential reset

- **Criterion:** A second `pytest -m cert` run on a different day, or after a credential
  reset, succeeds using only the documented steps.
- **Status:** UNTESTABLE
- **Evidence:** All repository notes and validator runs are dated 2026-07-13; no
  credential reset occurred during validation. Same-day fresh-process auth and the live
  six-test run passed, but neither satisfies the stated temporal condition.
- **Notes:** `backend/tests/test_sabre_cert.py:91,122` hard-code 2026-08-13 travel dates,
  so the suite is time-bounded even if the credentials remain valid.

### Tone check

- **Criterion:** Notes use confidence labels, trimmed payloads, and tables in the prior
  notes style.
- **Status:** PASS
- **Evidence:** `sabre-cert-notes.md` labels claims verified-live/docs-only/inferred,
  uses an endpoint table, records only shape-relevant snippets, and contains no raw
  credential or token value.
- **Notes:** No user-facing product copy was introduced.

### Definition of done

- **Criterion:** (1) CERT auth and bridge are reproducible.
- **Status:** PASS
- **Evidence:** See the auth results above.
- **Notes:** None.

- **Criterion:** (2) Search/create/cancel findings are proven through the real client
  and hermetic CI remains unaffected.
- **Status:** PASS
- **Evidence:** Six live tests passed; the no-credential suite passed with all six
  deselected.
- **Notes:** The allowed result is real search entitlement with documented BFM/create
  limitations, not successful PNR creation.

- **Criterion:** (3) The entitlement sweep and Flight Search v1 answer are recorded.
- **Status:** FAIL
- **Evidence:** Flight Search v1 is answered, but the required full cross-domain sweep is
  incomplete as detailed above.
- **Notes:** None.

- **Criterion:** (4) No production-client changes, secrets, or orphaned PNRs exist.
- **Status:** PASS
- **Evidence:** Production diff and secret scans are clean; observed create attempts
  returned no confirmation ID.
- **Notes:** The cleanup test still lacks the guarantee required by its separate
  criterion.

- **Criterion:** (5) Phase 25 is marked complete only after criteria 1-4 pass.
- **Status:** FAIL
- **Evidence:** `specs/roadmap.md:11` is already marked `[x] COMPLETE (implementation;
  manual QA pending)`, while definition-of-done item 3 fails.
- **Notes:** The validator did not edit the roadmap.

## Missing tests

- `backend/tests/test_sabre_cert_cleanup.py::test_shape_drift_after_created_pnr_still_cancels`:
  simulate a create response with a confirmation ID plus a schema mismatch and assert
  the confirmation is cancelled before the test fails.
- `backend/tests/test_sabre_cert_docs.py::test_sweep_manifest_covers_required_domains`:
  compare a canonical Try-it-Out endpoint/domain manifest with both `probes/sweep.py`
  and the notes matrix; require an explicit executed classification for every entry.
- `backend/tests/test_sabre_cert_docs.py::test_notes_have_required_decision_sections`:
  assert the auth bridge, deltas, rate/reset evidence, Flight Search answer, and final
  demo recommendation headings are present.
- No automated test can prove a different-day live rerun in ordinary hermetic CI. A
  scheduled/manual CERT job should retain dated results if this remains a release gate.

No validator-authored test file was added.

## Gaps in validation.md

- Which versioned endpoint inventory is the canonical “Try-it-Out sweep,” and must every
  endpoint be present in the runnable sweep probe as well as the notes matrix?
- When an endpoint depends on an upstream entitlement (for example modifyBooking after
  createBooking is denied), does `UNTESTABLE/inferred` satisfy the classification rule,
  or is an executed authorization probe required?
- When createBooking returns no confirmation references, is an empty per-reference PNR
  hygiene check sufficient, or should validation require an account-level booking list?
- What durable evidence should establish the different-day/post-reset repeatability
  criterion: a dated artifact, CI job URL, or a second signed validation report?

## Risks not covered by validation.md

- The live CERT tests hard-code 2026-08-13 travel dates, so their repeatability expires.
- `probes/sweep.py` prints `NETWORK-ERR` and still exits 0; a partially or wholly failed
  sweep can look successful to shell automation.
- `probes/booking_lifecycle.py` also exits 0 after createBooking errors without asserting
  the expected `UNAUTHORIZED_ACCESS` category, so entitlement drift requires manual
  output review.
