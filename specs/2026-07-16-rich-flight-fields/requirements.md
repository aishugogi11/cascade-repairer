# Rich flight fields — requirements (Phase 33)

Pull the `jupyter_notebook/sabre_endpoints.ipynb` `describe_itinerary()` parsing through
to production: the fields the notebook already extracts from InstaFlights itineraries
become part of the `FlightOption`, ride both `details` stamping paths, surface on the
cascade page's flight card, and are available to the Concierge when talking options.

## Scope

**In scope — the full field set** (interview decision: roadmap four + both notebook
extras):

| Field | Source (per itinerary) | FlightOption field | Notes |
|---|---|---|---|
| Airline name | `MarketingAirline.Code` → static table | `airline_name: str` | Static code→name dict, NOT the live `/v1/lists/utilities/airlines` lookup (decision below). Fallback: the bare code. |
| Flight number | `FlightSegment[0].FlightNumber` | *(already carried)* | No change. |
| Cabin | `AirItineraryPricingInfo.FareInfos.FareInfo[0].TPA_Extensions.Cabin.Cabin` → letter map | `cabin: str` (default `""`) | Notebook `CABIN_NAMES` map (Y/S/B/M→Economy, W→Premium Economy, C/J/D/I→Business, F/A/P→First Class). Empty when upstream omits it. |
| Nonstop vs. connecting | segments + `StopQuantity` | *(already carried as `stops`)* | Plus the layover airports below. |
| Total duration | `OriginDestinationOption[0].ElapsedTime` (minutes, whole journey incl. layovers) | `duration_minutes: int` (default `0`) | Display format `Xh Ym`; 0 = unknown (upstream omitted it). |
| Layover airports | `FlightSegment[:-1].ArrivalAirport.LocationCode` | `layover_airports: List[str]` (default `[]`) | "1 stop via ORD". Empty when nonstop. |
| Arrives next day | PT arrive date ≠ PT depart date | `arrives_next_day: bool` (default `False`) | `arrive_date` already exists; the explicit flag makes it showable/speakable without client-side date math. |

**Where the fields go:**

1. **`FlightOption`** (`backend/api/flight_options.py`) — all new fields additive with
   safe defaults, so stored booking payloads (`raw_response.option`) and pre-33
   construction sites stay valid (the `arrive_date` precedent).
2. **Both `details` stamping paths** — the Phase 32 scoping constraint: the repair
   write-back replaces the flight item's `details` JSON **wholesale**
   (`repair_tools._rebook_flight` → `itinerary_items.update_flight_fields`), so every
   rich key must be stamped by BOTH `concierge._booking_writes` (item creation,
   `concierge.py` ~line 450) and the repair write-back (`repair_tools.py` ~line 380) —
   or the first repair wipes it from the card mid-demo.
3. **Cascade page flight card** (`api/assets/cascade/page.html`) — airline name +
   flight number in the headline, a facts row (cabin · nonstop / "1 stop via ORD" ·
   duration · "arrives next day" when true). The Phase 32 `rebooked_from` was-line
   treatment is unchanged.
4. **The Concierge** — spoken option clause gains the airline name only (decision
   below); duration / cabin / layovers are available in the tool result so the agent
   can answer "how long is it?" / "is that economy?" without another search.

**Out of scope:**

- The live airline-name lookup endpoint (`GET /v1/lists/utilities/airlines`) — not
  called, not wired (decision below).
- The booking page (`/v1/demo/`, `/v1/booking/`) — kept-backup surfaces; the cascade
  page is the demo's primary surface and the only page this phase touches.
- Any change to the trip model, booking writes ordering, repair cascade, consent flow,
  exclusion-identity keys (`details.airline` / `details.flight_number` stay exactly as
  Phase 31 defined them), or the never-book-once-booked rule.
- Per-segment spoken breakdowns of connections (the notebook prints each leg; the voice
  surface gets the via-airports summary only).

## Decisions

1. **Airline names resolve from a static table, no live calls** (interview: Static
   table). A code→name dict for the carriers InstaFlights actually returns, falling
   back to the bare code — the `AIRPORT_TZ` pattern. Zero live calls, works in
   `SABRE_MODE=mock`, no new demo-day failure path. **Promote the existing
   `_AIRLINE_NAMES` table in `itinerary_ui.py` (10 US carriers) into
   `flight_options.py` as the single shared source** and have `itinerary_ui` import
   it — no second copy to drift.
2. **Spoken clause gains the airline name only** (interview: Airline name only):
   "Option one on Delta: nonstop, leaves at 8 AM and lands at 11:30 AM, about 214
   dollars." Duration, cabin, and layovers are NOT read per option (3 options per
   turn — length kills the pacing) but ride in the tool result so the agent can answer
   follow-ups. The standing no-codes rule extends: airline *names* are spoken, airline
   *codes* and fare-class letters never are.
3. **Missing upstream fields degrade, never skip.** `ElapsedTime` and the
   `FareInfos → TPA_Extensions → Cabin` chain become *Optional* additions to
   `shapes.py` — a real itinerary missing them still parses and is still offered
   (duration unknown, cabin empty). Contrast with the timezone table: unmappable
   airports still skip the itinerary (correctness of spoken clocks); missing garnish
   fields don't (they're additive color, not correctness).
4. **The mock emits the rich fields deterministically** — `mock_client.
   instaflights_search` gains `ElapsedTime` consistent with its segment clocks and a
   cabin code per itinerary, so the full rich-field path rehearses in mock mode and
   the parser tests don't need CERT.
5. **Stamping-path parity is a tested invariant**, not a convention: a test asserts
   the booking stamp and the repair re-stamp write the same rich-field key set from a
   `FlightOption` (the wholesale-`details` wipe guard). `rebooked_from` additionally
   gains the original's `airline_name` so the was-line can name the old carrier
   without a code lookup at render time.

## Context

- **Tone (standing spoken-copy rules):** speakable strings only from tools; prices
  rounded, no digits-as-labels (option numbers as words), times as "8 AM" / "11:30
  AM" PT, airline names not codes, no fare-class letters. Durations, when the agent
  is asked, speak naturally ("about 5 hours 49 minutes" / "just under six hours" is
  the model's choice — the tool provides `5h 49m`).
- **Stack pointers:** parser + shape work in `backend/api/flight_options.py` and
  `backend/api/sabre/shapes.py` (additive Optional fields only — real CERT responses
  must keep parsing); mock in `backend/api/sabre/mock_client.py`; stamping in
  `backend/api/concierge.py` (`_booking_writes`) and `backend/api/repair_tools.py`
  (`_rebook_flight`); status-payload / detail surface in `backend/api/itinerary_ui.py`;
  page in `backend/api/assets/cascade/page.html` (read per request — no reload needed,
  but `uvicorn --reload` ignores HTML edits either way).
- **Existing patterns to follow:** additive-with-default model fields (`arrive_date`,
  Phase 27); best-effort detail payloads that can never break the poll (Phase 17);
  static lookup tables with bare-code fallback (`AIRPORT_TZ`, `_AIRLINE_NAMES`);
  hermetic tests, GCP mocked at the helper boundary; the `cert` marker fence for
  anything live.
- **No new dependencies.** Pure parsing, stamping, and rendering work — nothing added
  to `requirements.txt`, no new env vars, no deployment surface beyond the normal
  `vb/dev` build.
- **Notebook is reference, not import:** `jupyter_notebook/sabre_endpoints.ipynb`
  cells 4–5 hold the field paths, cabin map, and formatting helpers to port; the
  notebook's live airline lookup and print-based output are deliberately not ported.
