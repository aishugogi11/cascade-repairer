# Phase 12: Dress rehearsal — requirements

## Scope

This phase turns the pieces built in Phases 4–10 into the actual demo: a single
operator-facing **demo page** where the whole Cascade Repairer story runs on two
button presses, each of which places a **real outbound phone call** — the voice
is the point of the hackathon, and it is the one thing the existing
`/v1/itinerary/` page cannot do.

### In scope

1. **Demo orchestrator router** (`backend/api/demo.py`, mounted at `/v1/demo`) —
   the "one button, one beat" surface. Two POST endpoints:

   | Endpoint | Demo beat | What it composes |
   |----------|-----------|------------------|
   | `POST /v1/demo/book` | **Beat 1 — the trip gets booked over a phone call.** Traveler receives a call; while the agent talks through the trip, the booking lands and the page fills in. | Place an outbound call (existing `vb_cli.place_call` seam, purpose = booking-confirmation narrative with the trip details) **and** seed the booked trip (existing `seed_trip` logic). Returns `{trip_id, call_id, call_status}`. |
   | `POST /v1/demo/disrupt` | **Beat 2 — the flight cancels and the agent reaches out first.** "Your flight was just cancelled; I'm already rebooking, give me thirty seconds." Repairs run while the call is live; the page flips broken → repairing → fixed. | Break the flight (existing `break_flight` repository flow), place the second outbound call (purpose = cancellation + already-rebooking narrative), **and** launch all-item repairs in the background (existing `launch_trip_repairs`, no wait). Returns `{trip_id, call_id, repair_session_id, launched}`. |

   Both endpoints take `trip_id` where applicable (`/book` creates it;
   `/disrupt` requires it). Failure of any leg returns an error status — never a
   silent partial success (the Phase 6 rule).

2. **Demo page** (`GET /v1/demo/` serving
   `backend/api/assets/demo/page.html`) — a **new page**, kept separate from
   `/v1/itinerary/` so the proven QA'd page stays untouched. It reuses the
   itinerary page's working patterns (self-contained vanilla HTML/CSS/JS, no
   build step, read per request, poll `GET /v1/itinerary/status/{trip_id}`
   every 1.5 s, status cards, repair feed, recovery timer) and adds the
   operator controls:
   - **"Trigger call"** button → `POST /v1/demo/book`; disabled once a trip is
     live; page locks onto the returned `trip_id` and starts polling.
   - **"Flight canceled"** button → `POST /v1/demo/disrupt`; enabled only when
     a booked trip is on screen; starts the 60-second recovery timer.
   - Call state indicator per beat (dialing / in progress / done) sourced from
     the `/v1/demo/*` responses and, where useful,
     `GET /v1/outbound_call/status`.

3. **Demo runbook** (`specs/2026-07-10-dress-rehearsal/runbook.md`) — the
   written script of the 60-second moment: preconditions (env vars, Cloud Run
   URL, callee phone answered), the two operator actions, what the audience
   sees/hears at each beat, expected timings, and recovery moves if a beat
   misfires (e.g. call not answered, repair stuck).

4. **The rehearsal itself** — run the full flow through the deployed stack
   (button → Cloud Run → Vocal Bridge outbound call → mock Sabre → BigQuery →
   demo page) and fix what breaks. The phase is done when a deployed run is
   clean and the broken → all-fixed recovery lands **under 60 seconds** (hard
   gate — see validation.md).

### Out of scope

- The three itinerary-UI edge cases parked from Phase 10 (backend-restart
  mid-poll recovery, cancelled-item muted rendering, projector readability) —
  not selected for this branch; they stay on the roadmap.
- Full eval-harness capture (`eval_runs` rows) for the rehearsal — the 60 s
  recovery time is measured by the page timer and recorded in the runbook, not
  persisted. Eval scoring of phone calls is Phase 13 territory.
- Persisting outbound calls to our own DB (`outbound_calls` table) — Phase 13,
  deliberately after this rehearsal.
- Any change to the existing `/v1/itinerary/` page, the repair tools, or the
  Sabre client layer beyond what composition requires.
- Real Sabre credentials — the rehearsal runs `SABRE_MODE=mock` (the event-day
  flip is a config change, not this phase).

## Decisions

- **New demo orchestrator endpoints, injector untouched** (user decision).
  `POST /v1/demo/disrupt` composes `break_flight` + outbound call + repairs;
  `/v1/disruption/break_flight` keeps working standalone for teammates
  curling from a phone. Composition happens at the router level by calling the
  same repository/`vb_cli`/`launch_trip_repairs` seams the existing endpoints
  use — no logic is duplicated.
- **A new page instead of extending `/v1/itinerary/`** (user decision): keeps
  the QA-verified page clean; the demo page copies its polling/rendering
  patterns rather than importing them (both pages are deliberately
  self-contained single files — same reasoning as Phase 10).
- **The phone call is the narrative; the backend does the booking.** The Vocal
  Bridge caller agent is hosted and cannot call our tools mid-call, so
  `/demo/book` performs the booking itself (seed pattern) while the injected
  call purpose has the agent *narrate* it — trip details are passed into the
  purpose so the voice and the screen tell the same story. Same for the repair
  beat: repairs launch server-side; the call narrates them. This is accepted
  stagecraft — the concurrency underneath (repairs during a live call) is real.
- **Repairs launch without waiting** (`launch_trip_repairs`, no
  `asyncio.gather`): `/demo/disrupt` returns immediately so the page timer and
  the phone call run while repairs land — the Phase 5 pattern.
- **Strict 60 seconds on the deployed stack** (user decision): validation runs
  only against Cloud Run + real BigQuery, and broken → all-fixed in under 60 s
  is a pass/fail criterion, not a soft target.
- **Call ordering inside each beat**: fire the outbound call first (it takes
  seconds to connect; `vb_cli.place_call` returns as soon as the call is
  queued), then do the data writes — so the phone rings while the screen
  changes, not after.

## Context

- **Tone**: the demo page is projector-facing at a hackathon — big, legible,
  minimal chrome; copy in the traveler's voice matching the itinerary page's
  repair feed ("Your flight was cancelled — already rebooking"). Call purposes
  are agent-voiced, calm and concrete: what happened, what's being done,
  a time promise ("give me thirty seconds").
- **Existing patterns to follow**:
  - Router style: pydantic request models, 503 when required env vars are
    missing (`_missing_env` in `outbound_call.py`), secrets scrubbed from
    every payload (`_scrub`), blocking work via `asyncio.to_thread`
    (tech-stack standing rule).
  - Page style: `backend/api/assets/itinerary/page.html` — vanilla, no
    external requests, read per request (uvicorn --reload only watches `.py`).
  - Register the router in `backend/main.py` like the other eight.
- **Stack constraints**: no new dependencies; tests stay hermetic (mock
  `vb_cli` and the repositories at their seams — no GCP creds, no
  `VOCAL_BRIDGE_API_KEY`); everything already deploys via the `vb/dev` push
  trigger.
- **Environment prerequisites** (already set on Cloud Run from Phase 7):
  `VOCAL_BRIDGE_API_KEY`, `VOCAL_BRIDGE_CALLER_AGENT_ID`,
  `VOCAL_BRIDGE_CALLEE_PHONE`. The rehearsal callee is the operator's own
  phone.
- **Open question carried into the rehearsal** (answer empirically, note in
  runbook): whether the second call should be placed *before* or *after*
  `break_flight` for the best stage feel — the spec starts with call-first
  (see Decisions) and the rehearsal confirms.
