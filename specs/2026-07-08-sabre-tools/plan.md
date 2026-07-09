# Plan — Sabre Tools (Phase 6)

Task groups in build order. Group 1 front-loads the docs pull so shape
questions surface early; groups 2–6 are independently implementable once the
shapes exist; group 7 closes with the real-BigQuery proof.

## 1. Sabre API research → documented shapes

1. Pull current Sabre API documentation for both paths: flight search/booking
   *and* cancel/rebook (Air Shopping + Booking Management), hotel booking
   *and* date change. Use live docs (developer.sabre.com), not training data.
2. Record exact endpoints, auth model, request shapes, and response payloads
   in `specs/2026-07-08-sabre-tools/sabre-api-notes.md` — one section per
   operation, with a trimmed real example payload each.
3. Create `backend/api/sabre/shapes.py`: pydantic request/response models
   matching the documented payloads 1:1 for the operations in the notes file
   (flight search, flight book, flight cancel, flight rebook, hotel book,
   hotel date change).

## 2. Sabre client layer (mock, real stub, dispatcher)

1. `backend/api/sabre/mock_client.py` — returns `shapes.py` model instances
   with realistic canned data; deterministic given the same request (tests
   assert on it); tiny artificial latency parameterizable to zero for tests.
2. `backend/api/sabre/real_client.py` — same interface, constructs the
   documented HTTP requests; **not called this phase** (no sandbox
   credentials); raises a clear error if invoked without configuration.
3. `backend/api/sabre/client.py` — the dispatcher: reads `SABRE_MODE` env var
   (`mock` | `real`, default `mock`) **at call time**; in `real` mode wraps
   each call so any exception falls back to the mock for that call and logs a
   `logger.warning` naming the operation and error.
4. Unit tests: mock shapes validate against `shapes.py`; dispatcher honors
   `SABRE_MODE` via `monkeypatch.setenv`; a real-mode failure returns the
   mock result and logs the fallback (`caplog`).

## 3. Concurrency core — surface failed status writes (Phase 5 gap 1)

1. In `backend/api/concurrency_core.py` `_repair_one`, check the
   `(success, affected_rows, error)` tuple from both `update_status` calls;
   raise `RuntimeError` naming the item, target status, and cause when
   `success` is `False` or `affected_rows == 0`, so `_record` emits a
   `status="error"` completion event instead of a false `ok`.
2. Tests in `backend/tests/` (extend `test_concurrency_spike.py`): a failed
   `update_status` and a 0-row `update_status` each produce an `error` event;
   the happy path still produces `ok`.

## 4. Repair tools (OpenAI Agents SDK)

1. `backend/api/repair_tools.py`: six plain functions wrapped with
   `function_tool` (the `hello.py` `_get_weather` pattern) —
   `search_and_book_flight`, `rebook_flight`, `shift_hotel_dates` calling the
   Sabre client layer; `reschedule_ground`, `move_dining`, `rebook_experience`
   as simple canned mocks.
2. Each tool writes through the existing repositories: a `bookings` row (with
   `raw_response` JSON from the Sabre payload) and the `itinerary_items`
   status transition (`booked` for the booking tool, `fixed` for repair
   tools). Blocking BigQuery calls go through `asyncio.to_thread` when called
   from async paths.
3. Tests: each plain function, with `bq_helper` mocked, produces the expected
   DML calls and returns a payload the agent can read back (confirmation ref,
   new times, price).

## 5. Disruption injector

1. `backend/api/disruption.py`: `APIRouter` with
   `POST /v1/disruption/break_flight` — takes `trip_id`, finds the trip's
   flight item via `itinerary_items.list_items_for_trip`, flips it to
   `broken` via `update_status`, returns the item id and affected row count.
   404 when the trip has no flight item; surface failed/0-row writes as
   errors, not success.
2. Tests: happy flip, no-flight-item, failed-write cases with `bq_helper`
   mocked.

## 6. Wiring & walkthrough surface

1. Mount the new router(s) in `backend/main.py`; add landing-page links in
   `hello.py` per convention.
2. A thin demo endpoint (e.g. `POST /v1/sabre_tools/repair_trip`) that runs
   the six tools through `run_repairs` against a trip — the curl surface for
   the validation walkthrough and the seam Phase 9 will lift.
3. Seed helper (script or endpoint) to create a booked demo trip with all
   five item types, reusing the repositories — needed by the walkthrough and
   later phases.

## 7. Real-BigQuery proof (Phase 5 gap 2) & validation

1. Walkthrough against real BigQuery (local with credentials or the deployed
   Cloud Run service): seed a booked trip → injector breaks the flight →
   repair run → query `itinerary_items` showing every item `fixed` with
   `updated_at` stamps fresher than the disruption time. Capture the query
   output in the validation evidence.
2. Full suite green (`python -m pytest` in `backend/`), hermetic — no
   credentials, no `OPENAI_API_KEY`.
3. Complete `validation.md`; mark Phase 6 `[x] COMPLETE` in
   `specs/roadmap.md` only after both automated and manual sections pass.
