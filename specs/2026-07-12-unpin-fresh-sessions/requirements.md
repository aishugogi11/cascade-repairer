# Requirements — Unpin fresh sessions (Phase 18)

Make Act 1 (voice-booking a brand-new trip) reachable. Today every fresh session
auto-pins the backend's most recently created trip, and the instructions then
forbid `search_flights`/`book_flight` — so guided booking is unreachable whenever
the trips table is non-empty, which it always is. Fully broken in
`SABRE_MODE=mock`; not a Sabre issue.

## Scope

Exactly the three roadmap items (confirmed with Josh 2026-07-12). Nothing rides
along: iOS empty-start onboarding, device QA, and App Store submission stay in
Phase 17's remainder; agent-instruction copy changes only where the two fixes
force them.

### 1. Drop the latest-trip auto-pin

`ensure_trip_context` (`backend/api/concierge.py:132`) currently falls back to
`SELECT * FROM trips ORDER BY created_at DESC LIMIT 1` when a session has no
cached pin and no explicit `trip_id`. Remove that fallback entirely.

After the change, `ensure_trip_context` pins a trip in exactly two cases:

| Path | Trigger | Behaviour (unchanged) |
|------|---------|----------------------|
| Explicit `trip_id` | Disrupt/outbound flow (Phase 12 seam), `complete_trip` build-out | Pins that trip |
| After `book_flight` | `book_flight_impl` pops the session then re-pins via explicit `trip_id` | Pins the new trip |

With no cached pin and no `trip_id`, the function returns no context plus the
existing speakable line "I don't see a booked trip for you yet." — so
`fix_trip` from a cold unpinned session still answers gracefully, while
`answer_query` (which discards the speakable error) builds the agent with
`_NO_TRIP_LINE`, enabling the guided-booking flow.

**Accepted loss** (decision 2026-07-12, supersedes the 2026-07-11 replan's
"confirm once, then search while pinned" approach): cold-session "ask about my
existing trip" no longer works without context. The demo reaches existing trips
through the disrupt flow (explicit `trip_id`) anyway.

### 2. Inject today's date into the agent context

Instructions ask the model to turn "leaving on Monday" into `YYYY-MM-DD`, but
nothing supplies today's date, so relative dates cannot resolve. Add a date
line to the agent's instructions at `build_agent` time, e.g.:

> "Today is Saturday, 2026-07-12 (US Pacific time). Resolve relative dates
> like 'Monday' or 'tomorrow' from this date, always into the future."

- Timezone: **America/Los_Angeles** (Josh's decision — the hackathon is in
  Mountain View, CA), via stdlib `zoneinfo`. No new dependency.
- Computed per `build_agent` call (the agent is already rebuilt every turn), so
  a long-lived process never serves a stale date.

### 3. End-to-end regression test

The coverage gap that let this ship: existing tests call
`search_flights_impl`/`book_flight_impl` directly with mocked repos and never
exercise `answer_query` → `ensure_trip_context`. Required: a test that drives
`answer_query` with a **non-empty** trips table and proves a booking request
still reaches `search_flights`.

## Out of scope

- Any Sabre client change (mock or real) — the tools work in isolation.
- iOS app changes (`latest_trip_id` cold-start resolution is the Phase 17
  "empty-start onboarding" item).
- Changes to `/v1/sabre_tools/latest_trip_id` or the itinerary page's trip
  selector — server-side latest-trip *reads* are fine; only the session *pin*
  goes.
- Intent-gating the auto-pin (rejected in triage: brittle, still shadows fresh
  sessions).

## Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Fix shape | Drop the auto-pin outright | Explicit-`trip_id` paths already cover Acts 2/3; the fallback exists only for cold-session trip Q&A, which the demo never uses |
| Date injection | Interpolated line in instructions, not a tool | Zero extra round-trips in a latency-sensitive voice turn |
| Date timezone | America/Los_Angeles default (Josh, interview 2026-07-12) | Demo audience and event are Pacific |
| Test approach | Mock the LLM, real wiring (Josh, interview 2026-07-12) | Stub at the `Runner`/model boundary with mocked repos seeded non-empty; assert `search_flights` is reachable through the real `answer_query` → `ensure_trip_context` → `build_agent` chain. No live API calls |

## Context

- Tests must stay hermetic (no GCP creds, no `OPENAI_API_KEY`) — mock at the
  `bq_helper` boundary and the `Runner` boundary, exactly the existing
  `test_concierge.py` patterns (`_FakeRunner`, `bq` fixture).
- Tool failure paths return **speakable strings** (standing rule) — the
  unpinned `fix_trip` path must keep doing so.
- Some existing `test_concierge.py` tests assert the old auto-pin behaviour;
  they must be updated to the new contract, not deleted wholesale.
- Rehearse on the deployed service via `/v1/web_call/?code=…` — no outbound
  calls, no quota spend.
- This phase gates the rest of Phase 17 (device QA → first App Store
  submission); keep it narrow and land it fast.
