# Plan — Talk to My Trip: full voice demo experience (Phase 17)

Order is deliberate: the access-code gate (group 1) lands first and atomically — middleware plus
every client's code pass-through in one group, so no deployed state ever has gated APIs with
broken rehearsal surfaces. Guided booking (group 2) is the phase's core and is fully testable
from the desktop `/v1/web_call/` page before any iOS work. The `detail` payload (group 3) is the
designated first cut, so nothing later may depend on it except the sheet (group 5, which degrades
to static text). Groups 4–6 are the app; group 7 is deploy + device verification.

Groups 2 and 3 are independent of each other; 4 depends on 1; 5 depends on 3 (or its cut line);
6 is independent of 3/5; 7 depends on everything.

## 1. Backend + pages — access-code gate

1.1 Add `DEMO_ACCESS_CODE` handling in a new `backend/api/access_gate.py`: a FastAPI
    middleware (or router dependency) requiring header `X-Access-Code` on `/v1/*`, compared
    with `secrets.compare_digest`; 401 with a JSON error body on missing/wrong code.
1.2 Public allowlist: `/v1/legal/*`, `POST /v1/auth/validate`, and the `GET` HTML pages
    (`/v1/web_call/`, `/v1/mobile_voice/`, `/v1/itinerary/`, `/v1/demo/`). Everything else
    under `/v1/` is gated.
1.3 Fail-open when `DEMO_ACCESS_CODE` is unset: allow all requests, log one startup warning —
    local dev and hermetic CI need zero setup.
1.4 Add `POST /v1/auth/validate` (`backend/api/auth.py`, prefix `/v1/auth`): body `{code}`,
    returns 200 `{valid: true}` or 401 — the iOS first-launch check.
1.5 Page pass-through: the four HTML pages read `?code=` (falling back to `localStorage`),
    persist it, and attach `X-Access-Code` on every `fetch` (token, query, status polls, demo
    triggers). No code → pages still render; their API calls 401 cleanly.
1.6 Tests (`backend/tests/test_access_gate.py`): unset env → gated route passes; set env →
    missing/wrong header 401s, correct header passes; each allowlisted route stays public with
    the env set; `validate` returns 200/401 correctly; pages contain the header-attach wiring.
1.7 After deploy: set the code on Cloud Run —
    `gcloud run services update vocal-bridge-be-dev --region us-west1 --update-env-vars DEMO_ACCESS_CODE=…`.

## 2. Backend — guided multi-turn voice booking on the Concierge

2.1 In `backend/api/concierge.py`, add a per-session options store
    `_SESSION_FLIGHT_OPTIONS: dict[str, list[FlightOption]]` (the `_SESSION_TRIPS` pattern).
2.2 `search_flights_impl(session_id, origin, destination, depart_date)` — plain function for
    tests (the `fix_trip_impl` pattern): call `api.sabre.client.flight_search` via
    `asyncio.to_thread`, store the top 2–3 options in `_SESSION_FLIGHT_OPTIONS`, return a
    speakable numbered summary; every failure path returns a speakable string, never raises.
2.3 `book_flight_impl(session_id, option_number)` — validate the option exists (speakable
    error if not, including "search first"); create `Trip` + flight `ItineraryItem`
    (`planned`, flipped to `booked` on the booking write) + `Booking` row via
    `trips.create_trip` / `itinerary_items.create_item` / `bookings.create_booking` (via
    `asyncio.to_thread`); **replace** `_SESSION_TRIPS[session_id]` with the new trip's
    context; clear the session's options; return a short spoken confirmation.
2.4 `complete_trip_impl(session_id)` — guard: speakable error if no trip is pinned; fire an
    `asyncio.create_task` background task that creates hotel/ground/dining/experience items
    sequentially with ~1.5s `asyncio.sleep` spacing (items derived from the booked flight's
    dates/destination, `_SEED_ITEMS` shapes as templates; each created `planned` then
    `booked`); return immediately with a spoken "building the rest of your trip now" line.
2.5 Register `search_flights` / `book_flight` / `complete_trip` in `build_agent`; **remove**
    `book_trip` from the toolset. Extend `BASE_INSTRUCTIONS` with the guided script: ask
    destination → dates → `search_flights` → offer the options → traveler picks by voice →
    `book_flight` → confirm → `complete_trip`; never search when a trip is already pinned
    (offer `fix_trip`/answers instead). Disruption rules untouched.
