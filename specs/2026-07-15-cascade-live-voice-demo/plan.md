# Plan — Phase 23: live voice surfaces + the consent-gated demo flow

Task groups are ordered so each lands independently: backend truth first (purposes,
consent machinery, watchers), then the status surface, then the page. Group 1–4 are
pure backend and fully testable in mock mode; Group 5 is the page; Group 6 closes.

## 1. Purpose builders from real trip data (kill the MSP→SFO scripts)

1. Add a purpose-builder module (e.g. `backend/api/call_purposes.py`) with plain,
   test-friendly functions:
   - `build_disrupt_purpose(trip, items) -> str` — Call 1: names the traveler's real
     route/date (from the `trips` row + flight `itinerary_items`), states the flight
     was cancelled, and asks one clear consent question ("I can rebook it and
     recheck the rest of the trip — want me to?").
   - `build_results_purpose(trip, items, details) -> str` — Call 2: composed from the
     post-repair state — rebooked flight (route, PT times), price delta, downstream
     legs re-checked — reusing the `detail` derivation (`itinerary_ui._details_for`
     / `_item_detail`) so the script *is* the live state. Degrade gracefully when a
     `detail` is absent (best-effort, never raises).
   - `build_book_purpose(...)` for Beat 1's `/v1/demo/book` if it survives — at
     minimum, stop describing a trip the data contradicts.
2. In `demo.py`, delete `_DISRUPT_PURPOSE` / `_book_purpose` hardcoded narratives;
   builders read the pinned trip at placement time (repo reads via
   `asyncio.to_thread`, standing rule).
3. Tests (`test_demo.py` / new `test_call_purposes.py`): a JFK→LAX trip yields
   purposes containing "JFK"/"New York" and "LAX"/"Los Angeles" and **never**
   "Minneapolis"/"San Francisco"; Call 2 purpose carries the rebooked details and
   price delta from a canned `raw_response`; missing detail degrades, never raises;
   no purpose ever contains the callee number or API key.

## 2. Consent registry + the `/v1/demo/disrupt` split

1. New module (e.g. `backend/api/consent.py`): in-process registry keyed by
   `trip_id` — states `awaiting_call → awaiting_consent → granted | declined |
   timed_out` (+ `call_id`, timestamps, human-readable `message`). Module-level
   dict, same lifecycle rules as `_SESSION_TRIPS` / `concurrency_core._SESSIONS`.
2. Rework `demo.disrupt()` (`demo.py:124-162`) to do exactly two things:
   - `place_call(build_disrupt_purpose(...))` — **before any write** (invariant).
   - `break_trip_flight(trip_id)` — screen turns red.
   Then register `awaiting_consent` with Call 1's `call_id` and
   `asyncio.create_task(consent_watcher(...))`. **No `launch_trip_repairs` here.**
   Response shape gains `consent: "awaiting"` (additive); keep
   `trip_id/item_id/call_id/call_status`.
3. Re-trigger semantics: clicking Cancel again on the same trip replaces the
   registry entry and starts a fresh watcher (flight break is idempotent; a stale
   watcher observing a superseded entry exits without acting).
4. Tests: disrupt places the call before `break_trip_flight` (existing invariant
   test updated), launches **no** repairs, registers `awaiting_consent`, spawns the
   watcher; failed call → nothing written, no watcher.

## 3. Consent watcher → repairs → completion watcher → Call 2

1. `consent_watcher(trip_id, call_id, ...)` (async, in `consent.py` or `demo.py`):
   poll `find_session(call_id)` via `asyncio.to_thread` every ~4 s until the session
   reads completed (`status`/`call_status`), overall timeout ~2–3 min. Handle both
   id shapes (`find_session` already matches `id`/`session_id`); tolerate
   `transcript_text` lag (`post_processing_status` may be null — keep polling until
   text is present or timeout).
2. Consent classifier behind a seam: `classify_consent(transcript_text) -> "yes" |
   "no" | "ambiguous"` — a minimal Agents SDK call (`Agent` + `Runner.run`,
   `gpt-5.4-mini` default, env-overridable), instructions pinned to judge only the
   USER turns' answer to the repair question, forced to one of the three labels.
   Plain function so tests monkeypatch it.
3. Outcomes:
   - **yes** → `launch_trip_repairs(session_id, items)` (seam unchanged; fresh
     `demo-…` repair session id), registry → `granted`, then hand the launched
     tasks to the completion watcher.
   - **no / ambiguous / timeout / no transcript** → registry → `declined` /
     `timed_out` with a speakable `message`; no repairs; watcher exits.
4. `completion_watcher(...)`: `await asyncio.gather(*tasks)` on the repair tasks
   the backend itself launched, then read the post-repair trip/items/details
   (`to_thread`), `build_results_purpose(...)`, and `place_call` (Call 2). A repair
   task erroring still yields a truthful Call 2 (the purpose reflects actual item
   states — best-effort, never silent).
5. Keep strong references to both watcher tasks (the `_BUILD_TASKS`/`_LOG_TASKS`
   pattern) so they can't be GC'd mid-flight.
6. Tests (canned `transcript_text` payloads incl. the real-shaped "Yeah" consent):
   yes → repairs launched + Call 2 placed **after** tasks land, with the results
   purpose; no → stand down, no repairs, no Call 2; ambiguous → stand down;
   timeout (session never completes) → `timed_out`, no repairs; transcript-lag
   (completed but text arrives on poll N) → still granted; classifier seam is
   mocked everywhere (no `OPENAI_API_KEY`).

## 4. `trip_status` Concierge tool + Sabre search-log seam

1. `trip_status_impl(session_id)` in `concierge.py`: resolve the pinned trip
   (`ensure_trip_context`), read current item statuses (repo via `to_thread`),
   return a **speakable** one-liner per leg (statuses in plain words, PT-labeled
   times where spoken); speakable failure strings for no-pin/no-trip.
2. Register in `build_agent()` (`concierge.py:637-681`) as
   `function_tool(_trip_status, name_override="trip_status")`; add a
   `BASE_INSTRUCTIONS` clause (answer "how's my trip?" with the tool, marked
   authoritative per the Phase 5 snapshot lesson).
3. Search-log ring buffer: record at the dispatcher boundary (`sabre/client.py`) —
   `(ts, op, mode, origin/dest/date summary, outcome: n-options | empty |
   fallback | error)` into a bounded `deque`; expose `GET
   /v1/sabre_tools/search_log` (gated, JSON list, newest first).
4. Tests: tool registered and speaking statuses honestly across sessions (book in
   one session, repairs under another id, `trip_status` still truthful); ring
   buffer records real/mock/fallback outcomes; endpoint gated
   (`test_access_gate.py` route list) and additive.

## 5. Status surface + the cascade page

1. Additive `consent` block on `GET /v1/itinerary/status/{trip_id}`
   (`itinerary_ui.py`): `{state, message, since}` from the registry — omitted when
   no entry; a registry read can never break the poll (the `detail` /
   `pending_options` precedent).
2. Voice orb (center column, replaces `#voice-placeholder`,
   `assets/cascade/page.html:539-547`): the `/v1/web_call/` wiring — token via
   `POST /v1/web_call/token`, `useAIAgent → POST /v1/web_call/query` with
   `session_name` + pinned `trip_id`; connect/disconnect control; connection state
   (idle → connecting → live → error) and a simple latency readout (e.g. per-turn
   query round-trip). Serve via `cascade_ui.py` template substitution importing the
   pinned CDN versions from `web_call.py` (the `mobile_voice.py` no-drift pattern —
   this converts the page from static-read to template-substituted; keep per-request
   read).
3. Conversation feed: traveler/Cascade turns appended client-side from the orb's
   own session (query + reply pairs), newest visible, in the mockup's feed
   treatment.
4. Sabre live-search log panel: poll `GET /v1/sabre_tools/search_log` (~4 s),
   render op/pair/mode/outcome rows.
5. Timer re-anchor + consent treatment (`page.html:805-834`): the 60-s timer starts
   on first **`repairing`** observed (never on `broken`); between break and consent
   the page shows red disruption + "waiting for the traveler's go-ahead" (no
   running clock), driven by the status `consent` block; `declined`/`timed_out`
   render the stand-down message and leave Cancel re-armable.
6. Tests (markup-level, no browser — `test_cascade_ui.py` conventions): page
   carries the orb wiring (`/v1/web_call/token`, `/v1/web_call/query`, pinned CDN
   versions match `web_call.py`'s), the feed and search-log containers, the
   waiting-treatment strings, and **no** timer-start-on-broken logic; status
   endpoint tests for the additive `consent` block (present/omitted/failure-proof).

## 6. Integration, docs, close-out

1. End-to-end mocked flow test: book (mock fares) → disrupt (mock call) → canned
   consent "yes" → repairs land → Call 2 placed with results purpose — one test
   walking the whole contract.
2. Optional (only if trivial, per interview): thread the page's live web-voice
   `session_name` through the disrupt POST so repairs report into that session's
   snapshot. Drop silently if not small.
3. README: update the demo-run notes (cascade page is now the one-page demo; quota
   math unchanged at 2 calls/run) and the local mock-mode walkthrough.
4. Run the full validation pass (validation.md), then mark Phase 23 `[x] COMPLETE`
   in `specs/roadmap.md` per the SDD flow.
