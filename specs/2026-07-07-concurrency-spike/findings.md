# Findings — Concurrency Spike (Phase 5)

**Answer to Pallavi's flag (Discord 2026-07-06): no rewire needed.** Voice-as-a-tool
is sequential only if you `await` the slow tool inline. Firing the slow work with
`asyncio.create_task` alongside the session and awaiting only the conversational
`Runner.run` keeps the agent responsive the whole time. Measured, not argued:

## Pallavi's test, verbatim (live run, 2026-07-07, local dev container, real gpt-4.1-mini)

`POST /v1/concurrency_spike/talk_while_tool_runs` with a 10.0s fake API call:

- Slow call started `15:49:51.168Z`; follow-up answered `15:49:57.110Z` —
  **5.94s in, with the slow call still running** (`answered_before_tool_finished: true`).
- The ~5.9s is almost entirely the LLM turn itself (a long packing-list answer);
  the concurrency machinery adds effectively nothing.

## The cascade shape (live run, five categories)

`POST /v1/concurrency_spike/cascade` (durations 2–6s, staggered):

- All five repairs started within 10ms of each other and overlapped fully;
  completions reported back into the session log as each landed
  (flight → hotel → ground → dining → experience).
- Wall time 11.9s vs a 20s sequential sum. Concurrency confirmed; the excess
  over the 6s max duration was BigQuery client overhead per status flip (see
  sharp edges).
- Hermetic pytest re-proves overlap, completion order, and per-item
  `repairing → fixed` DML on every CI build (`tests/test_concurrency_spike.py`).

## The pattern Phases 7–9 should reuse (`api/concurrency_core.py`)

1. `start_background_call(session_id, name, coro)` — fire-and-forget
   `asyncio.create_task`; completions append to a per-session event log the
   agent can read between turns.
2. `run_repairs(session_id, specs, do_repair)` — one background task per
   itinerary item; each flips `repairing` on start and `fixed` on landing via
   the existing repository layer.
3. Agent turns stay a plain `await Runner.run(...)` on the same loop — the
   foreground/background split needs no SDK feature beyond function tools that
   *launch* work and return immediately.
4. `session_snapshot(session_id)` — a status line of pending/landed background
   work injected into the agent's instructions each turn, so "how are the
   repairs coming?" gets a grounded answer mid-cascade. Prompt wording matters:
   a terse status list alone made gpt-4.1-mini ask "which repairs?"; marking it
   authoritative ("this list is what 'the repairs' means") fixed it. Verified
   live: mid-cascade follow-up answered in ~3.0s naming all five repairs.

## Sharp edges found

- **Blocking BigQuery calls are the real latency threat, not the SDK.** Each
  `update_status` is a synchronous query-job DML; on the event loop it would
  stall the conversation. The core runs every repository call through
  `asyncio.to_thread` — keep that rule in the voice phases.
- **Status-write failures are silent by design** (helpers return error tuples;
  the repair still reports `ok`). Fine for the spike; the Concierge phase
  should surface a failed flip so the agent doesn't read back a fix the UI
  never showed. Local runs without ADC exercise exactly this path.
- **The session/event registry is in-memory and single-process** — fine for
  one Cloud Run instance and one demo conversation; do not scale past that
  without external state.
- **One failed repair doesn't kill its siblings** — exceptions are captured
  into the event log (`status: "error"`), and the item is deliberately left
  un-`fixed`.
