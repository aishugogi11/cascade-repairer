# Requirements — Voice Booking Page (Phase 21)

New FastAPI-served page for the **pre-disruption** beat of the demo: booking happens
by voice only, but the screen shows the current flight (and the rest of the
reservation) plus — during the guided booking conversation — the candidate flight
options being discussed, before any event that would trigger a cascade repair.

## Scope

### In scope

**The page** — `GET /v1/booking/`, a self-contained static page
(`backend/api/assets/booking/page.html`) served by a new thin router
(`backend/api/booking_ui.py`), cloned from the itinerary page's *technical*
conventions (visuals come from the mockup — Decision 5):
vanilla HTML/CSS/JS, no build step, no external requests, HTML read per request
(`uvicorn --reload` only watches `.py` files), `?code=` → `localStorage` →
`X-Access-Code` header on every fetch, page shell added to the access-gate GET
allowlist (inert without the gated JSON APIs).

**What the screen shows**, driven entirely by the existing 1.5 s poll of
`GET /v1/itinerary/status/{trip_id}`:

| Surface | Content | Source |
|---------|---------|--------|
| Current flight card | Prominent: route, times (PT), price, status, booking detail when present | `items[type=flight]` + `detail` |
| Trip timeline + reservation cards | Left-rail timeline of the journey plus hotel, ground transportation, dining, experience — the full reservation, materializing one by one as `complete_trip` builds them (mockup's per-leg status icons) | `items[]` |
| Candidate options panel | During the guided booking conversation: the 2–3 flight options the Concierge is speaking, so the audience sees what the booking *could be*; clears once one is booked. Styled on the mockup's right-column "AI Recommended" option card | new additive `pending_options` block (below) |
| Traveler-context card + header | Mockup's left-rail traveler card and app header with status pill (booking-beat statuses, e.g. "Booking by voice" / "Trip confirmed") | `trip` + `items[]` |
| Trip selector | Recent trips, newest-first, PT-labeled `created_at` — mockup's collapsible "Recent Trips" left-rail panel | `GET /v1/itinerary/trips` |

Layout and styling follow `about/ui_ideas/ui_mockup_2026_07_09.png` (see
Decision 5) — Phase 21 builds the mockup's header, left rail, and right-column
card language; the center voice column and repair surfaces arrive in Phases
22–23.

**The backend extension** — additive `pending_options` block on the status
payload (see Decisions). No other backend logic changes.

**Trip pinning contract** — the page honors `?trip_id=` seeding and exposes
`window.vbSetTrip()`, same contract as the itinerary/web_call pages, and
re-resolves `GET /v1/sabre_tools/latest_trip_id` on a cadence so a trip the
agent books mid-conversation appears without a reload (the iOS `TripManager`
pattern).

### Not in scope

- **No voice wiring on this page** — no orb, no token minting, no `/query`
  delegation. The voice conversation happens on the web_call page or over an
  outbound phone call; this page is a display surface. Phase 23 adds voice
  surfaces to the dashboard.
- **Mockup surfaces that belong to later phases**: the center voice column
  (orb, mic/speaker controls, latency stats, conversation feed) and the Sabre
  live-search log panel are Phase 23; the recovery banner/timer,
  repair-status surfaces, disruption score, and "downstream impact" panel are
  Phase 22. Phase 21 builds the mockup's *frame* (header, left rail,
  right-column card language) around the booking beat only.
- **No new booking/search logic** — the guided flow
  (`search_flights` → `book_flight` → `complete_trip`) is reused untouched
  except for recording pending options (Decisions).
- **No disruption/repair UI** — that is Phases 22–23. This page ends where the
  cascade begins.
- **No browser-automation tests** (standing decision) — page JS behavior is
  scripted manual QA.

## Decisions

1. **Candidates travel on the status payload** (user decision, this interview):
   `GET /v1/itinerary/status/{trip_id}` gains an **additive, best-effort
   `pending_options` block** so the existing 1.5 s poll drives everything — no
   separate candidates endpoint, mirroring how `detail` was added in Phase 17
   (omitted when there is nothing to say; a failure can never break the poll).

2. **Source of pending options — an in-process "latest search" slot.**
   `_SESSION_FLIGHT_OPTIONS` is session-keyed and the trip does not exist until
   `book_flight`, so a trip-keyed read needs a bridge: `search_flights_impl`
   additionally records `(session_id, options, recorded_at)` into a module-level
   latest-search slot in `concierge.py`; `book_flight_impl` clears it. The
   status endpoint surfaces the slot as `pending_options` when the slot's
   session is pinned to the requested trip **or has no pin yet** (the
   pre-booking window). Consistent with the standing single-instance,
   in-process-memory decision; accepted demo-grade looseness: with two
   simultaneous unpinned conversations, an unrelated trip's poll could briefly
   show the other session's candidates — a non-issue for a single-operator demo.

3. **Cold start**: with no trip displayed, the page shows an awaiting state,
   keeps the selector populated from `GET /v1/itinerary/trips`, and re-resolves
   `latest_trip_id`; candidates render only while some trip is displayed. A
   truly empty database (no trips ever) is out of demo scope — the deployed
   dataset always has prior trips.

4. **Full reservation on screen** (user decision): not just the flight — hotel,
   ground transportation, dining, and experience cards render too, so the
   audience sees the whole trip that will later break. Card treatment reuses the
   itinerary page's five-card / six-status visual hooks.

5. **Look and feel = the mockup** (user decision 2026-07-12, superseding the
   interview's "match itinerary page" answer): the design source of truth for
   this page *and* the Phases 22–23 dashboard is
   `about/ui_ideas/ui_mockup_2026_07_09.png`. Phase 21 establishes the shared
   visual language — the app header (product name + current-traveler +
   status pill), the left rail (traveler-context card, trip timeline with
   per-leg status icons, collapsible recent-trips), the card/pill styling, and
   the right-column panel shapes (the "AI Recommended"-style option card is
   the template for the candidates panel). The itinerary page contributes only
   its *technical* conventions (self-contained static page, no build step,
   per-request HTML read, `?code=` handling) — not its visuals. Mockup
   surfaces that belong to later phases stay out (see Not in scope).
   Stage-readability still applies (large type, high contrast — Phase 17
   polish standards).

## Context

- **Tone**: on-screen copy is traveler-voiced and speakable-adjacent — matches
  the itinerary page's repair-feed voice; times labeled "PT" (never "PST");
  prices rounded like the Concierge speaks them; no airline codes in headline
  copy.
- **Design source of truth**: `about/ui_ideas/ui_mockup_2026_07_09.png` —
  layout grid, card/pill styles, color language, header/left-rail structure.
- **Stack pointers**: `backend/api/itinerary_ui.py` + `assets/itinerary/page.html`
  (technical conventions to clone), `backend/api/concierge.py:252` (`_SESSION_FLIGHT_OPTIONS`),
  `_details_for`/`_item_detail` (the additive-block precedent),
  `backend/api/access_gate.py` (page-shell allowlist), `web_call.py`
  (`?trip_id=`/`vbSetTrip` contract to mirror).
- **Constraints**: no new dependencies; hermetic tests (no GCP creds, no
  `OPENAI_API_KEY`, repositories mocked at the helper boundary); works in
  `SABRE_MODE=mock` (the deterministic three-option search is what the panel
  shows in rehearsal); rehearsal path is `/v1/web_call/` + curl on the `/query`
  seam — no outbound-call quota spent.
