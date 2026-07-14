# Requirements — Real Sabre Search in the Demo Path (Phase 27)

Branch: `vb/feature/real-sabre-search`. Roadmap: Phase 27.

Judges hear **real airlines, real fares, real routes** while booking stays mock (the
`createBooking` entitlement wall — see `specs/2026-07-13-sabre-cert-exploration/sabre-cert-notes.md`).
The voice agent's flight search moves from the empty-on-this-PCC Bargain Finder Max v5
to **InstaFlights** (`GET /v1/shop/flights`) when `SABRE_MODE=real`.

## Scope

### In scope

- **Voice search path**: `search_flights_impl` (`backend/api/concierge.py`) sources its
  options from InstaFlights via the existing per-call dispatcher (`backend/api/sabre/client.py`).
  A new dispatcher operation `instaflights_search` routes real vs mock per call, keeping the
  silent per-call mock fallback and warning log exactly as `flight_search` has today.
- **Booking page candidates** (interview decision): the "AI Recommended" panel on
  `GET /v1/booking/` shows the real options. This rides for free on the existing
  `pending_options` bridge — `search_flights_impl` writes `_LATEST_SEARCH`, the status
  endpoint surfaces it — so the requirement is to **verify** real options flow through with
  correct PT times, not to build new wiring. The `pending_options` payload shape is unchanged.
- **Additive InstaFlights shapes** in `backend/api/sabre/shapes.py`: request (query params)
  and response (`PricedItineraries[].AirItinerary.OriginDestinationOptions
  .OriginDestinationOption[].FlightSegment[]`, `AirItineraryPricingInfo.ItinTotalFare`),
  plus the supported-markets list response
  (`GET /v1/lists/supported/shop/flights/origins-destinations`).
- **Mock InstaFlights**: `MockSabreClient.instaflights_search` returns three deterministic
  InstaFlights-shaped itineraries carrying the same semantic content as today's BFM mock
  (times, prices, stops), so the guided-booking flow and its tests keep working in
  `SABRE_MODE=mock`.
- **Real client GET support**: `RealSabreClient` gains a `_get` helper (it only has `_post`)
  and `instaflights_search`, which **always sends `onlineitinerariesonly=N`**
  (`Y` triggers a CERT-side 500 — verified-live, Phase 25 notes).
- **Airport-local → Pacific time conversion** (interview decision — see Decisions).
- **Supported-markets validation**: best-effort city-pair check so the agent can fail
  speakably on routes CERT doesn't carry (see Decisions).

### Out of scope

- **BFM v5 stays untouched**: its shapes (including the known dead-`POS`-field bug), the
  `flight_search` dispatcher operation, and the real client's `/v5/offers/shop` call all
  remain as-is — they are the conditional Phase 24 punch list. `search_flights_impl` simply
  stops calling `flight_search`.
- **Repair tools keep the mock path**: `repair_tools.py` calls `sabre_client.flight_search`
  in two places; both stay on BFM (mock in practice). Real repair/booking is the Phase 24
  event-day ask.
- **Booking stays mock**: `book_flight_impl` and everything downstream (trips/items/bookings
  writes) are unchanged. Real InstaFlights options get booked as mock rows — that is the
  demo posture.
- **`_LATEST_SEARCH` expiry**: the stale-candidates hardening rides with Phase 22, not here.
- **BFM offset-bearing time conversion**: the `06:15:00-05:00` variant is Phase 24
  conditional work; this phase handles only InstaFlights' offset-less variant.
- The demo page (`/v1/demo/`) outbound-call beats — no change to what they seed or speak.

### Data shape

`FlightOption` (concierge) stays the internal currency. Additive changes only:

| Field | Change |
|---|---|
| `depart_date`, `depart_time`, `arrive_time` | Now hold **Pacific-converted** values in real mode (mock values are already Pacific fiction) |
| `arrive_date` (new, additive) | PT arrival date — a converted red-eye can land on a different PT day than it departs; `_booking_writes` must build `end_ts` from it so `end_ts` can never precede `start_ts` |

