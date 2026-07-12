# Requirements — Pacific-time discipline & pin the displayed trip

Phase 19 (roadmap). Two hotfixes from the 2026-07-12 post-Phase-18 validation pass,
shipping together on `vb/feature/pacific-time-trip-pin` because both block Phase 17's
device QA. Neither reopens the Phase 18 unpin decision.

## Scope

### Bug 1 — Timezone discipline: the database stores UTC, the edges speak Pacific

Josh voice-booked the 6:15 AM MSP→DFW flight; the itinerary page showed 1:15 AM.
Mock wall-clock times are stamped `tzinfo=timezone.utc` at write, and pages render
browser-local. Decision (Josh, 2026-07-12): everything displayed or spoken to a user
is **Pacific time** (`America/Los_Angeles`), regardless of viewer location; storage
stays honest UTC instants.

**Ingest — declare mock times Pacific wall-clock, convert to UTC at write:**

| File | Site | Today | Required |
|---|---|---|---|
| `backend/api/concierge.py` | `_booking_writes` flight `start_ts`/`end_ts` (~lines 421–424) | `tzinfo=timezone.utc` | `tzinfo=ZoneInfo("America/Los_Angeles")` (`ZoneInfo` already imported) |
| `backend/api/concierge.py` | `_completion_items` `ts()` helper (~line 513) | `tzinfo=timezone.utc` | same |
| `backend/api/sabre_tools.py` | `_SEED_ITEMS` all five items (lines 38–63) | `tzinfo=timezone.utc` | same |

BigQuery `TIMESTAMP` remains a UTC instant; a Pacific-aware `datetime` converts
correctly on write with no repository changes. Real Sabre responses carry offsets
and convert naturally — no special-casing needed.

**Display — every user surface renders `America/Los_Angeles` explicitly:**

| File | Site | Required |
|---|---|---|
| `backend/api/assets/itinerary/page.html` | item card `toLocaleString` (~lines 325–327) | add `timeZone: 'America/Los_Angeles'` to `opts`; label times “PT” |
| `backend/api/assets/itinerary/page.html` | repair-feed clock `toLocaleTimeString` (~line 400) | same `timeZone` option |
| `backend/api/assets/demo/page.html` | item card `toLocaleString` (~lines 390–392) | same as itinerary page |
| `backend/api/assets/demo/page.html` | repair-feed clock (~line 465) | same |

**Verified non-surfaces (sweep already done while speccing; re-confirm during
implementation, no changes expected):**

- The `web_call` and `mobile_voice` pages (inline templates in their `.py` files)
  render transcripts only — no timestamps.
- **iOS renders no clock times anywhere**: `ItineraryCardView` shows type/location/
  status; `APIService`'s `start_ts`/`end_ts` are decoded but unused; the only `Date`
  use is the recovery-timer stopwatch (elapsed seconds, timezone-free). No iOS
  formatter changes are needed — the roadmap's assumption predates this audit.
- Voice readback (`_spoken_clock`) speaks the mock's wall clock, which this fix
  *defines* as Pacific — spoken and displayed times now agree by construction.

### Bug 2 — Voice session pins the trip the app is displaying

The iOS UI shows a trip (server-side latest-trip reads were kept in Phase 18) but the
in-app voice agent starts unpinned and denies it — Q&A and in-app `fix_trip` on
pre-existing trips are dead. Thread the app's known `trip_id` through the existing
Phase 12 explicit-pin seam:

- `QueryRequest` (`backend/api/web_call.py`) gains an **optional** `trip_id` field;
  `delegated_query` → `web_call.answer_query` → `concierge.answer_query` →
  `ensure_trip_context(session, trip_id=…)`. Absent/blank `trip_id` behaves exactly
  as today.
- The `web_call` and `mobile_voice` pages read `?trip_id=` from their URL, keep it in
  a JS variable, and include it in every `/v1/web_call/query` POST. They also expose
  **`window.vbSetTrip(tripId)`** so native can update the value after page load.
- iOS: `APIConfig.mobileVoiceURL` gains a `tripId` parameter, and `VoiceManager`
  calls `window.vbSetTrip(...)` via `evaluateJavaScript` whenever `TripManager`'s
  displayed trip changes — the URL param alone loses the race with the app's
  cold-start `latest_trip_id` resolution (the webview loads before the trip resolves).
