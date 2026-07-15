# Validation — Search Hardening (Phase 28)

Branch: `vb/feature/search-hardening`. Spec: `requirements.md` beside this file.

Scope note for the validator: "computed dates only" applies to **this phase's added or
modified tests and fixtures**, not the pre-existing test tree (the Phase 27 report's
open question, answered here). The cert-marked parity test is the only test allowed to
touch the network, and only when deliberately selected.

## Automated

All of the following run and pass hermetically — no GCP credentials, no
`OPENAI_API_KEY`, no network — via `docker compose exec -T backend pytest`
(the `cert` marker stays deselected by default):

1. **Suite green**: the full bare-container run passes with no new warnings introduced
   by this phase (the six pre-existing unawaited-coroutine warnings are Phase 24's and
   may remain).
2. **Unmapped connection skips the itinerary**: a mapped-endpoints itinerary with an
   unmapped connection airport (e.g. JFK→XXQ→LAX) is absent from the parsed options and
   the next fully mapped itinerary takes its slot with contiguous numbering. A fully
   mapped multi-segment itinerary still parses (no over-skipping), and the
   all-unmappable case still yields the no-flights line.
3. **Mock west-to-east ordering**: mock-mode SFO→JFK — every parsed option's arrival
   instant follows its departure; option one speaks the classic
   "leaves at 8 AM and lands at 10:05 AM"; a booking write from those options produces
   `end_ts > start_ts`. A reverse (east-to-west) pair parses to the same PT spread.
4. **Honest empty, strict**: a faked InstaFlights HTTP 404 carrying the documented
   `WARN.RAF.APPLICATION` / "No results were found" body returns an empty
   `InstaFlightsResponse` from the real client — no mock fallback — and
   `search_flights_impl` speaks the existing "couldn't find any flights for that day"
   line with no options stored. A 404 with any other body still raises and mock-swaps
   (the insurance path asserted intact).
5. **Token refresh once**: a faked 401 on a cached token clears it, refetches, retries
   the request exactly once, and succeeds; a persistent 401 raises to the dispatcher.
6. **Metro aliases**: `NYC`/`WAS`/`CHI` as origin or destination reach the client and
   the market check as `JFK`/`IAD`/`ORD`; unaliased codes pass through unchanged.
7. **Dedupe**: two identical itineraries plus one distinct parse to exactly two
   options, contiguously numbered — no spoken clause duplicates another.
8. **Computed dates**: no literal travel date appears in this phase's test/fixture diff.

## Manual

9. **Deliberate cert run** (implementation day, credentialed, in-container):
   `pytest -m cert` green — including the new timezone-parity test (every airport code
   in the live supported-markets list resolves via `airport_zone`) and the existing
   Phase 25/26 tripwires. Capture the dated output tail.
10. **Mock-mode walkthrough** (`SABRE_MODE` unset): drive `search_flights_impl` for
    SFO→JFK (west-to-east, the criterion-14 reproducer) on a computed future date —
    spoken options are the classic spread, arrivals after departures; book option one
    and confirm sane `start_ts`/`end_ts`. This is the regression walkthrough Phase 27
    failed.
11. **Real-mode honest-empty spot check** (if CERT is reachable): search a supported
    pair on a date known to have no cached content (per-pair windows — pick one outside
    its advance-purchase window from the 2026-07-14 sweep). The agent speaks the
    no-flights line; the log shows **no** mock-fallback warning for that call.
12. **Real-mode happy path unchanged**: one supported near-term pair (e.g. SFO→MIA at
    +2 days) still returns real spoken options — dedup'd, no metro redirect, no
    duplicates read aloud.

## Tone check

13. No new spoken copy is expected; if any line was touched, it stays short, warm,
    speakable, jargon-free — no codes, no "sandbox"/"mock"/"API" words in anything the
    agent says. The `BASE_INSTRUCTIONS` metro-code clause is terse and doesn't leak
    into spoken replies.

## Definition of done

- All automated assertions above exist and pass in the bare container run.
- The cert run (item 9) and both walkthroughs (items 10–12 as reachable) happened on
  implementation day, **evidenced in the PR description** — transcript/output snippets,
  not just prose claims. (Phase 27's DoD failed on an empty PR body; an empty PR
  description fails this phase too.)
- Any airport codes the parity test surfaced are added to `AIRPORT_TZ`.
- `specs/roadmap.md` Phase 28 heading marked `[x] COMPLETE`.
