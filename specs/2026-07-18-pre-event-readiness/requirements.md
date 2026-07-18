# Phase 24 — Pre-event readiness: Requirements

Event day is **today, 2026-07-18**. This is the roadmap's last open phase: the readiness
bundle that survived every replan since 2026-07-13. Everything here either hardens the
morning smoke into a real drift alarm, closes a validator-proposed hermetic test, removes
known demo-day failure modes, or executes the readiness checks themselves.

## Scope

**Everything on the Phase 24 roadmap list is in scope** (settled at the spec interview),
ordered so demo-critical items land first and nice-to-haves can be dropped without ceremony
if the clock runs out.

| # | Item | Kind | Priority |
|---|------|------|----------|
| 1 | Fast-fail `place_call` without a session key — disrupt 502s before the break when the call payload carries neither `call_id` nor `room_name` | Code + tests | Demo-critical |
| 2 | Access gate: accept `?code=` on GET requests (+ tests, + README note) | Code + tests | Demo-critical |
| 3 | Consent-launch invariant test — AST assertion that no `await` sits between `consent.resolve(...GRANTED)` and `launch_trip_repairs` in `_watch_consent_then_repair` | Test only | Demo-critical |
| 4 | Sweep drift detection — `sweep.py` checks classifications against the notes matrix, exits nonzero on deviation (403↔404 availability/exchange gateway flap = one class) | Code + tests | Smoke hardening |
| 5 | CERT priced-search tripwire de-brittling — probe the verified anchor (JFK→LAX) and/or several pairs; skip/xfail when all are drifted-empty; red means code broke, not cache emptied. Phase 33 rider: assert rich fields (`ElapsedTime`/cabin) parse present-or-cleanly-absent on whatever pair returns fares | Code + tests | Smoke hardening |
| 6 | Event-day-morning Sabre smoke — `auth_check.py` → `pytest -m cert` → `sweep.py` → demo-pair probe (scripted pair at scripted date, its repair route, and the reverse direction, informational) → single-instance cap re-confirm; dated artifact appended to the Phase 25 notes | Execution | Demo-critical |
| 7 | Two-repair rich-field lifecycle test — hermetic book → break → repair → break → repair over one flight item; each wholesale `details` write carries the full shared stamp, prior flight preserved under `rebooked_from` | Test only | Validator closure |
| 8 | Return-check-during-repair purity test — hermetic: seed an active repair/consent state, call `check_return_flights_impl`, assert repair events / consent state / session options byte-for-byte unchanged | Test only | Validator closure |
| 9 | Async test hygiene — chase the six unawaited-coroutine `RuntimeWarning`s in the concierge/repair tests to their fixtures/mocks and fix | Test hygiene | Nice-to-have |
| 10 | `APIConfig.swift` hardcoded dev Cloud Run URL review | Review | Nice-to-have |
| 11 | Phase 37 zero-quota iOS rehearsal — tabs, clean-slate booking, accessibility, offline/resume per `specs/2026-07-16-ios-cascade-demo/validation.md` | Manual QA (0 calls) | Nice-to-have |
| 12 | Device QA call paths — yes-path (2 calls), decline-path (1 call) on a physical iPhone via Xcode install | Manual QA (quota) | **Optional, last** |

**Out of scope:**

- The retired conditional punch list (dead `POS` field, empty-BFM shapes, BM errors-as-200,
  BFM offset-bearing conversion) — deleted with the 2026-07-14 no-entitlement-ask decision;
  documented in the Phase 25 notes only.
- The `git_pull_dev.sh` evidence-guard test — dropped at the 2026-07-16 evening replan
  (the guard was deliberately removed by commit `933f8e8`).
- Phase 37's booking-first device validation — **blocked, not waived**, on BACKLOG Phase 20's
  TEMP-bridge removal, which lost its arming trigger with the 2026-07-18 Apple-path drop.
- Any instruction tuning of conversational looseness (Phase 34 close-out decision stands).
- Fixing the revision-level `maxScale: 100` annotation — it's cosmetic; the service-level
  cap `run.googleapis.com/maxScale: '1'` is the real guarantee. **Touching that knob is the
  hazard**; item 6 only re-confirms it.

## Decisions

All three settled at the spec interview (2026-07-18, event-day morning):

1. **Full scope, priority-ordered.** All twelve items in one spec, sequenced so
   demo-critical work (fast-fail, gate, smoke) lands first and nice-to-haves (async
   hygiene, Device QA) sit past the cut line. If the clock runs short, the plan is cut
   from the bottom without renegotiation.
