# Rich flight fields — plan (Phase 33)

Task groups in dependency order; each group is independently implementable and leaves
the suite green.

## 1. Sabre shapes + mock data

1.1 Add the optional rich-field paths to `backend/api/sabre/shapes.py` (all additive,
    `Optional`/defaulted — a real itinerary missing them must still parse):
    `OriginDestinationOption.ElapsedTime: Optional[int]`, and the pricing chain
    `AirItineraryPricingInfo.FareInfos → FareInfo[].TPA_Extensions → Cabin.Cabin`
    (new small models mirroring the notebook's observed response shape).
1.2 Teach `mock_client.instaflights_search` to emit the new fields on its three
    deterministic itineraries: `ElapsedTime` consistent with each itinerary's segment
    clocks (arrival − departure in minutes, per the mock's airport-local fiction), a
    cabin code (e.g. `Y` on two options, `J` on one so the non-economy path renders),
    and keep at least one connecting itinerary so `layover_airports` exercises.
1.3 Tests: shapes round-trip with and without the optional fields (a payload missing
    `ElapsedTime`/`FareInfos` parses); mock response carries them deterministically.

## 2. Shared parser: FlightOption rich fields

2.1 Promote `_AIRLINE_NAMES` from `itinerary_ui.py` into `flight_options.py` as
    `AIRLINE_NAMES` (module-level, exported); `itinerary_ui` imports it — delete the
    local copy. Add an `airline_name(code)` helper with bare-code fallback.
2.2 Add the notebook's `CABIN_NAMES` letter map and a `fmt_duration(minutes)` helper
    (`349 → "5h 49m"`) to `flight_options.py`.
2.3 Extend `FlightOption` with the additive fields (defaults keep stored payloads and
    pre-33 construction sites valid, the `arrive_date` precedent): `airline_name: str
    = ""`, `cabin: str = ""`, `duration_minutes: int = 0`,
    `layover_airports: List[str] = []`, `arrives_next_day: bool = False`.
2.4 Fill them in `_parse_instaflights_options`: airline name from the table; cabin
    letter mapped (empty when the chain is absent); `duration_minutes` from
    `ElapsedTime` (0 when absent — degrade, never skip); layover airports from
    `segments[:-1]` arrival codes; `arrives_next_day` from the PT dates already
    computed. Dedup key, timezone skipping, and 3-option cap unchanged.
2.5 Spoken clause (`_spoken_option`): gains the airline name only — "Option one on
    Delta: nonstop, leaves at 8 AM…". Name, never code; no cabin/duration in the
    per-option clause.
2.6 Tests: parser fills every rich field from the mock shapes; missing
    `ElapsedTime`/cabin chain yields defaults with the option still offered;
    connecting itinerary yields the via list; PT-crossing red-eye sets
    `arrives_next_day`; spoken clause contains the airline name and no code/fare
    letters; existing parser tests (dedup, tz-skip) stay green.

## 3. Stamping paths (the Phase 32 wipe guard)

3.1 `concierge._booking_writes`: the flight item's `details` stamp grows the rich
    keys — keep `airline`/`flight_number` byte-identical (Phase 31 exclusion
    identity), add `airline_name`, `cabin`, `duration_minutes`, `layover_airports`,
    `arrives_next_day`, `stops`.
3.2 `repair_tools._rebook_flight`: the `update_flight_fields` `details` payload stamps
    the same key set from the chosen option; `rebooked_from` rides along unchanged in
    shape but gains the original's `airline_name` (from the shared table) so the
    was-line names the old carrier.
3.3 Extract a tiny shared helper (e.g. `flight_options.details_from_option(option)`)
    both call sites use, so the key sets cannot drift — the repair adds
    `rebooked_from` on top.
3.4 Tests: stamping parity — booking stamp and repair re-stamp produce the same
    rich-key set for the same option (the wholesale-`details` wipe guard); a book →
    break → repair walk through the existing mocked-repository fixtures leaves the
    item's `details` carrying rich fields for the NEW flight with `rebooked_from`
    preserved; exclusion identity keys unchanged.

## 4. Concierge surface (agent-facing)

4.1 `search_flights` tool result: after the numbered spoken clauses, append a compact
    per-option reference block the agent can draw on when asked (airline + flight
    number, cabin, duration, stops/via) — clearly framed as reference, not script.
4.2 `BASE_INSTRUCTIONS`: one or two sentences — speak airline names never codes; give
    duration/cabin/connection details only when the traveler asks; keep option
    read-outs to the numbered clauses.
4.3 Tests: tool-result text carries the reference facts; instructions clause present.

## 5. Cascade page + status payload

5.1 Confirm the rich fields reach the status poll: the flight item's `details` now
    carries them (group 3) — verify `GET /v1/itinerary/status/{trip_id}` exposes item
    `details` (or extend the additive `detail` block in `itinerary_ui.py` if it
    doesn't); best-effort, can never break the poll.
5.2 Flight card (`api/assets/cascade/page.html`): headline gains airline name +
    flight number; a facts row renders cabin · nonstop / "1 stop via ORD" · duration ·
    "arrives next day" when true — each part hidden when its field is absent (pre-33
    trips render exactly as today). Was-line treatment unchanged; use
    `rebooked_from.airline_name` when present.
5.3 `_flight_repair_detail` / `_voice_booking_detail` in `itinerary_ui.py`: prefer the
    stamped `airline_name` (fall back to the shared table lookup) — no behavior change
    beyond naming.
5.4 Pending-options candidates panel (same page, `pending_options` block): each
    candidate gains airline name and duration (no codes — the standing rule already
    bans them here).
5.5 Tests: status-payload test showing rich fields on a booked flight item;
    `pending_options` carries `airline_name`/duration. (Page JS stays scripted manual
    QA — the standing no-browser-automation decision.)

## 6. Full-suite pass + evidence

6.1 `docker compose exec -T backend python -m pytest tests/ -q` — bare suite green,
    no new warnings.
6.2 Mock-mode walkthrough on `localhost:1019` per `validation.md` § Manual; capture
    the walkthrough notes into this spec directory (evidence lives here, not the PR
    body — the 2026-07-16 convention).
