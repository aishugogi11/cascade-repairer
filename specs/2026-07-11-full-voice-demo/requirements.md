# Requirements — Talk to My Trip: full voice demo experience (Phase 17)

Turn the submitted Phase 16 MVP into the full three-act demo from `IOS_PLAN.md`, shipped as an
**app update** (updates re-review much faster than a first submission). The voice bridge, headless
page, and magic-utterance booking already shipped in Phase 16; this phase is the upgrade: guided
multi-turn voice booking, the recommendation sheet, hidden demo gestures, stage polish — and the
access-code gate that must be in place before this update goes out, because the public backend
carries real OpenAI and Vocal Bridge spend.

Branch: `vb/feature/full-voice-demo` (single branch — `ios/` rides along untouched by Cloud Build).
Umbrella plan: `IOS_PLAN.md` at the repo root. External blocker, not in this spec: the Phase 16
build still needs archive → upload → **submit for review** in App Store Connect; this phase's
update queues behind it.

## Scope

### In scope — the user story

Launch the app → enter the shared access code (once) → tap the orb → *"book me a trip to San
Francisco, July 17 to 19"* → the agent searches, **speaks 2–3 flight options**, the traveler picks
one **by voice** → the flight books, then hotel/ride/dinner/experience cards materialize one by one
(~1.5s apart) → triple-tap the orb → the flight breaks, five cards heal in under 60s while the
agent keeps talking → the traveler's phone rings with the recovery call → tap a card → the
"AI Recommended / why chosen / downstream impact" sheet slides up.

### In scope — surfaces

| Surface | What | New/Existing |
|---|---|---|
| Concierge guided booking | `search_flights` → `book_flight` → `complete_trip` tools on the one Concierge (`backend/api/concierge.py`), **replacing** the Phase 16 magic-utterance `book_trip` | **New** (IOS_PLAN A1) |
| Access-code gate (backend) | `DEMO_ACCESS_CODE` env var; middleware requiring an `X-Access-Code` header on `/v1/*` (small public allowlist); `POST /v1/auth/validate` for the first-launch check | **New** |
| Access-code gate (iOS) | First-launch gate screen before the main screen; code stored in Keychain; `APIService` and the voice webview send the header on every request | **New** |
| `detail` payload on `GET /v1/itinerary/status/{trip_id}` | Additive per-item object (why chosen, price delta, downstream impact) feeding the sheet; web page ignores it. **First thing to cut.** | **New** (IOS_PLAN A4) |
| `RecommendationSheet` | Native bottom sheet rendering `detail` on card tap | **New** (IOS_PLAN Track B) |
| Hidden demo gestures | Triple-tap orb → `POST /v1/demo/disrupt` (Act 2/3 backup trigger); long-press orb → trip selector backed by `GET /v1/itinerary/trips` | **New** |
| Orb/timeline polish | Stage-readability pass: bigger status states, clearer broken→repairing→fixed transitions, recovery timer legible from a distance | Existing views, polish only |
| `POST /v1/demo/disrupt` | Act 2/3 trigger with the **real outbound call** — reused as-is from Phase 12 | Existing |
| `POST /v1/web_call/token`, `POST /v1/web_call/query`, `GET /v1/mobile_voice/` | Voice transport — unchanged except for carrying the access code | Existing |

### Booking flow data shape (Act 1)

| Step | Tool | Behaviour |
|---|---|---|
| Search | `search_flights(origin, destination, depart_date)` | Calls existing `api.sabre.client.flight_search` (mock until keys); stores options in a per-session dict (the `_SESSION_TRIPS` pattern); returns a **speakable** 2–3-option summary ("Option one: nonstop, lands 12:05, $385…") |
| Book | `book_flight(option_number)` | Creates `Trip` + flight `ItineraryItem` (`planned` → `booked`) + `Booking` row via the existing repositories (same calls `create_seed_trip` makes); **replaces** `_SESSION_TRIPS[session_id]` so the session immediately owns the new trip |
| Complete | `complete_trip()` | Background task (`asyncio.create_task`, the `demo.py` pattern) creating hotel/ground/dining/experience items sequentially with **~1.5s spacing** so cards materialize one by one on the 1.5s polling client; items derive from the chosen flight's dates/destination, reusing `_SEED_ITEMS` shapes |

No schema changes: `planned`/`booked` already exist in `ItemStatus`.

### Out of scope

- The Phase 16 App Store **submission itself** (archive/upload/submit) — external prerequisite.
- `SABRE_MODE=real` — keys arrive Monday 7/14; flipping the env var on Cloud Run is a config
  change, not a task here. Everything in this spec is buildable and verifiable in `mock`.