- **Temporary page bridge for the in-review binary** (decision 2026-07-12, added
  after the App Review constraint surfaced): the `mobile_voice` page — served by
  this backend, so it reaches existing binaries on their next load — additionally
  fetches `GET /v1/sabre_tools/latest_trip_id` itself (with the access-code header
  it already sends) and uses that as the query `trip_id` when nothing better is
  available. Precedence: `vbSetTrip` value (future binaries) → `?trip_id=` URL
  param → fetched latest; a failed fetch silently omits `trip_id` (voice must
  never break on it). This makes the binary currently on Josh's phone and in App
  Review trip-aware from a backend deploy alone. It mirrors what the app displays
  because `TripManager` resolves the same endpoint. **Mark it in-code as a
  temporary bridge to remove once native `vbSetTrip` ships in v1.0.1.** Known gap,
  accepted: the hidden long-press selector won't repoint the old binary's voice
  session. The `web_call` page does **not** get the bridge — desktop stays
  explicit-`?trip_id=` only, so Act 1 rehearsals keep a clean unpinned default.

**Not in scope**

- Migrating or reseeding existing dev rows written wall-clock-as-UTC (display ~7 h
  off after the fix) — cosmetic rehearsal junk, decision: ignore, let it age out.
- Converting *real* Sabre times to Pacific before speaking (`_spoken_clock`) — real
  keys land 7/14; tracked under Phase 17's `SABRE_MODE=real` flip, not here.
- Re-introducing any latest-trip fallback in `ensure_trip_context` — Phase 18's
  removal stands. (The temporary page bridge lives client-side in the mobile
  page and sends an explicit `trip_id`; the concierge itself never falls back.)
- iOS empty-start onboarding (don't auto-resolve `latest_trip_id` on cold start) —
  next Phase 17 sub-item, explicitly not this branch.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Surfaces covered | All (backend ingest + itinerary/demo pages + iOS) | Josh 2026-07-12; iOS portion collapsed to verification because the audit found no time rendering there |
| Re-pin semantics | **Pin only if unpinned** — a passed `trip_id` never clobbers an existing pin | Josh 2026-07-12; a just-booked trip's pin survives; `ensure_trip_context` already checks its cache before `trip_id`, so this is the seam's natural behavior — codify with a test, don't add logic |
| Old dev rows | Ignore | Cosmetic; reseed manually later if it bothers anyone |
| Timezone label | “PT” / “Pacific time”, never “PST” | It's PDT in July; hardcoding PST would be wrong on event day |
| trip_id transport | Optional field in the query POST body (not a new endpoint/header) | Smallest change on the stable `/query` seam; pages/native own when to send it |
| Mid-session trip change (long-press selector) | Native still calls `vbSetTrip`; server ignores it if pinned | Consequence of pin-only-if-unpinned; acceptable — the selector repoints *polling*, and voice follows the session's first pinned trip |
| App Review constraint (Josh, 2026-07-12) | iOS code **merges** on this branch, but **no build is archived/uploaded to App Store Connect** this phase | A binary is in App Review; replacing it restarts the queue. Repo commits and Xcode installs to Josh's own device don't touch the submission; the fix ships to the store in the first post-approval update |
| Page bridge (Josh, 2026-07-12) | `mobile_voice` page temporarily self-resolves `latest_trip_id` as its `trip_id` fallback | The only path that makes the in-review/production binary trip-aware without a new upload. Scoped to the mobile page only (not `web_call`, not `ensure_trip_context`) and removed in v1.0.1 — this is *not* a revival of the Phase 18 removed concierge fallback |

## Context

- **Tone:** all agent-facing failure strings stay speakable (standing rule); any new
  user-visible time label says “PT” or “Pacific time”.
- **Testing:** suite must stay hermetic (no GCP creds, no `OPENAI_API_KEY`); the
  Phase 18 regression test (`answer_query` with a non-empty trips table still reaches
  `search_flights`) must stay green — the pin threading touches the same path.
- **HTML edits aren't hot-reloaded** locally (`uvicorn --reload` watches `.py` only)
  — restart the container when hand-testing page changes.
- **Patterns to follow:** tool bodies stay plain `*_impl` functions; blocking
  BigQuery work stays in `asyncio.to_thread`; the `/query` seam
  (`web_call.answer_query`) remains the single patch point tests rely on.
- Rehearse via `/v1/web_call/?code=…&trip_id=…` and curl against
  `/v1/web_call/query` — no outbound-call quota spent.
