# Requirements — Talk to My Trip: App Store submission MVP (Phase 16)

**The goal, in Josh's words: "GET APPROVED."** First-time App Store review takes days and the
event is 7/18, so the deliverable of this phase is an approvable build **submitted to App Review
today (Fri 2026-07-11)** — not the full three-act demo. Everything here is scoped to the minimum
app that (a) genuinely represents the product ("talk to my trip" — voice is the app) and (b)
survives App Review.

Branch: `vb/feature/mobile-plan` (created by Josh; single branch — `ios/` rides along untouched
by Cloud Build, per `IOS_PLAN.md`). Umbrella plan: `IOS_PLAN.md` at the repo root.

## Scope

### In scope — the user story

Open the app → tap the orb → talk to the agent → tell it where you want to go → **the agent books
the complete trip by voice** (magic utterance) → five itinerary cards appear → trigger the flight
cancellation → cards flip broken → repairing → fixed while the agent keeps talking.

### In scope — surfaces

| Surface | What | New/Existing |
|---|---|---|
| `ios/TalkToMyTrip/` | Native SwiftUI app: voice orb + live trip timeline, one main screen | **New** |
| `GET /v1/mobile_voice/` | Headless clone of the web_call page for the hidden WKWebView bridge (`window.vbConnect()`/`vbDisconnect()`, `postMessage` events to native) | **New** (IOS_PLAN A2) |
| Concierge booking tool | **Magic utterance** (IOS_PLAN cut-line 2): one tool wrapping the existing `create_seed_trip` — traveler says where/when, agent confirms and books the whole 5-item trip in one shot | **New** (small delta in `backend/api/concierge.py`) |
| `GET /v1/legal/privacy`, `GET /v1/legal/support` | Privacy policy + support pages (App Store Connect requires both URLs), served by the backend | **New** |
| `POST /v1/web_call/token`, `POST /v1/web_call/query` | Token mint + delegated spoken turns — reused as-is, same-origin from the headless page | Existing |
| `GET /v1/itinerary/status/{trip_id}`, `GET /v1/itinerary/trips`, `GET /v1/sabre_tools/latest_trip_id` | Trip state polling + discovery | Existing |
| `POST /v1/disruption/break_flight`, `POST /v1/sabre_tools/repair_trip` | In-app demo trigger (break) + non-voice repair fallback — **no phone call, no VB quota spend** | Existing |
| App Store submission | App Store Connect record, metadata, screenshots, privacy labels, age rating, archive + upload + **submit** | **New** (process, not code) |

### Out of scope (deferred to Phase 17)

- Guided multi-turn booking (`search_flights` → speak options → `book_flight` → `complete_trip`
  with 1.5s card spacing) — the full IOS_PLAN Track A1. MVP books the fixed seed-trip shape.
