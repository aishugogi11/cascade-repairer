# Phase 41 — live QA evidence (2026-07-18, event-day morning PT)

Run against the deployed Cloud Run service after the Phase 41 merge/deploy,
entirely through the zero-quota `/v1/web_call/query` seam (no outbound calls
spent). All commands used unique `session_name`s per the README probe rule.

## 1. Diverse live menu (validation § Manual, item 4)

Search JFK→LAX 2026-07-21 (the anchor pair, ~18:10 UTC):

> "I found two good options: one on JetBlue, nonstop, leaving at 5 AM and
> landing at 11 AM for about $301; and one on Delta, nonstop, leaving at
> 5 AM and landing at 10:58 AM for about $301. Which one would you like?"

- **Two distinct airlines, one option each** — today's cache holds B6 + DL
  on the anchor pair, and the menu names both (pre-41 this would have been
  three same-carrier options in response order).
- Fares tied at ~$301, so cheapest-first ordering is untestable live today;
  the ordering contract is covered hermetically (`test_airline_diversity.py`).
- `GET /v1/sabre_tools/search_log` for the search:
  `{"op": "instaflights_search", "mode": "real", "route": "JFK → LAX",
  "date": "2026-07-21", "outcome": "15 fares"}` — **the limit=15 fetch is
  live**: 15 real fares pulled, distilled to the 2-airline menu.

## 2. Booking resolves the renumbered menu (item 5)

Same-session "Book option 2 please" → "Booked — your nonstop flight to LAX
is set for July 21 at 5 AM." The landed trip
(`8f9f0fec-2896-487e-a3fc-08cf66bf7753`, adopted as
`/v1/sabre_tools/latest_trip_id`) carries the flight item:

- status `booked`, **airline `DL` / "Delta", flight 713, $301.40 USD** —
  exactly the airline option 2 named. The renumbered-menu → `book_flight`
  path works live; the trip is page-adoptable (the cascade page's normal
  latest-trip pickup).

## 3. Reference-block follow-up (mock-walkthrough item 3, verified live)

Fresh session, search, then "How long is the Delta flight and what cabin is
it?" → "It's about 5 hours 58 minutes, and it's Economy." The search log
gained **no additional row** for the follow-up — answered from the bracketed
reference block, no re-search.

## Repair path

No repair-side code changed; the structural guards
(`test_parser_default_cap_is_first_three_response_order`,
`test_repair_tools_call_sites_use_default_parser_args`) pass in the
CI-identical container run (634 passed, 12 skipped, 11 deselected).

## Residual

The single-carrier degrade could not be observed live (the anchor pair had
two carriers today — the happy case); it is covered by
`test_single_airline_pool_degrades_to_response_order_top_three`. If the
cache drops to one carrier by demo time, the menu reading like the classic
top-N of that carrier is the specified behavior, not a failure.
