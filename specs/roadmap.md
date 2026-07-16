# Roadmap

High-level implementation order for the hackathon-ready foundation. Hackathon day is **July 18, 2026** — every phase before the last must land ahead of it. Each phase is narrowly scoped and becomes a feature branch (`vb/feature/<feature-name>`); mark a phase `[x] COMPLETE` in its heading when done.

Phases appear in **execution order** — the first heading not marked `[x] COMPLETE` is what `sdd-feature-spec` picks up next. Phase numbers are historical IDs, not ordering. Completed phases have moved to [changelog.md](changelog.md) — this file tracks only open and upcoming work; deferred phases (14 → 13 → 15, plus the approval-gated v1.0.1 bridge removal, Phase 20) wait in [BACKLOG.md](BACKLOG.md) behind everything here. `IOS_PLAN.md` is the umbrella plan.

**State as of 2026-07-12 (late-night replan):** Phase 21 (voice booking page) is merged, deployed, and QA'd, and **Phase 17 is complete** — the full three-act build was submitted to App Review 2026-07-11; per `mission.md` #4 approval is a bonus, the web surfaces are the demo path, and no new binary is uploaded until the in-review one is approved (BACKLOG Phase 20). Details in [changelog.md](changelog.md). **Restoration note:** this replan re-restores the 2026-07-12 evening replan's roadmap (PR #34, commit `4ac1bb0`), which the booking-page branch's merge resolution (PRs #35/#36) had silently reverted — Phase 17's completion and Phases 22–24 below were lost from this file for a few hours; if a roadmap statement conflicts with the changelog, trust the changelog. Open work, in order: the cascade dashboard (Phases 22–23) on the visual frame Phase 21 established, then pre-event readiness (Phase 24 — **time-gated, not order-gated**: pull the Sabre-keys work ahead the moment the keys arrive, expected Monday 2026-07-13).

**Update 2026-07-13 (Phase 25 archived):** the Sabre CERT exploration ran the same day the keys landed and is archived to [changelog.md](changelog.md) with caveats — headline finding: **real shopping, mock booking** (Flight Search API v1 entitled with real priced itineraries; `createBooking` entitlement-blocked at `PassengerDetailsRQ`; full matrix and demo recommendations in `specs/2026-07-13-sabre-cert-exploration/sabre-cert-notes.md`). Its independent validation returned **FAIL**; the fixes shipped as **Phase 26** and the close-out re-validation passed 2026-07-14 (both archived to [changelog.md](changelog.md)). The deal-manufacturing upsell engine stays backlogged in [BACKLOG.md](BACKLOG.md) (revisit after Phase 23, minimum slice `extend_stay`); its API-entitlement gate is now answered **go**.

**Replan 2026-07-13 (evening; updated 2026-07-14):** the Phase 25 findings reshaped the tail of the roadmap. Order: **27 (real search in the demo path) → 22 → 23 → 24** (Phase 26, validation fixes, is complete and archived). All four validation-triage decisions were answered at the replan interview (targeted sweep additions, executed dummy-PNR probe for modifyBooking, empty-set PNR hygiene, dated re-run artifact); the frozen-client bug fixes (dead `POS` field, empty-BFM response shapes, BM errors-as-200 masking) are deliberately **conditional Phase 24 work** — they only matter if Sabre grants BFM content / booking entitlement, realistically via the event-day ask. One Phase 26 item remains open and rides with Phase 24: the **different-day `pytest -m cert` dated artifact** appended to `sabre-cert-notes.md` (D4 — event-day morning at the latest).

**Replan 2026-07-14 (evening — real data everywhere reachable):** Phase 27 shipped, deployed, and spoke real CERT fares on Cloud Run the same day, but its independent validation returned **FAIL** with two code defects (unmapped *connection* airports pass the parser; the mock's Pacific-fiction clocks are re-read as airport-local, so mock west-to-east arrivals precede departures) — those are now **Phase 28**. Two strategic facts landed the same evening (tech-stack § entitlement addendum): InstaFlights content is **per-pair** (113 of 731 supported pairs had +2-day content, so near-term real repair shopping is possible today), and **the Sabre entitlement-ask route is closed** (decision 2026-07-14) — Sabre's newer flightShop/flightShopLite are entitled-but-empty on this PCC and the MCP Server pilot can't bypass entitlements, so no unlock is coming. The cascade's credibility therefore rides on **Phase 29**: the flight-repair leg re-shops real InstaFlights data. Phases 27 and 28 shipped and deployed 2026-07-14 and are archived to [changelog.md](changelog.md). Phase 24's "event-day ask" bullet and its conditional BFM/booking punch list are deleted with the decision (the punch-list items remain documented in the Phase 25 notes if circumstances ever change).

**Replan 2026-07-14 (late night — Phase 28 close-out):** Phase 28's independent validation returned **FAIL** on acceptance-package gaps while every behavior criterion passed (report: `specs/2026-07-14-search-hardening/validation-report.md`) — criterion 6 needs all six committed metro-alias cases and the token-refresh tests cover only the GET path; the report also surfaced one real behavior risk (an empty repeat search leaves the previous options bookable) and one tooling hazard (`git_pull_dev.sh` defaults its merge base to `main`, not `vb/dev`, and merges with `--admin`). Those four items are **Phase 30**, a small close-out landing before Phase 29 builds on the search path (the Phase 26 precedent). Constitution updates from the same evening: the documented no-results 404 is now an honest empty (never a mock swap), 401s refresh the token once, `AIRPORT_TZ` covers the full live supported-markets list (metro + non-US codes) under a cert parity test, and the pair menu shifts **as the UTC day rolls** (00:00 UTC = 5 PM PDT) — evening rehearsals cross that boundary, sharpening the Phase 24/29 morning-smoke rule. Process lesson carried into Phase 30's spec: PR evidence must be in the description **pre-merge** (the validator's four `validation.md` gap questions are that spec interview's input). New order: **30 → 29 → 22 → 23 → 24**.

**Update 2026-07-15 (Phase 30 shipped):** the search-hardening close-out is complete, merged (PR #47), deployed, and archived to [changelog.md](changelog.md) — all four remediation items landed and the bare suite is green (387 passed). Its independent validation returned **FAIL** on two non-code items only, both re-verified as environmental: an empty PR #47 description (DoD-B — the pre-merge-evidence gap, now superseded by the `pr-evidence-guard` workflow, PR #48) and a live CERT priced-search test that hardcodes DFW→LAX +30d and drifted to honest-empty (JFK→LAX +30d returns real fares through the identical path). One brittle-test residual, now **folded into Phase 24** (2026-07-15 replan decision — see its CERT-tripwire bullet): the cert priced-search tripwire pins a single pair/date (DFW→LAX +30d), so it reds on morning-smoke purely from cache drift; Phase 24 de-brittles it. The same replan reconciled the constitution to the thin/volatile cache reality (tech-stack § 2026-07-15 addendum: JFK→LAX is the current verified demo anchor; the 2026-07-14 menu is stale) and narrowed Phase 22's `_LATEST_SEARCH` hardening to age-expiry only (Phase 30 already clears on non-optioned returns).

**Update 2026-07-15 (Phase 29 shipped; QA closed by the evening's Phase 31 rerun):** the real-repair pivot is implemented, merged (PRs #51/#52), and archived to [changelog.md](changelog.md) — the flight-repair leg now re-shops real InstaFlights data (BFM → `instaflights_search`), PNR writes stay mock, and the shared `FlightOption` parser is extracted to `backend/api/flight_options.py`. Its independent validation returned **FAIL on the acceptance package only** (DoD-B: PRs #51/#52 carry placeholder descriptions, not the required pre-merge mock/CERT snippets; local mock-mode BigQuery walkthrough untestable) — every implementation criterion passed and the bare suite is green (405 passed); **manual QA closed 2026-07-15 (evening PT)** — the Phase 31 live rerun drove the repair re-shop end to end on the deployed service (a real cancelled flight rebooked onto a *different* real InstaFlights flight, spoken by Call 2). Phase 24's morning-smoke keeps its Phase 29 rider regardless (probe the scripted pair's repair re-shop route on demo morning — cache windows drift).

**Update 2026-07-15 (Phase 22 shipped, QA'd, archived):** the consolidated cascade dashboard (`GET /v1/cascade/` — repair surfaces, disruption score, downstream impact, on-page demo triggers, Phase 23 voice placeholder, item-H age expiry) is merged (PR #53), deployed, manually QA'd on Cloud Run the same day, and archived to [changelog.md](changelog.md). Its independent validation returned **FAIL on the acceptance package only** (DoD-B again: PR #53 placeholder description; report in the spec dir). **QA produced the Phase 23 demo contract** (settled with Josh 2026-07-15): booking by voice, consent-gated repairs read from the VB transcript, the timer anchored at the spoken yes, real-trip call scripts, and a results callback.

**Update 2026-07-15 (evening — Phases 23 and 31 shipped and archived):** Phase 23 (live voice surfaces + the consent-gated demo flow, PR #54) and its same-day close-out Phase 31 (PR #55 — the `room_name` session join that unblocks Call 2, the different-flight rebooking guarantee, the re-trigger race, `trip_status` honesty, the `fix_trip` phone deferral, and the hardened PR-evidence guard) are merged, deployed, and archived to [changelog.md](changelog.md). **Manual QA closed the same evening (2026-07-15 PT): the live rerun PASSED** on the post-31 deploy (commit `2637754`) — booked by voice through the on-page orb, Call 1 asked consent from the real trip's data, the spoken yes granted and launched repairs with the timer anchored at the go-ahead, and **Call 2 arrived speaking a different rebooked flight**. Both phases are fully complete. Two same-evening riders shipped on `vb/dev` ahead of the rerun (commits `1ac2659`/`2637754`, both deployed): the Phase 31 validation's fixes (the missing `broken`-status trip_status test; the max-instances roadmap correction — the service-level cap was already `1`) and the **New trip clean-slate control** — the rerun's first attempt hit a client-side rebuild of the Phase 18 pin trap (the orb pins every fresh session to the displayed trip, making guided booking unreachable), fixed by a header control that clears the display, ends the live voice session, and re-adopts only a newly booked trip; README carries the operator run sheet. Open work: the one follow-up below, then **Phase 24**.

**Replan 2026-07-16 (constitution reconciled to the shipped one-page demo):** tech-stack now records what Phases 22–23/31 made true — `/v1/cascade/` is the demo's primary surface (the two-button `/v1/demo/` page is a kept backup, decision at this replan), the demo orchestrator is the consent-gated flow with the `room_name` session join, the Concierge carries `trip_status` / flight-identity stamping / the `fix_trip` phone deferral, the repair re-shop guarantees a different rebooked flight, the single-instance guarantee is the *service-level* Cloud Run cap, and `git_pull_dev.sh` is the PR-evidence guard (convention, not enforcement). Phase 24 gains four small items from this cycle's validation/QA findings (fast-fail `place_call`, `?code=` GET support on the gate, and the two invariant tests). `mission.md` unchanged — scope and audience didn't move.

**Open follow-ups (from Phases 23/31, 2026-07-15):**
- **PR #55 evidence**: the manual GitHub merge bypassed the new guard, so the description is still the unfilled template — backfill it with `gh pr edit 55 --body-file PR_BODY.md` (three sections: the mock/verification summary, the passing live-run notes with both call outcomes and the differing rebooked flight, and the pytest tail — currently 484 passed).

## Phase 24: Pre-event readiness

The residuals that survived Phase 17's completion, re-scoped at the 2026-07-13 evening replan and again 2026-07-14 (evening): **the full `SABRE_MODE=real` flip shipped with Phase 27** (search real on Cloud Run since 2026-07-14), and **the event-day entitlement ask is deleted** — decision 2026-07-14: no extra permissions are coming, so the former "conditional punch list" (dead `POS` field, empty-BFM shapes, BM errors-as-200, BFM offset-bearing time conversion) is retired from this roadmap; it stays documented in the Phase 25 notes' deltas if circumstances ever change. Everything here must land before July 18.

- **Event-day-morning Sabre smoke** (per replan decision D4; extended by the 2026-07-14
  evening replan): `probes/auth_check.py`, then `pytest -m cert`, then `probes/sweep.py`,
  then **probe InstaFlights for the scripted demo pair at the scripted date** — the
  manual form now exists and shipped 2026-07-15 (README "Demo-day: check which flight
  pairs are live" — the `/v1/web_call/query` curl loop; unique `session_name` per call).
  Phase 29 rider: per-pair cache windows shift hour-to-hour, so a green +30d sweep does
  not prove the demo date, and the scripted pair's **repair route** must be probed too.
  Detects overnight credential resets and entitlement drift before the first rehearsal;
  append the dated output to the Phase 25 notes (this may also be what closes Phase 26's
  different-day repeatability item).
- **Sweep drift detection** (2026-07-14 replan, from the Phase 26 close-out report): the
  sweep's exit code trips only on `NETWORK-ERR` — `SERVER-ERR` or a changed classification
  (e.g. InstaFlights flipping to 403 after a credential reset) still exits 0, so the
  morning smoke could look green while entitlements regressed. Teach `sweep.py` an
  expected-classification check against the notes matrix (exit nonzero on deviation,
  with the availability/exchange 403↔404 gateway flap treated as one class) so the D4
  smoke is a real drift alarm, not just a network check.
- **CERT priced-search tripwire brittleness** (2026-07-15 replan, Phase 30 close-out):
  `test_sabre_cert.py::test_instaflights_search_returns_real_priced_itineraries`
  hardcodes DFW→LAX +30d and **reds on cache drift alone** — proven 2026-07-15 (that pair
  honest-empty while JFK→LAX +30d returned real fares through the identical path), so the
  morning `pytest -m cert` step can false-alarm even when the code is healthy. De-brittle
  it: probe the verified anchor (JFK→LAX) and/or try several pairs, skip/xfail when all are
  drifted-empty, so a red means the code broke — not that the cache emptied.
- **Async test hygiene** (2026-07-14 replan, same report): the bare suite emits six
  unawaited-coroutine `RuntimeWarning`s across the concierge/repair tests (pre-Phase-26
  debt). Chase them to their fixtures/mocks and fix or properly close the coroutines —
  they can mask async cleanup defects in the exact code that keeps the agent talking
  during repairs.
- **Single-instance cap: verified, leave it alone** (Phase 31 validation, 2026-07-15):
  the service-level `run.googleapis.com/maxScale` is already `1` — the enforced cap
  protecting the in-process consent/session/search-log state. The revision-level
  `autoscaling.knative.dev/maxScale: 100` annotation is a cosmetic default that does
  NOT override it; an operator "fixing" that knob is the actual risk. Morning smoke
  may re-confirm with `gcloud run services describe vocal-bridge-be-dev
  --format='value(metadata.annotations."run.googleapis.com/maxScale")'`.
- **Fast-fail `place_call` without a session key** (2026-07-16 replan, from the Phase 31
  validation's risk list): a successful `vb call` that returns neither `call_id` nor
  `room_name` currently lets the disrupt succeed and the consent watcher drift to its
  3-minute timeout. Make disrupt 502 (before the break, before quota-relevant state)
  when the call payload carries no usable session key — a fast, visible failure
  instead of a demo-day mystery stall.
- **Access gate: accept `?code=` on GET requests** (2026-07-16 replan, from live-QA
  friction): the JSON endpoints are header-only, so browser debugging 401s even with
  the code in the URL. Teach `access_gate.py` to also read `?code=` on GETs (+ tests,
  + a README note) — codes already ride in page URLs, so marginal exposure is nil for
  a shared demo secret, and phone/browser debugging on event day gets much easier.
- **Two invariant tests** (2026-07-16 replan, the validator's proposals): an AST test
  asserting no `await` sits between the consent grant (`consent.resolve(...GRANTED)`)
  and `launch_trip_repairs` in `_watch_consent_then_repair` (the race fix's structural
  property — source-inspected only today), and a non-mutating body-check mode for
  `git_pull_dev.sh` (e.g. `CHECK_BODY_ONLY=1`) with a test covering
  placeholder-fails / complete-body-passes, so the evidence guard is exercisable
  without opening a real PR.
- **Device QA** (kept as a pre-event item at the 2026-07-12 replan): the three acts on a
  physical iPhone via Xcode install — does not touch the in-review binary
  (`SABRE_MODE=mock`; one run = 2 outbound calls, 10/day quota), sheet & gestures, edge
  cases (Phase 17 validation.md § 7).
- Review the hardcoded dev Cloud Run URL in `APIConfig.swift`.
