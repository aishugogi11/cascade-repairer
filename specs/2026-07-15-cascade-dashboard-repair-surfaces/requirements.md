# Phase 22 — Cascade dashboard, part 1: repair surfaces

**Feature branch:** `vb/feature/cascade-dashboard-repair-surfaces`
**Date:** 2026-07-15
**Roadmap:** `specs/roadmap.md` § "Phase 22: Cascade dashboard, part 1"
**Design source of truth:** `about/ui_ideas/ui_mockup_2026_07_09.png`

## Summary

Phase 21 shipped the mockup's **frame** on `GET /v1/booking/` (app header +
status pill, left rail, current-flight card, reservation cards, right-column
"AI Recommended" candidates panel) as the pre-disruption beat. Phase 22 builds
the **single consolidated demo surface** — a new page, `GET /v1/cascade/`,
cloned from the booking frame — that shows **everything** and lets the operator
**trigger both demo beats without leaving the page**: book a trip and fire the
cascade, then watch the mockup's repair surfaces (recovery banner + 60-second
timer, broken → repairing → fixed status treatments, disruption score,
downstream-impact panel) resolve in place. **The whole demo runs on one page —
no bouncing between `/v1/booking/`, `/v1/demo/`, and an itinerary view.**

The trigger controls fire the **existing** `/v1/demo` orchestrator (real
outbound phone calls — the actual stage moment): "Book" → `POST /v1/demo/book`,
"Cancel flight → cascade" → `POST /v1/demo/disrupt`. No **voice** wiring on the
page in this phase (the web voice orb is Phase 23) — the demo's voice is the
live phone call the orchestrator places, and the center voice column ships as a
clearly-marked placeholder so Phase 23 drops into the **same page** without a
relayout.

Everything the page *displays* is still driven **entirely** by the existing
1.5 s poll of `GET /v1/itinerary/status/{trip_id}` plus `GET /v1/itinerary/trips`
and `GET /v1/sabre_tools/latest_trip_id`; the only writes come from the two
existing `/v1/demo` endpoints the controls call. **No new backend endpoint, no
schema change, no server-side event state.** The one backend touch is a small
hardening carried from the Phase 21 validation report (see § Scope, item H).

## Scope

### In scope

