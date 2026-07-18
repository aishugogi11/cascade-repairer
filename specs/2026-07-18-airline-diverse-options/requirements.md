# Phase 41 — Airline-diverse flight options: Requirements

Roadmap phase: **Phase 41** (`specs/roadmap.md`, promoted at the 2026-07-18 third
triage — original TODO text and the motivating 14-itinerary JFK→LAX sample live in
the phase blockquote there). Branch: `vb/feature/phase-41-airline-diverse-options`.

## Scope

Today `search_flights` offers the **first 3 parsed itineraries in response order**
(`_MAX_SPOKEN_OPTIONS = 3` inside the shared parser), so a JetBlue-heavy cache —
12 of 14 itineraries in the observed JFK→LAX pull — speaks a single-carrier menu
even when American (and potentially Delta) have priced content further down.

**In scope**

| Change | Where |
|--------|-------|
| Fetch up to 15 itineraries per guided-booking search (`limit=15` on the concierge's request only) | `concierge.py` `search_flights_impl` |
| Parser accepts a caller-supplied pool ceiling (default unchanged at 3) | `flight_options.py` `_parse_instaflights_options` |
| New airline-diversity selection: from the parsed pool, one option per distinct airline, **at most 3 airlines spoken** | `flight_options.py` (new helper), applied only by the concierge |
| Selected options renumbered 1..N with regenerated `spoken` clauses (speakable rules intact) | the new helper |
| Mock client emits ≥2 distinct carriers across its 3 deterministic itineraries so hermetic tests and zero-quota rehearsals exercise the diversity rule | `sabre/mock_client.py` |

**Out of scope (explicit, from the spec interview)**

- **The flight-repair re-shop is untouched.** `repair_tools.py` calls the shared
  parser with its current default cap and keeps its closest-arrival pick and
  exclusion identity byte-identical. This is why the diversity rule is a separate
  selection step, not a change to the parser's own cap, and why `limit=15` is
  passed by the concierge's request rather than raising the
  `InstaFlightsRequest.limit` default (which the repair path also uses).
- No changes to `book_flight`, `_SESSION_FLIGHT_OPTIONS` semantics,
  `_LATEST_SEARCH`/`pending_options`, the `details_from_option` stamp, or the
  cascade/booking pages — they consume the (now diverse) list as-is.
- No `BASE_INSTRUCTIONS` tuning (standing event-day rule from the Phase 34
  close-out: no prompt changes that could regress rehearsed beats).
- No dedupe/timezone-skip changes — the parser's correctness rules are untouched.

## Decisions (spec interview, 2026-07-18)

1. **Search only, cap 3** — the spoken menu never exceeds 3 options: one per
   distinct airline. When the pool holds more than 3 airlines, the 3 cheapest
   representatives win. When only one airline has content, degrade to today's
   behavior exactly: the first 3 pool options in response order.
2. **Cheapest, tie earliest** — each airline's representative is its
   lowest-fare itinerary; equal fares tie-break to the earliest PT departure.
   Spoken order is by representative fare ascending (cheapest = "option one"),
   same tie-break. On the sample pull this yields option one B6 $198.40 5:45 PM,
   option two AA $278.40 6:00 AM.
3. **Deploy today, live-QA** — event-day ship posture: hermetic suite green,
   merge → deploy, then a zero-quota mock/web-voice verification plus the live
   probe loop before the demo (the Phases 38–40 pattern this morning).
4. *(Design, from code reading)* **Renumbering re-stamps `spoken`** — parse-time
   numbering covers the pool; the selection helper rebuilds `option_number` and
   the `spoken` clause via the existing `_spoken_option` so "option one/two"
   always matches the offered list. All other `FlightOption` fields carry over
   unchanged (`model_copy`).

## Context

- **Speakable rules stand** (tech-stack § Backend): airline *names* spoken, never
  codes or fare-class letters; prices rounded; every failure path returns a
  speakable string. The bracketed reference block and rich-fields clause follow
  the selected options automatically.
- **Existing seams to follow**: `_spoken_option` / `airline_name` in
  `flight_options.py`; the `count_word` map in `search_flights_impl` already
  handles 1–3 options; the mock's `_INSTA_VARIANTS` derive deterministic data —
  keep determinism and the classic clock spread when adding a second carrier.
- **Cache reality**: whether the live menu actually shows 2–3 airlines depends on
  the day's InstaFlights cache (the sample pull had B6 + AA on JFK→LAX). The
  feature must be correct on any pool shape; live QA verifies against whatever
  the cache holds at demo time.
- Standing rule: this `validation.md` must not require PR-body evidence
  (2026-07-16 evening replan) — run evidence lives in this spec dir and the
  changelog entry.
