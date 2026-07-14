# Roadmap

High-level implementation order for the hackathon-ready foundation. Hackathon day is **July 18, 2026** — every phase before the last must land ahead of it. Each phase is narrowly scoped and becomes a feature branch (`vb/feature/<feature-name>`); mark a phase `[x] COMPLETE` in its heading when done.

Phases appear in **execution order** — the first heading not marked `[x] COMPLETE` is what `sdd-feature-spec` picks up next. Phase numbers are historical IDs, not ordering. Completed phases have moved to [changelog.md](changelog.md) — this file tracks only open and upcoming work; deferred phases (14 → 13 → 15, plus the approval-gated v1.0.1 bridge removal, Phase 20) wait in [BACKLOG.md](BACKLOG.md) behind everything here. `IOS_PLAN.md` is the umbrella plan.

**State as of 2026-07-12 (late-night replan):** Phase 21 (voice booking page) is merged, deployed, and QA'd, and **Phase 17 is complete** — the full three-act build was submitted to App Review 2026-07-11; per `mission.md` #4 approval is a bonus, the web surfaces are the demo path, and no new binary is uploaded until the in-review one is approved (BACKLOG Phase 20). Details in [changelog.md](changelog.md). **Restoration note:** this replan re-restores the 2026-07-12 evening replan's roadmap (PR #34, commit `4ac1bb0`), which the booking-page branch's merge resolution (PRs #35/#36) had silently reverted — Phase 17's completion and Phases 22–24 below were lost from this file for a few hours; if a roadmap statement conflicts with the changelog, trust the changelog. Open work, in order: the cascade dashboard (Phases 22–23) on the visual frame Phase 21 established, then pre-event readiness (Phase 24 — **time-gated, not order-gated**: pull the Sabre-keys work ahead the moment the keys arrive, expected Monday 2026-07-13).

**Update 2026-07-13 (Phase 25 archived):** the Sabre CERT exploration ran the same day the keys landed and is archived to [changelog.md](changelog.md) with caveats — headline finding: **real shopping, mock booking** (Flight Search API v1 entitled with real priced itineraries; `createBooking` entitlement-blocked at `PassengerDetailsRQ`; full matrix and demo recommendations in `specs/2026-07-13-sabre-cert-exploration/sabre-cert-notes.md`). Its independent validation returned **FAIL**; the fixes shipped as **Phase 26** and the close-out re-validation passed 2026-07-14 (both archived to [changelog.md](changelog.md)). The deal-manufacturing upsell engine stays backlogged in [BACKLOG.md](BACKLOG.md) (revisit after Phase 23, minimum slice `extend_stay`); its API-entitlement gate is now answered **go**.

**Replan 2026-07-13 (evening; updated 2026-07-14):** the Phase 25 findings reshaped the tail of the roadmap. Order: **27 (real search in the demo path) → 22 → 23 → 24** (Phase 26, validation fixes, is complete and archived). All four validation-triage decisions were answered at the replan interview (targeted sweep additions, executed dummy-PNR probe for modifyBooking, empty-set PNR hygiene, dated re-run artifact); the frozen-client bug fixes (dead `POS` field, empty-BFM response shapes, BM errors-as-200 masking) are deliberately **conditional Phase 24 work** — they only matter if Sabre grants BFM content / booking entitlement, realistically via the event-day ask. One Phase 26 item remains open and rides with Phase 24: the **different-day `pytest -m cert` dated artifact** appended to `sabre-cert-notes.md` (D4 — event-day morning at the latest).

## [x] COMPLETE (implementation; manual QA pending) Phase 27: Real Sabre search in the demo path

The Phase 25 headline made this the cheapest real-Sabre win: judges hear **real airlines, real fares, real routes** while booking stays mock (entitlement wall). Wire `search_flights_impl` (`backend/api/concierge.py`) to `GET /v1/shop/flights` (InstaFlights) when `SABRE_MODE=real`, keeping the per-call mock fallback and the speakable-options contract (top 2–3, rounded prices, no airline codes spoken). Scope notes: additive InstaFlights response models (new — `shapes.py` doesn't model this API; the Phase 25 freeze is over but BFM shapes stay untouched); always send `onlineitinerariesonly=N` (Y = CERT 500); validate city pairs against the supported-markets list where it helps the agent fail speakably; and **handle InstaFlights' offset-less airport-local times** — `2026-08-13T07:20:00` means 7:20 AM *at the departure airport*, so speaking/storing it as Pacific repeats the Phase 19 bug class; convert via airport → timezone mapping or speak it as "local departure time" explicitly. The Cloud Run flip for search is then `SABRE_MODE=real` + the two bridge env vars (`SABRE_BASE_URL`, `SABRE_CLIENT_SECRET` — recipe in the Phase 25 notes).

## Phase 22: Cascade dashboard, part 1 — repair surfaces on the Phase 21 frame

Re-scoped at the late-night 2026-07-12 replan: Phase 21 already built the mockup's *frame* (app header + status pill, left rail with traveler-context card / trip timeline / recent trips, prominent current-flight card, reservation cards, right-column "AI Recommended" candidates panel) on `GET /v1/booking/`, so this phase adds the mockup's **repair surfaces** to that frame instead of building a new shell from scratch: the recovery banner + timer against the 60-second target, the broken → repairing → fixed status treatments, the disruption score, and the "downstream impact" panel (fed by the existing `detail` payload) — all still driven entirely by the existing `GET /v1/itinerary/status/{trip_id}` 1.5 s poll, no voice wiring in this phase. Whether the dashboard grows inside the booking page or clones its frame into a new page is a spec-interview decision. Carry one hardening from the Phase 21 validation report: expire or clear the `_LATEST_SEARCH` slot so stale candidates can't linger indefinitely after an abandoned booking conversation.

> **TODO (verbatim, 2026-07-12 triage):** There are three HTML pages I serve through the FastAPI. They are `web_call`, `itinery`, and `demo`.  How feasible is to build this ui in new page?  ./about/ui_ideas/ui_mockup_2026_07_09.png?

## Phase 23: Cascade dashboard, part 2 — live voice surfaces

The dashboard's live layers on top of Phase 22: the conversation feed (traveler/Cascade turns), the voice orb with connection/latency state (the `web_call` VB wiring — server-minted token, `useAIAgent → /v1/web_call/query` delegation), and the Sabre live-search log panel. Ends with the full mockup experience on one page.

## Phase 24: Pre-event readiness

The residuals that survived Phase 17's completion, re-scoped at the 2026-07-13 evening replan now that Phase 25 sized up the credentials: **the full `SABRE_MODE=real` flip is no longer a Phase 24 deliverable** — the search half moved to Phase 27, and the booking half is an entitlement wall, not a config flip. Everything here must land before July 18.

- **Event-day ask to Sabre staff** (first thing on the day plan): can hackathon teams get
  a PCC with BFM air content and `PassengerDetailsRQ` (createBooking) authorization? Both
  walls name the account manager as the unlock (Phase 25 notes, endpoint matrix).
- **Conditional — only if that entitlement lands on-site:** the pre-scoped real-booking
  punch list from `specs/2026-07-13-sabre-cert-exploration/sabre-cert-notes.md` deltas
  #1–#3: fix the dead `POS` field in `shapes.py` (name-shadowing bug), make the empty-BFM
  response lists optional, detect Booking Management's errors-as-HTTP-200 payloads and
  surface a speakable failure instead of a silent mock swap — plus **convert BFM's
  offset-bearing times to Pacific before speaking/storing** (the Phase 19 residual;
  `06:15:00-05:00` must not be mis-declared Pacific). Phase 27 handles the InstaFlights
  offset-less variant separately.
- **Event-day-morning Sabre smoke** (per replan decision D4): `probes/auth_check.py`,
  then `pytest -m cert`, then `probes/sweep.py` — detects overnight credential resets and
  entitlement drift before the first rehearsal; append the dated output to the Phase 25
  notes (this may also be what closes Phase 26's different-day repeatability item).
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