- Recommendation bottom sheet + `detail` payload on `/status` (A4).
- Outbound-call finale (Act 3), hidden demo gestures, `SABRE_MODE=real` (keys arrive Mon 7/14).
- iPad layout, landscape, dark-mode polish beyond defaults.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Voice in the MVP build | **Yes — voice is the app** (Josh, interview 2026-07-11): trip planning starts as a conversation | An app named "Talk to My Trip" submitted without talking misrepresents the product; guideline 4.2 wants real functionality |
| Booking depth | **Magic utterance**: one Concierge tool wrapping `create_seed_trip` (already extracted, `sabre_tools.py:69`) via `asyncio.to_thread`; the spoken destination personalizes the trip title; cards appear on the next poll | Smallest backend delta that makes "plan your trip by voice" true; full A1 upgrades it in Phase 17 as an app update (updates re-review much faster than first submissions) |
| Session trip pin | Booking **replaces** the session's `_SESSION_TRIPS` pin | `ensure_trip_context` caches the pin for the session's life (`concierge.py:123`); without replacement the agent keeps answering about the old trip after booking a new one |
| Voice transport | Hidden WKWebView bridge (IOS_PLAN locked decision): headless page runs the VB WebRTC client; native ⇄ webview via `WKScriptMessageHandler` + `evaluateJavaScript` | No LiveKit-Swift risk; the proven web_call stack does the work; all visible UI stays native (a 4.2 webview-wrapper rejection targets *visible* web UI — this app's UI is fully native SwiftUI) |
| Break/heal in-app | "Simulate flight cancellation" control calls `break_flight`; healing happens **by voice** (`fix_trip` already exists) with a visible "Repair now" fallback button (`repair_trip`, `wait:false`) | The voice heal is the product story; the fallback guarantees a reviewer who won't talk still sees the cascade complete |
| Legal URLs | Served from this backend: `/v1/legal/privacy` + `/v1/legal/support`, self-contained static pages (the `assets/` pattern from `/v1/itinerary`) | Stable Cloud Run URLs, versioned in-repo, no new infra; deployed via the normal `vb/dev` pipeline **before** they're entered in App Store Connect |
| Apple account / targets | **Zen Software** Apple Developer Program org; bundle id `com.zensoftware.talktomytrip` (confirm exact reverse-domain in Xcode); **iPhone-only, iOS 17+, portrait** | Josh's interview answer; matches IOS_PLAN conventions and `example_project/ios_assessor` precedent |
| Dependencies | None (SwiftUI + WebKit + Foundation only); backend adds no new packages | Tech-stack constraint; nothing here needs one |

## App Review readiness (what they look for — checked 2026-07-11)

- **Guideline 4.2 minimum functionality**: native UI + live data + real voice interaction clears
  it; the WKWebView is invisible plumbing, not the interface. The most common first-submission
  killers are crashes, incomplete metadata, and 4.2 — roughly 40% of first submissions get
  rejected, usually for trivia (broken links, wrong screenshot sizes).
- **SDK**: since April 2026, uploads must be built with the **iOS 26 SDK** — archive with
  current Xcode 26.x.
- **Privacy**: privacy policy URL (must cover mic audio → Vocal Bridge processing and
  transcript/turn logging to BigQuery; no accounts, no tracking, no ads), **privacy nutrition
  labels** in App Store Connect (audio data + transcripts, *not linked to identity*, *no
  tracking*), and a **`PrivacyInfo.xcprivacy` privacy manifest** in the app (no tracking domains;
  declare required-reason APIs only if used, e.g. UserDefaults → CA92.1).
- **Age rating**: the questionnaire was overhauled (mandatory since Jan 2026) and now asks
  explicitly about **AI assistants/chatbots** — answer honestly (the app fronts an AI agent);
  expect a 13+ class rating.
- **Mic permission**: `NSMicrophoneUsageDescription` with copy that says exactly why ("to talk
  to your trip assistant"); single native prompt (grant the webview's capture request via
  `WKUIDelegate` so iOS doesn't double-prompt).
- **Export compliance**: `ITSAppUsesNonExemptEncryption = NO` (HTTPS only) so submission doesn't
  stall on the encryption question.
- **App Review notes**: no login/demo account needed — say so; include a 5-line reviewer script
  (tap orb → allow mic → say "plan me a trip to San Francisco" → cards appear → tap "Simulate
  flight cancellation" → watch it heal / tap "Repair now"); note the backend is a live demo
  service. Verify Cloud Run `min-instances=1` first so the reviewer never hits a cold start.
- **Metadata**: app icon (no placeholder art), name "Talk to My Trip" (confirm availability in
  App Store Connect), subtitle, description, keywords, support URL, screenshots for the required
  iPhone display sizes (mirror `example_project/ios_assessor/app_store_screenshots/` sizes) —
  screenshots must show the real app.

## Context

- **Conventions**: mirror `example_project/ios_assessor` (actor `APIService`, `APIConfig`,
  Manager pattern), scaled down per the IOS_PLAN Track B file layout. Backend code follows the
  established patterns: routers registered in `backend/main.py` with `/v1/<name>` prefixes,
  self-contained HTML in `backend/api/assets/<name>/`, per-request env reads, blocking BigQuery
  through `asyncio.to_thread`, speakable strings returned from tools (a raising tool kills the
  spoken turn — `concierge.py:178`).
- **Agent copy tone**: replies are spoken aloud — one or two short conversational sentences, no
  markdown, no ids (the `BASE_INSTRUCTIONS` rules stand). Booking confirmation should narrate the
  trip parts ("Done — flight, hotel, ride, dinner, and a museum visit are booked for July 17th
  through 19th").
- **App Store copy tone**: plain consumer language; no "hackathon", "demo", "test", or "MVP" in
  user-facing metadata (words that invite 4.2/2.1 scrutiny); the App Review *notes* are where the
  demo-service context belongs.
- **Testing**: pytest runs in the container (`docker compose exec` — standing rule); tests stay
  hermetic (no GCP creds, no `OPENAI_API_KEY`, no live VB calls). No browser-automation tests
  (standing decision); page JS behavior is scripted manual QA. iOS side has no CI — build/run
  verification is Xcode-local.
- **Quota discipline**: nothing in this phase places phone calls; rehearse voice via
  `/v1/web_call/` in the browser (the Concierge upgrade is testable there before iOS exists —
  the A2 design keeps `/query` delegation identical).
- **Deploy order matters**: backend (legal pages, mobile_voice, booking tool) must be merged to
  `vb/dev` and live on Cloud Run before App Store Connect metadata references the URLs and
  before the submitted build's voice flow can work for a reviewer.
