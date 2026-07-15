# Plan — Search Hardening (Phase 28)

Branch: `vb/feature/search-hardening`. Spec: `requirements.md` beside this file.

Task groups are independently implementable; 1–4 touch disjoint code paths. Group 5's
cert test is the only live-network piece. Tests land with the group they verify
(existing suite conventions: `backend/tests/test_sabre_instaflights.py` for parser/mock
behavior, `test_sabre_real_client.py`-style respx/monkeypatch fakes for HTTP behavior,
`test_sabre_cert.py` for the fenced live test).

## 1. Parser correctness — all-segment skip + dedupe (`backend/api/concierge.py`)

1. In `_parse_instaflights_options`, replace the endpoints-only zone check with a walk
   of **every** segment: resolve `airport_zone` for each segment's
   `DepartureAirport.LocationCode` *and* `ArrivalAirport.LocationCode`; if any resolves
   `None`, `continue` to the next itinerary. Keep using the first segment's departure
   and last segment's arrival (with their zones) for the spoken/stored times.
2. Add dedupe before numbering: build the candidate's key
   `(first.FlightNumber, first.DepartureDateTime, last.ArrivalDateTime, fare.Amount)`
   and skip the itinerary if the key was already offered (first occurrence wins).
   Numbering (`len(options) + 1`) already stays contiguous.
3. Tests (`test_sabre_instaflights.py`):
   - `test_parser_skips_itinerary_with_unmapped_connection_airport` — first itinerary
     mapped JFK→XXQ→LAX (unmapped connection), second fully mapped; assert the first is
     absent and the second renumbers into slot one (the validation report's named
     missing test).
   - A mapped multi-segment itinerary still parses (guard against over-skipping),
     with stops = segment StopQuantity sum + plane changes.
   - `test_parser_dedupes_identical_itineraries` — two byte-identical itineraries plus
     one distinct; assert two options, contiguous numbering, distinct spoken clauses.

## 2. Mock airport-local times (`backend/api/sabre/mock_client.py`)

1. In `MockSabreClient.instaflights_search`, treat each `_INSTA_VARIANTS` clock as the
   **Pacific-fiction instant** on the requested date: build the datetime in
   `ZoneInfo("America/Los_Angeles")`, then `astimezone(airport_zone(code))` for each
   end — departure in the origin's zone, arrival in the destination's. Serialize
   offset-less (`%Y-%m-%dT%H:%M:%S`), date taken from the converted value (never the
   request string), so the parser's round-trip lands back on the classic PT spread.
2. Unmapped airport code: emit the fiction clock unchanged (the parser skips those
   itineraries; no crash, no fabricated zone).
3. Update any existing mock-path tests that assert the *old* (wrong) parsed times —
   the canonical mock expectation everywhere becomes: first option departs 8 AM PT,
   lands 10:05 AM PT, for **any mapped pair in either direction**.
4. Tests:
   - `test_mock_west_to_east_preserves_pacific_wall_clock_order` (the validation
     report's named missing test) — mock-mode SFO→JFK: every option's parsed arrival
     instant follows its departure, and option one speaks the classic
     "leaves at 8 AM and lands at 10:05 AM".
   - The reverse pair (JFK→SFO or MSP→SFO) parses to the same PT spread — direction
     independence.
   - A mock west-to-east booking write keeps `end_ts > start_ts`
     (the `_booking_writes` regression from criterion 14).

## 3. Real-client honesty — 404 empties + token refresh (`backend/api/sabre/real_client.py`)

1. Confirm the documented no-results body against
   `specs/2026-07-13-sabre-cert-exploration/sabre-cert-notes.md` (and a live probe if
   ambiguous): HTTP 404 carrying `WARN.RAF.APPLICATION` / "No results were found".
2. In `instaflights_search`, catch the 404 `httpx.HTTPStatusError`; **strict match**
   (requirements decision 2): error-code marker first, message fallback. On match,
   return an empty `InstaFlightsResponse`; on any other 404 body, re-raise so the
   dispatcher's mock swap still covers genuine failures.
3. Token refresh in `_get` and `_post`: on a 401 response, clear `self._token`, mint a
   fresh token, retry the request once; a second 401 raises. Keep the change in the two
   helpers so every operation inherits it; `_get_token` keeps its per-instance cache.
4. Tests (hermetic, fake transport/monkeypatched httpx):
   - 404 + documented marker → empty response object, dispatcher **not** consulted for
     a mock, and (at the concierge seam) the agent speaks the existing
     "couldn't find any flights for that day" line — no mock options.
   - 404 with a different body → raises → dispatcher mock-swaps (existing insurance
     intact).
   - 401 once → token cleared, refetched, request retried, result returned; 401 twice
     → raises. Assert exactly one retry.

## 4. Metro-code discipline (`backend/api/concierge.py`)

1. Add the alias map `_METRO_ALIASES = {"NYC": "JFK", "WAS": "IAD", "CHI": "ORD"}`;
   apply to both origin and destination in `search_flights_impl` right after the
   `.strip().upper()` normalization, before the market check.
2. Extend `BASE_INSTRUCTIONS`' guided-flow sentence: airport codes never metro/city
   codes, with the New York → JFK example (one short clause — instructions ride every
   turn).
3. Tests: `search_flights_impl("s", "NYC", "WAS", …)` searches JFK→IAD (assert the
   request the client saw and the market check both used the aliased codes); non-alias
   codes pass through untouched.

## 5. Timezone-table parity (cert-fenced) (`backend/tests/test_sabre_cert.py`)

1. Add a `cert`-marked test: fetch the live supported-markets list
   (`RealSabreClient.supported_markets`), collect every distinct airport code from
   origin and destination sides, assert each resolves via `airport_zone`, failing with
   the list of unmapped codes. Computed dates aren't needed (no travel date), but the
   test follows every other cert convention (credential passthrough via
   `docker compose exec -e`, no secrets in output).
2. If the live run surfaces unmapped codes, add them to `AIRPORT_TZ` (grouped-by-zone
   style) in the same commit — the test defines done.

## 6. Validation & evidence

1. Full hermetic suite green in the container (`docker compose exec -T backend pytest`).
2. Deliberate cert run: `pytest -m cert` with the documented credential passthrough —
   the new parity test plus the existing tripwires all green; note the dated output.
3. Manual mock-mode and (if CERT is reachable) real-mode spot checks per
   `validation.md` § Manual.
4. **PR description carries the evidence** — walkthrough output, cert-run tail, and the
   parity result. Phase 27's definition-of-done failed on an empty PR body; this phase
   does not repeat that.
