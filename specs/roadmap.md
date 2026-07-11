# Roadmap

High-level implementation order for the hackathon-ready foundation. Hackathon day is **July 18, 2026** — every phase before the last must land ahead of it. Each phase is narrowly scoped and becomes a feature branch (`vb/feature/<feature-name>`); mark a phase `[x] COMPLETE` in its heading when done.

Completed phases have moved to [changelog.md](changelog.md) — this file tracks only open and upcoming work.

**Updated 2026-07-11 (TODO triage):** the **"Talk to My Trip" iOS app** is promoted as Phases 16–17 and jumps the queue — App Store review takes a couple of days, so getting an approvable build submitted is the immediate goal (today). The phases already queued in [BACKLOG.md](BACKLOG.md) (14 → 13 → 15) wait behind these two. `IOS_PLAN.md` at the repo root is the umbrella plan for both phases.

## Phase 16: Talk to My Trip — App Store submission MVP

**Goal: an approvable app submitted to App Store review ASAP — today, Fri 2026-07-11.** First-time review takes days and the event is 7/18, so this phase is the bare minimum to stand the app up and get it *approved*, deliberately deferring the voice experience to Phase 17 (app updates re-review much faster than a first submission).

Scope (re-interviewed 2026-07-11 during the feature spec — **voice is in the MVP**: "it's really as simple as starting a conversation with the agent… you plan your trip [by voice]. After the trip is saved, you can break it and have it re-planned"):

- New `ios/TalkToMyTrip/` SwiftUI app (iOS 17 minimum, iPhone-only, no third-party dependencies), per `IOS_PLAN.md` Track B: voice orb + live trip timeline (polling `GET /v1/itinerary/status/{trip_id}`), voice via the hidden-WKWebView bridge to a new headless `GET /v1/mobile_voice/` page (Track A2, pulled forward), and an in-app break/heal demo trigger (existing `break_flight` / `repair_trip` endpoints — no phone calls).
- **Magic-utterance voice booking** (IOS_PLAN cut-line 2, pulled forward): one Concierge tool wrapping `create_seed_trip` — speak where/when, the agent books the whole 5-item trip; full guided booking stays Phase 17.
- App Review readiness: `/v1/legal/privacy` + `/v1/legal/support` pages served from the backend, App Store Connect record + metadata + screenshots, privacy nutrition labels + `PrivacyInfo.xcprivacy` (mic audio covered), 2026 age-rating questionnaire (AI-assistant questions), export compliance, reviewer script in the notes.
- Archive with Xcode 26 (iOS 26 SDK mandatory since April 2026), upload, **submit for review** — "Waiting for Review" is this phase's definition of shipped.

Spec: [`2026-07-11-talk-to-my-trip-appstore-mvp/`](2026-07-11-talk-to-my-trip-appstore-mvp/) on branch `vb/feature/mobile-plan`.

> **TODO:** I'm Josh Janzen, The lead developer of this entire project, and also an iOS developer with Zen Software. The current UI: https://vocal-bridge-be-dev-24105435206.us-west1.run.app/v1/itinerary Is a solid start. In In addition to the web demo, which also needs to be polished and end up like ./about/ui_ideas/ui_mockup_2026_07_09.png, I want to have a companion iOS application. This application is going to be called "Talk to My Trip". Use this ./IOS_PLAN.md. For this hackathon, remember requirements are:
> - Must use vocal bridge and Saber (mock for now until API keys come out on Monday).
> *(Triage note 2026-07-11: promoted with an explicit goal override from Josh — "I need to get the iOS app sent to the App store ASAP (as takes a couple days to get approved. THAT IS THE GOAL, GET APPROVED). So bare min to get the App stood up and approved… that is the goal today." The web-demo-polish part of this TODO is backlogged in BACKLOG.md, not part of this phase.)*

## Phase 17: Talk to My Trip — full voice demo experience

Turn the submitted app into the full three-act demo from `IOS_PLAN.md`, shipped as an app update (updates re-review much faster than a first submission). The voice bridge, headless page, and magic-utterance booking shipped in Phase 16; this phase is the upgrade:

- **Backend (Track A remainder):** guided multi-turn voice booking on the Concierge (`search_flights` → speak 2–3 options → `book_flight` by voice → `complete_trip` with ~1.5s card spacing), replacing the magic utterance; demo-orchestration reuse (`/v1/demo/disrupt` as the Act 2/3 trigger with the real outbound call); the additive `detail` payload on `/status/{trip_id}` for the recommendation sheet (first thing to cut).
- **iOS (Track B remainder):** recommendation bottom sheet, hidden demo gestures (triple-tap disrupt, long-press trip selector), orb/timeline polish for stage readability.
- Vocal Bridge + Sabre remain the hard requirements: Sabre stays in `SABRE_MODE=mock` until real keys arrive **Monday 7/14**, then flip on Cloud Run (per-call mock fallback already protects the demo).
- Verify per `IOS_PLAN.md` § Verification: Act 1 booked by voice on device, Act 2 cascade < 60s while conversing, Act 3 the phone rings — minding the 10 outbound-calls/day Vocal Bridge quota.
