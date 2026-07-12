# Roadmap

High-level implementation order for the hackathon-ready foundation. Hackathon day is **July 18, 2026** — every phase before the last must land ahead of it. Each phase is narrowly scoped and becomes a feature branch (`vb/feature/<feature-name>`); mark a phase `[x] COMPLETE` in its heading when done.

Phases appear in **execution order** — the first heading not marked `[x] COMPLETE` is what `sdd-feature-spec` picks up next. Phase numbers are historical IDs, not ordering. Completed phases have moved to [changelog.md](changelog.md) — this file tracks only open and upcoming work; deferred phases (14 → 13 → 15, plus the approval-gated v1.0.1 bridge removal, Phase 20) wait in [BACKLOG.md](BACKLOG.md) behind everything here. `IOS_PLAN.md` is the umbrella plan.

**State as of 2026-07-12 (night):** Phases 18 and 19 are merged, deployed, and QA'd (details in [changelog.md](changelog.md)) — the timezone/pin gates on Phase 17 are cleared, so Phase 17's remainder (empty-start onboarding → device QA → **first** App Store submission; the Phase 16 build was never submitted) is the only open work. Runbook: `IOS_DEPLOY.md`.

## Phase 21: Voice booking page — the pre-disruption beat on screen [x] COMPLETE (implementation; manual QA pending)

**Spec:** [specs/2026-07-12-voice-booking-page/](2026-07-12-voice-booking-page/) · landed 2026-07-12 on `vb/feature/voice-booking-page`. `GET /v1/booking/` shows the booking conversation's candidates (new additive `pending_options` block on the status poll) and the full five-item reservation, styled to `about/ui_ideas/ui_mockup_2026_07_09.png` — the visual frame Phases 22–23 lift. Automated suite green (331 passed); the manual walkthrough in the spec's `validation.md` (curl rehearsal on the `/query` seam with the page open) is still owed.

## Phase 17: Talk to My Trip — full voice demo experience

**Shipped 2026-07-11** (`vb/dev`, deployed): guided multi-turn voice booking on the Concierge, the `DEMO_ACCESS_CODE` gate across backend/pages/iOS, the additive `detail` payload + native recommendation sheet, hidden demo gestures, stage-readability polish, and the App-Review privacy hardening. 290 backend tests green; simulator-verified end to end.

**Still open:** device QA (2026-07-11) exposed the Act 1 blocker (Phase 18) and the follow-up validation pass added two hotfixes (Phase 19) — both landed and QA'd 2026-07-12 (see [changelog.md](changelog.md)), so this remainder is unblocked. In order:

- **iOS empty-start onboarding** (promoted from TODO 2026-07-11): don't auto-resolve
  `latest_trip_id` on cold start — show the "tap the orb" empty state; remember this
  device's own trip in UserDefaults once booked; keep the after-reply re-resolve and
  the long-press selector.
- **Device QA:** the three acts on a physical iPhone (`SABRE_MODE=mock`; one run =
  2 outbound calls, 10/day quota), sheet & gestures, edge cases (validation.md § 7).
- **Submit:** archive → upload → submit per `IOS_DEPLOY.md` (access code in the review
  notes; the deployed privacy policy already matches).
- Standing pre-event items: verify Cloud Run `min/max-instances=1`; flip
  `SABRE_MODE=real` when keys arrive **Monday 7/14** — and convert real Sabre
  offset-bearing times to Pacific before speaking/storing (Phase 19 residual:
  `_spoken_clock`/option parsing truncate to `HH:MM`, so a real
  `06:15:00-05:00` would be mis-declared Pacific — see the Phase 19
  validation-report risks); review the hardcoded dev Cloud Run URL in
  `APIConfig.swift`.
