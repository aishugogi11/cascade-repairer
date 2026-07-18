# Phase 24 — Pre-event readiness: Validation

Per the standing 2026-07-16 replan decision, this file requires **no PR-body evidence** —
run evidence lands in this spec directory and the changelog entry.

## Automated

All run inside the container (`docker compose exec` — host Python is not the test
environment).

1. **Bare suite green and hermetic**: `pytest` with default addopts (cert deselected)
   passes with no GCP credentials and no `OPENAI_API_KEY`/`TAVILY_API_KEY`/`RESEND_API_KEY`
   set. No new test requires network.
2. **Fast-fail disrupt**: a mocked `place_call` returning a payload with neither `call_id`
   nor `room_name` makes `POST /disrupt` return **502**, with the flight item's status
   unchanged and no consent-watcher state created. Existing disrupt invariants stay green:
   404-before-quota on an unbreakable trip, call-before-any-write, sanitized payload.
3. **Access gate `?code=` on GET**: tests assert — GET with only a correct `?code=` passes;
   GET with a wrong `?code=` 401s; a non-GET with only `?code=` still 401s; the
   `X-Access-Code` header works everywhere unchanged; the public allowlist is untouched;
   fail-open with `DEMO_ACCESS_CODE` unset still warns-and-passes.
4. **Consent-launch AST invariant**: the new test fails if any `await` is introduced
   between `consent.resolve(...GRANTED)` and `launch_trip_repairs` in
   `_watch_consent_then_repair` (verify by inspection that the assertion actually walks
   the statements between the two calls, not just their presence).
5. **Two-repair lifecycle**: the new hermetic test walks book → break → repair → break →
   repair on one flight item and asserts every wholesale `details` write carries the full
   shared `details_from_option` key set (parity with `flight_options`) and the prior
   flight under `rebooked_from` (including `airline_name`).
6. **Return-check purity**: the new hermetic test seeds an active repair/consent state,
   calls `check_return_flights_impl`, and asserts repair events, consent state, and
   session flight options are byte-for-byte unchanged.
7. **Tripwire de-brittled**: `test_instaflights_search_returns_real_priced_itineraries`
   (cert-fenced) tries the anchor-first pair list with computed dates and
   **skips/xfails — does not fail — when every pair is drifted-empty**; when a pair
   returns fares, the rich fields assert present-or-cleanly-absent. Verified two ways:
   the live run in the morning smoke, and by reading the drift branch (no hermetic
   harness mocks the cert path — that fence is deliberate).
8. **Sweep drift detection**: `sweep.py` exits nonzero on a classification deviating from
   the notes matrix (not only `NETWORK-ERR`), with the availability/exchange 403↔404 flap
   treated as one class — covered by the extracted comparison-logic unit test (or the
   documented dry-run self-test if extraction wasn't cheap).
9. **Async hygiene** *(if group 5 survived the cut)*: the bare suite emits zero
   unawaited-coroutine `RuntimeWarning`s from the concierge/repair tests.

## Manual

1. **Morning smoke executed and committed** (the phase's core deliverable): the dated
   2026-07-18 artifact appended to
   `specs/2026-07-13-sabre-cert-exploration/sabre-cert-notes.md` shows — `auth_check.py`
   clean; `pytest -m cert` run with outcome noted (pass, or skip-on-drift with the pairs
   tried); `sweep.py` exit 0 against the expected matrix; the scripted-pair probe results
   (JFK→LAX July 21: fares or honest-empty), the repair-route probe, and the reverse-pair
   probe (informational). This closes Phase 26's D4 item.
2. **Single-instance cap**: the `gcloud run services describe` check printed `1`; the
   revision-level annotation was **not** modified.
3. **Gate in a browser**: a gated JSON endpoint (e.g. `/v1/sabre_tools/search_log`)
   opened directly in a browser with `?code=` returns data instead of 401, on the
   deployed service after merge.
4. **Fast-fail visibility**: reasoning documented (or a controlled check performed) that a
   session-key-less call surfaces as an immediate visible 502 on the cascade page's
   disrupt path rather than a silent 3-minute stall — no live quota spend required to
   validate; the hermetic tests carry the behavior.
5. **iOS items** *(if group 6 survived the cut)*: the `APIConfig.swift` finding is
   documented in this spec dir; the Phase 37 zero-quota rehearsal checklist run and
   its results noted.
6. **Device QA** *(optional group 7 — explicitly not required for done)*: if run, note
   yes-path and decline-path outcomes and calls spent.

## Edge cases

- Gate: `?code=` present but empty; code in both header and query with only one correct
  (header wins); an allowlisted page shell with a wrong `?code=` still serves (shells are
  public).
- Disrupt fast-fail: payload with `room_name` but no `call_id` (usable — must NOT 502);
  payload with `call_id` but no `room_name` (usable); payload with neither (502).
- Tripwire: exactly one pair in the list returns fares (assert on it, don't skip);
  rich fields absent on a returned itinerary (defaults asserted, itinerary not skipped).
- Lifecycle test: the second repair's `rebooked_from` holds the **first repair's** flight,
  not the original — the "immediately prior" contract.

## Tone check

The only user-facing copy is the README gate note — operator prose matching the existing
run-sheet register ("Running it live"); no marketing tone, no security theater (the code
is a shared demo secret and the note should say so plainly).

## Definition of done

- Groups 1–4 complete: demo-critical code + tests merged, smoke instrumentation merged,
  the three validator-closure/invariant tests green in the bare suite, and the dated
  morning-smoke artifact committed to the Phase 25 notes.
- Bare suite green in the container; cert suite behavior verified live in the smoke.
- Groups 5–6 done **or explicitly noted as cut** in the changelog entry (the cut is
  pre-authorized by the spec — noting it is the only requirement).
- Group 7 remains optional; running or skipping it does not affect done.
- Phase 24 marked `[x] COMPLETE` in `specs/roadmap.md` — closing the roadmap's last
  open phase.
