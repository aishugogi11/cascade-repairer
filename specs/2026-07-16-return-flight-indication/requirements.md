# Requirements — Phase 34: Return-flight indication (verify-only, Tavily-backed)

Re-scoped 2026-07-16 at the Phase 35 QA follow-up: the data source is **Tavily
web search**, not InstaFlights (the reverse pair AND round-trip `returndate`
are honest-empty at every probed date while the one-way control was healthy —
tech-stack § 2026-07-16 addendum). No longer data-gated.

The requirement, from Josh's live-QA transcript: a traveler who booked the
outbound asked *"is there a way to get home"* and hit the booked-trip guard
message. When someone books the outbound, the agent must give *some* credible
indication a return exists — ideally for their return date.

## Scope

**In scope**

| Piece | What it is |
|---|---|
| `check_return_flights` tool | New read-only Concierge tool (7th), `check_return_flights(return_date: Optional[str])` — `return_date` as `YYYY-MM-DD` when the traveler gave one, omitted otherwise |
| Route derivation | Reverse route from the pinned trip via cache-first `ensure_trip_context`: primary destination (first `trip.destinations` entry) → `trip.origin`. Unpinned sessions get the no-trip line — the question only makes sense after a booking |
| Tavily lookup | Phase 35 plumbing reused wholesale: `_tavily_search` (same `search_depth='basic'` / `include_answer=True` / `max_results=3`, same `_speakable` sanitizer contract), run via `asyncio.to_thread` inside the 8 s `wait_for`. Query shaped like the proven example: `flights from LAX to JFK on July 26, 2026` (date rendered human-readably from `YYYY-MM-DD`; dateless queries ask about the route generally) |
| Spoken result | The tool composes the full speakable line **with the honesty framing baked in**: "I can't book the return from here, but …" + the Tavily indication. Web schedule info, spoken as an indication — never presented as searched fares or bookable inventory |
| Instruction routing | `BASE_INSTRUCTIONS` routes the live-QA phrasings ("is there a way to get home", "flights to get me back", any return question after booking) to the new tool — today the booked-trip guard message fires on them. If the traveler gave no date, the agent asks for their return date first (it may suggest the pinned trip's `end_date` when one exists); "whenever" / a declined date → call the tool dateless |
| Docs | `DEMO_FLOW.md` gains the return-question beat; the README operator run sheet notes the rehearsal line ("is there a way to get home") so it can be exercised deliberately |
| Tests | Hermetic, mirroring `test_destination_info.py` — mocked at the Tavily boundary, plus the session-state-purity assertions below |

**Out of scope — hard exclusions (the point of the phase)**

- **No return booking, no return options displayed, ever.** Nothing bookable
  enters session state: the tool must not touch `_SESSION_FLIGHT_OPTIONS`,
  `_LATEST_SEARCH`, `_booking_writes`, or the trip model. Do NOT reuse
  `search_flights` — its storage would make return options bookable
  (`book_flight` would create a second new trip) and leak them onto the
  booking page's poll. The Tavily path stores nothing.
- Zero changes to the never-book-once-booked rule, the booking page, or the
  cascade page.
- The InstaFlights verify variant is retired. If the reverse-pair cache ever
  returns (the Phase 24 morning-smoke probe still checks, informationally),
  speaking real cached fares is a possible upgrade — nothing here gates on it.

## Decisions (settled at the spec interview, 2026-07-16)

1. **Date optional, agent asks.** The tool accepts an optional `return_date`.
   The Concierge elicits the date when the traveler didn't give one (it may
   offer the trip's `end_date` as the suggestion); if they decline or say
   "whenever", the tool runs dateless and Tavily answers about the route
   generally. Rationale: the live-QA phrasings carry no date, and a required
   parameter would stall the answer behind an elicitation loop.
2. **Honest soft fallback.** On any failure (missing key, Tavily error,
   timeout, empty/unusable answer) the tool mirrors `destination_info`'s
   posture but stays route-aware without inventing schedule facts — e.g.
   *"I couldn't check return schedules just now, but Los Angeles back to New
   York is a well-traveled route — ask me again in a minute and I'll take
   another look."* Never invented specifics (no airline names, counts, or
   times in the fallback); a raising tool would kill the voice turn.
3. **Docs ride along.** `DEMO_FLOW.md` + README run-sheet note ship in this
   phase so the rehearsal script exercises the beat deliberately. The
   guard-message-softening option was declined — routing via instructions is
   the fix; the guard text stays as is.

## Context

- **Tone:** replies are spoken aloud — short conversational sentences, no
  markdown, no URLs, airline *names* never codes (the Tavily answer passes
  `_speakable`; the proven answer already speaks names: "JetBlue, American
  Airlines, and Delta Air Lines"). The agent says city names where natural.
  The honesty framing ("I can't book the return from here, but …") must
  survive into what's actually spoken — it's baked into the tool result, not
  left to the model.
- **Stack pointers:** everything lands in `backend/api/concierge.py` (tool
  impl + `build_agent` registration + `BASE_INSTRUCTIONS` clause) and
  `backend/tests/` — the Phase 35 pattern exactly. No new dependencies:
  `tavily-python` is already pinned and `TAVILY_API_KEY` is already on Cloud
  Run. The tool is **always registered** (lazy client, call-time key read) so
  the hermetic suite needs no credentials.
- **Existing patterns to follow:** `destination_info_impl` is the template —
  plain `_impl` function for tests, closure in `build_agent` with a
  routing-quality docstring, every failure path returning one speakable
  string, `asyncio.to_thread` for the blocking client (standing rule).
  Accepted Phase 35 loosenesses carry over unchanged: a timed-out lookup
  finishes out its worker thread, and key-less environments log a warning
  traceback per question.
