# Requirements — Search Hardening: Phase 27 Validation Fixes and Honest Empties (Phase 28)

Branch: `vb/feature/search-hardening`. Roadmap: Phase 28.

Phase 27 put real InstaFlights fares in the demo path; its independent validation returned
**FAIL** with two behavior defects, and the same evening's live rehearsal surfaced three
more findings. This phase fixes all of them plus the two risk items the validation report
flagged — the guided-search path (`backend/api/concierge.py`, `backend/api/sabre/`) comes
out honest, deduplicated, and drift-resistant before the cascade work (Phase 29) builds
on it. Source of truth for the defects:
`specs/2026-07-14-real-sabre-search/validation-report.md` (criteria 5 and 14, § Risks).

## Scope

### In scope — all seven roadmap items (interview decision)

1. **All-segment unmapped-airport skip** (validation criterion 5):
   `_parse_instaflights_options` checks only `segments[0]`'s departure and
   `segments[-1]`'s arrival, so a mapped `JFK → XXQ → LAX` itinerary survives an unmapped
   connection airport. Requirements decision 2 of Phase 27 says an itinerary *touching*
   any unmapped airport is skipped. Check **every segment's both ends** via
   `airport_zone`; any `None` skips the itinerary in favor of the next.
2. **Mock times survive the airport-local parse** (validation criterion 14 — a
   deterministic regression): `MockSabreClient.instaflights_search` emits the old
   Pacific-fiction wall clocks (`08:00`, `10:05`, …) as offset-less values, which the
   parser re-reads as *airport-local* — a mock SFO→JFK search arrives "before" it departs
   and `_booking_writes` can produce `end_ts < start_ts`. Fix the **mock, not the
   parser**: emit each end expressed in *its own airport's local zone*, derived from the
   Pacific fiction via `airport_tz` — so the parsed PT output is the classic
   8 AM / 11:30 AM / 6:15 AM spread for any mapped pair, in any direction.
3. **Documented empties speak honestly** (live finding + Sabre docs): InstaFlights
   signals "no results" as **HTTP 404 `WARN.RAF.APPLICATION` "No results were found"** —
   a documented response, not a failure. Today that 404 raises, the dispatcher
   mock-swaps, and the agent offers mock options for a genuinely empty date — which
   betrays the realness posture (decision 2026-07-14: no mock options in the demo).
   Detect it in `RealSabreClient.instaflights_search` and return an empty
   `InstaFlightsResponse`, so the agent speaks the existing "couldn't find any flights
   for that day" line.
4. **City-name → airport-code discipline** (live finding): the model resolved "New York"
   to the metro code `NYC`; the supported-markets list is airport codes only, so the
   agent redirected the traveler to the very route it was refusing. Two-layer fix:
   `BASE_INSTRUCTIONS` says never metro codes (New York → JFK), and
   `search_flights_impl` applies a small metro-alias map as belt-and-suspenders.
5. **Duplicate-option dedupe** (live finding): CERT returned two identical itineraries
   and the agent said "option three is the same as option two" aloud. Dedupe parsed
   options by (flight number, times, price) before numbering.
6. **Token-refresh truth** (validation report, risks): `_get_token`'s docstring claims
   refetch-on-401, but nothing clears the cached token — after the 7-day expiry or a
   credential reset, real mode silently mock-swaps every call until a process restart.
   Clear and refetch once on 401 in `_get`/`_post`.
7. **Timezone-table parity** (validation report, risks): a `cert`-marked test asserting
   every airport code in the **live** supported-markets list resolves via
   `airport_zone` — so a supported route can never be silently unmappable.

### Out of scope

- **Phase 29's re-shop swap**: `repair_tools.py` stays on `sabre_client.flight_search`
  (BFM) — the flight-repair InstaFlights move is the next phase, deliberately building on
  this one's fixes.
- **BFM anything**: shapes, the `flight_search` op, `/v5/offers/shop` — the conditional
  punch list was retired from the roadmap 2026-07-14 (no entitlement unlock coming) and
  stays documented in the Phase 25 notes only.
- **`_LATEST_SEARCH` expiry** — rides with Phase 22, unchanged.
- **The six unawaited-coroutine warnings** — Phase 24's async-test-hygiene item, not this
  branch (they predate Phase 26).
- **Sweep drift detection** (`sweep.py` expected-classification check) — Phase 24.
- **Walkthrough-evidence process gaps** from the validation report (empty PR body) are
  addressed by *doing it right this time* (see validation.md § Definition of done), not
  by new tooling.

### Behavior table

