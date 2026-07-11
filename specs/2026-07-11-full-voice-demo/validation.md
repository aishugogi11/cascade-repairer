# Validation — Talk to My Trip: full voice demo experience (Phase 17)

## Automated

Run the full suite **in the container** (standing rule):

```
docker compose exec backend pytest
```

All tests pass, including the new ones. Specific assertions that must exist and pass:

**Access gate**
- With `DEMO_ACCESS_CODE` unset, a normally-gated route (e.g. `POST /v1/web_call/query`) returns
  its usual response — fail-open for dev/CI.
- With the env var set: missing header → 401; wrong code → 401; correct `X-Access-Code` → passes.
- With the env var set, every allowlisted surface stays public: `GET /v1/legal/privacy`,
  `GET /v1/legal/support`, `POST /v1/auth/validate`, and the four `GET` HTML pages
  (`/v1/web_call/`, `/v1/mobile_voice/`, `/v1/itinerary/`, `/v1/demo/`).
- `POST /v1/auth/validate` returns 200 `{valid: true}` for the right code, 401 for a wrong one.
- Each of the four pages contains the `?code=` / `localStorage` / header-attach wiring in its JS.

**Guided booking**
- `search_flights_impl` stores 2–3 options in the per-session store and returns a spoken-style
  numbered summary; a failing `flight_search` yields a speakable string, never an exception.
- `book_flight_impl` with no prior search or a bad option number returns a speakable error and
  writes no rows.
- `book_flight_impl` on a valid option creates the `Trip`, flight `ItineraryItem`, and `Booking`
  rows (mocked repositories), **replaces** `_SESSION_TRIPS[session_id]`, and clears the options.
- `complete_trip_impl` with no pinned trip returns a speakable error; with a pinned trip it
  creates the four remaining items sequentially with ~1.5s spacing (asserted on sleep calls, not
  wall clock).
- `build_agent` exposes `search_flights`, `book_flight`, `complete_trip` — and no longer
  `book_trip`; `BASE_INSTRUCTIONS` carries the guided script and the untouched disruption rules.

**Detail payload**
- `/status/{trip_id}` items with a booking carry `detail` (`why_chosen`, `price_delta`,
  `impact`); items without omit the key; all pre-existing status-contract tests pass unchanged.

**Hermeticity**: suite runs with no GCP credentials and no `OPENAI_API_KEY`; CI (pytest inside
the built image) gates the `vb/dev` deploy.

## Manual

**Browser rehearsal first — zero VB quota.** All of Act 1 and Act 2 verify from a desktop
browser before touching the phone (remember: Dark Reader can distort page colors — check with it
off).

1. **Gate walkthrough (deployed):** with `DEMO_ACCESS_CODE` set on Cloud Run, hit
   `POST /v1/web_call/query` with no header → 401. Open `/v1/web_call/` with no `?code=` → page
   renders, calls fail cleanly. Re-open with `?code=<right code>` → voice session works;
   reload without the param → still works (localStorage).
2. **Act 1 in the browser:** on `/v1/web_call/?code=…` say "book me a trip to San Francisco,
   July 17 to 19" → agent asks/confirms, speaks 2–3 options → "option one" → spoken booking
   confirmation → on `/v1/itinerary/?code=…` the flight card appears, then hotel/ride/dinner/
   experience materialize one by one (~1.5s apart). Confirm rows in BigQuery (`trips`,
   `itinerary_items`, `bookings`).
3. **Act 2 in the browser:** trigger disrupt from `/v1/demo/` → flight flips broken, five cards
   run repairing → fixed < 60s while asking the agent "how are the repairs coming?" mid-repair
   and getting a live, specific answer.
4. **iOS gate:** fresh install → gate screen before anything else; wrong code → friendly error,
   no crash; right code → main screen; relaunch → no gate; rotate the code server-side → next
   API call returns the app to the gate.
5. **Three acts on device** (`SABRE_MODE=mock`; one run = 2 outbound calls, 10/day quota):
   - **Act 1:** book by voice on the phone — options spoken, picked by voice, cards materialize
     one by one with the spring insert.
   - **Act 2:** triple-tap the orb → cascade renders natively < 60s while conversing; orb shows
     the repairing state; recovery timer runs.
   - **Act 3:** the demo phone rings with the proactive recovery call; recording archived
     (`GET /v1/outbound_call/recording/{session_id}`).
6. **Sheet & gestures:** tap a fixed card → RecommendationSheet shows why-chosen / price delta /
   downstream impact (or the static fallback if `detail` was cut); long-press orb → trip
   selector lists recent trips and switching repoints the timeline; no visible demo buttons
   anywhere in the app.
7. **Edge cases:** "option four" when three were offered → graceful spoken correction;
   "book me a trip" while a trip is already pinned → agent declines and offers help instead of
   re-searching; backend restart mid-session → app recovers on next poll; webview page opened
   in a desktop browser (no `window.webkit`) → events no-op to console, no errors.
8. **Deployment health:** `GET /v1/hello/gcp_check` green on Cloud Run; verify
   `min-instances=1`/`max-instances=1` (in-process session state).

## Tone check

- Every new agent line is **speakable**: option summaries are 2–3 short clauses, prices rounded,
  no airline/fare codes, no markdown artifacts in spoken text; every tool failure path returns a
  speakable sentence (a raising tool kills the spoken turn).
- Access-gate copy is one line, demo-honest, no account language ("Enter the access code from
  your demo invitation"); the error is friendly, not scolding.
- Sheet copy matches the mockup's register: one-sentence "why chosen," one-sentence downstream
  impact — glanceable, not paragraphs.

## Definition of done

- All automated assertions above pass in the container and in CI; the `vb/dev` deploy is green
  with `DEMO_ACCESS_CODE` set.
- Acts 1–3 verified on a physical iPhone against the deployed backend in `SABRE_MODE=mock`,
  including the gate on fresh install.
- The recommendation sheet, hidden gestures, and stage polish are in the update build — or their
  cut lines are consciously taken and noted in the roadmap.
- The app-update build is archived and uploaded to App Store Connect with the access code in the
  App Review notes (submission timing rides behind the Phase 16 first review).
- Phase 17 marked `[x] COMPLETE` in `specs/roadmap.md`.
