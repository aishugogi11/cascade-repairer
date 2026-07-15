# Validation — Real repair data: the cascade re-shops InstaFlights (Phase 29)

## Automated

Full bare-container suite (the artifact CI runs):

```
docker compose build backend
docker run --rm hackathon-vocal-bridge-backend python -m pytest tests/ -q
```

**Assertions that must exist and pass in the bare-container run:**

1. **Suite green, no new warnings.** All tests pass; the only warnings are the allowed
   baseline (one Starlette deprecation + the six pre-existing unawaited-coroutine
   `RuntimeWarning`s). No phase-introduced warnings.
2. **Refactor is behavior-neutral.** The entire Phase 27/28/30 InstaFlights + concierge
   suite passes unchanged after the extract, and `concierge.FlightOption is
   flight_options.FlightOption` (re-export identity holds). `flight_options.py` imports no
   `concierge`/`sabre_tools`/`repair_tools` (no cycle) — verifiable by import.
3. **Real re-shop wires InstaFlights.** In `SABRE_MODE=mock`, `_rebook_flight` produces a
   booking whose `raw_response.source == "flight_repair"`, `option` is a parsed itinerary
   (real InstaFlights shape), `alternatives` is non-empty, and the item flips to `fixed`.
   No BFM `flight_search` call remains in the flight-repair path.
4. **Selection: different flight, closest arrival.** `_pick_replacement` excludes the
   cancelled `(airline, flight_number)` when alternatives allow, returns the option whose
   PT arrival is nearest the original arrival, and tolerates `cancelled_flight=None` and
   the all-same-number case (falls back to closest-arrival over all).
5. **Empty → mock fallback, never a stall.** With the real client's `instaflights_search`
   stubbed to `PricedItineraries=[]`, the repair falls back to the mock, sets
   `from_mock_fallback=True`, logs a warning naming the route, and **still writes a booking
   row and flips the item to `fixed`** (a failed/0-row write still raises — the standing
   rule).
6. **Real, signed price-delta.** `_flight_repair_detail` computes `price_delta =
   option.price − original_price`: a costlier rebook renders `+$NN`, within ±$0.50 renders
   `$0`, and a cheaper rebook renders `-$NN`. `_item_detail` routes a `flight_repair`
   booking to this builder (not the static `_REPAIR_WHY` fallback).
7. **Computed dates only.** No literal travel date in any test/fixture added by this phase.

## Manual

8. **Mock-mode cascade walkthrough.** In an ephemeral container (mock mode), seed a trip,
   break the flight, run the repair; confirm the flight card flips broken → repairing →
   fixed and the `GET /v1/itinerary/status/{trip_id}` `detail` for the flight shows a real
   why-chosen (names a flight + arrival) and a numeric price-delta — not the static
   "Rebooked automatically…" copy. Capture the status JSON.
9. **Live CERT repair on the demo anchor.** With `SABRE_MODE=real` and credentials, run the
   repair for **JFK→LAX** (the 2026-07-15 verified anchor) at a near-term cached date;
   confirm the chosen replacement is a **real** flight (real airline/number/fare), differs
   from the cancelled flight where the cache allows, `from_mock_fallback=False`, and the
   `detail` price-delta reflects the real fares. Capture the output.
10. **Empty-route fallback observed live.** Point the repair at a route/date known to be
    cache-empty; confirm the cascade still completes (mock fallback), the warning is
    logged, and `from_mock_fallback=True` — the demo never dead-ends on drift.

## Tone check

11. The new `_flight_repair_detail` why-chosen copy is warm and speakable, names the
    airline + flight + arrival time, and contains no API/mock/sandbox jargon. No other
    user-facing copy changed.

## Definition of done

- **A.** Every automated assertion (§1–7) exists and passes in the bare-container run.
- **B.** The mock walkthrough (§8) and the live CERT repair (§9) are evidenced in the PR
  description with **transcript/output snippets pasted before merge** — not prose claims
  (the Phase 30 DoD-B lesson).
- **C.** PNR writes remain mock (no real `createBooking`); only the *search* is real. The
  entitlement posture is unchanged.
- **D.** Hotel/ground/dining/experience repairs are untouched; the guided-booking path is
  behaviorally unchanged (§2 refactor is neutral).
- **E.** Phase 29 is marked `[x] COMPLETE` in `specs/roadmap.md`.
