# Plan — Repaired flight reflected on the cascade page (Phase 32)

Branch: `vb/feature/repaired-flight-on-page`. Groups are independently implementable
in order; each lands with its tests green.

## 1. Repository: flight-field update

1.1 Add `update_flight_fields(item_id, *, start_ts, end_ts, price, currency, details)`
    to `backend/api/repositories/itinerary_items.py`, modeled on `update_status`:
    parameterized query-job DML `UPDATE` (never streaming), sets the passed fields
    plus `updated_at = CURRENT_TIMESTAMP()`, returns `(success, rowcount, error)`.
    `details` serializes to the JSON column the same way `create_item` does.
1.2 Hermetic tests (mock the bq helper boundary, per the existing repository tests):
    success path builds the expected DML + params; failure/0-row surfaces through
    the return tuple.

## 2. Repair write-back (the actual fix)

2.1 Extract the option→timestamps conversion from `concierge._booking_writes`
    (`concierge.py:435-448` — PT localization, red-eye `arrive_date` handling) into a
    small shared helper (e.g. `flight_options.option_timestamps(option) ->
    (start_ts, end_ts)`); `_booking_writes` calls it, behavior unchanged.
2.2 In `_rebook_flight` (`backend/api/repair_tools.py`), after the booking write and
    before returning: build the new item fields from `chosen` (timestamps via 2.1,
    `price`/`currency`, `details = {airline, flight_number, rebooked_from: {...}}`)
    and write them via `asyncio.to_thread(itinerary_items.update_flight_fields, ...)`
    (standing rule: blocking BigQuery DML off the event loop). Raise on failed/0-row
    write, mirroring `_flip_status` — so `_repair_one` reports `error` instead of
    flipping `fixed` over stale fields.
2.3 `rebooked_from` (structured, best-effort): original `airline`/`flight_number`
    (from the `cancelled_flight` param when present), `depart_time`/`arrive_time`
    (the `original_depart_time`/`original_arrive_time` params), `price`/`currency`.
    Include the same block in the booking's `raw_response` so the detail derivation
    (group 3) can speak it. All fields optional; absent context degrades gracefully.
2.4 Tests (existing repair-tools test patterns, mock Sabre client + mocked repos):
    - after `_rebook_flight`, the item update was called with the chosen option's
      timestamps/price/identity; `details.airline`/`flight_number` are the **new**
      flight's (exclusion-identity re-stamp).
    - a failed field update raises (no silent `fixed` with stale fields).
    - mock-fallback path (`from_mock_fallback=True`) updates fields the same way.
    - missing original context (all optional params omitted, the walkthrough shape)
      still repairs and writes a `rebooked_from` without identity — no crash.
    - existing Phase 31 exclusion tests stay green.

## 3. Detail payload: the "was" line

3.1 In `itinerary_ui._flight_repair_detail`, derive an additive `rebooked_from`
    string from the `raw_response` original block — e.g.
    "Was UA 512 · departed 8:05 AM PT · $214". Identity absent → times/price only;
    nothing usable → omit the key. Never raises (best-effort detail contract).
3.2 Tests in the existing itinerary-ui detail suite: full context, identity-less
    context, empty context; other detail sources (`voice_guided_booking`, seeded)
    unchanged.

## 4. Cascade page: old → new treatment

4.1 In `backend/api/assets/cascade/page.html` `renderFlight`: when
    `detail.rebooked_from` is present, show a "was …" line on the flight card,
    struck-through/muted, beneath the route/times; hidden otherwise. Card headline
    fields need no change — they now render the corrected row.
4.2 Styling consistent with the card's existing status treatments (the `fixed`
    state's green frame stays the hero; the was-line is quiet).
4.3 No browser-automation tests (standing decision) — behavior is covered by the
    scripted manual QA in `validation.md`.

## 5. Validation & evidence

5.1 Full bare suite green in the container: `docker compose exec backend python -m pytest`.
5.2 Mock walkthrough locally (see `validation.md` § Manual) — seed → break → repair →
    page shows the new flight with the was-line.
5.3 Deploy via PR to `vb/dev`; re-run the walkthrough against Cloud Run.
5.4 Write the `### Mock walkthrough` / `### Live run` / `### Pytest` evidence into
    `PR_BODY.md` **before** merging (Phase 31 guard).
5.5 Mark Phase 32 `[x] COMPLETE` in `specs/roadmap.md`.
