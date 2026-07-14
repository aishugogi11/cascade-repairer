# Plan — Real Sabre Search in the Demo Path (Phase 27)

Task groups in dependency order; each group is independently implementable and testable.
Read `requirements.md` first; endpoint truth lives in
`specs/2026-07-13-sabre-cert-exploration/sabre-cert-notes.md`.

## 1. Shapes & airport-timezone data

1.1 Add InstaFlights models to `backend/api/sabre/shapes.py` under a new
    `# --- flight search: InstaFlights (GET /v1/shop/flights) ---` section, **additive
    only** (BFM classes untouched, including the dead `POS` field):
    `InstaFlightsRequest` (origin, destination, departuredate, onlineitinerariesonly,
    limit — the query-param bag), `FlightSegment` (`DepartureDateTime`,
    `ArrivalDateTime` — offset-less strings, `MarketingAirline.Code`, `FlightNumber`,
    `StopQuantity`), the `OriginDestinationOption` → `AirItinerary` chain,
    `AirItineraryPricingInfo.ItinTotalFare` (amount + currency), and
    `InstaFlightsResponse` rooted at `PricedItineraries`. Model only the fields the
    parser needs; tolerate extra fields.
1.2 Add `SupportedMarketsResponse` for
    `GET /v1/lists/supported/shop/flights/origins-destinations` (origin/destination
    pairs — model the minimal fields needed for a membership check).
1.3 New module `backend/api/sabre/airport_tz.py`: a static `dict[str, str]` mapping
    IATA code → IANA zone for the airports appearing in CERT's supported-markets list
    (majors: JFK, LGA, EWR, BOS, ATL, ORD, DFW, DEN, SEA, SFO, LAX, LAS, PHX, MIA, …),
    plus `airport_zone(code) -> ZoneInfo | None`. Static data in code — no runtime
    lookup, no new dependency.

## 2. Client layer

2.1 `MockSabreClient.instaflights_search(request) -> InstaFlightsResponse`: three
    deterministic itineraries mirroring today's BFM mock semantics (same spread of
    nonstop/one-stop, morning/midday times, price points) so guided-booking behavior in
    mock mode is unchanged in spirit. Times are the existing Pacific wall-clock fiction.
2.2 `RealSabreClient`: add a `_get(path, params)` helper (token handling identical to
    `_post`, including the refetch-on-401 posture) and
    `instaflights_search`, which always merges `onlineitinerariesonly=N` into the params
    (CERT 500s on `Y` — never overridable) and validates the JSON into
    `InstaFlightsResponse`.
2.3 `RealSabreClient.supported_markets()`: lazy fetch of the origins-destinations list,
    cached on the instance (in-process, single-instance demo). Expose through the
    dispatcher as a best-effort helper that returns `None` in mock mode or on any
    failure — callers skip validation on `None`.
2.4 Dispatcher (`client.py`): add `instaflights_search` routing through `_dispatch`
    (per-call mode read, silent mock fallback + warning log — the existing contract,
    for free).

## 3. Concierge wiring

3.1 New parser `_parse_instaflights_options(response, origin, destination) ->
    List[FlightOption]`: walk `PricedItineraries` in response order; for each, resolve
    the first `OriginDestinationOption`'s segments (first segment departure, last
    segment arrival, stops from segment count/StopQuantity); localize
    `DepartureDateTime` with `airport_zone(origin-airport)` and `ArrivalDateTime` with
    the destination airport's zone; convert both to `_PACIFIC`; **skip the itinerary if
    either airport has no zone mapping** and continue to the next; stop at
    `_MAX_SPOKEN_OPTIONS`. Populate `FlightOption` with PT-converted
    `depart_date`/`depart_time`/`arrive_time` and the new additive `arrive_date`;
    build `spoken` via the existing `_spoken_option` (contract unchanged — no airline
    codes, rounded price).
3.2 Add `arrive_date: str` to `FlightOption` (default = `depart_date` so existing mock
    construction sites and stored payloads stay valid) and teach `_booking_writes` to
    build `end_ts` from `arrive_date` — a converted red-eye must not produce
    `end_ts < start_ts`.
3.3 Switch `search_flights_impl` from `sabre_client.flight_search` (BFM) to
    `sabre_client.instaflights_search`, request built from origin/destination/
    depart_date. Keep every existing speakable failure path; the blanket
    `except` → `_SEARCH_ERROR_LINE` stays.
3.4 Supported-markets check in `search_flights_impl`, before the search call: if the
    dispatcher's markets helper returns a list and the pair is absent, return the new
    speakable redirect line (suggest a known-good pair, e.g. "something like San
    Francisco to New York"); on `None` (mock mode / fetch failure) proceed without
    validation.
3.5 Confirm `pending_options_for_trip` needs no change (shape untouched; times now
    arrive PT-converted upstream) — the booking-page half of the interview scope.
    `repair_tools.py`'s two `flight_search` calls stay exactly as they are.

## 4. Tests (hermetic — no network, no credentials)

4.1 Fixture: a captured-shape InstaFlights response (computed future dates, never
    literals) with ≥3 itineraries including one red-eye (arrival crosses the PT date
    line) and one itinerary touching an unmapped airport.
4.2 Shapes/parser tests: response validates; parser converts `07:20` JFK-local to
    `04:20` PT; red-eye yields `arrive_date` ≠ `depart_date` and `_booking_writes`
    produces `end_ts > start_ts`; unmapped-airport itinerary is skipped in favor of the
    next; spoken clauses contain no airline codes and rounded prices.
4.3 Real-client contract tests (mocked transport, the `test_sabre_client.py` pattern):
    `instaflights_search` always sends `onlineitinerariesonly=N` even if the request
    says otherwise; `_get` sends the Bearer token.
4.4 Dispatcher/fallback tests: `SABRE_MODE=real` with a raising real client serves mock
    options for that call and logs the warning; `SABRE_MODE=mock` never touches the
    real client.
4.5 Concierge-flow tests: `search_flights_impl` end-to-end on the mock returns the
    speakable summary and populates `_SESSION_FLIGHT_OPTIONS`/`_LATEST_SEARCH`;
    unsupported-market pair (markets helper stubbed) returns the redirect line and
    performs no search; `pending_options_for_trip` payload shape is byte-for-byte the
    Phase 21 contract.
4.6 Full suite green: `docker compose exec -T backend pytest` (existing guided-booking
    tests keep passing against the InstaFlights mock).

## 5. Live verification (deliberate, credentialed — not CI)

5.1 Add a `cert`-marked test to `backend/tests/test_sabre_cert.py`: real
    `instaflights_search` against CERT returns ≥1 priced itinerary for a supported
    pair with a computed future date, and every parsed option carries a mappable
    airport pair. Run via the documented `docker compose exec -e` credential
    passthrough.
5.2 Local real-mode rehearsal through the no-quota seam: `SABRE_MODE=real` + the env
    bridge (Phase 25 notes) in the container, then curl `POST /v1/web_call/query`
    driving search → book; confirm real airlines/fares spoken, booking rows still mock,
    booking page candidates panel shows the real options with PT labels.
5.3 No Cloud Run flip in this phase's tasks — record in the PR description that the
    flip is `--update-env-vars SABRE_MODE=real,SABRE_BASE_URL=…,SABRE_CLIENT_SECRET=…`
    per the Phase 25 recipe (an operator action for rehearsal/event day).
