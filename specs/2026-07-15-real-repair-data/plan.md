# Plan — Real repair data: the cascade re-shops InstaFlights (Phase 29)

Five task groups. Group 1 is a pure refactor that must land green before anything
builds on it (the Phase 26/30 precedent — a clean base first). Groups 2–4 are the
real-repair change in `repair_tools.py` + `itinerary_ui.py`. Group 5 is tests.

## 1. Extract the shared flight-options module (refactor — no behavior change)

Target: new `backend/api/flight_options.py`; edit `backend/api/concierge.py`.

1.1. Create `backend/api/flight_options.py`. Move, verbatim, from `concierge.py`:
     `FlightOption` (the pydantic model + its `_arrive_date_defaults_to_depart_date`
     validator), `_parse_instaflights_options`, `_spoken_option`, `_MAX_SPOKEN_OPTIONS`,
     and the `_PACIFIC` constant. Imports in the new module: `datetime`, `ZoneInfo`,
     pydantic, `api.sabre.shapes`, `api.sabre.airport_tz.airport_zone`. Confirm no import
     of `concierge`/`sabre_tools`/`repair_tools` (no cycle).
1.2. In `concierge.py`, replace the moved definitions with
     `from api.flight_options import (FlightOption, _parse_instaflights_options,
     _spoken_option, _MAX_SPOKEN_OPTIONS, _PACIFIC)` — a re-export so `concierge.FlightOption`
     etc. still resolve for every existing caller and test. Keep `concierge`'s own
     `_PACIFIC` users pointing at the re-exported constant (or leave concierge's local
     `_PACIFIC` if it has other Pacific users — whichever avoids a duplicate; verify the
     guided-booking timestamps are unchanged).
1.3. Run the full suite — Phase 27/28/30 tests (`test_sabre_instaflights.py`, concierge
     tests) must pass unchanged. This group is done only when the suite is green with zero
     behavior diff.

## 2. Real re-shop in `_rebook_flight`

Target: `backend/api/repair_tools.py`.

2.1. Add params to `_rebook_flight` for the original flight's context, supplied by the
     caller (group 4): `original_price: float`, `original_currency: str`,
     `original_arrive_time: Optional[str]` (HH:MM PT), `cancelled_flight: Optional[tuple]`
     (airline, flight_number) — all best-effort/optional so the walkthrough endpoint and
     tests can omit them.
2.2. Replace the BFM `flight_search(...)` block with
     `await sabre_client.instaflights_search(shapes.InstaFlightsRequest(origin=...,
     destination=..., departuredate=departure_date))`, then
     `options = flight_options._parse_instaflights_options(search, origin, destination)`.
2.3. **Empty → mock fallback** (Decisions §3): if `not options`, call the mock client
     directly (`from api.sabre.mock_client import MockSabreClient` — instantiate or reuse a
     module singleton) for the same request, re-parse, set a `from_mock_fallback = True`
     flag, and `logger.warning("flight repair re-shop empty for %s-%s %s; using mock",
     origin, destination, departure_date)`. If the real parse succeeded,
     `from_mock_fallback = False`.
2.4. **Selection** (Decisions §2): a helper `_pick_replacement(options, cancelled_flight,
     original_arrive_time)` — drop options whose `(airline, flight_number)` equals
     `cancelled_flight` (skip this filter if it empties the list or the arg is None); of
     what remains, return the option minimizing `abs(arrive_pt − original_arrive_time)`
     (parse `arrive_time`/`arrive_date` to a PT datetime; if `original_arrive_time` is
     None, take option 1). Keep the full parsed list as `alternatives`.

## 3. Rebook the chosen real flight + enriched raw_response

Target: `backend/api/repair_tools.py`.

3.1. Build the mock `rebook_flight` (cancel + create) from the **chosen option's** real
     fields — `flightNumber=chosen.flight_number`, `airlineCode=chosen.airline`,
     `fromAirportCode=origin`, `toAirportCode=destination`,
     `departureDate=chosen.depart_date`, `departureTime=chosen.depart_time` — replacing the
     BFM `schedule.*` sources. The create stays the mock client (PNR write stays mock).
3.2. Assemble the `flight_repair` raw_response (requirements § shape):
     `source="flight_repair"`, `option=chosen.model_dump()`,
     `alternatives=[o.model_dump() for o in options if o is not chosen]`,
     `original_price`, `original_currency`, `from_mock_fallback`, and `rebooked=<mock
     payload>`. Pass it to `_write_booking` (unchanged — still raises on failed/0-row
     write, the standing rule).
3.3. Return dict: keep the existing keys but source `price`/`currency`/`flight_number`/
     `airline`/`departure_*` from the **chosen option** (real), and add
     `from_mock_fallback` and `price_delta = chosen.price − original_price` for the event
     log / callers.

## 4. Real `detail` for repaired flights

Target: `backend/api/itinerary_ui.py`, `backend/api/sabre_tools.py`.

4.1. In `sabre_tools.py` `_repair_call`, for the flight branch pass the broken item's
     context into `_rebook_flight`: `original_price=item.price`,
     `original_currency=item.currency`, `original_arrive_time=<HH:MM PT from item.end_ts>`,
     and `cancelled_flight` derived best-effort from the item's latest booking (None if
     unavailable — the selection filter tolerates it).
4.2. In `itinerary_ui.py`, add `_flight_repair_detail(raw: dict) -> dict`: read
     `option`/`alternatives`/`original_price`; `why_chosen` names airline + flight number
     + arrival time (reuse the nonstop/one-stop phrasing helper from
     `_voice_booking_detail`); `price_delta = option.price − original_price` rendered
     `+$NN` / `$0` / `-$NN` (±$0.50 threshold); `impact = _REPAIR_IMPACT["flight"]`.
4.3. In `_item_detail`, dispatch `raw.get("source") == "flight_repair"` →
     `_flight_repair_detail(raw)` **before** the generic repair fallback. Leave the
     `voice_guided_booking`, `seeded`, and static-repair branches untouched.

## 5. Tests (hermetic, mock mode)

Target: `backend/tests/`.

5.1. **Extract refactor:** a smoke test that `from api.flight_options import FlightOption,
     _parse_instaflights_options` works and `concierge.FlightOption is
     flight_options.FlightOption` (re-export identity). The existing
     `test_sabre_instaflights.py` suite passing is the main guard.
5.2. **Real re-shop (mock mode):** `_rebook_flight` in `SABRE_MODE=mock` writes a
     `flight_repair` booking whose `option` is a parsed mock itinerary, `alternatives`
     non-empty, and the item flips to `fixed` (repositories mocked/captured). Assert the
     chosen flight number differs from a supplied `cancelled_flight` when alternatives
     allow.
5.3. **Selection:** `_pick_replacement` picks the closest-arrival option, excludes the
     cancelled flight number, and tolerates `cancelled_flight=None` and the
     all-same-number edge (falls back to closest-arrival over all).
5.4. **Empty → mock fallback:** stub the real client's `instaflights_search` to return
     `InstaFlightsResponse(PricedItineraries=[])`; assert the mock is used,
     `from_mock_fallback` is True, the warning is logged, and a booking row is still
     written (cascade never stalls).
5.5. **Detail panel:** `_flight_repair_detail` produces real why-chosen naming the flight,
     a correct signed `price_delta` vs `original_price` (a cheaper rebook renders `-$NN`),
     and the flight impact line; `_item_detail` routes a `flight_repair` booking to it.
5.6. Computed dates only (no literals); no new unawaited-coroutine warnings.
