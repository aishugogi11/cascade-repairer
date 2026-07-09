# Plan — Concierge hybrid architecture (Phase 9)

Task groups in build order; each leaves the suite green. Reference
implementations: `concurrency_agent.py` (the inversion + snapshot),
`sabre_tools.repair_trip` (the launch assembly), `web_call.py` (the seam).

## 1. Shared repair-launch seam

1. Extract the assembly inside `sabre_tools.repair_trip` — the
   `_repair_call(item)` per-item coroutine map, `RepairSpec` construction, and
   `do_repair` closure — into `launch_trip_repairs(session_id, items) ->
   list[asyncio.Task]` (plus the launched-names list), importable without the
   router.
2. Re-point `repair_trip` at it; endpoint request/response contract and
   existing tests unchanged.

## 2. Single-writer cleanup (roadmap-mandated, folded from Phase 6)

1. In `repair_tools.py`, stop the five repair tools stamping `fixed`:
   `_write_booking_and_status` keeps writing the `bookings` row and drops the
   itinerary status flip for repair calls (the initial `_search_and_book_flight`
   `booked` transition stays — it is a booking, not a repair, and has no
   cascade unit around it). Tool return payloads stop claiming
   `"item_status": "fixed"`.
2. `_repair_one` in `concurrency_core.py` is now the only writer of the
   `repairing` → `fixed` transitions — confirm, don't change; update the
   `repair_trip` docstring that documents the old double-write.
3. Update `test_repair_tools.py` assertions: tools write bookings only;
   cascade tests (`test_sabre_tools.py`, `test_concurrency_spike.py`) still
   prove items reach `fixed` through the cascade unit.

## 3. Concierge foreground agent (`backend/api/concierge.py`)

1. Session snapshot: reuse/adapt `concurrency_agent.session_snapshot` wording
   (authoritative marker verbatim — it is measured, see Phase 5 findings) over
   the `concurrency_core` session keyed by the VB session name.
2. `fix_trip` function_tool (plain async function kept callable for tests):
   resolve the latest trip's items (`trips`/`itinerary_items` repositories via
   `asyncio.to_thread`, the `latest_trip_id` lookup), call
   `launch_trip_repairs(session_name, items)`, and return immediately with a
   speakable summary naming the launched repairs. No trip → a speakable "I
   don't see a booked trip" string. **No `await` of the repair tasks.**
3. `answer_query(session_name: str, query: str) -> str`: per-turn `Agent`
   build — model `CONCIERGE_LLM_MODEL` (default `gpt-4.1-mini`), instructions =
   spoken-style rules + fresh session snapshot, tools=[fix_trip closure over
   session_name] — with the same in-process history-replay shape as
   `web_call.answer_query` (`Runner.run(history + turn)`, `to_input_list()`,
   `max_turns` bounded).

## 4. Swap the web_call seam

1. `web_call.answer_query` delegates to `concierge.answer_query` (one-line
   body; keep the function so the seam, its tests, and rollback stay in
   place). Remove web_call's now-unused local agent wiring; `/token`, the
   page, and turn logging untouched.

## 5. Tests (`backend/tests/test_concierge.py` + updates)

1. Concierge unit: mocked `Runner` → history replay and per-session isolation
   (the web_call test shape); instructions passed to the agent contain the
   snapshot with pending/finished names and the authoritative marker.
2. `fix_trip` tool: with repositories and launch seam mocked — resolves the
   latest trip, launches one repair per item, returns before tasks complete
   (assert no await: tasks still pending when it returns), speakable no-trip
   message on empty tables.
3. The acceptance shape, hermetic (the Phase 5 test over the seam): a /query
   turn whose mocked agent calls `fix_trip` with slow fake repairs returns
   immediately; a second /query turn answers while the fakes are still
   pending; completion events land in the session log afterwards.
4. `test_web_call.py`: seam-swap keeps existing contract green (patch
   `concierge.answer_query` where the old tests patched `Runner`).
5. Groups 1–2 test updates as listed in their tasks.
