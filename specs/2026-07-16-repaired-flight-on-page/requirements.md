# Requirements — Repaired flight reflected on the cascade page (Phase 32)

## The bug

After the repair cascade rebooks the flight, the cascade page (`GET /v1/cascade/`)
still displays the **original** flight's times and price with status `fixed`. The
broken → fixed flip is the demo moment — it must show the *new* flight.

**Root cause (diagnosed at spec time, 2026-07-16):** `_rebook_flight`
(`backend/api/repair_tools.py:248`) writes an enriched `bookings` row and returns the
chosen replacement, and the cascade unit (`concurrency_core._repair_one`) flips the
item's status to `fixed` — but **nothing ever updates the `itinerary_items` row**.
The page's `renderFlight` (`backend/api/assets/cascade/page.html`, ~line 1022)
renders the flight card purely from that row: `location`, `price`, `start_ts`/`end_ts`,
`status`. Only the best-effort `detail.why_chosen` sentence (derived from the booking's
`raw_response` in `itinerary_ui._flight_repair_detail`) names the new flight — the
card's headline fields stay stale. The fix is server-side, at the source of truth;
the page stays a pure reflection of server state.

## Scope

### In

| Field on the flight `itinerary_items` row | After repair must hold |
|---|---|
| `start_ts` / `end_ts` | The rebooked flight's PT-localized departure/arrival instants (UTC in BigQuery, per the standing timezone rule), including the red-eye arrive-date handling `_booking_writes` already proves out (`concierge.py:435-448`) |
| `price` / `currency` | The rebooked flight's fare |
| `details.airline` / `details.flight_number` | The **rebooked** flight's identity — this is the Phase 31 exclusion identity, so a second disrupt→repair excludes the *current* flight, not the long-gone original |
| `details.rebooked_from` | Structured record of the original flight (identity when known, depart/arrive PT clocks, price) — the old→new UI's data |
| `updated_at` | Refreshed by the update (the page feed timestamps from it) |
| `location` | Unchanged — the re-shop searches the same route |

- **Old → new transition on the card**: the flight card shows the rebooked flight
  prominently, with the original flight visible as a struck-through "was …" line.
  The copy rides the established **additive, best-effort `detail` channel**: 
  `_flight_repair_detail` gains a `rebooked_from` string (e.g. 
  "Was UA 512 · departed 8:05 AM PT · $214"), derived from new fields in the repair
  booking's `raw_response`; the page shows the line only when the field is present.
- **Ordering guarantee**: the item-field update lands **before** the `fixed` status
  flip. `_repair_one` flips only after the tool coroutine returns, so performing the
  update inside `_rebook_flight` (raising on a failed/0-row write, like `_flip_status`)
  gives this for free — the poll can never render `fixed` + stale fields.
- A new repository update function in `backend/api/repositories/itinerary_items.py`
  (today it has only `update_status`) — parameterized **query-job DML, never streaming**
  (standing rule; streaming-buffer rows can't be UPDATEd).

### Out

- Rich flight fields on the card (airline name, cabin, nonstop, duration) — **Phase 33**.
- The booking page (`/v1/booking/`) and iOS surfaces — they read the same status
  payload and inherit the corrected row automatically; no markup changes there.
  Unknown `detail` fields are ignored by design (additive contract).
- Any change to the repair guarantee (`_pick_replacement`), consent flow, voice
  scripts, trip model, schema, or `_booking_writes`.
- Mock-fallback behavior changes — when the re-shop falls back to mock options,
  the item row updates from the mock-chosen option exactly the same way.

## Decisions

1. **Fix at the source of truth** (settled at the spec interview; diagnosis confirmed
   the server side): the repair writes the rebooked flight into the item row; no
   client-side caching/merging workarounds.
2. **Old → new treatment** over clean replacement: the visible flip *is* the demo
   moment; a struck-through "was" line makes the change legible from the audience.
3. **`detail` channel for the "was" copy**: server-side sentence in
   `_flight_repair_detail` (register-controlled, best-effort, can never break the
   poll), structured original under `item.details.rebooked_from` for anything that
   needs data rather than copy.
4. **Best-effort degradation**: seed/pre-31 trips may lack original flight identity
   (`cancelled_flight` is `None`); the "was" line then falls back to times/price only,
   or is omitted entirely — never a crash, never a blocked repair.
5. **Re-stamp the exclusion identity**: `details.airline`/`flight_number` must become
   the rebooked flight's — otherwise a second break→repair on the same trip could
   "repair" onto the flight the traveler is already on.

## Context

- **Demo-critical, minimal blast radius** (settled at the interview): 2 days to event
  day; this is the one known bug in an otherwise-working flow. No new dependencies,
  no refactors beyond extracting the option→timestamps conversion for reuse, no
  changes to consent/repair/voice seams.
- Timezone discipline: DB stores UTC, edges speak Pacific labeled "PT" (never "PST").
- Copy register: match the page's traveler-voiced feed — glanceable, plain, no codes
  the traveler wouldn't say (existing detail copy is the model).
- No browser-automation tests — the page's JS behavior is scripted manual QA
  (standing decision, Phase 10).
- Tests are hermetic (no GCP creds); run inside the container:
  `docker compose exec backend python -m pytest`.
- **PR evidence pre-merge** (Phase 31 guard): mock walkthrough / live run / pytest
  evidence written into `PR_BODY.md` before `git_pull_dev.sh` merges.