| # | Item | Detail |
|---|------|--------|
| A | **New page + thin router** | `GET /v1/cascade/` serving `backend/api/assets/cascade/page.html`, wired via `backend/api/cascade_ui.py` (the `booking_ui.py` thin-router shape: no logic, HTML read per request). `/v1/booking/` is **unchanged**. This page is the **single consolidated demo surface** — it shows the pre-disruption booking beat *and* the repair beat, and carries the trigger controls (item I), so the whole demo runs here. |
| B | **Cloned frame** | Reuse the booking page's frame — app header (product name, current traveler, status pill), left rail (traveler-context card, trip timeline with per-leg status icons, collapsible recent trips), current-flight card, four reservation cards, right-column recommendation panel. Same technical conventions: no build step, self-contained (no external requests), `?code=` → `localStorage` → `X-Access-Code`, `?trip_id=`/`window.vbSetTrip()` pinning, re-resolve `latest_trip_id` every 4 s and adopt a **change**. |
| C | **Recovery banner + timer** | Top banner in the mockup's treatment ("Cascade is actively repairing your itinerary…") shown while any leg is `broken`/`repairing`, with a recovery timer counting against the **60-second** target. Reuse the itinerary page's client-side timer approach (no server-side event state). Banner resolves to an all-clear treatment when `summary.all_clear` / no active legs. |
| D | **broken → repairing → fixed treatments** | Visual status treatments on the current-flight card, reservation cards, and trip-timeline legs across all six lifecycle statuses (`planned/booked/broken/repairing/fixed/cancelled`), matching the mockup's red-broken / in-progress-repairing / green-fixed register. Transitions derived client-side by diffing item `status` between polls (the itinerary page's repair-feed precedent — no server event state). |
| E | **Disruption score** | The mockup's "Disruption score" chip (e.g. "12 · Minimal"). **Derived client-side** in page JS from the existing status payload — a 0–100 score + band label (Minimal / Moderate / Severe) computed from a documented heuristic (count of broken/repairing legs, `detail.price_delta` where present, elapsed vs. the 60 s target). No backend/schema change. Score moves as legs heal and reads Minimal when `all_clear`. |
| F | **Downstream-impact panel** | The mockup's "Downstream impact" list under the recommendation card, fed by the **existing** additive `detail` payload (`why_chosen`, `price_delta`, `impact`) already on booked items — one glanceable line per affected leg with an OK / Adjusted status dot. Omit gracefully when `detail` is absent (best-effort, mirrors iOS fallback). |
| G | **Center voice-column placeholder** | Reserve the center column with a static, clearly-labeled placeholder (e.g. "Voice — Phase 23") so the three-column layout matches the mockup now. **No** VB wiring, token minting, orb, or conversation feed in this phase. |
| H | **`_LATEST_SEARCH` age-expiry hardening** | Backend: expire the pending-options slot by **age** so a conversation that got real flight options and never booked can't leave them visible on the poll indefinitely. Phase 30 already clears both slots on every *non-optioned* search return and on booking; the only residual is abandonment. Add a module-level TTL and have `pending_options_for_trip` (`concierge.py`) return `None` for a slot older than the TTL (keying off the existing `LatestSearch.recorded_at`). Additive, best-effort — a stale slot simply stops surfacing; nothing else changes. |
| I | **On-page trigger controls (both beats)** | Two controls on the page, wired to the **existing** `/v1/demo` orchestrator — the real outbound-call demo path: **"Book"** → `POST /v1/demo/book` (`BookRequest{user_id, title}` → returns `{trip_id}`); **"Cancel flight → cascade"** → `POST /v1/demo/disrupt` (`DisruptRequest{trip_id}`). Clone the control JS from the shipped `/v1/demo/page.html` (fetch with the `X-Access-Code` header the page already attaches). On a successful **Book**, the page **pins the returned `trip_id`** so the just-booked trip appears immediately (no reload, no `latest_trip_id` wait); **Disrupt** targets the currently-pinned trip. Copy/treatment in the mockup's register. These fire **real phone calls** — see § Context (cost & env). |

### Out of scope (explicit non-goals)

- **Any voice wiring on the page** — server-minted token, `useAIAgent →
  /v1/web_call/query` delegation, the web voice orb with connection/latency
  state, the on-page conversation feed, the Sabre live-search log panel. All of
  that is **Phase 23**, landing in this same page's reserved center slot. (The
  demo's *voice* in Phase 22 is the live phone call the `/v1/demo` orchestrator
  places — not a web voice session.)
- **New backend endpoints or schema changes.** The page *displays* from the
  three read endpoints that already exist and *triggers* via the two `/v1/demo`
  endpoints that already exist. Item H edits one existing function; it adds no
  endpoint and no field. No new orchestration logic — the controls call the
  Phase 12 seams as-is.
- **Quota-free / local trigger seams on the page.** Per the interview the
  on-page controls use the **real outbound-call** path only; wiring the
  quota-free `seed_trip`/`break_flight`/`repair_trip` seams as page buttons is
  not in scope (those remain available manually for silent visual rehearsal).
- **Modifying `/v1/booking/`.** The Phase 21 page is shipped and QA'd; the
  dashboard is a clone, not an edit. (Shared CSS/markup is copied, not
  refactored into a shared asset — that refactor is not in this phase.)
- **Server-side event/repair state.** Repair transitions and the timer are
  derived client-side from the status poll, exactly as the itinerary page does.
- **Browser-automation tests** for page JS (standing decision, itinerary
  triage 2026-07-09 — page behavior is scripted manual QA).

## Decisions