- The stretch `POST /v1/demo/recovery_call` ("all fixed" follow-up call) — stays a cut line.
- Username/password accounts, Sign in with Apple, per-user anything — deliberately avoided
  (Apple account-deletion + Sign-in-with-Apple obligations). One shared code, period.
- A custom domain / prod Cloud Run service for `APIConfig.swift`'s hardcoded dev URL — flagged
  in the roadmap as pre-event review, post-hackathon work.

## Decisions

- **Access code protects the API, not just the UI** (Josh, spec interview 2026-07-11): the code
  is sent as an `X-Access-Code` header on requests and validated **server-side** by middleware —
  actually protecting OpenAI/Vocal Bridge spend from anyone who finds the Cloud Run URL, not
  just gating the app's front door. A validate-once UI gate was rejected as leaving the public
  API open to direct callers.
- **Public allowlist** (required for the gate not to break what must stay public): `/v1/legal/*`
  (App Store Connect requires these URLs publicly reachable), `POST /v1/auth/validate` (the gate's
  own front door), and the `GET` static HTML pages (`/v1/web_call/`, `/v1/mobile_voice/`,
  `/v1/itinerary/`, `/v1/demo/`) — the pages are inert without the gated JSON APIs behind them.
  Everything else under `/v1/` requires the header.
- **Fail-open when unset**: with no `DEMO_ACCESS_CODE` env var the middleware allows everything
  and logs a warning once — keeps local dev and the hermetic CI test suite working with zero
  setup; Cloud Run gets the code via `--update-env-vars` (merge — survives redeploys, no rebuild).
  Comparison uses `secrets.compare_digest`.
- **How each client carries the code**: iOS validates once at first launch
  (`POST /v1/auth/validate`), stores the code in the **Keychain**, and `APIService` attaches the
  header on every call; the hidden webview loads `/v1/mobile_voice/?code=…` and the page JS
  attaches the header on its `token`/`query` fetches. Desktop demo/itinerary/web_call pages accept
  the same `?code=` param (persisted to `localStorage`) so rehearsal surfaces keep working.
- **The code ships in App Review notes and the judges' hands** — it is a shared demo secret, not
  a security boundary; rotating it is an env-var update.
- **Guided booking replaces the magic utterance** (roadmap): `book_trip` is retired from the
  agent's toolset; the instructions carry the guided script (destination → dates → search → offer
  options → confirm by voice → book → complete). Existing disruption/`fix_trip` rules untouched.
- **One Concierge, one brain**: booking tools extend the existing agent — no second agent, no
  fork; per-turn rebuild, `_HISTORY`, `_SESSION_TRIPS` all as-is.
- **`detail` is additive and the first thing to cut** (roadmap): the status payload stays
  UI-agnostic; the web page ignores the new field; the sheet degrades to static text if cut.
- **Spec assumes mock Sabre throughout** (Josh, spec interview): tests and rehearsals run
  `SABRE_MODE=mock`; the per-call mock fallback already protects the demo if real mode flakes.

## Context

- **Spoken-copy rules stand**: every tool failure path returns a **speakable string** — a raising
  tool kills the spoken turn. Option summaries must be listenable, not readable: 2–3 options max,
  short clauses, prices rounded, no airline codes.
- **Access-gate screen copy**: minimal and honest — this is a hackathon demo gate, not a login.
  One field, one button, one line of copy ("Enter the access code from your demo invitation"),
  a friendly error on a wrong code. No account language.
- **Rehearsal discipline**: Acts 1–2 rehearse free via the existing `/v1/web_call/` browser page
  (the A1 tools are automatically testable there before iOS is involved) and the `/query` curl
  seam. Real outbound calls only on full dress runs — **10 calls/day VB quota**, resets 00:00 UTC.
- **Testing** (standing rules): pytest **in the container** (`docker compose exec`); tests stay
  hermetic — no GCP creds, no `OPENAI_API_KEY`; repositories and Sabre client mocked at existing
  boundaries; `uvicorn --reload` doesn't watch HTML edits.
- **iOS conventions**: SwiftUI, iOS 17+, zero third-party dependencies; actor `APIService`,
  `@Observable` managers; Xcode 16 file-system-synchronized groups (new Swift files need no
  pbxproj edits); no CI for `ios/` — build verification is Xcode-local.
- **Single-instance session state**: `_HISTORY`, `_SESSION_TRIPS`, and the new options dict are
  in-process memory by standing decision — verify Cloud Run `min-instances=1`/`max-instances=1`
  before event day.
