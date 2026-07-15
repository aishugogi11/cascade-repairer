# Requirements — Phase 31: Phase 23 close-out — the consent flow works live

Branch: `vb/feature/consent-repair-closeout` (off `vb/dev`). Spec interview
2026-07-15: **all six findings in scope**, **fix_trip defers to the phone during a
consent window**, **watcher timeout unchanged + one budgeted live rerun**.

Sources: the independent validation report
(`specs/2026-07-15-cascade-live-voice-demo/validation-report.md` — two CONFIRMED
failing tests in `backend/tests/test_validator_cascade_live_voice_demo.py`,
currently untracked) and Josh's 2026-07-15 live QA run, diagnosed same-day against
the deployed service and the VB session logs.

## Scope

Six fixes, ordered by demo criticality:

| # | Finding | Fix |
|---|---------|-----|
| 1 | **Call 2 never fires live**: the watcher polls `find_session(call_id)` forever — `vb call` returns `call_id` + `room_name`, but the session log carries only `id`/`room_name` (proven live: watcher `timed_out` at 21:58:28 while the completed, transcript-bearing session sat in the log with a different `id`) | `place_call` returns `room_name` in its sanitized payload; `find_session` also matches `room_name`; the disrupt flow keys the watcher on `room_name` (falling back to `call_id`) |
| 2 | **The re-shop rebooked the original flight** (Delta 773 → Delta 773): voice-booked items carry no flight identity, so `_cancelled_flight()` returns None and the exclusion filter is starved — "closest arrival to the original" converges on the original | `book_flight` stamps `airline`/`flight_number` into the flight item's `details`; the repair's exclusion then works. Belt-and-braces: when identity is unavailable, also exclude candidates whose depart+arrive times equal the original's; an exclusion that empties the pool falls back to the unfiltered pool with a warning log (never a crash) |
| 3 | **Re-trigger race** (validator, CONFIRMED): the watcher checks token currency after the transcript but not again across the classifier/repository awaits — a Cancel re-click mid-classification still launches repairs and Call 2 from the stale watcher | `consent.resolve(..., GRANTED)` becomes the atomic gate: attempted **before** `launch_trip_repairs`, with no awaits between them; a False return stands the watcher down silently |
| 4 | **`trip_status` dishonesty** (validator, CONFIRMED): a `cancelled` leg gets "Everything is on track." appended | The all-clear tail is suppressed when any item is `broken`, `repairing`, **or `cancelled`** |
| 5 | **`fix_trip` races the consent gate** (observed live: the orb repaired the trip while the phone watcher waited) | During an `awaiting_consent` window **for the session's pinned trip**, `fix_trip` launches nothing and answers with a speakable deferral ("I'm already asking you on the phone — just say yes on the call and I'll get started."). Other trips, and windows already resolved, behave as today |
| 6 | **Acceptance-package recurrences** | Adopt the validator's two tests into the suite (they must pass); harden `pr-evidence-guard` to reject placeholder bodies — it must require the three evidence sections (mock walkthrough, live run, pytest tail), not merely a non-empty body |

### Not in scope

- Raising the watcher timeout (interview decision: 180 s was never the problem — the
  match was).
- The validator's proposed browser-automation e2e tests (standing Phase 10 decision:
  page JS is scripted manual QA).
- The report's "risks not covered": multi-instance session state (standing
  single-instance scope — but the live rerun should confirm the service's
  max-instances setting), the dial-succeeds/break-fails window (accepted
  call-before-write consequence), Secret Manager migration (post-hackathon ops).
- Any change to the demo contract, page layout, or call scripts beyond the fixes.

## Decisions

- **`room_name` is the session join key** (finding of fact, not a choice): the
  `/api/v1/calls` response and the logs-list rows share `room_name`; `call_id`
  appears only in the former. `find_session` keeps matching `id`/`session_id` and
  adds `room_name` — additive, so the L4 `/status?session_id=` surface is untouched.
  `room_name` is a session identifier, not a transport secret — returning it from
  `place_call` does not violate the sanitization invariant (callee number and API
  key stay scrubbed).
- **fix_trip defers to the phone** (interview): one consent channel at a time. The
  deferral triggers only when the registry holds `awaiting_consent` for the
  session's own pinned trip; it is a speakable string, never an error. This keeps
  Call 2 always originating from the watcher and makes the QA hazard (operator
  talks to the orb mid-window) safe by construction.
- **The atomic grant** (race fix): `resolve` is synchronous module state on a
  single event loop — calling it immediately before `launch_trip_repairs`, with no
  awaits between, closes the race completely. The items read moves *before* the
  gate; an items-read failure still resolves `ERROR` (token-guarded, as today).
- **Same-flight exclusion is hard but never fatal**: prefer a different flight
  always; if the cache offers literally nothing but the original (post-exclusion
  empty pool), fall back to the unfiltered closest-arrival pick and log — a
  repaired-if-identical flight beats a crashed repair, and the demo pins a pair
  with multiple cached itineraries anyway.
- **Validator tests are adopted verbatim** (file kept under its
  `test_validator_cascade_live_voice_demo.py` name — the name documents
  provenance) and must pass; new close-out tests follow the existing per-module
  test conventions.
- **Timeout stays 180 s** (interview); the live rerun (one full run, 2 calls) is
  the manual re-verification, and its notes go **in the PR description pre-merge**
  — which the hardened guard will now actually enforce.

## Context

- **Key seams** (all mapped this phase): `vb_cli.place_call` sanitized return
  (`vb_cli.py:147-150`) and `find_session` match tuple (`vb_cli.py:188-195`);
  the watcher chain in `demo.py` (`_await_call_transcript`,
  `_watch_consent_then_repair`, `_call_back_with_results`); the consent registry
  (`consent.py` — `resolve` is the atomic primitive); `concierge._booking_writes`
  (the item write to stamp identity into `details`), `fix_trip_impl` (the deferral
  site), and `trip_status_impl`'s all-clear tail; `sabre_tools._cancelled_flight`
  (already reads `details.airline`/`flight_number` — it just never gets them) and
  `repair_tools._rebook_flight`'s exclusion filter; the `pr-evidence-guard`
  workflow file (locate under `.github/workflows/`).
- **Live-log ground truth** (for test fixtures): a real session row carries
  `id`, `room_name`, `status`/`call_status: completed`, `transcript_text`
  (interleaved `AGENT:`/`USER:`), `started_at`/`ended_at`, `duration_seconds`,
  `post_processing_status: None` — and **no `call_id` key**. Canned payloads in
  watcher tests must use this shape (id + room_name, no call_id) so the bug class
  can't regress silently.
- **Standing rules bind as in Phase 23**: hermetic tests (no creds, no network),
  speakable failure strings from Concierge tools, `asyncio.to_thread` for blocking
  calls, additive-only status payload, no payload ever carries the callee number
  or API key.
- **Tone**: the fix_trip deferral line and any new spoken copy follow the
  Concierge voice — short, first person, one clear instruction, no jargon.
- **Schedule**: event day is 2026-07-18; this phase must land, deploy, and pass
  its live rerun before Phase 24's morning-smoke work begins. Quota note: 9 calls
  remain today (resets 5 PM PDT); the rerun costs 2.