1. **One consolidated demo page** (interview, 2026-07-15 — refined the same day):
   `/v1/cascade/` is a **new** page (not an in-place edit of `/v1/booking/`, which
   stays untouched and QA'd), but unlike the first cut it is **not** a repair-only
   clone — it is the *single* surface the operator uses for the whole demo: it
   shows the pre-disruption booking beat *and* the repair beat, and carries the
   trigger controls for both. Rationale: the operator explicitly does **not** want
   to bounce between `/v1/booking/`, `/v1/demo/`, and an itinerary view mid-demo.
   Cost — some markup/CSS is duplicated from the booking page; accepted for the
   hackathon (no shared-asset refactor this phase).

6. **On-page triggers use the real outbound-call `/v1/demo` path** (interview,
   2026-07-15). The controls call `POST /v1/demo/book` and `POST /v1/demo/disrupt`
   as-is — the real stage moment (phone rings). No new trigger logic; the page is
   a thin caller of the Phase 12 orchestrator. The web voice orb stays a Phase 23
   placeholder, so booking-by-talking is deferred, but triggering the beats from
   this one page is not.

7. **Booking pins immediately from the trigger response.** `POST /v1/demo/book`
   returns the seeded `trip_id`; the page pins it directly rather than waiting on
   the 4 s `latest_trip_id` re-resolve, so the booked trip is on screen the moment
   the control returns. `Disrupt` targets the pinned trip.

2. **Disruption score is a client-side heuristic** (interview, 2026-07-15), not
   a backend field and not a static value. It must be honest to real state
   (move as legs heal) with **no** schema/endpoint change. The exact formula and
   band thresholds are an implementation choice in `plan.md`, documented in a
   page-JS comment so the number is explainable to a judge.

3. **Center column is a labeled placeholder** (interview, 2026-07-15), reserving
   the three-column layout for Phase 23 so the voice column drops in without a
   relayout.

4. **Item H expires the visible pending-options panel by age** — scoped to
   `pending_options_for_trip`'s read path (the surface that lingers). The TTL is
   a single documented module-level constant. Bookability of a stale
   `_SESSION_FLIGHT_OPTIONS` entry is **not** widened here (Phase 30 already
   covers the non-optioned/booked clears; pure-abandonment bookability is a
   single-operator-demo non-issue) — keeping the change minimal and additive.

5. **`/v1/cascade/` shell joins the access-gate allowlist** alongside the other
   four page shells (`access_gate.py`), inert without the gated JSON APIs — the
   established pattern for every rehearsal page.

## Context

- **Trigger cost & env (real-call path).** Each full run costs **~2 Vocal
  Bridge outbound calls** against the **10/day** cap (reset 00:00 UTC = 5 PM PDT
  prior evening) — Book places one call, Disrupt another. `place_call` blocks
  ~10–16 s until queued; the phone rings ~10–15 s later. The `/v1/demo`
  endpoints return **503** when the VB call env vars are unset (common in local
  dev), so the on-page controls only *fire real calls* where those are
  configured (Cloud Run) — locally the buttons surface the 503 cleanly and the
  visual demo is rehearsed via the quota-free seams by hand. Callee numbers must
  be verified in the VB dashboard. **Rehearse the visuals silently; spend calls
  only on the real run.**
- **Tone / copy.** Match the mockup's glanceable register (`about/ui_ideas/
  ui_mockup_2026_07_09.png`): short, plain, traveler-voiced ("Cascade is
  actively repairing your itinerary…", "Late check-in 11:30 PM — no change
  needed"). Never surface airline codes in traveler-facing copy where the
  existing pages avoid them; keep the Phase 19 timezone discipline — any clock
  time rendered is `America/Los_Angeles`, labeled **PT** (never PST).
- **Stack limits** (`specs/tech-stack.md`). No new dependencies. Self-contained
  vanilla HTML/CSS/JS, no build step, no external requests, read per request
  (uvicorn `--reload` only watches `.py`). Follow the itinerary/booking page
  patterns exactly.
- **Patterns to clone.** `backend/api/booking_ui.py` (router), `backend/api/
  assets/booking/page.html` (frame + poll + pinning + access-code), `backend/
  api/assets/itinerary/page.html` (recovery timer + client-side status-diff
  feed). Status payload shape: `backend/api/itinerary_ui.py` (`detail`,
  `pending_options`, `summary.counts`/`all_clear`).
- **Testing** (`specs/tech-stack.md` § Testing). Hermetic pytest inside the
  container; no GCP creds, no network. New backend behavior (router shell,
  access-gate allowlist, item H age-expiry) is unit-tested; page JS is scripted
  manual QA, not browser-automated.
- **Open question deferred to Phase 23:** whether the live conversation feed and
  Sabre live-search log read from turn logs or a new seam — not decided here.
