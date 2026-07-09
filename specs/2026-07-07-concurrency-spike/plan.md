# Plan — Concurrency Spike (Phase 5)

Task groups are independently implementable in order; each leaves the suite
green.

## 1. Concurrency core (plain asyncio, no LLM, no FastAPI)

1. Create `backend/api/concurrency_core.py` (or similar) holding the reusable
   pattern the voice phases will import:
   - `start_background_call(coro) -> asyncio.Task` — fire-and-forget wrapper
     around `asyncio.create_task` that records start time and, on completion,
     appends a completion event `{name, started_at, finished_at, result}` to a
     per-session in-memory event log.
   - `run_repairs(items, do_repair, ...) -> list[asyncio.Task]` — launches one
     background task per itinerary item; each task flips the item
     `repairing` on start and `fixed` on finish via
     `api.repositories.itinerary_items.update_status`, then logs its
     completion event. Durations injectable per item.
2. Keep the session/event registry a simple module-level dict keyed by
   session id — spike-grade, documented as such.

## 2. Fake tools + agent wiring

1. Fake slow API call: plain async function `_slow_api_call(seconds)` that
   `asyncio.sleep`s and returns a canned payload; keep it callable directly by
   tests, wrap with `function_tool` for the agent (the `_get_weather` pattern
   in `hello.py`).
2. Fake repair functions per category (flight/hotel/ground/dining/experience)
   returning canned "rebooked" payloads after their injected duration.
3. Agent setup mirroring `hello.py`: `Agent(model="gpt-4.1-mini", ...)` whose
   tools launch background work via the concurrency core instead of awaiting
   it inline, then answer immediately (e.g. "repair started").

## 3. Endpoints & router

1. `backend/api/concurrency_spike.py` with an `APIRouter`, mounted in
   `backend/main.py` under `/v1/concurrency_spike`; add a link on the
   `hello.py` landing page.
2. **Proof A endpoint** — `POST /talk_while_tool_runs`: starts the 10s fake
   call in the background, then runs a follow-up agent turn
   (`await Runner.run`) while it is in flight. Response: the follow-up answer,
   timestamps for slow-call start / follow-up answered / slow-call end (or
   "still running"), and a boolean `answered_before_tool_finished`.
3. **Proof B endpoint** — `POST /cascade`: seeds (or accepts) a trip's N≥3
   item ids, launches parallel repair tasks with staggered durations, returns
   immediately with the task list; a subsequent call (or the same response
   after completion, via an optional `wait=true` flag) exposes the completion
   event log showing overlapping intervals and per-item status writes.
4. Endpoints tolerate missing `OPENAI_API_KEY` / GCP creds with a clear error
   body rather than a 500 traceback (spike still curl-testable locally).

## 4. Tests (hermetic — no OPENAI_API_KEY, no GCP)

1. `backend/tests/test_concurrency_spike.py`.
2. Proof A timing: with the LLM turn replaced by a stub coroutine, assert the
   follow-up answer returns while a (shortened, e.g. 0.5s) background call is
   still running — `answered_before_tool_finished is True`, follow-up latency
   « background duration.
3. Proof B overlap: launch ≥3 repairs with staggered short durations; assert
   their `[started_at, finished_at]` intervals mutually overlap (concurrent,
   not sequential — total wall time ≈ max duration, not sum) and completions
   arrive in duration order, not launch order.
4. Status writes: mock `bq_helper.run_dml` (per `test_repositories.py`) and
   assert each repair produced the `repairing` then `fixed` UPDATEs for its
   item id, as each task finished.
5. Router smoke test: FastAPI `TestClient` hits both endpoints with the
   stubbed LLM and mocked bq boundary.

## 5. Findings writeup

1. Run the live curl walkthrough (real `OPENAI_API_KEY`, 10s tool) locally
   and/or on Cloud Run; capture timings.
2. Write `specs/2026-07-07-concurrency-spike/findings.md`: what was measured,
   whether voice-as-a-tool needs a rewire (Pallavi's flag), the exact pattern
   Phases 7–9 should reuse, and any sharp edges found (event-loop blocking,
   task lifetime on Cloud Run, etc.).
3. Mark Phase 5 `[x] COMPLETE` in `specs/roadmap.md` only after validation.md
   passes.
