# Requirements — Real repair data: the cascade re-shops InstaFlights (Phase 29)

The demo's credibility pivot (decision 2026-07-14: no mock data in the demo path;
no Sabre unlock coming). When the flight breaks, the repair must speak **real
replacement flights**: swap the flight-repair search from BFM (`flight_search` —
content-empty on this PCC, always mock-swaps) to the Phase 27 `instaflights_search`
dispatcher op, pick a real alternative, and carry the chosen option + alternatives
into the booking row so the booking page's `detail` panel shows real why-chosen /
price-delta. PNR writes stay mock (entitlement wall — permanent posture).

## Scope

### In scope

| # | Change | File(s) |
|---|--------|---------|
| 1 | **Extract the InstaFlights parser + `FlightOption`** into a shared module both `concierge` and `repair_tools` can import (a direct import would cycle — see Decisions §1) | new `backend/api/flight_options.py`; `backend/api/concierge.py` re-exports |
| 2 | **Real re-shop in `_rebook_flight`**: call `instaflights_search` for the broken route/date, parse into options, pick a real alternative (Decisions §2) | `backend/api/repair_tools.py` |
| 3 | **Mock-swap fallback on empty** re-shop, with a logged warning (Decisions §3) | `backend/api/repair_tools.py` |
| 4 | **Rebook the chosen real flight** (its airline/number/time drive the mock `rebook_flight` create) and write an enriched `raw_response` (Decisions §4) | `backend/api/repair_tools.py` |
| 5 | **Real `detail` for repaired flights**: a `flight_repair` source + a new detail builder speaking a repair-appropriate why-chosen and `price_delta = new − original fare` | `backend/api/itinerary_ui.py` |
| 6 | **Pass the original flight's fare + arrival + flight number** from the broken item into `_rebook_flight` so selection and price-delta are real | `backend/api/sabre_tools.py` (`_repair_call`) |
| 7 | Tests (hermetic, mock mode) for all of the above | `backend/tests/` |

### `flight_repair` raw_response shape (drives the detail panel)

```
{
  "source": "flight_repair",
  "option": { ...chosen FlightOption.model_dump()... },
  "alternatives": [ ...the other parsed options... ],
  "original_price": <float>,      # the cancelled flight's fare
  "original_currency": <str>,
  "from_mock_fallback": <bool>,   # true when the real re-shop was empty
  "rebooked": { ...mock rebook_flight payload, unchanged... }
}
```

`_item_detail` (itinerary_ui) dispatches on `source == "flight_repair"` to:
- **why_chosen** — e.g. *"Rebooked on Delta 2412, landing 3:10 PM — the closest available arrival to your original flight."* (nonstop/one-stop phrasing reused from `_voice_booking_detail`).
- **price_delta** — `new option price − original_price`, rendered `+$NN` / `$0` (same threshold rule as the voice path); a *cheaper* rebooking may show `-$NN` (a repair can legitimately drop the fare) — confirm rendering in Decisions §4.
- **impact** — the existing `_REPAIR_IMPACT["flight"]` line (unchanged).

### Not included

- **PNR writes stay mock** — `rebook_flight` (cancel + create) remains the mock
  client; the entitlement wall is permanent. Only the *search* becomes real.
- **Hotel / ground / dining / experience repairs stay category mocks** — unchanged
  scope; the flight is the beat judges hear.
- **The guided-booking path** (`search_flights_impl` → `book_flight_impl`) is
  behaviorally unchanged — task 1 is a pure extract-and-re-export refactor that must
  keep every Phase 27/28/30 test green.
- **`_LATEST_SEARCH` age-expiry** — that's Phase 22, not here.
- No new dependency, endpoint, page, or schema change.

## Decisions