2. **The morning smoke is a plan task, not just a manual check.** Executing the full D4
   sequence and committing the dated artifact to
   `specs/2026-07-13-sabre-cert-exploration/sabre-cert-notes.md` is implementation work:
   it closes Phase 26's open different-day repeatability item (D4) and proves the
   de-brittled tripwire and drift-aware sweep against live CERT **today** — the day it
   matters. The smoke runs *after* the smoke-hardening code (items 4–5) so `pytest -m cert`
   can't false-alarm on cache drift.
3. **Zero-quota bias.** Every plan task must be executable without spending an outbound
   call: hermetic tests, CERT probes (HTTP, not calls), code, simulator work. The only
   call-burning item — Device QA's yes/decline paths (3 calls total) — is explicitly
   optional, operator-triggered, and last; **rehearsal keeps the quota** (10/day, reset
   00:00 UTC — event day starts with a full pool).

Derived working decisions:

- **Fast-fail semantics** (roadmap wording): disrupt returns **502 before the break and
  before quota-relevant state changes** when a successful `vb call` returns neither
  `call_id` nor `room_name` — a fast, visible failure instead of a consent watcher
  drifting to its 3-minute timeout on a join key that will never match.
- **Gate exposure accepted**: `?code=` on GETs adds nil marginal exposure — codes already
  ride in page URLs and it's a shared demo secret, not a security boundary
  (tech-stack § Backend, access-code gate). Header behavior is unchanged; the query param
  is an additional GET-only source.
- **Tripwire red = code, not cache**: the de-brittled cert test tries the verified anchor
  (JFK→LAX) and a small pair list; all-empty ⇒ skip/xfail with a message naming the drift;
  a failure means the parse/auth/request path actually broke. Rich fields assert
  present-or-cleanly-absent (defaults, never a skipped itinerary) on whatever pair returns.
- **Sweep deviation classes**: compare each endpoint's observed classification against the
  expected matrix from `sabre-cert-notes.md`; the availability/exchange 403↔404 gateway
  flap counts as one class; any other deviation (e.g. InstaFlights flipping to 403 after a
  credential reset) exits nonzero.

## Context

- **Constitution:** `specs/mission.md` (success = the live demo lands; App Store is closed,
  web surfaces + Xcode install are the demo paths), `specs/tech-stack.md` (§ Testing for
  the `cert` fence and hermetic rules; § Backend for the consent watcher, `room_name` join,
  and access gate; § Deployment for the single-instance cap and trigger flow).
- **Key files:** `backend/api/demo.py` (`_watch_consent_then_repair`, disrupt),
  `backend/api/access_gate.py`, `backend/tests/test_sabre_cert.py`,
  `specs/2026-07-13-sabre-cert-exploration/probes/` (`auth_check.py`, `sweep.py`),
  `specs/2026-07-13-sabre-cert-exploration/sabre-cert-notes.md` (expected matrix + artifact
  destination), `backend/api/repair_tools.py` + `backend/api/flight_options.py` (lifecycle
  test), `backend/api/concierge.py` (`check_return_flights_impl`, purity test),
  `ios/TalkToMyTrip/` (`APIConfig.swift`).
- **Testing conventions:** hermetic by default (no creds, no network); cert tests are
  fenced behind `-m cert` and run via `docker compose exec -e` with the raw credential
  pair; travel dates computed, never literal; run pytest inside the container
  (host Python breaks tooling). New tests follow existing patterns in
  `backend/tests/`.
- **Standing rule (2026-07-16 replan):** `validation.md` must **not** require PR-body
  evidence — run evidence lives in this spec directory and the changelog entry.
- **Quota reality:** 10 outbound calls/day, reset 00:00 UTC (5 PM PDT yesterday — today's
  pool is full). One full cascade run = 2 calls. The web probe loop
  (`/v1/web_call/query` curl with a unique `session_name` per call) is quota-free.
- **Cache reality:** JFK→LAX is the verified demo anchor (July 21 menu is JFK→LAX **only**
  as of the 2026-07-16 probe loop); per-pair windows shift hour-to-hour and as the UTC day
  rolls; the reverse pair and round-trip variants are closed on InstaFlights — the
  reverse-direction probe is informational only (return answers ride Tavily).
- **Tone:** no user-facing copy in this phase except the gate's README note — plain
  operator prose, matching the existing "Running it live" run-sheet register.
