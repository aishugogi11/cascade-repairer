# Roadmap

High-level implementation order for the hackathon-ready foundation. Hackathon day is **July 18, 2026** — every phase before the last must land ahead of it. Each phase is narrowly scoped and becomes a feature branch (`vb/feature/<feature-name>`); mark a phase `[x] COMPLETE` in its heading when done.

Phases appear in **execution order** — the first heading not marked `[x] COMPLETE` is what `sdd-feature-spec` picks up next. Phase numbers are historical IDs, not ordering. Completed phases have moved to [changelog.md](changelog.md) — this file tracks only open and upcoming work; deferred phases (14 → 13 → 15, plus the approval-gated v1.0.1 bridge removal, Phase 20) wait in [BACKLOG.md](BACKLOG.md) behind everything here. `IOS_PLAN.md` is the umbrella plan.

**State as of 2026-07-12 (late-night replan):** Phase 21 (voice booking page) is merged, deployed, and QA'd, and **Phase 17 is complete** — the full three-act build was submitted to App Review 2026-07-11; per `mission.md` #4 approval is a bonus, the web surfaces are the demo path, and no new binary is uploaded until the in-review one is approved (BACKLOG Phase 20). Details in [changelog.md](changelog.md). **Restoration note:** this replan re-restores the 2026-07-12 evening replan's roadmap (PR #34, commit `4ac1bb0`), which the booking-page branch's merge resolution (PRs #35/#36) had silently reverted — Phase 17's completion and Phases 22–24 below were lost from this file for a few hours; if a roadmap statement conflicts with the changelog, trust the changelog. Open work, in order: the cascade dashboard (Phases 22–23) on the visual frame Phase 21 established, then pre-event readiness (Phase 24 — **time-gated, not order-gated**: pull the Sabre-keys work ahead the moment the keys arrive, expected Monday 2026-07-13).

**Update 2026-07-13 (Phase 25 archived):** the Sabre CERT exploration ran the same day the keys landed and is archived to [changelog.md](changelog.md) with caveats — headline finding: **real shopping, mock booking** (Flight Search API v1 entitled with real priced itineraries; `createBooking` entitlement-blocked at `PassengerDetailsRQ`; full matrix and demo recommendations in `specs/2026-07-13-sabre-cert-exploration/sabre-cert-notes.md`). Its independent validation returned **FAIL**; the fixes shipped as **Phase 26** and the close-out re-validation passed 2026-07-14 (both archived to [changelog.md](changelog.md)). The deal-manufacturing upsell engine stays backlogged in [BACKLOG.md](BACKLOG.md) (revisit after Phase 23, minimum slice `extend_stay`); its API-entitlement gate is now answered **go**.

**Replan 2026-07-13 (evening; updated 2026-07-14):** the Phase 25 findings reshaped the tail of the roadmap. Order: **27 (real search in the demo path) → 22 → 23 → 24** (Phase 26, validation fixes, is complete and archived). All four validation-triage decisions were answered at the replan interview (targeted sweep additions, executed dummy-PNR probe for modifyBooking, empty-set PNR hygiene, dated re-run artifact); the frozen-client bug fixes (dead `POS` field, empty-BFM response shapes, BM errors-as-200 masking) are deliberately **conditional Phase 24 work** — they only matter if Sabre grants BFM content / booking entitlement, realistically via the event-day ask. One Phase 26 item remains open and rides with Phase 24: the **different-day `pytest -m cert` dated artifact** appended to `sabre-cert-notes.md` (D4 — event-day morning at the latest).

**Replan 2026-07-14 (evening — real data everywhere reachable):** Phase 27 shipped, deployed, and spoke real CERT fares on Cloud Run the same day, but its independent validation returned **FAIL** with two code defects (unmapped *connection* airports pass the parser; the mock's Pacific-fiction clocks are re-read as airport-local, so mock west-to-east arrivals precede departures) — those are now **Phase 28**. Two strategic facts landed the same evening (tech-stack § entitlement addendum): InstaFlights content is **per-pair** (113 of 731 supported pairs had +2-day content, so near-term real repair shopping is possible today), and **the Sabre entitlement-ask route is closed** (decision 2026-07-14) — Sabre's newer flightShop/flightShopLite are entitled-but-empty on this PCC and the MCP Server pilot can't bypass entitlements, so no unlock is coming. The cascade's credibility therefore rides on **Phase 29**: the flight-repair leg re-shops real InstaFlights data. New order: **29 → 22 → 23 → 24** (Phases 27 and 28 shipped and deployed 2026-07-14 and are archived to [changelog.md](changelog.md) — Phase 28's deployed real-mode spot checks passed the same evening; its one open QA item, the interactive mock-mode walkthrough, is hermetically covered). Phase 24's "event-day ask" bullet and its conditional BFM/booking punch list are deleted with the decision (the punch-list items remain documented in the Phase 25 notes if circumstances ever change).

## Phase 29: Real repair data — the cascade re-shops InstaFlights

The demo's credibility pivot (decision 2026-07-14: no mock data in the demo path; no Sabre unlock coming): when the flight breaks, the repair must speak **real replacement flights**. Swap `repair_tools.py`'s flight-repair search from `sabre_client.flight_search` (BFM — content-empty, always mock-swaps) to the Phase 27 `instaflights_search` dispatcher op: re-shop the broken flight's route and date, pick a real alternative (different flight number/time than the cancelled one where possible), and carry it + the alternatives into the booking row's `raw_response` so the booking page's `detail` panel (why chosen / price delta) shows real data. PNR writes stay mock (entitlement wall — permanent posture). Scope riders: **demo scripting** — the demo trip books a pair from the verified near-term menu (2026-07-14 sweep: SFO→MIA, SEA→BOS, JFK→LAX, …) departing event day +2, documented in the demo runbook; **morning-smoke extension** — probe the scripted pair at the scripted date (per-pair cache windows can shift on refresh; +30d green does not imply the demo date is green). Hotel/ground/dining/experience repairs stay category mocks (unchanged scope — the flight is the beat judges hear).

## Phase 22: Cascade dashboard, part 1 — repair surfaces on the Phase 21 frame

Re-scoped at the late-night 2026-07-12 replan: Phase 21 already built the mockup's *frame* (app header + status pill, left rail with traveler-context card / trip timeline / recent trips, prominent current-flight card, reservation cards, right-column "AI Recommended" candidates panel) on `GET /v1/booking/`, so this phase adds the mockup's **repair surfaces** to that frame instead of building a new shell from scratch: the recovery banner + timer against the 60-second target, the broken → repairing → fixed status treatments, the disruption score, and the "downstream impact" panel (fed by the existing `detail` payload) — all still driven entirely by the existing `GET /v1/itinerary/status/{trip_id}` 1.5 s poll, no voice wiring in this phase. Whether the dashboard grows inside the booking page or clones its frame into a new page is a spec-interview decision. Carry one hardening from the Phase 21 validation report: expire or clear the `_LATEST_SEARCH` slot so stale candidates can't linger indefinitely after an abandoned booking conversation.

> **TODO (verbatim, 2026-07-12 triage):** There are three HTML pages I serve through the FastAPI. They are `web_call`, `itinery`, and `demo`.  How feasible is to build this ui in new page?  ./about/ui_ideas/ui_mockup_2026_07_09.png?

## Phase 23: Cascade dashboard, part 2 — live voice surfaces

The dashboard's live layers on top of Phase 22: the conversation feed (traveler/Cascade turns), the voice orb with connection/latency state (the `web_call` VB wiring — server-minted token, `useAIAgent → /v1/web_call/query` delegation), and the Sabre live-search log panel. Ends with the full mockup experience on one page.

## Phase 24: Pre-event readiness

The residuals that survived Phase 17's completion, re-scoped at the 2026-07-13 evening replan and again 2026-07-14 (evening): **the full `SABRE_MODE=real` flip shipped with Phase 27** (search real on Cloud Run since 2026-07-14), and **the event-day entitlement ask is deleted** — decision 2026-07-14: no extra permissions are coming, so the former "conditional punch list" (dead `POS` field, empty-BFM shapes, BM errors-as-200, BFM offset-bearing time conversion) is retired from this roadmap; it stays documented in the Phase 25 notes' deltas if circumstances ever change. Everything here must land before July 18.

- **Event-day-morning Sabre smoke** (per replan decision D4; extended by the 2026-07-14
  evening replan): `probes/auth_check.py`, then `pytest -m cert`, then `probes/sweep.py`,
  then **probe InstaFlights for the scripted demo pair at the scripted date** (Phase 29 —
  per-pair cache windows shift on refresh; a green +30d sweep does not prove the demo
  date). Detects overnight credential resets and entitlement drift before the first
  rehearsal; append the dated output to the Phase 25 notes (this may also be what closes
  Phase 26's different-day repeatability item).
- **Sweep drift detection** (2026-07-14 replan, from the Phase 26 close-out report): the
  sweep's exit code trips only on `NETWORK-ERR` — `SERVER-ERR` or a changed classification
  (e.g. InstaFlights flipping to 403 after a credential reset) still exits 0, so the
  morning smoke could look green while entitlements regressed. Teach `sweep.py` an
  expected-classification check against the notes matrix (exit nonzero on deviation,
  with the availability/exchange 403↔404 gateway flap treated as one class) so the D4
  smoke is a real drift alarm, not just a network check.
- **Async test hygiene** (2026-07-14 replan, same report): the bare suite emits six
  unawaited-coroutine `RuntimeWarning`s across the concierge/repair tests (pre-Phase-26
  debt). Chase them to their fixtures/mocks and fix or properly close the coroutines —
  they can mask async cleanup defects in the exact code that keeps the agent talking
  during repairs.
- **Device QA** (kept as a pre-event item at the 2026-07-12 replan): the three acts on a
  physical iPhone via Xcode install — does not touch the in-review binary
  (`SABRE_MODE=mock`; one run = 2 outbound calls, 10/day quota), sheet & gestures, edge
  cases (Phase 17 validation.md § 7).
- Review the hardcoded dev Cloud Run URL in `APIConfig.swift`.
