# Roadmap

High-level implementation order for the hackathon-ready foundation. Hackathon day is **July 18, 2026** — every phase before the last must land ahead of it. Each phase is narrowly scoped and becomes a feature branch (`vb/feature/<feature-name>`); mark a phase `[x] COMPLETE` in its heading when done.

Phases appear in **execution order** — the first heading not marked `[x] COMPLETE` is what `sdd-feature-spec` picks up next. Phase numbers are historical IDs, not ordering. Completed phases have moved to [changelog.md](changelog.md) — this file tracks only open and upcoming work; deferred phases (14 → 13 → 15, plus the approval-gated v1.0.1 bridge removal, Phase 20) wait in [BACKLOG.md](BACKLOG.md) behind everything here. `IOS_PLAN.md` is the umbrella plan.

**State as of 2026-07-12 (evening replan):** Phase 17 is **complete** — the full three-act build (empty-start onboarding included) was **submitted to App Review 2026-07-11**. Review latency is uncontrollable, so per `mission.md` #4 App Store approval is a bonus, not an event-day requirement: **the web surfaces are the demo path regardless**, and no new binary is uploaded until the in-review one is approved (post-approval fixes = v1.0.1+, see BACKLOG Phase 20). Open work, in order: the demo web UI (Phases 21–23, promoted at today's TODO triage), then pre-event readiness (Phase 24 — time-gated rather than order-gated: the Sabre-keys work may be pulled ahead when the keys arrive, expected 2026-07-13).

## Phase 21: Voice booking page — show the flight before it breaks

New FastAPI-served page (alongside `web_call`, `itinerary`, `demo`) for the **pre-disruption** beat of the demo: booking happens by voice only, but the screen must show the current flight and its details — and, during the guided booking conversation, what the booking *could be* (the candidate options) — before any event that would trigger a cascade repair. Reuses the existing seams: the Concierge guided booking flow (`search_flights` → `book_flight` → `complete_trip`), the `?trip_id=`/`window.vbSetTrip` pinning contract, and the `GET /v1/itinerary/status/{trip_id}` poll for the booked result. No new backend logic expected — this is a new page over existing endpoints.

> **TODO (added at the 2026-07-12 triage interview, verbatim):** "…booking your flight and showing what that booking could be, which is typically going to be done with the voice only, But the current flight and flight details need to be shown first before any sort of event would happen that would trigger a cascade repair."

## Phase 22: Cascade dashboard, part 1 — mockup skin over the status poll

New page shell styled to `about/ui_ideas/ui_mockup_2026_07_09.png`: traveler-context card, trip timeline, repair-status surfaces, recovery banner/timer, and the "AI Recommended / why Cascade chose this / downstream impact" panel fed by the existing `detail` payload — all driven entirely by the existing `GET /v1/itinerary/status/{trip_id}` 1.5 s poll and the recent-trips selector, same self-contained static-page conventions as the itinerary page. No voice wiring in this phase.

> **TODO:** There are three HTML pages I serve through the FastAPI. They are `web_call`, `itinery`, and `demo`.  How feasible is to build this ui in new page?  ./about/ui_ideas/ui_mockup_2026_07_09.png?

## Phase 23: Cascade dashboard, part 2 — live voice surfaces

The dashboard's live layers on top of Phase 22: the conversation feed (traveler/Cascade turns), the voice orb with connection/latency state (the `web_call` VB wiring — server-minted token, `useAIAgent → /v1/web_call/query` delegation), and the Sabre live-search log panel. Ends with the full mockup experience on one page.

> **TODO:** There are three HTML pages I serve through the FastAPI. They are `web_call`, `itinery`, and `demo`.  How feasible is to build this ui in new page?  ./about/ui_ideas/ui_mockup_2026_07_09.png?

## Phase 24: Pre-event readiness

The residuals that survived Phase 17's completion (2026-07-12 replan). **Time-gated, not order-gated** — the Sabre-keys work should be pulled ahead of Phases 21–23 the moment the keys arrive (expected **2026-07-13**); everything must land before July 18.

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

## Phase 17: Talk to My Trip — full voice demo experience [x] COMPLETE

**Shipped 2026-07-11** (`vb/dev`, deployed): guided multi-turn voice booking on the Concierge, the `DEMO_ACCESS_CODE` gate across backend/pages/iOS, the additive `detail` payload + native recommendation sheet, hidden demo gestures, stage-readability polish, the App-Review privacy hardening, and the iOS empty-start onboarding. 290 backend tests green; device QA'd through the Phase 18/19 hotfixes (see [changelog.md](changelog.md)).

**Submitted to App Review 2026-07-11** per `IOS_DEPLOY.md` (access code in the review notes; deployed privacy policy matches). Cloud Run `min/max-instances=1` verified. Approval is out of our hands — see `mission.md` #4 (web-first; the app is a bonus) and BACKLOG Phase 20 for the post-approval v1.0.1. Remaining residuals moved to Phase 24.
