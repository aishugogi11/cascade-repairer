# Validation — Talk to My Trip: App Store submission MVP (Phase 16)

## Automated (hermetic — no GCP creds, no `OPENAI_API_KEY`, no live VB calls)

Run the way CI does, in the container:

```bash
docker compose exec backend python -m pytest tests/ -v
```

Required assertions (new tests, alongside the full existing suite staying green):

- **Legal pages**: `GET /v1/legal/privacy` and `GET /v1/legal/support` return 200 `text/html`;
  the privacy page mentions microphone/audio processing and a contact; the support page links
  to the privacy page.
- **Booking tool**: `book_trip_impl` calls `create_seed_trip` (mocked) off the event loop and
  **replaces** `_SESSION_TRIPS[session_id]` with the new trip's context; a failing
  `create_seed_trip` returns a speakable error string (no exception escapes, nothing cached);
  `build_agent` exposes both `book_trip` and `fix_trip`; `BASE_INSTRUCTIONS` (or the built
  instructions) carry the book-when-no-trip rule.
- **Headless page**: `GET /v1/mobile_voice/` returns 200; body contains `vbConnect`,
  `vbDisconnect`, `messageHandlers.vb`, and `/v1/web_call/query`; no visible-UI markers
  (no `<button>`).
- **No regressions**: existing web_call, concierge, sabre_tools, demo, and itinerary tests
  unchanged and passing.

iOS: the app builds without warnings-as-errors in Xcode (no CI for `ios/` — build success +
manual QA below stand in; the standing no-browser-automation decision extends to no
XCUITest requirement for this phase).

## Manual walkthrough

**Browser-first (no quota, no device needed) — proves the backend before iOS exists:**

1. Local or deployed `/v1/web_call/`: connect, say "plan me a trip to San Francisco" → agent
   confirms and books; BigQuery gains 1 `trips` + 5 `itinerary_items` + 2 `bookings` rows;
   agent then answers "where am I staying?" from the **new** trip (pin replaced).
2. Same session: "my flight was canceled — fix my trip" → `fix_trip` launches; agent keeps
   answering while repairs run; items reach `fixed`.
3. `/v1/mobile_voice/` in a desktop browser: blank page, no JS errors; `window.vbConnect`
   defined; events logged to console (webkit handler absent → no-op path).
4. `/v1/legal/privacy` + `/v1/legal/support` render, read correctly, no external requests.

**On device (the submission build):**

5. Fresh install → tap orb → **exactly one** mic prompt → conversation with the Concierge
   works over the deployed backend.
6. Say the magic utterance → agent confirms → five cards materialize on the timeline (poll
   picks up the new trip without app restart).
7. Tap "Simulate flight cancellation" → flight card flips broken; say "fix my trip" → all five
   cards run repairing → fixed in < 60s (recovery timer shown) **while** asking "how's it
   going?" mid-repair gets a live spoken answer.
8. Reviewer-path fallback: break the flight, don't speak, tap "Repair now" → cascade completes.
9. Edge cases: mic permission denied → app stays usable (timeline + demo buttons work, orb
   shows a clear "microphone needed" state); airplane-mode poll failure → no crash, polling
   resumes; backgrounding during repair → timeline correct on return.

## Submission checks (the goal — verify before and at submit)

- Deployed URLs live on Cloud Run **before** they're entered in App Store Connect; Cloud Run
  `min-instances=1` confirmed.
- Archive built with Xcode 26 / iOS 26 SDK; Validate passes; upload succeeds.
- App Store Connect complete: metadata + screenshots (required iPhone sizes, real UI), privacy
  nutrition labels (Audio Data + transcripts, not linked, no tracking), 2026 age-rating
  questionnaire (AI assistant questions answered), export compliance NO, App Review notes with
  the reviewer script and no-login statement.
- Status reaches **"Waiting for Review"** — that status is this phase's definition of shipped.

## Tone check

- Agent booking copy: spoken-style, 1–2 short sentences, no markdown/ids; confirmation narrates
  the five parts and dates.
- App Store metadata: consumer language; no "hackathon", "demo", "test", "MVP" anywhere
  user-facing (App Review notes are the place for that context).
- Privacy/support pages: plain-language, accurate to what the backend actually does (mic audio
  → Vocal Bridge; transcripts + trip data → BigQuery; no accounts/ads/tracking/sale).

## Definition of done

1. All automated assertions above pass in the container; CI (pytest in the built image) green
   on the PR; backend merged to `vb/dev` and live on Cloud Run.
2. Manual walkthrough steps 1–8 pass (9's edge cases noted if deferred, not silently skipped).
3. The build is **submitted to App Review** ("Waiting for Review" in App Store Connect) with
   all submission checks satisfied.
4. Phase 16 marked `[x] COMPLETE` in `specs/roadmap.md`; submission id/build number recorded in
   this spec directory.
