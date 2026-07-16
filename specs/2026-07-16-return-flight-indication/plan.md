# Plan — Phase 34: Return-flight indication (verify-only, Tavily-backed)

Task groups are independently implementable in order. All code lands in
`backend/api/concierge.py` plus tests and two doc touches — no new
dependencies, no deployment surface changes (`tavily-python` and
`TAVILY_API_KEY` shipped with Phase 35).

## 1. Tool impl

1.1 Add the fallback builder: given the route names (or nothing, when the
    route is unknown), return the honest soft-fallback line — route-aware
    phrasing without invented schedule facts (see requirements § Decisions 2).
    Constant-ish helper next to `_DESTINATION_INFO_FALLBACK`.
1.2 Add a small date formatter: `YYYY-MM-DD` → "July 26, 2026" for the Tavily
    query (the proven-quality query shape). A malformed date passes through
    as-is — Tavily copes, and the tool must never raise on input shape.
1.3 Add `async def check_return_flights_impl(session_id: str,
    return_date: Optional[str] = None) -> str`:
    - `await ensure_trip_context(session_id)` (cache-first). Unpinned or
      trip-not-found → return the no-trip speakable (reuse `_NO_TRIP_SPOKEN`
      posture: the question only makes sense after a booking).
    - Derive the reverse route: first `trip.destinations` entry → `trip.origin`.
      Either end missing → the route-less fallback line.
    - Build the query: `flights from {destination} to {origin} on {date}` when
      dated; `flights from {destination} to {origin}` dateless.
    - `await asyncio.wait_for(asyncio.to_thread(_tavily_search, query),
      timeout=_TAVILY_TIMEOUT_S)` — `_tavily_search` reused wholesale
      (sanitizer, condensing, word-boundary cap included).
    - Compose the spoken result with the honesty framing baked in:
      `"I can't book the return from here, but "` + indication.
    - Whole body try/except → the route-aware fallback; log
      `logger.warning(..., exc_info=True)` like `destination_info_impl`.
      The tool never raises and **touches no session/booking state**
      (`_SESSION_FLIGHT_OPTIONS`, `_LATEST_SEARCH`, `_booking_writes`,
      trip model — all untouched by construction).

## 2. Registration & instructions

2.1 In `build_agent`, add the `_check_return_flights(return_date: str = "")
    ` closure (empty string → None, if the SDK's schema prefers a defaulted
    string over Optional) with a routing-quality docstring: "Whether return
    flights exist for the traveler's trip — a spoken indication from web
    schedule info, not bookable fares. Use when a traveler with a booked
    trip asks about getting back / getting home; pass their return date as
    YYYY-MM-DD when they gave one, omit it otherwise." Register always:
    `function_tool(_check_return_flights, name_override="check_return_flights")`.
2.2 Extend `BASE_INSTRUCTIONS`: when a traveler with a booked trip asks about
    getting back or getting home ("is there a way to get home", "flights to
    get me back", any return question), call `check_return_flights` — never
    `search_flights`, and never the booked-trip refusal for these questions.
    If they gave no return date, ask for it first in one short turn (suggest
    the trip's end date when there is one); if they decline or say
    "whenever", call the tool without a date. Relay the result as an
    indication — never as searched fares or something bookable.
2.3 Check the existing "Never call search_flights or book_flight when a trip
    is already booked" sentence still reads coherently next to the new
    clause; adjust wording minimally if the two collide.

## 3. Tests

All hermetic — mock at the Tavily boundary (monkeypatch `_tavily_search`);
no `TAVILY_API_KEY`, no network. New module `test_check_return_flights.py`
mirroring `test_destination_info.py`.

3.1 Pinned trip + date: the query passed to the mocked search contains the
    reverse route (destination → origin) and the human-formatted date; the
    returned string starts with the honesty framing and contains the mocked
    indication.
3.2 Pinned trip, dateless: query carries the route, no date; no error.
3.3 Unpinned session: no-trip speakable; the mocked search is never called.
3.4 Missing route ends (trip with empty `destinations` or no `origin`):
    fallback line, search never called, never raises.
3.5 Failure paths each return the route-aware fallback and never raise:
    search raises, `asyncio.TimeoutError` (slow mock), empty/unusable answer.
    Fallback contains no airline names/counts/times.
3.6 **Session-state purity (the phase's core invariant):** after a successful
    dated call, `_SESSION_FLIGHT_OPTIONS` and the `_LATEST_SEARCH` slot are
    exactly as before the call (empty stays empty; a pre-existing entry is
    byte-identical), and no bookings write occurred (mock the repositories /
    assert `_booking_writes` untouched).
3.7 `build_agent` registers `check_return_flights` (present by name in the
    agent's tools) with no `TAVILY_API_KEY` in the environment.
3.8 Instruction routing text: `BASE_INSTRUCTIONS` mentions
    `check_return_flights` and the elicitation rule (string-presence checks,
    the existing instructions-test pattern).

## 4. Docs

4.1 `DEMO_FLOW.md`: add the return-question beat — after the outbound is
    booked, the operator (or a judge) can ask "is there a way to get home";
    the agent asks the return date, then speaks the Tavily-backed indication;
    nothing appears on the booking page and nothing becomes bookable.
4.2 README operator run sheet ("Running it live"): one line noting the
    rehearsal phrasing and that the answer is web schedule info, not fares.

## 5. Land & verify

5.1 Bare suite green in-container
    (`docker compose exec backend python -m pytest`).
5.2 Land on `vb/dev` by PR; CI builds, tests inside the image, deploys.
    Missed webhook: `gcloud builds triggers run vocal-bridge-be-pr-to-dev
    --branch=vb/dev`.
5.3 Live spot-check per validation.md via the `/v1/web_call/query` seam —
    no call quota spent.
