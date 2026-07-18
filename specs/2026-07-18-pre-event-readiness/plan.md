# Phase 24 — Pre-event readiness: Plan

Ordered demo-critical-first with a hard zero-quota bias. Groups 1–4 are the substance;
groups 5–6 are cut-line candidates; group 7 is optional and operator-triggered. If the
clock runs short, cut from the bottom — no renegotiation needed.

## 1. Demo-critical hardening

1.1 **Fast-fail `place_call` without a session key** (`backend/api/demo.py`): when the
    `vb call` payload returns neither `call_id` nor `room_name`, `POST /disrupt` returns
    **502 before the flight is broken and before any quota-relevant state changes** —
    no consent watcher is started on a join key that can never match.
1.2 Tests for 1.1: hermetic — mock `place_call` returning a payload with no usable session
    key; assert 502, assert the trip's flight item is untouched, assert no watcher/consent
    state was created. Keep the existing happy-path and 404-before-quota invariants green.
1.3 **Access gate `?code=` on GETs** (`backend/api/access_gate.py`): on GET requests,
    accept the access code from the `?code=` query param in addition to the `X-Access-Code`
    header (header still wins when both present; non-GET methods unchanged; fail-open
    behavior when `DEMO_ACCESS_CODE` is unset unchanged).
1.4 Tests for 1.3: GET with `?code=` only (200), wrong `?code=` (401), POST with `?code=`
    only (still 401 — GET-only), header still works, allowlist untouched.
1.5 README note for 1.3 in the operator material: JSON endpoints are now
    browser-debuggable with the code in the URL on event day.
1.6 **Consent-launch invariant test** (new hermetic test): parse
    `backend/api/demo.py` with `ast`, locate `_watch_consent_then_repair`, and assert no
    `await` expression sits between the `consent.resolve(...GRANTED)` call and the
    `launch_trip_repairs` call — the atomic-grant property currently guaranteed only by
    source inspection.

## 2. Smoke instrumentation

2.1 **Sweep drift detection**
    (`specs/2026-07-13-sabre-cert-exploration/probes/sweep.py`): encode the expected
    per-endpoint classification matrix (from `sabre-cert-notes.md`) in the probe; after a
    run, compare observed vs expected and **exit nonzero on any deviation**, not just
    `NETWORK-ERR`. The availability/exchange 403↔404 gateway flap is treated as a single
    expected class; anything else (e.g. InstaFlights → 403 after a credential reset) trips.
2.2 Unit coverage for 2.1's comparison logic (hermetic — the classification-diff function
    tested against synthetic observed/expected pairs, including the flap-equivalence case),
    if the probe's structure allows extracting it cheaply; otherwise a dry-run self-test
    flag documented in the probe header.
2.3 **De-brittle the CERT priced-search tripwire**
    (`backend/tests/test_sabre_cert.py::test_instaflights_search_returns_real_priced_itineraries`):
    replace the hardcoded DFW→LAX +30d with an anchor-first pair list (JFK→LAX first, then
    a small shortlist), computed dates; first pair returning fares is asserted on;
    **all-empty ⇒ `pytest.skip`/`xfail`** with a message naming cache drift — a red now
    means the request/parse path broke.
2.4 **Rich-field cert assertion** (Phase 33 rider, same test or a sibling): on whatever
    anchor pair returned fares, assert the rich fields (`ElapsedTime`→`duration_minutes`,
    cabin) parse **present-or-cleanly-absent** — defaults, never a skipped itinerary.

## 3. Hermetic validator-closure tests

3.1 **Two-repair rich-field lifecycle test** (new test, mocked repositories + mock Sabre):
    book → break → repair → second break → second repair over a single flight item;
    assert each wholesale `details` write carries the full shared
    `flight_options.details_from_option` stamp and preserves the immediately prior flight
    under `rebooked_from` (with its `airline_name` for the was-line) — the integrated
    guard for the exact two-break sequence the live demo performs.
3.2 **Return-check-during-repair purity test** (new test, mocked repositories, in-process
    registries): seed an active repair/consent state, call `check_return_flights_impl`,
    assert repair events, consent state, and session options are **byte-for-byte
    unchanged** — the zero-quota structural closure of Phase 34's untested mid-repair edge.

## 4. Event-day morning smoke (execution — zero outbound calls)

Run after groups 1–3 are green so the smoke exercises the de-brittled tripwire and
drift-aware sweep. All steps are HTTP probes and test runs — no call quota spent.

4.1 `probes/auth_check.py` — detect overnight credential resets.
4.2 `pytest -m cert` via `docker compose exec -e` with the raw credential pair (command at
    the top of `test_sabre_cert.py`) — now drift-tolerant per 2.3/2.4.
4.3 `probes/sweep.py` — now a real drift alarm per 2.1.
4.4 Demo-pair probe loop (README "Demo-day: check which flight pairs are live" —
    `/v1/web_call/query` curl, **unique `session_name` per call**):
    the scripted pair (JFK→LAX) at the scripted date (July 21), then the **repair
    re-shop route** for that pair (Phase 29 rider), then the **reverse direction** at the
    scripted return date (Phase 34 rider — informational only; nothing gates on it).
4.5 Re-confirm the single-instance cap (verification only — **do not touch the knob**):
    `gcloud run services describe vocal-bridge-be-dev
    --format='value(metadata.annotations."run.googleapis.com/maxScale")'` → expect `1`.
4.6 Append the dated artifact (commands + output + observed pair menu) to
    `specs/2026-07-13-sabre-cert-exploration/sabre-cert-notes.md` — this closes Phase 26's
    open different-day repeatability item (D4).

## 5. Test hygiene *(cut-line candidate)*

5.1 **Async test hygiene**: chase the six unawaited-coroutine `RuntimeWarning`s in the
    concierge/repair tests to their fixtures/mocks; fix or properly close the coroutines.
    Bare suite runs warning-clean for this class afterward.

## 6. iOS readiness — zero quota *(cut-line candidate)*

6.1 **`APIConfig.swift` review**: assess the hardcoded dev Cloud Run URL; document the
    finding (and fix only if trivial — the Apple path is closed, so a dev-URL default may
    be exactly right for Xcode-install distribution; record the reasoning either way).
6.2 **Phase 37 zero-quota rehearsal** per `specs/2026-07-16-ios-cascade-demo/validation.md`:
    tabs, clean-slate booking, accessibility pass, offline/resume — simulator or device,
    no outbound calls.

## 7. Device QA — optional, operator-triggered, quota-burning (3 calls)

Explicitly **not** required for this phase to complete; rehearsal keeps the quota.
Run only if Josh decides the pool allows it after demo rehearsals are protected.

7.1 Yes-path on a physical iPhone via Xcode install (`SABRE_MODE=mock`; 2 calls):
    the three acts, sheet & gestures, per Phase 17 validation.md § 7 and the Phase 37
    device-run script.
7.2 Decline-path (1 call): consent declined → stand-down + re-armed Cancel.

*(Blocked, not part of this plan: the booking-first device validation — waits on BACKLOG
Phase 20's TEMP-bridge removal, which currently has no arming trigger.)*
