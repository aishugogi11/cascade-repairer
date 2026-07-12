# Roadmap

High-level implementation order for the hackathon-ready foundation. Hackathon day is **July 18, 2026** — every phase before the last must land ahead of it. Each phase is narrowly scoped and becomes a feature branch (`vb/feature/<feature-name>`); mark a phase `[x] COMPLETE` in its heading when done.

Phases appear in **execution order** — the first heading not marked `[x] COMPLETE` is what `sdd-feature-spec` picks up next. Phase numbers are historical IDs, not ordering: Phase 18 runs before Phase 17's remainder. Completed phases live in [changelog.md](changelog.md); deferred phases (14 → 13 → 15) wait in [BACKLOG.md](BACKLOG.md) behind everything here. `IOS_PLAN.md` is the umbrella plan.

**State as of 2026-07-12:** the Phase 17 build is on `vb/dev` and deployed (PR #26, access gate armed), but Act 1 — booking a new trip by voice — is unreachable. The 2026-07-12 browser rehearsal traced it to the latest-trip auto-pin in `ensure_trip_context`; the fix is **Phase 18**, which gates Phase 17's remaining device QA and App Store submission. That submission is the **first** one (the Phase 16 build was never submitted); runbook: `IOS_DEPLOY.md`.

## Phase 18: Unpin fresh sessions — make Act 1 guided booking reachable

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

## Phase 17: Talk to My Trip — full voice demo experience

**Shipped 2026-07-11** (`vb/dev`, deployed): guided multi-turn voice booking on the Concierge, the `DEMO_ACCESS_CODE` gate across backend/pages/iOS, the additive `detail` payload + native recommendation sheet, hidden demo gestures, stage-readability polish, and the App-Review privacy hardening. 290 backend tests green; simulator-verified end to end.

**Still open:** device QA (2026-07-11) exposed the Act 1 blocker, since diagnosed and carved out as **Phase 18 above** — it must land first. Then, in order:

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
