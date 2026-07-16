# Rich flight fields — validation (Phase 33)

Per the 2026-07-16 evening replan: **no PR-body evidence is required anywhere in this
file** — run evidence (pytest output, walkthrough notes, screenshots) lives in this
spec directory and the changelog entry.

## Automated

Run inside the dev container (host has no pytest):

```
docker compose exec -T backend python -m pytest tests/ -q
```

- [ ] Bare suite green — no new failures, no new warnings (the six pre-existing
      unawaited-coroutine RuntimeWarnings are Phase 24's, not this phase's, but the
      count must not grow).
- [ ] **Parser fills the rich fields from mock data**: `airline_name`, `cabin`,
      `duration_minutes`, `layover_airports`, `arrives_next_day` all populated from
      `mock_client.instaflights_search` itineraries, including one connecting
      itinerary yielding a non-empty via list and one non-economy cabin.
- [ ] **Degrade, never skip**: an itinerary missing `ElapsedTime` and the
      `FareInfos → TPA_Extensions → Cabin` chain still parses and is still offered,
      with `duration_minutes == 0` and `cabin == ""`.
- [ ] **Additive compatibility**: a pre-33 stored `FlightOption` payload (no rich
      fields) still validates — defaults apply.
- [ ] **Spoken clause**: contains the airline *name* ("on Delta"), never the code and
      never a fare-class letter; option numbers remain words; existing clause content
      (stops, times, rounded price) unchanged.
- [ ] **Stamping parity (the Phase 32 wipe guard)**: the booking stamp
      (`concierge._booking_writes`) and the repair re-stamp
      (`repair_tools._rebook_flight` → `update_flight_fields`) write the same
      rich-field key set for the same option; a mocked book → break → repair sequence
      leaves the flight item's `details` carrying the NEW flight's rich fields with
      `rebooked_from` preserved (now including the original's `airline_name`).
- [ ] **Exclusion identity untouched**: `details.airline` / `details.flight_number`
      keys and values behave exactly as Phase 31 tests already assert (those tests
      stay green unmodified).
- [ ] **Single airline table**: `itinerary_ui.py` imports the table from
      `flight_options.py`; no duplicate dict remains.
- [ ] **Status payload**: a booked flight item's rich fields reach
      `GET /v1/itinerary/status/{trip_id}`; `pending_options` candidates carry
      `airline_name` and duration; both blocks stay best-effort (a failure cannot
      break the poll — existing guard tests stay green).
- [ ] Timezone discipline and dedup unchanged: existing tz-skip and byte-identical
      dedup tests pass unmodified.

## Manual (mock mode, `localhost:1019`)

Walkthrough — the operator run sheet's booking beat, `SABRE_MODE=mock`:

- [ ] Book by voice on `/v1/cascade/` (🆕 New trip first): while options are pending,
      the candidates panel shows airline names and durations, no codes.
- [ ] The agent reads "Option one on <Airline>: …" — names spoken, codes never; the
      per-option clause has NOT grown duration/cabin.
- [ ] Ask "how long is option two?" and "is it economy?" mid-conversation — the agent
      answers from the tool result without re-searching.
- [ ] After booking, the flight card shows airline name + flight number in the
      headline and the facts row: cabin, nonstop / "1 stop via <code>", duration
      (`Xh Ym`), and "arrives next day" only when true.
- [ ] Break → consent → repair: the repaired card shows the NEW flight's rich fields;
      the struck-through was-line still renders and names the old carrier.
- [ ] Second break → repair on the same trip: rich fields survive (nothing wiped by
      the wholesale `details` replace) and the re-shop still excludes the current
      flight.
- [ ] A pre-33 trip (seeded or existing): flight card renders exactly as before — no
      "undefined", no empty facts-row artifacts.

Edge cases:

- [ ] Mock's connecting itinerary booked: card says "1 stop via <code>"; agent can
      name the layover when asked.
- [ ] An airline code missing from the static table (test via a doctored mock or
      unit-level): bare code displays/speaks — degraded, not broken.

Live spot-check (optional, cert-fenced — not a merge gate): one
`pytest -m cert` InstaFlights parse against the verified anchor pair (JFK→LAX)
confirming real CERT responses populate (or gracefully omit) the rich fields.

## Tone check

- [ ] Spoken copy: airline names only, no IATA codes, no fare-class letters, no
      digits-as-labels; durations only when asked, phrased naturally.
- [ ] Page copy: times labeled "PT"; facts row terse (card real estate — the mockup's
      aesthetic); "arrives next day" phrasing, not a "+1" glyph.

## Definition of done

- [ ] All automated assertions above pass in the container; suite green.
- [ ] Manual walkthrough completed in mock mode with notes (and any screenshots)
      saved to this spec directory.
- [ ] Merged to `vb/dev` via PR; Cloud Build green (pytest inside the image blocks
      the deploy); deployed service spot-checked on `/v1/cascade/`.
- [ ] `specs/roadmap.md` Phase 33 marked `[x] COMPLETE`.
