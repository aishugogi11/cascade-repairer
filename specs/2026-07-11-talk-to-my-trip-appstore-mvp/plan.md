# Plan — Talk to My Trip: App Store submission MVP (Phase 16)

Order is deliberate: backend groups (1–3) first so the deployed URLs and voice flow exist before
the iOS build and the App Store Connect metadata need them; groups 4–5 are the app; group 6 is
the submission itself — the phase's actual goal. Groups 1, 2, 3 are independently implementable;
4 depends on 3; 5 depends on 4; 6 depends on everything deployed.

## 1. Backend — legal & support pages

1.1 Create `backend/api/legal.py` router with `GET /privacy` and `GET /support`, serving
    self-contained static HTML from `backend/api/assets/legal/privacy.html` and `support.html`
    (read per request, the `/v1/itinerary` pattern — `uvicorn --reload` doesn't watch HTML).
1.2 Write `privacy.html`: what the app does; mic audio is streamed to Vocal Bridge for
    speech processing; conversation transcripts and trip data are stored (BigQuery) to operate
    the service; no accounts, no ads, no tracking, no sale of data; data deletion contact;
    effective date; contact email (Josh / Zen Software).
1.3 Write `support.html`: app name + one-paragraph description, how to get help (contact
    email), link to the privacy page.
1.4 Register the router in `backend/main.py` under `prefix="/v1/legal"`.
1.5 Tests (`backend/tests/test_legal.py`): both routes return 200 `text/html`; privacy page
    mentions microphone/audio and contact; support page links to privacy.

## 2. Backend — magic-utterance booking on the Concierge

2.1 In `backend/api/concierge.py`, add `book_trip_impl(session_id, destination, title)` —
    the tool body kept a plain function for tests (the `fix_trip_impl` pattern): call
    `create_seed_trip` (import from `api.sabre_tools`) via `asyncio.to_thread`, with the
    spoken destination folded into the trip title; every failure path returns a **speakable
    string**, never raises.
2.2 After a successful booking, build a fresh `TripContext` from the created trip and
    **replace** `_SESSION_TRIPS[session_id]` (the cached pin would otherwise keep the agent on
    the old/no-trip context for the rest of the session).
2.3 Return a narrated confirmation listing the five parts and dates ("Your trip is booked —
    flight to San Francisco on July 17th, hotel in Mountain View…"), per the spoken-copy rules.
2.4 Register the tool in `build_agent` as `book_trip` alongside `fix_trip`; extend
    `BASE_INSTRUCTIONS`: when there is **no booked trip** and the traveler asks to plan/book
    one, confirm destination in one short turn, then call `book_trip` immediately; never call
    it when a trip is already pinned (offer `fix_trip`/answers instead).
2.5 Tests (`backend/tests/` following the existing concierge test patterns): `book_trip_impl`
    calls `create_seed_trip` (mocked) and replaces the session pin; a failing
    `create_seed_trip` yields a speakable error and caches nothing; `build_agent` exposes both
    tools; instructions carry the booking rule.

## 3. Backend — headless mobile voice page (`/v1/mobile_voice`)

3.1 Create `backend/api/mobile_voice.py`: `GET /` serves a headless HTML page — the
    `web_call.py` page's VB wiring (same pinned CDN versions, same `tokenProvider` against
    `POST /v1/web_call/token`, same `useAIAgent → POST /v1/web_call/query` delegation,
    same-origin) with **no visible DOM** (blank body).
3.2 Expose `window.vbConnect()` / `window.vbDisconnect()` for native → webview control
    (`evaluateJavaScript`).
3.3 Post JSON events webview → native via `window.webkit.messageHandlers.vb.postMessage(...)`:
    `{type:"state", value}` on `ConnectionState` changes, `{type:"transcript", role, text}`
    per transcript line, `{type:"reply", text}` per backend reply, `{type:"error", message}`
    on token/query failures. Guard with a helper that no-ops (console.log) when
    `window.webkit` is absent — keeps the page smoke-testable in a desktop browser.
3.4 Register in `backend/main.py` under `prefix="/v1/mobile_voice"`.
3.5 Tests (`backend/tests/test_mobile_voice.py`): page serves 200; body contains `vbConnect`,
    `vbDisconnect`, `messageHandlers.vb`, and the `/v1/web_call/query` delegation URL; no
    `<button>`/visible-UI markers.

## 4. iOS app — scaffold & voice bridge (the fiddly part; spike first)

4.1 Create the Xcode project at `ios/TalkToMyTrip/` (SwiftUI app, iOS 17 minimum,
    iPhone-only, portrait, bundle id `com.zensoftware.talktomytrip`, Zen Software team), file
    layout per IOS_PLAN Track B: `TalkToMyTripApp.swift`, `Config/APIConfig.swift`,
    `Services/APIService.swift`, `Managers/`, `Views/`.
4.2 `APIConfig`: Cloud Run base URL (`https://vocal-bridge-be-dev-….run.app`) + a local
    override for simulator testing against `localhost:1019`.
4.3 `Views/VoiceWebView.swift` (`UIViewRepresentable`): `WKWebViewConfiguration` with
    `allowsInlineMediaPlayback = true`, `mediaTypesRequiringUserActionForPlayback = []`,
    script message handler named `"vb"`; `WKUIDelegate.requestMediaCapturePermission → .grant`
    (suppress the second mic prompt); loads `<base-url>/v1/mobile_voice/` (HTTPS required for
    `getUserMedia`); webview stays **in the hierarchy at 1×1pt, opacity 0** (detached webviews
    get throttled).
4.4 `Managers/VoiceManager.swift` (`@Observable`): owns the webview; decodes the `vb` messages
    into `connectionState`, `transcript`, and an orb state (`idle/connecting/listening/
    speaking`); `connect()`/`disconnect()` via `evaluateJavaScript`.
4.5 `Info.plist`: `NSMicrophoneUsageDescription` ("Talk to My Trip uses the microphone so you
    can speak with your trip assistant."); `ITSAppUsesNonExemptEncryption = NO`. Add
    `PrivacyInfo.xcprivacy` (no tracking; declare UserDefaults reason CA92.1 only if used).
4.6 **Bridge spike proof** (gates the rest of Track B work): on a real device, tap connect,
    grant mic once, hold a spoken conversation with the deployed Concierge from inside the app
    shell.

## 5. iOS app — trip timeline, booking flow, demo trigger

5.1 `Services/APIService.swift` (actor): `status(tripID:)` → `GET /v1/itinerary/status/{id}`,
    `latestTripID()` → `GET /v1/sabre_tools/latest_trip_id`, `recentTrips()` →
    `GET /v1/itinerary/trips`, `breakFlight(tripID:)` → `POST /v1/disruption/break_flight`,
    `repairTrip(tripID:)` → `POST /v1/sabre_tools/repair_trip` (`wait:false`). Codable models
    matching the status payload (`trip`, `items`, `summary.counts`/`all_clear`, `fetched_at`).
5.2 `Managers/TripManager.swift` (`@Observable`): polls status every 1.5s; on session start and
    after each agent `reply` event, re-resolves `latestTripID()` so the trip booked by voice
    mid-session is picked up and its cards appear; diffs item statuses between polls to drive
    card animations and the recovery timer (start on first `broken`, stop on `all_clear`).
5.3 Views: `ContentView` (orb top, timeline below), `VoiceOrbView` (idle/listening/speaking +
    spinning "Repairing" while `summary.counts.repairing > 0`), `TripTimelineView` +
    `ItineraryCardView` (five cards; spring insert on appear; status color/icon transitions
    booked → broken → repairing → fixed; recovery timer against the 60s target).
5.4 Demo controls: "Simulate flight cancellation" (calls `breakFlight`; enabled only when a
    trip with a non-broken flight exists) and a "Repair now" fallback (calls `repairTrip`) so
    a reviewer who never speaks still sees the heal; primary heal path stays voice
    (`fix_trip`).
5.5 About sheet: one paragraph on the app, links opening `/v1/legal/privacy` and
    `/v1/legal/support`.
5.6 App icon + launch screen assets (real art, no placeholders — screenshots and icon are
    review surface).

## 6. App Store submission — the goal

6.1 Merge/deploy checkpoint: PR `vb/feature/mobile-plan` → `vb/dev`; CI green (pytest in the
    built image); confirm on Cloud Run: `/v1/legal/privacy`, `/v1/legal/support`,
    `/v1/mobile_voice/` all serve, and a browser `/v1/web_call/` session can book a trip by
    voice end-to-end. Set Cloud Run `min-instances=1` so App Review never hits a cold start.
6.2 App Store Connect: create the app record — name "Talk to My Trip" (confirm availability),
    bundle id, primary category (Travel), no in-app purchases.
6.3 Metadata: subtitle, description, keywords, support URL + privacy policy URL (the Cloud Run
    pages), marketing URL optional. Consumer tone; no "demo/hackathon/test" words.
6.4 Privacy nutrition labels: collects Audio Data + Other User Content (transcripts) and
    usage/diagnostics as applicable — **not linked to identity, not used for tracking**.
6.5 Age rating: complete the 2026 questionnaire honestly, including the AI assistant/chatbot
    questions.
6.6 Screenshots: capture on the required iPhone sizes (mirror the display-size sets in
    `example_project/ios_assessor/app_store_screenshots/`) showing orb + booked timeline +
    repair-in-progress.
6.7 App Review notes: no account required; reviewer script (connect → mic → "plan me a trip to
    San Francisco" → cards appear → Simulate flight cancellation → watch repair / tap Repair
    now); note the live backend service.
6.8 Archive with Xcode 26 (iOS 26 SDK — mandatory since April 2026), run Validate, upload,
    answer export compliance (already `NO` via plist), **Submit for Review**.

## 7. Wrap-up

7.1 Full test suite in the container passes (`docker compose exec` pytest — standing rule).
7.2 Mark Phase 16 `[x] COMPLETE` in `specs/roadmap.md` only once the build is submitted
    (approval itself is asynchronous and out of our hands).
7.3 Record submission id / build number and any App Review correspondence expectations in this
    spec directory for the Phase 17 update.
