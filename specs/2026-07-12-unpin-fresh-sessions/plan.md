# Plan — Unpin fresh sessions (Phase 18)

All work is in `backend/api/concierge.py` and `backend/tests/test_concierge.py`.
Groups 1 and 2 are independent; Group 3 tests both.

## 1. Drop the latest-trip auto-pin

1.1. In `ensure_trip_context` (`backend/api/concierge.py:132`), delete the
     `else:` branch that runs `SELECT * FROM trips ORDER BY created_at DESC
     LIMIT 1`. With no cached pin and no `trip_id`, return
     `(None, "I don't see a booked trip for you yet.")` — the same speakable
     line the empty-table case uses today, so `fix_trip_impl` keeps answering
     gracefully and `answer_query` (which ignores the error) proceeds
     unpinned.

1.2. Update the function's docstring (the "the most recently created trip
     wins" paragraph) and the `_SESSION_TRIPS` comment block to the new
     contract: pin only on explicit `trip_id` or post-`book_flight`.

1.3. Remove anything the deleted query orphans (e.g. the `rows_to_models`
     import if this was its last use in the module).

1.4. Soften the stale instruction seam if needed: `BASE_INSTRUCTIONS` says
     "When there is no booked trip … follow the guided flow" — verify the
     wording still reads correctly now that unpinned is the *normal* fresh
     state, but do not rewrite copy beyond what the two fixes force
     (scope decision).

## 2. Inject today's date into the agent context

2.1. Add a small helper, e.g. `_today_line()`, that renders
     "Today is {weekday}, {YYYY-MM-DD} (US Pacific time). Resolve relative
     dates like 'Monday' or 'tomorrow' from this date, always into the
     future." using `datetime.now(ZoneInfo("America/Los_Angeles"))`
     (stdlib `zoneinfo`).

2.2. Interpolate it into the agent instructions in `build_agent`
     (`backend/api/concierge.py:620`), alongside `BASE_INSTRUCTIONS` +
     `trip_line` + `session_snapshot(...)`. Keep it a helper (not inlined) so
     tests can monkeypatch/freeze it.

## 3. Tests

3.1. Update existing `test_concierge.py` tests that encode the old auto-pin
     contract (the "where do I fly into?" cold-pin tests around
     `test_concierge.py:167` and any others that rely on the latest-trip
     SELECT): cold sessions now stay unpinned; explicit-`trip_id` tests
     (`:209`) are unchanged.

3.2. **The regression test (the roadmap's coverage-gap item).** Mock the LLM,
     real wiring: with the `bq` fixture seeded so the trips table is
     **non-empty**, drive `answer_query("fresh-session", "book me a flight
     from Minneapolis to Dallas on 2026-07-13")` with a `_FakeRunner` that
     acts like a booking-intent model — it invokes the agent's
     `search_flights` tool and records the agent it was given. Assert:
     - the session is **not** pinned (`"fresh-session" not in _SESSION_TRIPS`);
     - the agent's instructions contain `_NO_TRIP_LINE` and not the
       authoritative "TRIP CONTEXT" block;
     - the `search_flights` tool call goes through `search_flights_impl` to
       the mock Sabre client and returns a speakable options string
       (options land in `_SESSION_FLIGHT_OPTIONS`).
     This fails on the old code (instructions would carry the pinned trip and
     forbid booking) and guards against the fallback being reintroduced.

3.3. Pin-persistence checks: explicit `trip_id` still pins (Acts 2/3), and
     `book_flight_impl` still re-pins the new trip (existing tests cover the
     latter — confirm they pass unmodified).

3.4. Date-line tests: freeze `_today_line`'s clock (monkeypatch) and assert
     the built agent's instructions carry the expected Pacific date string;
     one direct unit test of `_today_line` formatting.

## 4. Validate & wrap up

4.1. Full suite green in the dev container:
     `docker compose exec -T backend python -m pytest tests/ -q`.

4.2. Manual rehearsal per `validation.md` (local `/v1/web_call/`, then the
     deployed service after merge).

4.3. Mark Phase 18 `[x] COMPLETE` in `specs/roadmap.md` (per the roadmap's
     convention) once validation passes.