## Decisions

1. **Call-path scope — voice + booking page** (interview): both surfaces flip together
   because they share one data source; no separate booking-page wiring is built. The demo
   page and repair flows are untouched.
2. **Time handling — convert to Pacific** (interview): InstaFlights `DepartureDateTime`
   is offset-less airport-local (`2026-08-13T07:20:00` = 7:20 AM *at that airport*).
   Speaking or storing it as Pacific unconverted repeats the Phase 19 bug class. So: a
   small static IATA → IANA timezone table (new module under `backend/api/sabre/`) covers
   the airports in CERT's supported-markets list; each segment time is localized to its
   airport's zone, converted to `America/Los_Angeles`, and only then spoken/stored —
   honoring the standing rule (tech-stack § Data): *the database stores UTC; the edges
   speak Pacific*. Departure times use the origin airport's zone, arrival times the
   destination's. **Unknown airport → skip that itinerary** and take the next one; if all
   candidates are unmappable, the existing "couldn't find any flights" speakable line is
   the honest answer. Spoken copy keeps its current shape (no "PT" suffix in the voice
   clause — every time the agent has ever spoken is Pacific by discipline; the booking
   page already labels PT).
3. **Failure fallback — silent per-call mock swap** (interview): a real-mode InstaFlights
   failure (500, timeout, credential reset, shape mismatch) logs a warning naming the
   operation and serves mock options for that call, exactly the existing `_dispatch`
   contract. The agent never mentions it. Judges listening live never hear an apology for
   Sabre's sandbox.
4. **Unsupported market ≠ failure**: an origin/destination pair absent from the
   supported-markets list in real mode gets a **speakable redirect** ("I couldn't search
   that route in the demo sandbox — want to try …") rather than a silent mock swap — an
   honest answer, not an error (roadmap: "fail speakably"). The markets list is fetched
   lazily and cached in-process (single-instance demo, the standing pattern); if the fetch
   itself fails, validation is skipped and the search proceeds — best-effort only. Mock
   mode never validates markets.
5. **Dispatcher operation, not a mode branch in concierge**: `search_flights_impl` always
   calls `sabre_client.instaflights_search`; mock/real routing and per-call fallback stay
   the dispatcher's job. No `SABRE_MODE` reads in `concierge.py`.
6. **Speakable-options contract is invariant**: top 2–3 options, prices rounded, option
   numbers as words, 12-hour clock, **no airline codes spoken**. The airline lands in
   `FlightOption.airline` for the booking rows, never in `spoken`.

## Context

- **Constitution pointers**: `specs/mission.md` (Cascade Repairer demo, July 18),
  `specs/tech-stack.md` § Backend (Sabre client layer, `SABRE_MODE` per-call dispatch),
  § Data (timezone discipline). Endpoint truth:
  `specs/2026-07-13-sabre-cert-exploration/sabre-cert-notes.md` (InstaFlights caveats,
  env bridge, response root, delta #5).
- **Tone**: all failure paths in concierge tools return speakable strings — a raising tool
  kills the spoken turn (standing rule). New copy matches the existing register: short,
  warm, no jargon, no codes, dates as "July 17th", times as "7:20 AM".
- **Stack limits**: no new dependencies — `httpx`, pydantic, and `zoneinfo` cover
  everything. Tests stay hermetic (no network, no credentials, `cert`-marked live tests
  deselected by default). The airport-timezone table is static data in code, not a
  runtime lookup service.
- **The Cloud Run flip is config, not code**: after this phase, real search is
  `SABRE_MODE=real` + `SABRE_BASE_URL` + `SABRE_CLIENT_SECRET` via `--update-env-vars`
  (recipe: Phase 25 notes § Phase 24 env bridge). Nothing in this phase hardcodes CERT
  URLs or credentials.
- **Existing patterns to follow**: additive response blocks that can never break a poll
  (`detail`, `pending_options` precedents); `_dispatch`'s blanket-except fallback;
  deterministic mock data (`mock_client.py`); computed travel dates in tests, never
  literals (Phase 26 rule).
