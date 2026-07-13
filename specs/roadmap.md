# Roadmap

High-level implementation order for the hackathon-ready foundation. Hackathon day is **July 18, 2026** — every phase before the last must land ahead of it. Each phase is narrowly scoped and becomes a feature branch (`vb/feature/<feature-name>`); mark a phase `[x] COMPLETE` in its heading when done.

Phases appear in **execution order** — the first heading not marked `[x] COMPLETE` is what `sdd-feature-spec` picks up next. Phase numbers are historical IDs, not ordering. Completed phases have moved to [changelog.md](changelog.md) — this file tracks only open and upcoming work; deferred phases (14 → 13 → 15, plus the approval-gated v1.0.1 bridge removal, Phase 20) wait in [BACKLOG.md](BACKLOG.md) behind everything here. `IOS_PLAN.md` is the umbrella plan.

**State as of 2026-07-12 (late-night replan):** Phase 21 (voice booking page) is merged, deployed, and QA'd, and **Phase 17 is complete** — the full three-act build was submitted to App Review 2026-07-11; per `mission.md` #4 approval is a bonus, the web surfaces are the demo path, and no new binary is uploaded until the in-review one is approved (BACKLOG Phase 20). Details in [changelog.md](changelog.md). **Restoration note:** this replan re-restores the 2026-07-12 evening replan's roadmap (PR #34, commit `4ac1bb0`), which the booking-page branch's merge resolution (PRs #35/#36) had silently reverted — Phase 17's completion and Phases 22–24 below were lost from this file for a few hours; if a roadmap statement conflicts with the changelog, trust the changelog. Open work, in order: the cascade dashboard (Phases 22–23) on the visual frame Phase 21 established, then pre-event readiness (Phase 24 — **time-gated, not order-gated**: pull the Sabre-keys work ahead the moment the keys arrive, expected Monday 2026-07-13).

## Phase 22: Cascade dashboard, part 1 — repair surfaces on the Phase 21 frame

Re-scoped at the late-night 2026-07-12 replan: Phase 21 already built the mockup's *frame* (app header + status pill, left rail with traveler-context card / trip timeline / recent trips, prominent current-flight card, reservation cards, right-column "AI Recommended" candidates panel) on `GET /v1/booking/`, so this phase adds the mockup's **repair surfaces** to that frame instead of building a new shell from scratch: the recovery banner + timer against the 60-second target, the broken → repairing → fixed status treatments, the disruption score, and the "downstream impact" panel (fed by the existing `detail` payload) — all still driven entirely by the existing `GET /v1/itinerary/status/{trip_id}` 1.5 s poll, no voice wiring in this phase. Whether the dashboard grows inside the booking page or clones its frame into a new page is a spec-interview decision. Carry one hardening from the Phase 21 validation report: expire or clear the `_LATEST_SEARCH` slot so stale candidates can't linger indefinitely after an abandoned booking conversation.

> **TODO (verbatim, 2026-07-12 triage):** There are three HTML pages I serve through the FastAPI. They are `web_call`, `itinery`, and `demo`.  How feasible is to build this ui in new page?  ./about/ui_ideas/ui_mockup_2026_07_09.png?

## Phase 23: Cascade dashboard, part 2 — live voice surfaces

The dashboard's live layers on top of Phase 22: the conversation feed (traveler/Cascade turns), the voice orb with connection/latency state (the `web_call` VB wiring — server-minted token, `useAIAgent → /v1/web_call/query` delegation), and the Sabre live-search log panel. Ends with the full mockup experience on one page.

## Phase 24: Pre-event readiness

The residuals that survived Phase 17's completion (2026-07-12 replan). **Time-gated, not order-gated** — the Sabre-keys work should be pulled ahead of Phases 22–23 the moment the keys arrive (expected **Monday 2026-07-13**); everything must land before July 18.

- **Flip `SABRE_MODE=real`** when the keys arrive (Josh handles the keys) — and, with the
  flip, **convert real Sabre offset-bearing times to Pacific before speaking/storing**
  (Phase 19 residual, status unconfirmed at the 2026-07-12 replan: `_spoken_clock`/option
  parsing truncate to `HH:MM`, so a real `06:15:00-05:00` would be mis-declared Pacific —
  see the Phase 19 validation-report risks).
- **Device QA** (kept as a pre-event item at the 2026-07-12 replan): the three acts on a
  physical iPhone via Xcode install — does not touch the in-review binary
  (`SABRE_MODE=mock`; one run = 2 outbound calls, 10/day quota), sheet & gestures, edge
  cases (Phase 17 validation.md § 7).
- Review the hardcoded dev Cloud Run URL in `APIConfig.swift`.
