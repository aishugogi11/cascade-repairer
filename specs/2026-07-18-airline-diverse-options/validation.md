# Phase 41 — Airline-diverse flight options: Validation

Per the standing rule (2026-07-16 evening replan): no PR-body evidence is
required anywhere below — run evidence lands in this spec directory and the
changelog entry.

## Automated

Run the suite the CI-identical way:

```bash
docker compose build backend
docker run --rm hackathon-vocal-bridge-backend python -m pytest tests/ -v
```

All must pass, including these specific assertions:

1. **Diversity**: a parsed pool containing ≥2 distinct `airline` codes yields
   one option per airline, at most 3, ordered by representative fare ascending
   (tie: earliest PT departure).
2. **Representative pick**: within an airline, the lowest fare wins; equal
   fares tie-break to the earliest PT departure (fixture must include an
   equal-fare pair).
3. **Airline cap**: a 4-airline pool yields the 3 cheapest representatives.
4. **Single-carrier degrade**: a one-airline pool returns the first 3 pool
   options in response order — field-for-field equal to today's behavior.
5. **Renumbering**: selected options are numbered 1..N and each `spoken`
   clause contains its own number and the airline *name* (never the code);
   all non-renumbered fields are carried over unchanged.
6. **Repair parity**: `_parse_instaflights_options` with default arguments on
   a >3-itinerary fixture returns exactly the first-3 response-order options —
   the repair re-shop's input is byte-identical to pre-41.
7. **Concierge flow**: against the mock client, `search_flights_impl` stores a
   multi-airline menu in `_SESSION_FLIGHT_OPTIONS` and `_LATEST_SEARCH`, and
   `book_flight` resolves an option number against the renumbered list.
8. The concierge's `InstaFlightsRequest` carries `limit=15`;
   `shapes.InstaFlightsRequest.limit` default remains 10.

## Manual

**Zero-quota mock walkthrough** (local, `SABRE_MODE=mock`, VB env unset —
drive the `/v1/web_call/query` curl seam):

1. Search a supported pair; the spoken menu offers **two distinct airline
   names** (the mock's parity carriers), numbered, prices rounded, no codes.
2. Book "option two"; the booked flight card and `details` stamp match the
   airline that option two named.
3. Ask a follow-up ("which one is nonstop?"); the reference block answers
   without a re-search.

**Live QA on the deployed service** (event-day, after merge → deploy — the
Phases 38–40 posture; re-run the README probe loop first for a LIVE pair):

4. Search the live anchor pair via the cascade orb or the `/query` seam. If
   the day's cache holds ≥2 airlines (the sample pull had B6 + AA on
   JFK→LAX): the menu names distinct airlines, cheapest first. If the cache
   is single-carrier at demo time: the menu reads like today's (top options
   of that carrier) — that is the specified degrade, not a failure; note
   which case was observed in the evidence.
5. Book by voice end-to-end once (web-voice, free) and confirm the trip
   appears on the page with the chosen airline — the diverse menu must not
   disturb the booking beat.
6. Confirm the repair path is undisturbed: no repair-side code changed
   (assertion 6 is the structural check); if a full break → repair rehearsal
   runs today anyway, the rebooked-flight beat behaves exactly as yesterday.

## Tone check

Spoken menu clauses stay speakable: airline names ("JetBlue", "American"),
rounded dollar amounts, no IATA codes, no fare-class letters, no markdown.
The single-carrier degrade must not apologize or explain itself.

## Definition of done

- All automated assertions pass in the container run; suite fully green.
- Mock walkthrough (items 1–3) observed locally; dated notes in this spec dir.
- Merged to `vb/dev`, deployed, and live QA (items 4–5) performed on the
  deployed service before the demo, outcome recorded here.
- Roadmap Phase 41 heading marked `[x] COMPLETE`.