2.6 Tests (existing concierge test patterns, mocked Sabre client + repositories): search
    stores options and speaks 2–3 of them; book with a bad/missing option number speaks an
    error and writes nothing; book creates the three rows and replaces the session pin;
    complete spaces item creation (assert on the sleep calls, not wall clock) and errors
    speakably with no pinned trip; `build_agent` exposes the three tools and not `book_trip`;
    instructions carry the guided script.

## 3. Backend — `detail` payload on the status endpoint *(first thing to cut)*

3.1 In the itinerary status route, add an optional `detail` object per item: `why_chosen`
    (one sentence), `price_delta` (string, e.g. "+$42"), `impact` (one sentence on downstream
    effects). Derive from the item + its booking's `raw_response` where present; omit the key
    when there's nothing to say. Additive only — existing fields and the web page untouched.
3.2 Tests: status payload carries `detail` for a repaired item with a booking; items without
    bookings omit it; existing status-contract tests still pass unchanged.

## 4. iOS — access gate

4.1 `Views/AccessGateView.swift`: one field, one button, copy per requirements ("Enter the
    access code from your demo invitation"); loading state; friendly inline error on 401.
4.2 `Services/KeychainHelper.swift` (small, no dependencies): store/read/delete the code.
4.3 Gate flow in `TalkToMyTripApp`/`ContentView`: no stored code → show the gate; on
    successful `POST /v1/auth/validate` → save to Keychain, enter the main screen; relaunch
    with a stored code skips the gate; a 401 on any later API call clears the code and
    returns to the gate (handles server-side rotation).
4.4 `APIService` attaches `X-Access-Code` on every request; `VoiceManager` loads the webview
    as `/v1/mobile_voice/?code=…` so the page's token/query fetches carry the header.
4.5 Xcode-local verification: build succeeds; wrong code shows the error; correct code
    persists across relaunch.

## 5. iOS — recommendation sheet

5.1 `RecommendationSheet.swift`: bottom sheet on card tap — "AI Recommended" header, why-chosen
    line, price delta, downstream-impact line, from the item's `detail` payload (pull-through
    from `about/ui_ideas/ui_mockup_2026_07_09.png`, simplified for mobile).
5.2 Decode `detail` in the status models as optional; sheet falls back to sensible static text
    per item type when `detail` is absent — this fallback **is** the cut line for group 3.
5.3 Sheet presentation from `TripTimelineView` card tap; swipe to dismiss.

## 6. iOS — hidden demo gestures + stage polish

6.1 Triple-tap on the orb → `APIService` calls `POST /v1/demo/disrupt` (the Act 2/3 backup
    trigger — real outbound call; rehearse with care, 10 calls/day quota). No visible button.
6.2 Long-press on the orb → trip selector sheet listing recent trips via
    `GET /v1/itinerary/trips`; picking one repoints `TripManager` polling.
6.3 Orb/timeline stage-readability pass: larger status typography/icons, higher-contrast
    broken/repairing/fixed colors, recovery timer legible at arm's length on a projected
    phone screen; orb states (idle/listening/speaking/repairing) distinguishable from the
    back of a room.

## 7. Deploy, end-to-end verification, and the update build

7.1 PR `vb/feature/full-voice-demo` → `vb/dev`; CI builds, tests in the container, deploys;
    set `DEMO_ACCESS_CODE` on the service (1.7); re-run the trigger manually if the webhook
    is missed.
7.2 Browser rehearsal (no quota spend): full guided booking via `/v1/web_call/?code=…`, then
    disrupt via `/v1/demo/` — cascade on the itinerary page.
7.3 Device verification per `IOS_PLAN.md` § Verification: Act 1 booked by voice on the phone
    (cards materialize one by one; rows in BigQuery), Act 2 triple-tap → cascade < 60s while
    conversing, Act 3 the phone rings. Budget: one full run = 2 outbound calls.
7.4 Archive + upload the update build to App Store Connect, queued behind the Phase 16 first
    submission; access code goes in the App Review notes.
7.5 Mark Phase 17 `[x] COMPLETE` in `specs/roadmap.md` (code-complete; store review is
    external).
