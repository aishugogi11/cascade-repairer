# Roadmap

High-level implementation order for the hackathon-ready foundation. Hackathon day is **July 18, 2026** — every phase before the last must land ahead of it. Each phase is narrowly scoped and becomes a feature branch (`vb/feature/<feature-name>`); mark a phase `[x] COMPLETE` in its heading when done.

Phases appear in **execution order** — the first heading not marked `[x] COMPLETE` is what `sdd-feature-spec` picks up next. Phase numbers are historical IDs, not ordering: Phase 18 runs before Phase 17's remainder. Completed phases live in [changelog.md](changelog.md); deferred phases (14 → 13 → 15) wait in [BACKLOG.md](BACKLOG.md) behind everything here. `IOS_PLAN.md` is the umbrella plan.

**State as of 2026-07-12 (evening):** Phase 18 is merged and deployed (PR #29, image `c897f15`) and the live web-call rehearsal confirmed Act 1 guided booking works end to end. That same validation pass surfaced two hotfixes — timezone display is wrong on every surface, and the iOS app's voice session can't reach the trip on its own screen — promoted (TODO triage 2026-07-12) as **Phase 19**, which now gates Phase 17's remaining device QA and App Store submission. That submission is the **first** one (the Phase 16 build was never submitted); runbook: `IOS_DEPLOY.md`.

## Phase 18: Unpin fresh sessions — make Act 1 guided booking reachable [x] COMPLETE (implementation; manual QA pending)

Fresh sessions auto-pin the backend's most recently created trip (`ensure_trip_context`, `backend/api/concierge.py`), and the guided-booking instructions then forbid `search_flights`/`book_flight` — so voice-booking a new trip fails whenever the trips table is non-empty, which it always is. Not a Sabre issue: fully broken in `SABRE_MODE=mock`. One branch via `sdd-feature-spec`; rehearse via `/v1/web_call/?code=…`.

Scope (ships together):

- **Drop the latest-trip auto-pin** (decision 2026-07-12; supersedes the 2026-07-11 replan's
  "confirm once, then search while pinned" approach): `ensure_trip_context` pins only on an
  explicit `trip_id` (disrupt flow) or after `book_flight` (which already pins the new trip).
  New sessions start unpinned so guided booking runs; Acts 2/3 keep working via explicit
  `trip_id`. Accepted loss: cold-session "ask about my existing trip" — the demo reaches
  existing trips through disrupt anyway.
- **Inject today's date into the agent context**: instructions ask the model to turn "leaving
  on Monday" into `YYYY-MM-DD`, but nothing supplies today's date, so relative dates can't
  resolve.
- **End-to-end regression test**: `answer_query` → `ensure_trip_context` with a **non-empty**
  trips table must still reach `search_flights` — the coverage gap that let this ship
  (existing tests call the tool impls directly with mocked repos).

<details>
<summary>Original TODO entry (verbatim, raised 2026-07-12) — full diagnosis, transcripts, and evidence; kept here because TODO.md is gitignored</summary>

> **TODO:**
>
> ## BUG — Guided booking (Act 1) is unreachable: `ensure_trip_context` auto-pins the latest existing trip
>
> **Raised:** 2026-07-12 (Josh, live browser rehearsal on deployed `vocal-bridge-be-dev`)
> **Severity:** Blocker for Act 1 (book a brand-new trip by voice). This is why `/v1/itinerary/`
> and the iOS app always show the default/seed trip and why a voice booking never "hooks up."
> **Not related to Sabre.** Real Sabre keys (arriving 7/14) change nothing here — the flow is
> fully broken in `SABRE_MODE=mock`, and the mock already returns flights unconditionally.
>
> ### Symptom
> On the deployed `/v1/web_call/` page, asking the agent to book a new trip fails. The agent
> stalls with filler and then improvises an apology instead of searching flights. Two live
> transcripts (2026-07-12):
>
> - *"I would like to travel from Minneapolis to Dallas, leaving on Monday."* →
>   *"Let me look that up… still gathering… almost there… I'm sorry, it looks like the response
>   came back empty. Could you clarify what kind of travel you're looking for — flights, trains,
>   or something else?"*
> - *"I'd like to book a flight. What's available for me?"* → *"Minneapolis to San Francisco"* →
>   *"Still gathering the flight options… I'm still waiting on the details…"* (never books).
>
> An agent actually running the guided-booking tools + instructions would never offer "trains" or
> stall like this — the tell that the booking path is suppressed, not failing.
>
> ### Root cause (confirmed in code + deployed logs)
> 1. Every `/v1/web_call/query` turn → `concierge.answer_query` → **`ensure_trip_context(session_name)`**
>    (`backend/api/concierge.py:638`).
> 2. For a new session with no explicit `trip_id`, `ensure_trip_context` runs
>    (`backend/api/concierge.py:149-158`):
>    ```sql
>    SELECT * FROM trips ORDER BY created_at DESC LIMIT 1
>    ```
>    The single most-recently-created trip in the **entire** BigQuery table wins — regardless of
>    session/user/who booked it — and gets pinned to the session.
> 3. `build_agent` then sets `trip_line = trip_context.summary` instead of `_NO_TRIP_LINE`
>    (`backend/api/concierge.py:616`), so the agent's instructions now assert the traveler
>    already has a booked trip.
> 4. The guided-booking instructions are gated on the opposite state
>    (`backend/api/concierge.py:65-76`): booking fires only *"When there is no booked trip,"* and
>    *"**Never call `search_flights` or `book_flight` when a trip is already booked** — offer
>    `fix_trip` or answer questions about the existing trip instead."*
>
> Net: because the dev BigQuery always has a recent seed/rehearsal trip, every fresh session is
> pinned to it, and the agent is instructed **never to book**. Act 1 is unreachable whenever the
> trips table is non-empty.
>
> ### Evidence
> - `search_flights_impl('diag', 'MSP', 'DFW', '2026-07-13')` in the container returns three
>   speakable options and stores them — **the tool works in isolation.** The mock
>   (`backend/api/sabre/mock_client.py:40-126`) returns three flights for any route/date; no
>   hard-coded flights need to be added.
> - Deployed logs (revision `vocal-bridge-be-dev-00069-kpp`, 2026-07-12): every
>   `POST /v1/web_call/query` returns **200 OK, no tracebacks**, while status polling runs against
>   the pre-existing seed trip `556641ba-70f6-4ebb-b10f-47a3a63fbd8d` — proving the table is
>   non-empty and the pin latched onto the seed trip, not a new booking.
>
> ### Why tests stayed green
> Concierge tests call `search_flights_impl` / `book_flight_impl` directly with mocked repos; they
> never exercise `answer_query` → `ensure_trip_context`. The "no trip → book" path only triggers on
> an **empty** trips table, which hasn't been true since the first dress rehearsal.
>
> ### Underlying design tension
> - **Act 1 (book new)** needs the session to start with **no** pinned trip.
> - **Act 2/3 (disrupt & repair)** needs a pinned **existing** trip — and the disruption/outbound
>   flow already pins **explicitly via `trip_id`** (`backend/api/concierge.py:139-141`). The
>   `ORDER BY created_at DESC` auto-pin is only a convenience fallback for "answer questions about
>   my trip" without a UUID — and that fallback is exactly what kills Act 1.
>
> ### Proposed fix (for triage — not yet decided)
> **Preferred:** drop the latest-trip auto-pin. `ensure_trip_context` pins only when given an
> explicit `trip_id` (disrupt flow) or after `book_flight` (which already pins the new trip). New
> sessions start unpinned, so guided booking runs; Act 2/3 keeps working via explicit `trip_id`.
> Only loss: "ask about my existing trip" from a cold session with no context — which the demo
> always reaches through disrupt (explicit `trip_id`) anyway.
>
> **Rejected:** intent-gating the auto-pin (skip it when the turn "looks like" a booking request)
> — brittle intent detection, still shadows fresh sessions.
>
> ### Follow-on considerations surfaced while diagnosing
> - **Today's date is never injected into the agent context** (`backend/api/concierge.py` has no
>   `date.today()`/`now()` outside a formatting helper). Instructions tell the model to turn
>   "leaving on Monday" into a `YYYY-MM-DD` date, but an LLM can't resolve relative dates without
>   knowing today. Fix alongside the pin so Act 1 date handling is reliable.
> - Add a test that exercises `answer_query`/`ensure_trip_context` end-to-end with a **non-empty**
>   trips table and asserts a booking request still reaches `search_flights` — the coverage gap
>   that let this ship.

