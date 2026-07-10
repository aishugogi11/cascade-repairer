# Phase 12: Dress rehearsal — plan

Task groups are independently implementable in order; each leaves the branch
green (`pytest` passes hermetically).

## 1. Demo orchestrator router

1.1. Create `backend/api/demo.py` with router `demo` and module docstring
     explaining the beat → endpoint mapping (follow `outbound_call.py` style).

1.2. Refactor the seed-trip logic in `backend/api/sabre_tools.py` so the
     orchestrator can call it: extract the body of `seed_trip` into a plain
     function `create_seed_trip(user_id, title) -> dict` that raises
     `HTTPException` on write failure; the existing endpoint becomes a thin
     wrapper. No behaviour change (existing tests must still pass).

1.3. Same for the disruption flow: extract `break_trip_flight(trip_id) -> dict`
     from `backend/api/disruption.py`'s handler; endpoint wraps it.

1.4. Implement `POST /v1/demo/book`:
     - 503 via `_missing_env`-style check for `VOCAL_BRIDGE_API_KEY`,
       `VOCAL_BRIDGE_CALLER_AGENT_ID`, `VOCAL_BRIDGE_CALLEE_PHONE`.
     - Compose the booking-narrative call purpose (trip title, MSP→SFO
       July 17–19, the five legs) — agent-voiced copy per requirements.
     - `await asyncio.to_thread(vb_cli.place_call, purpose, name)` first;
       502 with scrubbed error on failure.
     - Then `await asyncio.to_thread(create_seed_trip, ...)`.
     - Return `{trip_id, call_id, call_status}`.

1.5. Implement `POST /v1/demo/disrupt` (request: `trip_id`):
     - Same env guard.
     - Place the cancellation/rebooking call (purpose: flight cancelled,
       already rebooking, "give me thirty seconds").
     - `await asyncio.to_thread(break_trip_flight, trip_id)` — its 404/500
       semantics pass through.
     - List the trip's items (`asyncio.to_thread`), then
       `launch_trip_repairs(session_id, items)` **without** awaiting the tasks.
     - Return `{trip_id, call_id, repair_session_id, launched}`.

1.6. Register the router in `backend/main.py` at prefix `/v1/demo`,
     tag `demo`.

## 2. Demo page

2.1. Create `backend/api/assets/demo/page.html`, seeded from
     `backend/api/assets/itinerary/page.html`: keep the status cards, repair
     feed, recovery timer, and 1.5 s polling of
     `GET /v1/itinerary/status/{trip_id}`; drop the trip selector (the page
     drives its own trip).

2.2. Add the operator controls:
     - **"Trigger call"** → `POST /v1/demo/book`; on success lock onto
       `trip_id`, start polling, disable the button, show call state.
     - **"Flight canceled"** → `POST /v1/demo/disrupt` with the live
       `trip_id`; enabled only when the trip renders as booked; on success
       start the 60 s recovery timer and show call state.
     - Error states render on-page (not just console) — a failed beat must be
       visible to the operator mid-demo.

2.3. Serve it: `GET /v1/demo/` handler in `demo.py` reading the file per
     request (`HTMLResponse`, same pattern and reasoning as `itinerary_ui.py`).

2.4. Projector pass: type scale and contrast readable from distance; traveler-
     voiced copy per requirements Context.

## 3. Runbook

3.1. Write `specs/2026-07-10-dress-rehearsal/runbook.md`: preconditions
     (Cloud Run URL, env vars present via `/v1/hello/gcp_check` + a 503-free
     `POST /v1/demo/book` dry check, operator phone ready, page loaded on the
     projector), the two-beat script with expected audience sight/sound at
     each step and expected timings, and recovery moves (call unanswered,
     repair stuck, page stalls).

3.2. Include the measured timings table to be filled during rehearsal runs
     (per-run: dial→answer, disrupt→all-fixed, total beat time).

## 4. Tests

4.1. `backend/tests/test_demo.py`, hermetic (mock `vb_cli.place_call`,
     repositories / extracted functions at their seams):
     - `/book` and `/disrupt` return 503 when any Vocal Bridge env var is
       missing.
     - `/book` happy path: call placed with a purpose containing the trip
       narrative, trip seeded, response shape `{trip_id, call_id, call_status}`.
     - `/book` when `place_call` fails → 502, no trip seeded, error scrubbed.
     - `/disrupt` happy path: call placed, flight broken, repairs launched
       (not awaited), response carries `repair_session_id` and `launched`.
     - `/disrupt` on a trip with no flight item → 404 passes through.
     - `GET /v1/demo/` returns the page HTML.
     - Existing `seed_trip` / `break_flight` endpoint tests still pass after
       the 1.2/1.3 extractions.

## 5. Deployed rehearsal (the phase's point)

5.1. Land groups 1–4 on `vb/dev` via PR; confirm the Cloud Build deploy.

5.2. Run the two-beat demo end to end against Cloud Run with the operator's
     phone as callee, following the runbook. Record timings.

5.3. Fix what breaks; repeat until one run is clean and broken → all-fixed is
     under 60 seconds. Update the runbook with measured timings and the
     empirical answer to the call-ordering question.

5.4. Mark Phase 12 `[x] COMPLETE` in `specs/roadmap.md` (note: the three
     Phase 10 UI edge cases were scoped out of this branch and stay listed).
