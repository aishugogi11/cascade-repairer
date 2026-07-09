# Requirements — Live Itinerary UI (Phase 10)

The demo's second surface: a single FastAPI-served page showing the unified trip
itinerary and flipping **broken → repairing → fixed** live while the agent talks.
This is the screen the judges watch during the Cascade Repairer moment.

## Scope

### In scope

- **A new router `backend/api/itinerary_ui.py`** registered in `main.py` under
  `/v1/itinerary`, serving both the page and its JSON endpoints. No separate
  frontend deploy, no CORS, no build step.
- **The itinerary page** (`GET /v1/itinerary/`) rendering one trip:
  - All five item types (flight, hotel, ground, dining, experience) as status
    cards with type icon, description, time/location, and current status.
  - Live updates via **polling** (~1.5 s) against the trip-status endpoint.
  - **Repair event feed**: a running timeline ("Flight UA123 broken",
    "Flight rebooked → fixed") appended as statuses change.
  - **Trip selector**: pick which trip to watch from recent trips; the demo
    trip loads by default (most recent trip, or `?trip_id=` override).
  - **Elapsed-time indicator**: a visible timer that starts on the first
    `broken` flip and stops when nothing is broken/repairing — supporting the
    "all five fixed in under 60 seconds" target.
- **Trip-status endpoint** (`GET /v1/itinerary/status/{trip_id}`): trip header
  + all itinerary items with status and `updated_at`, shaped for the poller.
- **Recent-trips endpoint** (`GET /v1/itinerary/trips`) backing the selector —
  requires a new `list_recent_trips(limit)` function in
  `backend/api/repositories/trips.py` (the only repo gap).

### Trip-status payload

| Field | Source | Notes |
|-------|--------|-------|
| `trip` | `trips.get_trip` | trip_id, title, status, origin, destination, dates |
| `items[]` | `itinerary_items.list_items_for_trip` | item_id, type, status, provider, start_ts, end_ts, location, details, price, updated_at |
| `summary` | computed server-side | counts per status + `all_clear` bool (no item broken/repairing) |
| `fetched_at` | server timestamp | lets the client show staleness if polling hiccups |

### Out of scope

- The voice orb, conversation transcript, and "AI Recommended / Sabre live
  search" panels from the mockup — the voice surface is the Phase 9 web-call
  page; those panels are event-day polish (Phase 12), not foundation.
- SSE/WebSocket transport (polling is the decision — see below).
- Any write path: this page is read-only; disruption and repair are driven by
  the existing `/v1/disruption` and `/v1/sabre_tools` endpoints and the agent.
- Auth (consistent with every other page in the repo).

## Decisions

- **Polling, not SSE** (user decision): the page polls the status endpoint
  every ~1.5 s. Simplest and robust on Cloud Run; BigQuery reads stay
  request-scoped. One `list_items_for_trip` SELECT per poll is irrelevant at
  demo scale.
- **Event feed is derived client-side**: the page diffs item statuses between
  polls and appends a feed entry per transition, timestamped from the item's
  `updated_at`. No new table, no server-side event state — keeps the endpoint
  a pure read and honors the "session state is in-process memory" rule without
  touching it at all.
- **Endpoints are `async def` + `asyncio.to_thread` around repository calls**,
  following `concierge.py` — the standing rule that blocking BigQuery calls
  never run on the event loop.
- **Page HTML lives in `backend/api/assets/itinerary/page.html`**, read once at
  import and served via `HTMLResponse` — same serving shape as `web_call.py`,
  but a file instead of an inline `Template` because demo-polished CSS makes
  the page too large to inline comfortably. Vanilla HTML/CSS/JS only.
- **Visuals follow the team mockup** (`about/ui_ideas/ui_mockup_2026_07_09.png`,
  teammate's design): its trip-timeline rail with status-colored nodes, card
  layout, status chips, and activity feed are the reference. Adapted, not
  cloned — we build the itinerary/timeline/feed portion, skipping the voice
  and Sabre-detail panels (out of scope above).
- **Status → color language** (readable from across a room, per the mockup):
  `booked/planned` neutral blue, `broken` red, `repairing` amber with a pulse
  animation, `fixed` green, `cancelled` muted gray. Transitions animate so the
  flip is visible on a projector.
- **Reusable endpoint**: the status payload is plain JSON with no UI-specific
  shaping beyond `summary`, so Phase 12 rehearsal scripting and eval capture
  can hit the same endpoint.

## Context

- The demo moment (mission.md): the screen flipping broken → fixed *while the
  agent talks* **is** the demo. Latency of a status flip appearing on screen
  should be one poll interval, ~1.5 s worst case.
- Drive-it-yourself loop already exists: `POST /v1/sabre_tools/seed_trip` →
  `POST /v1/disruption/break_flight` → `POST /v1/sabre_tools/repair_trip`
  (or the concierge agent) — the page needs no new demo plumbing.
- On-screen copy is traveler-facing and calm-confident, matching the mockup's
  tone ("Cascade is actively repairing your itinerary") — reassuring, present
  tense, no exclamation points, no jargon like "DML" or "row".
- Tests follow the hermetic pattern (`test_disruption.py`,
  `test_sabre_tools.py`): repositories mocked at the module boundary, no GCP
  credentials, run inside the container in CI.
- Statuses are the repository enums (`planned/booked/broken/repairing/fixed/
  cancelled`) — the UI must render all six, not just the repair-cycle four.