</details>

## Phase 19: Validation hotfixes — Pacific-time discipline & pin the displayed trip [x] COMPLETE (implementation; manual QA pending)

Two bugs surfaced by the 2026-07-12 post-Phase-18 validation pass (live web call + Talk to My Trip device check), promoted per Josh as one combined hotfix phase — both must land before Phase 17's device QA, which would hit them immediately. One branch via `sdd-feature-spec`.

Scope (ships together):

- **Timezone discipline across the codebase** (decision 2026-07-12): **the database stores UTC;
  the edges speak Pacific.** Josh booked the 6:15 AM MSP→DFW flight by voice; the itinerary page
  showed 1:15 AM — `_booking_writes`/`_completion_items` stamp wall-clock times as UTC and the
  page renders browser-local. Fix at ingest (declare mock Sabre times Pacific wall-clock, convert
  to UTC at write — `concierge.py`, seed items in `sabre_tools.py`) and at display (every user
  surface renders `America/Los_Angeles` explicitly: itinerary `page.html`, iOS formatters, a
  sweep of demo/web_call pages; label "PT"/"Pacific time", never "PST" — it's PDT in July).
  Existing dev rows were written under the old fiction and will display ~7 h off — cosmetic,
  reseed or ignore.
- **Voice session pins the trip the app is displaying**: Phase 18's documented accepted loss
  surfaced on device — the iOS UI shows the trip (server-side latest-trip reads were kept) but
  the in-app voice agent starts unpinned and denies it, which also breaks in-app "my flight was
  cancelled, fix it" on pre-existing trips. Thread the app's known `trip_id` through the existing
  explicit-pin seam (Phase 12): iOS → `/v1/mobile_voice/?trip_id=…` → the `/v1/web_call/query`
  delegation → `concierge.answer_query` → `ensure_trip_context(session, trip_id=…)`. Deliberate
  context, not the removed latest-trip fallback — fresh users with no trips still start unpinned
  and get guided booking. Spec decision to settle: re-pin semantics when the displayed trip
  changes mid-session (suggested: only pin when the session has no pin yet, so a just-booked
  trip's pin is never clobbered). Same seam serves `/v1/web_call/?trip_id=…` for desktop parity.

<details>
<summary>Original TODO entries (verbatim, raised 2026-07-12) — kept here because TODO.md is gitignored</summary>

> **TODO:**
>
> ## HOTFIX — Timezone discipline across the codebase: store UTC, display/speak Pacific
>
> **Raised:** 2026-07-12 (Josh, comparing the live web-call transcript against
> `/v1/itinerary/?trip_id=…`). **Priority: hotfix** — Josh wants this implemented across the
> entire codebase ahead of normal triage order.
>
> **The bug that exposed it:** Josh booked the 6:15 AM MSP→DFW flight by voice; the itinerary
> page showed 1:15 AM. `_booking_writes` (`backend/api/concierge.py`) stamps the mock's
> wall-clock departure time with `tzinfo=timezone.utc` (6:15 stored as 06:15 UTC), and
> `page.html` renders `new Date(ts).toLocaleString()` in the **browser's** timezone (CDT for
> Josh = −5 h). Every card is shifted; every viewer in a different timezone sees different
> times; none match what the agent spoke.
>
> **Decision (Josh, 2026-07-12):** everything displayed or spoken to a user is **Pacific time**
> (`America/Los_Angeles` — PDT in July, so label it "PT"/"Pacific time", never hardcode "PST"),
> regardless of where the user sits. Storage stays honest UTC instants:
>
> > **The database stores UTC. The edges speak Pacific.**
>
> - **Storage:** BigQuery `TIMESTAMP` is a UTC instant by definition — never store wall-clock
>   fiction stamped as UTC. Nothing between storage and display needs timezone knowledge.
> - **Ingest rule (the single missing declaration):** mock Sabre times are timezone-less
>   wall-clock fiction — declare them **Pacific wall-clock** and convert Pacific→UTC at write.
>   Real Sabre responses carry offsets (`06:15:00-05:00`) and convert naturally.
> - **Display rule:** every user surface renders `America/Los_Angeles` explicitly, never
>   browser/device-local.
>
> **Touch points:**
> - `backend/api/concierge.py` — `_booking_writes` + `_completion_items`: build `start_ts`/
>   `end_ts` with `ZoneInfo("America/Los_Angeles")` instead of `timezone.utc`.
> - `backend/api/sabre_tools.py` — `_SEED_ITEMS` (same wall-clock-as-UTC pattern).
> - `backend/api/assets/itinerary/page.html` — `toLocaleString`/`toLocaleTimeString` calls
>   (~lines 325–400): add `timeZone: 'America/Los_Angeles'`, label times "PT" (includes the
>   repair-feed clock).
> - `ios/TalkToMyTrip/` — date formatters (`TripManager`/card views): fixed
>   `TimeZone(identifier: "America/Los_Angeles")`.
> - Voice readback (`_spoken_clock`/`FlightOption`) — fine for mock once mock times are defined
>   as Pacific (spoken == stored wall clock); when real Sabre lands, convert to Pacific before
>   speaking.
> - Check other user-facing timestamps (demo page, web_call page) for browser-local rendering.
>
> **Known cosmetic fallout:** existing dev-table rows were written wall-clock-as-UTC, so after
> the fix they display ~7 h off. Rehearsal junk — let it age out or reseed; don't chase it.
>
> ## HOTFIX — iOS voice session can't reach the trip the app is displaying
>
> **Raised:** 2026-07-12 (Josh, Talk to My Trip device check right after Phase 18 deployed).
> **Priority: hotfix** — Josh wants this handled right away, together with the timezone fix
> above; it blocks the iOS demo walkthrough (device QA is exactly what Phase 18 unblocked).
>
> **What happened:** the app's UI shows the seed trip (TripManager polls
> `GET /v1/sabre_tools/latest_trip_id` + the status endpoint — server-side latest-trip *reads*
> were deliberately kept), but the in-app voice agent says there's no trip. This is Phase 18's
> **documented accepted loss** surfacing on device, not a regression: fresh Concierge sessions
> no longer auto-pin the backend's latest trip, and nothing in the app's voice path passes a
> `trip_id` — `POST /v1/web_call/query` carries only `session_name` and `query`.
>
> **Goes past Q&A:** in-app voice can't do anything with a pre-existing trip — including "my
> flight was cancelled, fix it" (`fix_trip` needs the session pin). Still working: voice-booking
> a new trip in-session (pins it; Q&A and cancel-then-fix then work), and the triple-tap disrupt
> gesture (server-side cascade, doesn't need the voice pin).
>
> **Proposed fix (small; does NOT reopen the Phase 18 bug):** the app already knows which trip
> it's displaying — let it tell the voice session. Thread the trip_id through the existing
> explicit-pin seam (`ensure_trip_context(session, trip_id=…)`, the Phase 12 seam, built for
> exactly this):
>
> - iOS loads `/v1/mobile_voice/?trip_id=…` (or includes trip_id in the query POST body);
> - the mobile_voice page's `useAIAgent → POST /v1/web_call/query` delegation carries it;
> - `web_call.py` passes it through to `concierge.answer_query` → `ensure_trip_context`.
>
> This is *deliberate* context ("pin the trip on my screen"), completely different from the
> removed fallback ("silently grab whoever's latest trip") — a fresh user with no trips still
> starts unpinned and gets guided booking. Decide the re-pin semantics while speccing: what
> happens when the app's displayed trip changes mid-session (e.g. after an in-session booking,
> or the long-press trip selector) — probably only pin when the session has no pin yet, so a
> just-booked trip's pin is never clobbered. Same seam would serve the web pages
> (`/v1/web_call/?trip_id=…`) for parity and desktop testing.

