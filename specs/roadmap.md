# Roadmap

High-level implementation order for the hackathon-ready foundation. Hackathon day is **July 18, 2026** — every phase before the last must land ahead of it. Each phase is narrowly scoped and becomes a feature branch (`vb/feature/<feature-name>`); mark a phase `[x] COMPLETE` in its heading when done.

Completed phases have moved to [changelog.md](changelog.md) — this file tracks only open and upcoming work.

**Replanned 2026-07-06** around the team's locked demo concept, the **Cascade Repairer** (see `mission.md`): a booked trip takes a live flight cancellation and the agent repairs all five legs in parallel *while still talking*. That decision added the concurrency spike (Phase 5), repair-capable Sabre tools (Phase 6), and the live itinerary UI (Phase 10), and demoted the real-time voice-to-voice port to a stretch goal. **Updated 2026-07-06 post-Phase-3:** promoted the Vocal Bridge live-call test page from `TODO.md` to Phase 4, front of the line per Josh; later phases renumbered (old 4–11 → 5–12). **Updated 2026-07-07 post-Phase-5:** the concurrency question is answered — no rewire needed; the pattern (`backend/api/concurrency_core.py`) is standing infrastructure for Phases 7–9. Two Phase 5 loose ends folded into Phase 6: surfacing failed status writes, and proving real BigQuery rows flip with fresh `updated_at`. **Updated 2026-07-08:** Phase 7 now also carries the L4 "Voice as a Tool" outbound-call pattern, because it is not otherwise covered by an active phase; the stretch L4 item remains only the full real-time voice-to-voice architecture port. **TODO triage 2026-07-08 (post-Phase-6):** the Discord 2026-07-07 "agent reaches out first" demo opening is noted in Phase 12 (mechanics live in Phase 7); the LandingAI email-scanning ideas were dropped per Josh — the thread stays in README as context. **Updated 2026-07-09 post-Phase-10:** the live itinerary UI shipped and is QA-verified on Cloud Run; its residual visual edge cases (backend-restart recovery, cancelled-item rendering, projector readability) are carried into the Phase 12 rehearsal checklist below. **TODO triage 2026-07-09 (post-Phase-10):** the Phase 7 outbound-call persistence idea is promoted to Phase 13, deliberately after the rehearsal.

## Phase 11: Evaluation harness (L5 port) [x] COMPLETE (implementation; manual QA pending)

- Port the course evaluation patterns: TTFB/e2e latency, WER against ground-truth transcripts, MOS-style quality estimates.
- Runnable on demand against the shipped architectures; results persisted to `eval_runs` with git SHA and scenario.

## Phase 12: Dress rehearsal — the cascade, end to end

- Script the actual demo: a fully booked trip (flight, hotel, ride, dinner, tour) → disruption injector cancels the flight live → the agent keeps talking while all five repairs run in parallel → the itinerary UI flips broken → fixed → the agent reads back the repaired plan. Target: all five fixed in under 60 seconds.
- **The demo opens with the agent reaching out first** (team decision, Discord 2026-07-07): the disruption fires and the traveler *receives a call* — "your flight was just cancelled; I'm already rebooking, give me thirty seconds" — via the Phase 7 outbound-call tool, flipping the story from "user asks, agent responds" to "agent notices, agent acts."
  > **TODO (Discord 2026-07-07, Pallavi/Anusha):** "Flight cancels, the user gets a call from the agent… that flips the demo from user asks, agent responds to agent notices, agent acts. Much stronger story." Scope: a 10–20 second opening beat.
- Run it through the deployed stack (Vocal Bridge client → Cloud Run → mock Sabre → BigQuery → itinerary UI) with eval metrics captured.
- Close out the itinerary-UI edge cases parked from Phase 10 (per Josh's 2026-07-09 validation triage): backend-restart mid-poll recovery, a cancelled item rendering muted, projector-distance readability.
- Fix whatever breaks; the foundation is done when this run is clean.

## Phase 13: Outbound call persistence

Post-rehearsal per Josh (TODO triage 2026-07-09): the demo works without a local call record; this lands only once the Phase 12 run is clean. One small phase: `outbound_calls` table + repository (same config-driven pattern as the six existing tables), a row written at dial time, and backfill of the Vocal Bridge session id / recording URI when `/status` / `/recording` resolve them. Consider echoing turn transcripts into `turns` so the eval harness (Phase 11) can score phone calls like web sessions.

> **TODO (from Phase 7 manual QA, 2026-07-08):** Persist outbound calls in our own DB.
> Today the L4 outbound-call flow keeps no local record: `POST /call` returns a
> Vocal Bridge `call_id`, the session log lives only in Vocal Bridge (`vb logs`),
> and the two ids aren't linked anywhere on our side (learner confusion proved it:
> call_id was naturally pasted into `/status?session_id=`). Idea: an
> `outbound_calls` table (call_id, purpose, name, placed_at, vb_session_id,
> call_status, recording_gcs_uri) written at dial time and back-filled with the
> session id/recording when `/status` / `/recording` resolve them — schema yaml +
> config.yaml metadata entry + repository, same pattern as the six existing
> tables. Natural home: fold into Phase 9 (the Concierge places calls and the
> Phase 12 opening beat needs the call on record) or a small standalone phase.
> Consider also echoing turn transcripts into `turns` so eval (Phase 11) can
> score phone calls like web sessions.

## Stretch (post-rehearsal, only if time allows)

- **Real-time voice-to-voice architecture (L4 port)** — demoted 2026-07-06: the demo runs on the Concierge hybrid, so the L4 port is off the critical path. Notebook mastery still counts toward the mission's skill goal.
- Mocked extras from the team thread (Google Maps distances, Uber, Costco Travel bundles) — only after the core repair loop is clean end to end.

---

**Event day (July 18):** flip the Sabre config flag to real credentials (mocks remain the runtime fallback), assemble the Cascade Repairer demo with the team on top of the completed foundation ([changelog.md](changelog.md)) and Phases 7–12, and polish the 60-second moment.
