# Roadmap

High-level implementation order for the hackathon-ready foundation. Hackathon day is **July 18, 2026** — every phase before the last must land ahead of it. Each phase is narrowly scoped and becomes a feature branch (`vb/feature/<feature-name>`); mark a phase `[x] COMPLETE` in its heading when done.

Completed phases have moved to [changelog.md](changelog.md) — this file tracks only open and upcoming work.

**Replanned 2026-07-06** around the team's locked demo concept, the **Cascade Repairer** (see `mission.md`): a booked trip takes a live flight cancellation and the agent repairs all five legs in parallel *while still talking*. That decision added the concurrency spike (Phase 5), repair-capable Sabre tools (Phase 6), and the live itinerary UI (Phase 10), and demoted the real-time voice-to-voice port to a stretch goal. **Updated 2026-07-06 post-Phase-3:** promoted the Vocal Bridge live-call test page from `TODO.md` to Phase 4, front of the line per Josh; later phases renumbered (old 4–11 → 5–12). **Updated 2026-07-07 post-Phase-5:** the concurrency question is answered — no rewire needed; the pattern (`backend/api/concurrency_core.py`) is standing infrastructure for Phases 7–9. Two Phase 5 loose ends folded into Phase 6: surfacing failed status writes, and proving real BigQuery rows flip with fresh `updated_at`. **Updated 2026-07-08:** Phase 7 now also carries the L4 "Voice as a Tool" outbound-call pattern, because it is not otherwise covered by an active phase; the stretch L4 item remains only the full real-time voice-to-voice architecture port. **TODO triage 2026-07-08 (post-Phase-6):** the Discord 2026-07-07 "agent reaches out first" demo opening is noted in Phase 12 (mechanics live in Phase 7); the LandingAI email-scanning ideas were dropped per Josh — the thread stays in README as context.

## Phase 8: Vocal Bridge web client integration

- Connect the Vocal Bridge managed web client (WebRTC) to the deployed backend agent.
- A live voice conversation works against the Cloud Run instance end-to-end — this becomes the test surface for every later phase.

## Phase 9: Concierge hybrid architecture (demo architecture)

- Implement the hybrid Concierge pattern (L5): fast foreground agent for turn-taking, fillers, and bridge lines; background OpenAI Agents SDK agents for deep reasoning and Sabre tools — running the Phase 5 concurrency pattern (`backend/api/concurrency_core.py`: background tasks + session event log + per-turn session snapshot in the instructions), not sequential calls.
- **Acceptance:** the foreground agent holds a voice conversation while multiple background repair tools execute in parallel (Phase 5's test, now over voice).
- This is the demo architecture — polish interruption handling, endpointing, and tool-call latency masking.
- Cleanup folded in from Phase 6 (replan 2026-07-08): when the repair tools wire into the Concierge, make the cascade unit (`_repair_one`) the **single writer** of item status transitions — today both the tool and the cascade unit stamp `fixed` (idempotent but two writers own one transition).

## Phase 10: Live itinerary UI

- A single FastAPI-served page (static HTML/JS from the existing backend — no separate frontend deploy, no CORS) rendering the unified trip itinerary: all five item types with statuses.
- Updates live as repairs complete (polling or SSE against a trip-status endpoint) — the screen flips **broken → repairing → fixed** while the agent talks. This is the demo's second surface (per Aishwarya's proposal + team agreement).
- Can start any time after Phase 6 (needs only the trip tables + status transitions); sequenced here so the Concierge phase feeds it real repair events.

## Phase 11: Evaluation harness (L5 port)

- Port the course evaluation patterns: TTFB/e2e latency, WER against ground-truth transcripts, MOS-style quality estimates.
- Runnable on demand against the shipped architectures; results persisted to `eval_runs` with git SHA and scenario.

## Phase 12: Dress rehearsal — the cascade, end to end

- Script the actual demo: a fully booked trip (flight, hotel, ride, dinner, tour) → disruption injector cancels the flight live → the agent keeps talking while all five repairs run in parallel → the itinerary UI flips broken → fixed → the agent reads back the repaired plan. Target: all five fixed in under 60 seconds.
- **The demo opens with the agent reaching out first** (team decision, Discord 2026-07-07): the disruption fires and the traveler *receives a call* — "your flight was just cancelled; I'm already rebooking, give me thirty seconds" — via the Phase 7 outbound-call tool, flipping the story from "user asks, agent responds" to "agent notices, agent acts."
  > **TODO (Discord 2026-07-07, Pallavi/Anusha):** "Flight cancels, the user gets a call from the agent… that flips the demo from user asks, agent responds to agent notices, agent acts. Much stronger story." Scope: a 10–20 second opening beat.
- Run it through the deployed stack (Vocal Bridge client → Cloud Run → mock Sabre → BigQuery → itinerary UI) with eval metrics captured.
- Fix whatever breaks; the foundation is done when this run is clean.

## Stretch (post-rehearsal, only if time allows)

- **Real-time voice-to-voice architecture (L4 port)** — demoted 2026-07-06: the demo runs on the Concierge hybrid, so the L4 port is off the critical path. Notebook mastery still counts toward the mission's skill goal.
- Mocked extras from the team thread (Google Maps distances, Uber, Costco Travel bundles) — only after the core repair loop is clean end to end.

---

**Event day (July 18):** flip the Sabre config flag to real credentials (mocks remain the runtime fallback), assemble the Cascade Repairer demo with the team on top of the completed foundation ([changelog.md](changelog.md)) and Phases 7–12, and polish the 60-second moment.