</details>

## Phase 17: Talk to My Trip — full voice demo experience

**Shipped 2026-07-11** (`vb/dev`, deployed): guided multi-turn voice booking on the Concierge, the `DEMO_ACCESS_CODE` gate across backend/pages/iOS, the additive `detail` payload + native recommendation sheet, hidden demo gestures, stage-readability polish, and the App-Review privacy hardening. 290 backend tests green; simulator-verified end to end.

**Still open:** device QA (2026-07-11) exposed the Act 1 blocker, carved out as **Phase 18 above** (landed 2026-07-12); the post-Phase-18 validation pass carved out the two hotfixes in **Phase 19 above** — it must land first. Then, in order:

- **iOS empty-start onboarding** (promoted from TODO 2026-07-11): don't auto-resolve
  `latest_trip_id` on cold start — show the "tap the orb" empty state; remember this
  device's own trip in UserDefaults once booked; keep the after-reply re-resolve and
  the long-press selector.
- **Device QA:** the three acts on a physical iPhone (`SABRE_MODE=mock`; one run =
  2 outbound calls, 10/day quota), sheet & gestures, edge cases (validation.md § 7).
- **Submit:** archive → upload → submit per `IOS_DEPLOY.md` (access code in the review
  notes; the deployed privacy policy already matches).
- Standing pre-event items: verify Cloud Run `min/max-instances=1`; flip
  `SABRE_MODE=real` when keys arrive **Monday 7/14**; review the hardcoded dev
  Cloud Run URL in `APIConfig.swift`.