| Real-mode InstaFlights outcome | Agent behavior after this phase |
|---|---|
| 200 with itineraries | Real options spoken (dedup'd, all airports mapped) |
| **404 with `WARN.RAF.APPLICATION` / "No results were found"** | Honest empty: "couldn't find any flights for that day" — **no mock swap** |
| Any other 4xx/5xx, timeout, shape mismatch | Silent per-call mock swap + warning log (unchanged event-day insurance) |
| 401 on a cached token | Token cleared, refetched, call retried once; a second 401 falls through to the mock swap |

## Decisions

1. **All seven items ship on this one branch** (interview): the two validation defects,
   the three live-rehearsal findings, and the two risk hardenings — the guided-search
   path is fixed once, before Phase 29 stacks the repair re-shop on it.
2. **Honest-empty detection is a strict match** (interview): only an HTTP 404 whose body
   carries the documented `WARN.RAF.APPLICATION` marker (or its "No results were found"
   message) counts as empty. Any other 404 — entitlement drift, a bad path, a gateway
   flap — stays a genuine failure and keeps the silent mock-swap insurance. Rationale:
   an over-broad match would speak "no flights" for outages; an under-broad one would
   mock-swap empty dates and betray the realness posture. The exact body shape is
   confirmed against `sabre-cert-notes.md` / a live probe during implementation, and the
   detection matches on the error **code first**, message as fallback.
3. **The mock converts, the parser stays single-path** (criterion-14 fix): the parser's
   airport-local interpretation is *correct for the real API* — the mock is the liar. The
   mock derives each airport-local clock from the Pacific fiction
   (`ZoneInfo("America/Los_Angeles")` instant → `astimezone(airport zone)`), keeping
   dates from the conversion (not string reuse) so nothing breaks if a variant ever
   crosses midnight. An airport code missing from `airport_tz` emits the fiction clock
   unchanged — the parser skips that itinerary anyway. No mode branches in the parser.
4. **Metro aliases are a tiny static map, applied server-side**: `NYC→JFK`, `WAS→IAD`,
   `CHI→ORD` in `search_flights_impl`, applied to origin and destination after
   normalization, *before* the market check. Instructions carry the same rule so the
   model usually gets it right without the net; the map catches the times it doesn't.
   No new airports in `airport_tz` needed (JFK/IAD/ORD are mapped).
5. **Dedupe key is (flight number, depart datetime, arrive datetime, price)** on the
   spoken endpoints, applied before numbering, first occurrence wins — so option numbers
   stay contiguous and the spoken count matches what's offered. Dedupe happens inside
   `_parse_instaflights_options`, keeping every consumer (voice, `pending_options`,
   future Phase 29 re-shop) consistent.
6. **Retry-once on 401, then fall through**: `_get`/`_post` clear `self._token`, mint a
   fresh one, and retry the request exactly once. A second 401 raises to the dispatcher
   (mock swap + warning) — no retry loops on the voice turn path.
7. **Test posture stays the baseline** (interview): every behavior change gets hermetic
   mock-mode unit tests (`docker compose exec backend pytest`); exactly **one new
   `cert`-marked test** (timezone parity against the live markets list) joins
   `test_sabre_cert.py` behind the existing fence. No other live-call tests.

## Context

- **Constitution pointers**: `specs/tech-stack.md` § Backend (dispatcher contract,
  `SABRE_MODE` per call), § Data (timezone discipline — the standing rule this phase
  finishes enforcing), § Testing (`cert` fence, computed dates only);
  `specs/roadmap.md` Phase 28 (the seven bullets, verbatim source).
  Defect evidence: `specs/2026-07-14-real-sabre-search/validation-report.md`.
  API truth: `specs/2026-07-13-sabre-cert-exploration/sabre-cert-notes.md`.
- **Tone**: no new spoken lines are expected — the honest-empty path reuses the existing
  "couldn't find any flights for that day" copy, and the metro fix reuses the existing
  redirect. If any copy is touched it follows the standing register: short, warm,
  speakable, no jargon, no codes. `BASE_INSTRUCTIONS` edits are instructions to the
  model, not spoken copy, but stay terse — every token rides on every turn.
- **Stack limits**: no new dependencies (`httpx`, pydantic, `zoneinfo` cover all seven
  items). Tests hermetic by default; the one `cert` test uses the documented
  `docker compose exec -e` credential passthrough and computed dates.
- **Existing patterns to follow**: the dispatcher's blanket-except per-call fallback
  (`client.py`); deterministic mock data derived from request fields
  (`mock_client.py`); speakable strings from every tool failure path; the Phase 26
  tripwire style for anything asserting documented Sabre behavior.
- **Demo timing**: event day is July 18; this phase is the gate for Phase 29 (real
  repair data) and should land fast — no scope growth beyond the seven items.
