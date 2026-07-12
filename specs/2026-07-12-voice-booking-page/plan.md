# Plan — Voice Booking Page (Phase 21)

Task groups are independently implementable, in dependency order.

## 1. Backend — pending options on the status payload

1.1 Add a module-level latest-search slot to `backend/api/concierge.py`
    (session_id, the stored `FlightOption` list, `recorded_at`), written by
    `search_flights_impl` right where it fills `_SESSION_FLIGHT_OPTIONS`, and
    cleared by `book_flight_impl` on a successful booking (alongside the
    existing `_SESSION_FLIGHT_OPTIONS.pop`).

1.2 In `backend/api/itinerary_ui.py`, extend `trip_status` with an additive
    `pending_options` block: present only when the slot is non-empty and its
    session is pinned to the requested trip or unpinned; shape mirrors the
    speakable summary (option number, route, times in PT, rounded price) plus
    `recorded_at`. Best-effort like `detail` — any failure omits the block,
    never breaks the poll.

1.3 Tests (`backend/tests/`): slot recorded by search, cleared by booking;
    status payload carries `pending_options` in the pinned and unpinned cases;
    payload omits the block when the slot is empty or belongs to a session
    pinned to a different trip; a raising slot-read still returns a valid
    status payload. Hermetic — repositories mocked at the helper boundary.

## 2. Page shell & route

2.1 Create `backend/api/booking_ui.py`: `GET /v1/booking/` returning
    `assets/booking/page.html` read per request — clone the thin-router shape
    of `itinerary_ui.itinerary_page`.

2.2 Register the router in the FastAPI app alongside the other page routers;
    add the `GET /v1/booking/` shell to the access-gate public allowlist in
    `backend/api/access_gate.py`.

2.3 Tests: shell served without a code (allowlisted), gated JSON endpoints
    still 401 without `X-Access-Code` when the env var is set.

## 3. Page content — mockup frame & reservation display

3.1 `backend/api/assets/booking/page.html`, technical conventions cloned from
    the itinerary page (`?code=` handling, 1.5 s status poll, `?trip_id=`
    seeding, `window.vbSetTrip()`), **visuals built to
    `about/ui_ideas/ui_mockup_2026_07_09.png`**: app header (product name,
    current-traveler, status pill), left rail + main-content grid, the
    mockup's card/pill/color language. This CSS frame is written to be lifted
    by Phases 22–23.

3.2 Left rail per the mockup: traveler-context card (name, airline, booking
    ref, route summary), trip timeline with per-leg status icons, and the
    collapsible Recent Trips panel backed by `GET /v1/itinerary/trips`
    (PT labels, newest-first).

3.3 Current flight card, prominent: route, PT times, rounded price, status,
    `detail` fields (why chosen / price delta / impact) when present.

3.4 Reservation cards for hotel, ground, dining, experience with the six-status
    visual hooks (mockup status-icon treatment), materializing as
    `complete_trip` lands them poll by poll.

3.5 Awaiting/cold-start state plus `latest_trip_id` re-resolution so a trip
    booked mid-conversation appears without a reload.

## 4. Page content — candidate options panel

4.1 Render `pending_options` as a "what this booking could be" panel styled on
    the mockup's right-column "AI Recommended" option card (arrival headline,
    route/stops line, price treatment) while the block is present: numbered
    options matching what the Concierge speaks (route, PT times, rounded
    price, no airline codes).

4.2 Clear the panel when the block disappears (booking happened); the booked
    flight then arrives through the normal items path within one poll —
    visually hand off candidate panel → current flight card.

## 5. Validation & docs

5.1 Run the full suite; walk `validation.md` (curl rehearsal of
    search → book → complete against the `/query` seam with the page open).

5.2 Update `specs/tech-stack.md` voice-layer section with the new page and the
    additive `pending_options` contract; mark Phase 21 `[x] COMPLETE` in
    `specs/roadmap.md` when validation passes.
