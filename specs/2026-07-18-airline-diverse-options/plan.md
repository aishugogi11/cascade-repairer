# Phase 41 — Airline-diverse flight options: Plan

Groups are independently implementable in order; each ends with the suite green.

## 1. Parser pool parameter (`backend/api/flight_options.py`)

1. Add `max_options: int = _MAX_SPOKEN_OPTIONS` to
   `_parse_instaflights_options` and use it in place of the hardcoded cap.
   Default preserves today's behavior for every existing caller — the repair
   path (`repair_tools.py` lines ~278/293) stays byte-identical without edits.
2. No other parser changes: dedupe, timezone-skip, rich fields, and parse-time
   numbering (1..N over the pool) are untouched.

## 2. Airline-diversity selection (`backend/api/flight_options.py`)

1. New helper `select_airline_diverse(options, max_airlines=3) ->
   List[FlightOption]`:
   - Group the pool by `airline` (the code — the Phase 31 exclusion identity;
     `airline_name` is garnish).
   - **Single distinct airline → return `options[:max_airlines]` unchanged**
     (today's response-order behavior, numbering already correct).
   - Otherwise: representative per airline = min by `(price, PT depart)`;
     order representatives by `(price, PT depart)` ascending; keep the first
     `max_airlines`.
   - Re-stamp each selected option: `option_number` = 1..N and `spoken`
     regenerated via `_spoken_option` (carrier display name from
     `airline_name`/`airline_name()` — same inputs the parser uses); all other
     fields carried over with `model_copy(update=...)`.
2. PT-depart comparison uses the option's `depart_date` + `depart_time`
   strings (already PT, zero-padded — lexicographic tuple compare is correct);
   no datetime re-parsing needed unless simpler.

## 3. Concierge wiring (`backend/api/concierge.py`)

1. `search_flights_impl`: pass `limit=15` in the `InstaFlightsRequest` (the
   shapes default stays 10 — repair path unaffected), parse with
   `max_options=15`, then run the pool through `select_airline_diverse` before
   storing. `_SESSION_FLIGHT_OPTIONS`, `_LATEST_SEARCH`, spoken assembly,
   count words, and the reference block all operate on the selected list —
   no changes needed downstream of the selection call.
2. Update the docstring ("2–3 options" → one per airline, up to 3) — no
   `BASE_INSTRUCTIONS` changes.

## 4. Mock parity (`backend/api/sabre/mock_client.py`)

1. Give the three `_INSTA_VARIANTS` itineraries at least two distinct
   marketing carriers (e.g. variants 1–2 keep the current carrier, variant 3
   gets a second code present in `AIRLINE_NAMES`), deterministically — no
   randomness, clock spread and hub-connection variant preserved.
2. Sweep existing tests that assert the mock's carrier/spoken output and
   update expectations; the mock walkthrough (`SABRE_MODE=mock`) must now
   speak a two-airline menu.

## 5. Tests (`backend/tests/`)

1. **Selection unit tests** (hermetic, new): multi-airline pool → one per
   airline; cheapest-tie-earliest representative; >3 airlines → 3 cheapest
   representatives; single-airline pool → first-3 response order (byte-equal
   to input slice); renumbering + regenerated `spoken` numbers match list
   position; non-selected fields carried over intact.
2. **Repair-parity test**: parsing a >3-itinerary fixture through the parser
   with default args yields exactly today's first-3 response-order result —
   the structural guard that Group 1 changed nothing for `repair_tools.py`.
3. **Concierge integration**: `search_flights_impl` against the mock stores a
   multi-airline menu; a re-search and `book_flight("2")` resolve against the
   renumbered list; `pending_options` surfaces the selected options.
4. Full bare suite green in the container (the CI-identical run).
