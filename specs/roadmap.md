# Roadmap

High-level implementation order for the hackathon-ready foundation. Hackathon day is **July 18, 2026** — every phase before the last must land ahead of it. Each phase is narrowly scoped and becomes a feature branch (`vb/feature/<feature-name>`); mark a phase `[x] COMPLETE` in its heading when done.

Completed phases have moved to [changelog.md](changelog.md) — this file tracks only open and upcoming work.

**Updated 2026-07-11 (changelog):** Phase 16 (the "Talk to My Trip" App Store MVP) is implementation- and QA-complete and has moved to the changelog — but the build is **not yet submitted to the App Store**; that submission is the immediate open item and Phase 17 ships as an app update behind it. The phases already queued in [BACKLOG.md](BACKLOG.md) (14 → 13 → 15) wait behind Phase 17. `IOS_PLAN.md` at the repo root is the umbrella plan.

## Phase 17: Talk to My Trip — full voice demo experience

*(Prerequisite: the Phase 16 build is QA-complete but still needs archive → upload → **submit for review** in App Store Connect — see [changelog.md](changelog.md) Phase 16.)*

Turn the submitted app into the full three-act demo from `IOS_PLAN.md`, shipped as an app update (updates re-review much faster than a first submission). The voice bridge, headless page, and magic-utterance booking shipped in Phase 16; this phase is the upgrade:

- **Backend (Track A remainder):** guided multi-turn voice booking on the Concierge (`search_flights` → speak 2–3 options → `book_flight` by voice → `complete_trip` with ~1.5s card spacing), replacing the magic utterance; demo-orchestration reuse (`/v1/demo/disrupt` as the Act 2/3 trigger with the real outbound call); the additive `detail` payload on `/status/{trip_id}` for the recommendation sheet (first thing to cut).
- **iOS (Track B remainder):** recommendation bottom sheet, hidden demo gestures (triple-tap disrupt, long-press trip selector), orb/timeline polish for stage readability.
- Vocal Bridge + Sabre remain the hard requirements: Sabre stays in `SABRE_MODE=mock` until real keys arrive **Monday 7/14**, then flip on Cloud Run (per-call mock fallback already protects the demo).
- Verify per `IOS_PLAN.md` § Verification: Act 1 booked by voice on device, Act 2 cascade < 60s while conversing, Act 3 the phone rings — minding the 10 outbound-calls/day Vocal Bridge quota.