1. **Extract the parser to a shared module (required, not stylistic).** `concierge`
   imports `sabre_tools` (`launch_trip_repairs`), `sabre_tools` imports `repair_tools`
   — so `repair_tools` importing `concierge` for `_parse_instaflights_options` /
   `FlightOption` would create a cycle (`repair_tools → concierge → sabre_tools →
   repair_tools`). Move `FlightOption`, `_parse_instaflights_options`, `_spoken_option`,
   `_MAX_SPOKEN_OPTIONS`, and the `_PACIFIC` constant into `backend/api/flight_options.py`
   (imports only `sabre.shapes`, `sabre.airport_tz`, pydantic, datetime — no cycle).
   `concierge` re-exports them (`from api.flight_options import FlightOption,
   _parse_instaflights_options`) so `concierge.FlightOption` and all existing test
   references keep resolving.
2. **Selection: different flight #, closest arrival** (user, interview). Parse the real
   options; exclude any whose `(airline, flight_number)` matches the cancelled flight's
   (best-effort — "where possible" per the roadmap; if the cancelled number is unknown or
   excluding leaves none, don't exclude); among the remainder pick the option whose PT
   arrival is **closest to the original flight's arrival time** (protects downstream
   hotel/ground timing). Store all parsed options as `alternatives`.
3. **Mock-swap fallback on empty, with a warning** (user, interview). The dispatcher
   does **not** mock-swap on the documented honest-empty 404 (Phase 28) — it returns an
   empty response — so `_rebook_flight` must handle empty explicitly: if the real re-shop
   yields zero options, call the **mock** client directly for the same route/date, set
   `from_mock_fallback: true`, and `logger.warning` naming the route so the 60-second
   cascade never stalls. The morning-smoke (Phase 24) probes the scripted repair route to
   keep it real on demo day. Judges see the same cascade either way.
4. **New `flight_repair` source; price-delta vs the original fare** (user, interview). Do
   not reuse the `voice_guided_booking` shape — its copy says "picked by voice" (wrong for
   an automatic repair) and its delta is vs the cheapest offered, not the meaningful
   number. A repair that finds a cheaper fare renders a negative delta (`-$NN`); `$0`
   inside the ±$0.50 threshold.

## Context

- **Tone:** the new why-chosen copy stays warm, speakable, and jargon-free (the standing
  rule) — names the airline + flight and the arrival time, never API/mock/sandbox terms.
  The web page ignores `detail`; it feeds the iOS recommendation sheet and the booking
  page's panel.
- **Timezone discipline (standing rule):** reuse the extracted parser's Pacific
  conversion verbatim — real InstaFlights times are offset-less airport-local and are
  converted to PT before anything is stored (the Phase 19/27 discipline). No new
  time-handling code.
- **Demo-scripting reality (2026-07-15 replan):** the cached menu has decayed to
  essentially one reliable anchor (**JFK→LAX**, held +2…+30 on 2026-07-15); the demo trip
  must book a morning-verified pair whose **repair re-shop route is also cached** (Phase 29
  re-shops the broken flight's own route). This is a runbook/morning-smoke concern, not
  code — but the mock-swap fallback (§3) is the safety net if it drifts.
- **Stack pointers:** `_rebook_flight`, `_write_booking`, `_latest_sabre_ref`
  (`repair_tools.py`); `_parse_instaflights_options` / `FlightOption` / `_spoken_option`
  (`concierge.py`, moving to `flight_options.py`); `instaflights_search` dispatcher +
  `mock_client.instaflights_search` (three deterministic itineraries); `_item_detail` /
  `_voice_booking_detail` / `_REPAIR_IMPACT` (`itinerary_ui.py`); `_repair_call`
  (`sabre_tools.py`).
- **Existing patterns to follow:** tests hermetic (no creds/network; mock client or mocked
  transport), computed travel dates never literals (the Phase 26 rule), every repair-tool
  failure still raises on a failed/0-row write (the standing rule — the mock-swap fallback
  must still produce a real booking write).
- **Process lesson carried from Phase 30 (DoD-B):** PR evidence — the cert-run and mock
  walkthrough transcripts — must be in the PR description **pre-merge**, not prose claims.
