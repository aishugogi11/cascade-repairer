# Requirements — Sabre Tools (Phase 6)

Roadmap Phase 6: repair-capable Sabre tools with a runtime mock fallback. This
is the phase that gives the Cascade Repairer real hands — the six repair tools
the demo fires in parallel, the disruption injector that triggers the demo, and
the two data-integrity gaps carried over from the Phase 5 spike.

## Scope

Full roadmap scope on this one branch (per Josh, 2026-07-08): documented Sabre
shapes + mock layer + runtime flag, all six agent tools, the disruption
injector, and both Phase 5 carry-over gaps.

### In scope

| Deliverable | What it delivers |
|---|---|
| **Sabre API documentation pull** | Current Sabre endpoints, request shapes, and response payloads for **both paths**: flight search/booking *and* cancel/rebook; hotel booking *and* date change. Recorded as `sabre-api-notes.md` in this spec directory — the source of truth the mock shapes are checked against. |
| **Sabre client layer** (`backend/api/sabre/`) | Pydantic models matching the documented payloads 1:1; a **mock client** returning those shapes; a **real client stub** implementing the same interface (docs-only this phase — no sandbox calls, no credentials required); a dispatcher that picks mock vs real per call from the runtime flag, with auto-fallback. |
| **Runtime config flag** | `SABRE_MODE` env var (`mock` \| `real`), default `mock`, read at call time. In `real` mode any Sabre call failure **automatically falls back to the mock for that call** and logs the fallback — event-day insurance if the sandbox flakes during judging. Flipping the mode on Cloud Run is an env-var update (`--update-env-vars` merge), no code change. |
| **Six repair tools** (OpenAI Agents SDK) | Three Sabre-documented tools plus three simple category mocks — exact table below. Each tool writes results into the trip tables (`bookings` row + `itinerary_items` status transition) through the existing repositories. |
| **Disruption injector** | An endpoint that flips a booked flight item to `broken` on cue — the demo's trigger. Idempotent, curl-able, works against real BigQuery rows. |
| **Phase 5 gap 1 — surface failed writes** | `_repair_one` in `backend/api/concurrency_core.py` currently ignores the `(success, affected_rows, error)` tuple from `itinerary_items.update_status`. A repair must **not** report `ok` when a status write fails or matches 0 rows. |
| **Phase 5 gap 2 — prove real rows flip** | A validation walkthrough that shows real `itinerary_items` rows transition `repairing → fixed` with fresh `updated_at` stamps in BigQuery (Phase 5 only proved DML emission against demo ids). |

### Tool surface (the six tools)

| Tool | Category | Backing | Writes |
|---|---|---|---|
| `search_and_book_flight` | flight (booking path) | Sabre documented shapes | `bookings` row, item → `booked` |
| `rebook_flight` | flight (repair path) | Sabre documented shapes | new `bookings` row, item → `fixed` |
| `shift_hotel_dates` | hotel (repair path) | Sabre documented shapes | `bookings` update, item → `fixed` |
| `reschedule_ground` | ground (repair) | simple mock | item → `fixed` |
| `move_dining` | dining (repair) | simple mock | item → `fixed` |
| `rebook_experience` | experience (repair) | simple mock | item → `fixed` |

Hotel *booking* and flight *cancel* shapes are documented and modeled in the
client layer (the docs pull covers them) even where no dedicated tool is
exposed this phase — `rebook_flight` composes cancel + book internally, and
seeded demo trips supply the initial hotel booking.

### Out of scope

- **Real Sabre sandbox calls** — no credentials this phase (per Josh). The real
  client is written behind the same interface but not exercised; wiring and
  certifying it is event-day prep.
- Voice transport (Phases 7–9) — tools are exercised via HTTP/JSON and pytest.
- The itinerary UI or any status-read surface beyond what exists (Phase 10).
- MCP-server packaging of the Sabre tools — tools ship as in-process
  `function_tool`s like `hello.py`; an MCP wrapper can come later if a phase
  needs it.
- New dependencies. FastAPI + OpenAI Agents SDK + pydantic + google-cloud
  libraries already in `backend/requirements.txt` cover everything.

## Decisions

- **Runtime flag: `SABRE_MODE` env var + per-call auto-fallback** (per Josh).
  Default `mock` until event day. In `real` mode, a failed Sabre call falls
  back to the mock **for that call** and logs it loudly (`logger.warning` with
  operation name and error) — the judges see the cascade either way, per the
  team decision recorded in `tech-stack.md`. The flag is read at call time,
  not import time, so tests can flip it with `monkeypatch.setenv` and Cloud
  Run can flip it without a rebuild.
- **Docs-only real client** (per Josh). `real_client.py` implements the shared
  interface with the documented request construction, but this phase never
  calls the sandbox; its correctness claim is "matches `sabre-api-notes.md`",
  not "certified against the sandbox".
- **Mock responses match documented shapes 1:1** — pydantic models are built
  from the docs pull, and mocks construct instances of those models, so a
  shape drift between mock and documentation is a test failure, not a demo-day
  surprise.
- **All writes go through the existing repository layer** — `bookings` and
  `itinerary_items` repositories, DML never streaming inserts, statuses
  validated as enums at the repository boundary. Tools never touch
  `bq_helper` directly.
- **Failed status writes surface as errors** (Phase 5 gap): `_repair_one`
  checks the `(success, affected_rows, error)` return of `update_status` and
  raises on `success=False` **or** `affected_rows == 0`, so `_record` captures
  a `status="error"` completion event instead of a false `ok`. The demo agent
  must never announce a repair that didn't land in the table the UI reads.
- **The disruption injector is an HTTP endpoint** (roadmap allows endpoint or
  script): `POST /v1/disruption/break_flight` taking a `trip_id`, flipping
  that trip's flight item to `broken` via the repository. An endpoint works
  from a phone, a script, or a teammate's laptop during the demo; a script
  only works from a checkout.

## Context

- Follow the router pattern of `backend/api/hello.py` / `backend/api/vb_test.py`
  / `backend/api/concurrency_spike.py`: `APIRouter` modules mounted in
  `backend/main.py`, linked from the landing-page list in `hello.py`.
- Agents SDK usage mirrors `hello.py` and `concurrency_agent.py`: `Agent` +
  `function_tool` + `await Runner.run(...)`, model `gpt-4.1-mini`; keep tool
  bodies as plain functions wrapped with `function_tool` so tests call the
  plain function (the `_get_weather` pattern).
- Blocking BigQuery calls inside async paths go through `asyncio.to_thread`
  (standing rule from Phase 5 — see `tech-stack.md`).
- Tests live in `backend/tests/`, hermetic per `test_repositories.py`
  conventions: mock at the `bq_helper` boundary (`run_dml`/`run_select` on the
  singleton), no credentials, no network, no `OPENAI_API_KEY`. They run in CI
  inside the built container; a failure blocks the deploy.
- Tone for `sabre-api-notes.md`, tool descriptions, and endpoint copy: plain
  engineering prose — state what the operation does and returns, no marketing.
- Hackathon clock: this must land well before July 18. Phases 7–10 all build
  on these tools; the docs pull happens first so shape questions surface early.
