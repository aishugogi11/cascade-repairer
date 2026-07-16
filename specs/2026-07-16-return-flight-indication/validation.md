# Validation — Phase 34: Return-flight indication (verify-only, Tavily-backed)

Per the 2026-07-16 evening replan decision, this file requires **no PR-body
evidence** — run evidence lands in this spec directory and the changelog
entry.

## Automated

Run in-container: `docker compose exec backend python -m pytest`
(hermetic — no `TAVILY_API_KEY`, no GCP credentials, no network).

Required assertions (plan § 3):

1. Query construction: pinned trip + `return_date` → the mocked
   `_tavily_search` receives the reverse route (primary destination →
   `trip.origin`) and the human-formatted date; dateless → route only.
2. The successful result begins with the honesty framing ("I can't book the
   return from here, but …") and carries the mocked indication.
3. Unpinned session → the no-trip speakable; the search is never invoked.
4. Missing route ends → fallback line, search never invoked, no exception.
5. Every failure path (search raises, timeout, empty answer) returns the
   route-aware soft fallback, never raises, and the fallback contains no
   invented specifics (no airline names, flight counts, or times).
6. **Session-state purity:** a successful call leaves
   `_SESSION_FLIGHT_OPTIONS`, the `_LATEST_SEARCH` slot, and booking writes
   exactly untouched — the phase's core invariant.
7. `build_agent` registers `check_return_flights` with no key in the
   environment; `BASE_INSTRUCTIONS` names the tool and the
   ask-for-the-date-first rule.
8. The full bare suite passes — no regressions in `test_concierge.py`,
   `test_destination_info.py`, or the booking-page/status tests.

## Manual

On the deployed service (or locally with `TAVILY_API_KEY` set), via the
`/v1/web_call/query` curl seam — unique `session_name`, no call quota:

1. **Happy path:** book an outbound by voice or seed+pin a trip (JFK→LAX
   anchor), then send the live-QA phrasing verbatim: *"is there a way to get
   home"*. Expect: the agent asks for the return date (not the booked-trip
   guard message, not a refusal). Reply with a date; expect a spoken
   indication naming real airlines for the reverse route, framed as
   schedule info — the words "I can't book the return from here" (or the
   shipped framing) present, no URLs, no fare-class letters, no markdown.
2. **Second phrasing:** *"flights to get me back"* routes the same way.
3. **Dateless path:** decline the date ("whenever works") — expect a general
   route indication, no stall.
4. **Nothing bookable:** immediately after the return answer, say "book
   option one" (and watch the booking page's poll during the exchange).
   Expect: no return options ever appear in `pending_options`, and no second
   trip is created — the agent has nothing to book and says so / offers the
   existing trip.
5. **Unpinned:** a fresh session with no trip asking "is there a way to get
   home" gets the no-trip line, not a crash or a Tavily call about nowhere.
6. **Edge:** ask the return question mid-repair (after a disrupt) — the tool
   still answers; repairs and consent flow are unaffected.

## Tone check

The spoken result is one or two conversational sentences: airline *names*
never codes, city names where natural, no web addresses, framed as an
indication ("there are flights back that day on …"), never as searched
fares, options, or anything bookable. The fallback line admits the miss
plainly and invents nothing.

## Definition of done

- All automated assertions above pass in the bare in-container suite.
- Manual walkthrough items 1–5 verified on the deployed service (item 6
  best-effort if quota allows), evidence (transcript snippets / curl output)
  saved in this spec directory.
- `DEMO_FLOW.md` return beat and README run-sheet note landed.
- Merged to `vb/dev` by PR, CI green (tests inside the image), deployed.
- `specs/roadmap.md` Phase 34 heading marked `[x] COMPLETE`.
