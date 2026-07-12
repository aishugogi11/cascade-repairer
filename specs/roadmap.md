# Roadmap

High-level implementation order for the hackathon-ready foundation. Hackathon day is **July 18, 2026** — every phase before the last must land ahead of it. Each phase is narrowly scoped and becomes a feature branch (`vb/feature/<feature-name>`); mark a phase `[x] COMPLETE` in its heading when done.

Completed phases have moved to [changelog.md](changelog.md) — this file tracks only open and upcoming work.

**Updated 2026-07-11 (replan #2):** the Phase 17 build landed on `vb/dev` (PR #26) and is deployed with the access gate armed — but the phase is **not complete**: QA on device revealed the core Act 1 story is unreachable (see below), so Phase 17 stays open with a re-scoped remainder. The Phase 16 build was never submitted; **the Phase 17 build is the first App Store submission**, per `IOS_DEPLOY.md`. The phases queued in [BACKLOG.md](BACKLOG.md) (14 → 13 → 15) wait behind Phase 17. `IOS_PLAN.md` is the umbrella plan.

## Phase 17: Talk to My Trip — full voice demo experience

**Shipped 2026-07-11 (in `vb/dev`, deployed):** guided multi-turn voice booking on the
Concierge (`search_flights` → 2–3 spoken options → `book_flight` → `complete_trip`),
the `DEMO_ACCESS_CODE` gate across backend/pages/iOS, the additive `detail` payload +
native recommendation sheet, hidden demo gestures replacing all visible demo buttons,
stage-readability polish, and the App-Review privacy hardening (first-use AI-consent
sheet, withdrawal path, retention-complete privacy policy). 290 backend tests green;
simulator-verified end to end.

**Why it's still open (Josh, QA on device 2026-07-11):** new sessions pin the
backend's *latest* trip and the guided script then refuses to search/book, so a fresh
user gets a pre-loaded trip and can never pick a flight by voice — Act 1 is
undemoable. Remaining scope (replan decisions 2026-07-11):

- **Concierge new-trip booking (the blocker):** when the traveler explicitly asks to
  plan/book a **new** trip while one is pinned, confirm once, then run the guided
  search; `book_flight` already replaces the pin. Supersedes the requirements.md
  "never search when a trip is already pinned" decision — route through
  `sdd-feature-spec` as a Phase 17 addendum, rehearse via `/v1/web_call/?code=…`.
- **iOS empty-start onboarding** (promoted from TODO 2026-07-11): don't auto-resolve
  `latest_trip_id` on cold start — show the "tap the orb" empty state; remember this
  device's own trip in UserDefaults once booked; keep the after-reply re-resolve and
  the long-press selector.
- **Device QA:** the three acts on a physical iPhone (`SABRE_MODE=mock`; one run =
  2 outbound calls, 10/day quota), sheet & gestures, edge cases (validation.md § 7).
- **Submit:** archive → upload → submit per `IOS_DEPLOY.md` (access code in the review
  notes; the deployed privacy policy already matches).
- Standing pre-event items: verify Cloud Run `min/max-instances=1`; flip
  `SABRE_MODE=real` when keys arrive **Monday 7/14**; review the hardcoded dev
  Cloud Run URL in `APIConfig.swift`.
