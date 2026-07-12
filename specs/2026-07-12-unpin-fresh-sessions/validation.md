# Validation — Unpin fresh sessions (Phase 18)

## Automated

Run the full suite in the dev container (host has no pytest):

```
docker compose exec -T backend python -m pytest tests/ -q
```

All tests green (290+ as of Phase 17), hermetic — no GCP credentials, no
`OPENAI_API_KEY`. Specific assertions that must exist and pass:

1. **Regression (the Phase 18 headline):** `answer_query` on a fresh session
   with a **non-empty** trips table (mocked at the `bq_helper` boundary, LLM
   stubbed at the `Runner` boundary) leaves the session unpinned, builds the
   agent with `_NO_TRIP_LINE` (no "TRIP CONTEXT" block), and a
   `search_flights` tool invocation reaches the mock Sabre client and returns
   a speakable options string.
2. **No fallback query:** `ensure_trip_context` with no `trip_id` and no
   cached pin performs **no** trips-table SELECT and returns
   `(None, <speakable "no booked trip" line>)`.
3. **Acts 2/3 intact:** explicit `trip_id` still pins (Phase 12 seam);
   `book_flight_impl` still replaces the pin with the newly booked trip.
4. **Date line:** with a frozen clock, `build_agent` instructions contain
   "Today is …, YYYY-MM-DD" rendered in America/Los_Angeles time.
5. `fix_trip_impl` on a cold unpinned session returns a speakable string (no
   raise, no traceback).

## Manual

Local first (`docker compose up`, `http://localhost:1019`), then the deployed
service after merge (`/v1/web_call/?code=…` — no outbound calls, no quota).
The dev BigQuery trips table is non-empty (seed/rehearsal trips), which is
exactly the condition that used to break Act 1 — do not empty it.

1. **Act 1 happy path (the bug):** fresh `/v1/web_call/` session → "I'd like
   to travel from Minneapolis to Dallas, leaving on Monday."
   - Agent confirms and calls `search_flights` — it must read back 2–3
     numbered options (mock Sabre returns three for any route/date), not
     stall with filler or offer "trains".
   - "Monday" resolves to the correct future `YYYY-MM-DD` given today's
     Pacific date (verify the searched date in logs or the readback).
   - Pick an option by number → booking confirmed in one sentence → agree to
     the rest → cards materialize on `/v1/itinerary/` one by one.
2. **Act 2/3 unaffected:** trigger the disrupt flow (`POST /v1/demo/disrupt`
   or `/v1/disruption/break_flight` + explicit-`trip_id` session) → agent
   pins the broken trip, `fix_trip` launches repairs, itinerary flips
   broken → repairing → fixed.
3. **Accepted-loss behaviour:** fresh session, "tell me about my trip" → the
   agent says there's no booked trip on file (plainly, no invented trip, no
   error), and offers to book one.
4. **Edge cases:**
   - "Leaving tomorrow" and "leaving on Friday" both resolve to future dates.
   - Book a flight, then ask about the trip in the same session — the new
     pin answers (post-`book_flight` pin still works).
   - Session that books, then says "my flight was cancelled" → `fix_trip`
     works against the just-booked trip.

## Tone check

New/changed speakable strings (unpinned "no booked trip" reply, date-line
wording is agent-internal but its downstream replies are not): one or two
short conversational sentences, no markdown, no ids, no tool names — the
standing voice rules in `BASE_INSTRUCTIONS`.

## Definition of done

- All automated assertions above green in the container, suite hermetic.
- Manual walkthrough 1–3 passes on the deployed service via
  `/v1/web_call/?code=…` with a non-empty trips table.
- Acts 2/3 rehearsal unchanged from Phase 17 behaviour.
- Phase 18 marked `[x] COMPLETE` in `specs/roadmap.md`, unblocking Phase 17's
  remaining device QA → first App Store submission.
