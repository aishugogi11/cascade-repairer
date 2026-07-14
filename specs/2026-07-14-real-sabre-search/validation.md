# Validation — Real Sabre Search in the Demo Path (Phase 27)

## Automated

Run inside the container (`docker compose exec -T backend pytest`, the standing
local-testing path). The bare suite must stay hermetic: no network, no Sabre env vars,
`cert`-marked tests deselected by `pytest.ini` `addopts`.

Specific assertions that must exist and pass:

- **Suite green, hermetically.** All pre-existing tests (guided booking, pending_options,
  repair tools, dispatcher) pass unchanged or with mock-shape-only updates.
- **`onlineitinerariesonly=N` is unconditional**: the real client's InstaFlights request
  carries `onlineitinerariesonly=N` regardless of what the request object says
  (`Y` = CERT 500, verified-live Phase 25).
- **Pacific conversion is real conversion**: an offset-less `2026-XX-XXT07:20:00`
  departure at a mapped Eastern airport parses to `04:20` PT in `FlightOption` — not
  `07:20` mis-declared Pacific (the Phase 19 bug class). Computed dates only, no literal
  travel dates anywhere in tests or fixtures.
- **Red-eye day shift**: an itinerary whose PT arrival lands the next calendar day yields
  `arrive_date != depart_date`, and `_booking_writes` produces `end_ts > start_ts`.
- **Unmapped airport is skipped, not mangled**: an itinerary touching an airport absent
  from the timezone table never appears in the options; the next itinerary takes its
  slot; all-unmappable yields the existing "couldn't find any flights" line.
- **Silent per-call fallback**: `SABRE_MODE=real` with a raising real client returns mock
  options for that call and logs a warning naming `instaflights_search`; the speakable
  reply contains no mention of the failure. `SABRE_MODE=mock` never constructs a real
  request.
- **Unsupported market fails speakably**: with the markets helper stubbed to a list not
  containing the pair, `search_flights_impl` returns the redirect line and makes no
  search call; with the helper returning `None`, the search proceeds.
- **Speakable-options contract invariant**: spoken summary has ≤3 options, option numbers
  as words, rounded whole-dollar prices, 12-hour times, and no airline codes anywhere in
  `spoken`.
- **`pending_options` shape unchanged**: the status endpoint's block still carries exactly
  `recorded_at` + `options[]` of `option_number`/`route`/`depart_date`/`depart_time`/
  `arrive_time`/`stops`/`price` (the Phase 21 contract the booking page consumes).
- **Scope discipline in the diff**: BFM classes in `shapes.py` untouched
  (`git diff vb/dev -- backend/api/sabre/shapes.py` shows additive-only changes);
  `repair_tools.py` still calls `sabre_client.flight_search` in both places; no raw
  credential or CERT token material anywhere in `git diff vb/dev...HEAD`.

## Manual

- **Credentialed live check** (implementation day): the new `cert`-marked InstaFlights
  test passes via the documented `docker compose exec -e` credential passthrough —
  ≥1 real priced itinerary for a supported pair on a computed future date.
- **Real-mode walkthrough, no call quota**: with `SABRE_MODE=real` + the env bridge in
  the local container, drive `POST /v1/web_call/query` (curl, the standing rehearsal
  seam) through "find me a flight from San Francisco to New York in three weeks" →
  "book option one" → "complete my trip":
  - The options spoken are real (recognizably real fares/times that change between
    runs), with no airline codes in the reply text.
  - `GET /v1/booking/` shows the same options in the AI Recommended panel, times
    labeled PT, before booking; the panel clears after booking (slot cleared).
  - Booking still writes mock rows (trip + flight item + booking with
    `voice_guided_booking` raw_response); the itinerary page poll shows the trip.
- **Edge cases by voice**: an unsupported route gets the speakable redirect (and no
  crash); an invalid/garbled city still gets the existing "I need the destination…"
  line; killing network mid-conversation (or unsetting the env bridge) silently serves
  mock options on the next search with a warning in the logs.
- **Mock mode regression**: with `SABRE_MODE` unset, the full guided-booking walkthrough
  behaves exactly as before this phase (deterministic three options).

## Tone check

New user-facing copy (the unsupported-market redirect, any adjusted search lines) reads
in the existing register: short, warm, speakable — no IATA/airline codes, no "API",
"sandbox" is acceptable only if phrased as "the demo system", prices as "about 320
dollars", option numbers as words. Read each new line aloud once.

## Definition of done

- All automated assertions above exist as tests and pass in the bare container run.
- The credentialed live check and the real-mode walkthrough both succeeded on the
  implementation day, evidenced in the PR description (spoken transcript snippet +
  booking-page screenshot or equivalent).
- Mock-mode regression walkthrough clean.
- Roadmap Phase 27 heading marked `[x] COMPLETE` (the sanctioned status-only edit) at
  merge time.
- The Cloud Run flip recipe is referenced (not executed) in the PR description.
