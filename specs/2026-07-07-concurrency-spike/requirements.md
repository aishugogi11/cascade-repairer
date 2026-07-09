# Requirements — Concurrency Spike (Phase 5)

Roadmap Phase 5: prove the voice-as-a-tool pattern can speak while background
repairs run, answering Pallavi's flag (Discord 2026-07-06) with evidence before
any voice architecture is built on top. Text transport; the *pattern* is what
Phases 7–9 will reuse.

## Scope

Two thin, curl-testable FastAPI endpoints plus tests and a findings note. No
UI, no new status-read endpoint (Phase 10 owns the itinerary surface).

### In scope

| Deliverable | What it proves |
|---|---|
| **Proof A — talk-while-tool-runs endpoint** | An agent session answers a follow-up turn while a fake 10-second tool call is still in flight. The response carries timing evidence (follow-up answered at `t < 10s` after the slow call started). |
| **Proof B — parallel cascade endpoint** | N≥3 fake repair tasks run concurrently (staggered durations, overlapping in time) and each writes its `repairing → fixed` status transition to `itinerary_items` as it lands — the cascade shape. Completion events also land back in the in-process session record. |
| **Pytest timing/ordering assertions** | Both proofs are repeatable in CI, hermetically (no `OPENAI_API_KEY`, no GCP). |
| **`findings.md` in this spec directory** | The spike's real output: does voice-as-a-tool need a rewire, or does `asyncio` + parallel tool dispatch suffice? Written for the team (answers Pallavi directly). |

### Out of scope

- Any voice transport (Phases 7–9) — text/JSON responses only.
- Real repair logic or Sabre calls (Phase 6) — fake tools are `asyncio.sleep` with canned results.
- A trip-status polling/SSE endpoint or any UI (Phase 10). Status flips are
  observable in `itinerary_items` via existing repositories and in the
  endpoint's returned event log.
- New dependencies. Everything ships on FastAPI + OpenAI Agents SDK + asyncio
  already in the stack.

## Decisions

- **Mechanism: `asyncio.create_task` background tasks + parallel tool dispatch
  via the OpenAI Agents SDK** (per Josh). Repairs are fire-and-forget asyncio
  tasks alongside the active session; agent turns keep flowing via
  `await Runner.run(...)` while they run. Not sequential `await` per tool, and
  not separate parallel `Runner.run` sessions — the roadmap's primary hint,
  and it stays inside the existing stack.
- **Concurrency core is separable from the LLM.** The task registry / repair
  runner must be plain asyncio, callable without an agent, so pytest can prove
  timing without `OPENAI_API_KEY`. The agent layer wraps it; the live curl
  walkthrough proves the wrapped version.
- **Statuses go through the existing repository layer** —
  `itinerary_items.update_status` (DML, never streaming inserts) so flips are
  immediately updatable and Phase 10 can read them unchanged. Repair task
  durations are parameterizable so tests run in milliseconds.
- **Proof is both a writeup and tests** (per Josh): `findings.md` records the
  answer to Pallavi's flag for the team; pytest keeps the timing claims true
  in CI on every build.
- **Acceptance is Pallavi's quick test verbatim:** *the agent speaks (responds)
  while a 10-second fake API call is still running.*

## Context

- Follow the router pattern in `backend/api/hello.py` / `backend/api/vb_test.py`:
  an `APIRouter` in `backend/api/concurrency_spike.py`, mounted in
  `backend/main.py` under `/v1/concurrency_spike`, linked from the landing page
  list in `hello.py`.
- Agents SDK usage mirrors `hello.py`: `Agent` + `function_tool` +
  `await Runner.run(...)`, model `gpt-4.1-mini`; keep fake tools as plain
  functions wrapped with `function_tool` so tests can call the plain function
  (the `_get_weather` pattern).
- Tests live in `backend/tests/`, hermetic per `test_repositories.py`
  conventions: mock at the `bq_helper` boundary (`run_dml`/`run_select` on the
  singleton), no credentials, no network. They run in CI inside the built
  container; a failure blocks the deploy.
- Tone for `findings.md` and endpoint copy: plain engineering prose for the
  team thread — state what was measured, numbers included, no marketing.
- Hackathon clock: this must land well before July 18; keep it a spike, not a
  framework.
