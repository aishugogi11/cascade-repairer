# Requirements — Phase 23: Cascade dashboard, part 2 — live voice surfaces + the consent-gated demo flow

Branch: `vb/feature/cascade-live-voice-demo` (off `vb/dev`). Spec interview 2026-07-15:
**full contract** in scope, **LLM-parsed consent**, **mock-first testing with 1–2 live
runs**. This spec promotes the Phase 23 demo contract settled with Josh at the
2026-07-15 Phase 22 QA (formerly in the local `TODO.md` inbox — promoted here and
removed there).

## Scope

One page — `GET /v1/cascade/` — carries the complete demo: **book → break → consent →
repair → callback**, with live voice surfaces layered onto the Phase 22 frame.

### The demo flow (the contract)

On stage Josh is both operator and traveler (one person, a phone and a computer).

1. **Book by voice, free of quota** — the guided Concierge flow (`search_flights`
   real InstaFlights → pick by number → `book_flight` → `complete_trip`), spoken
   through **this phase's on-page orb** in the cascade page's center column (the
   `/v1/web_call/` wiring: server-minted token, `useAIAgent → POST
   /v1/web_call/query` delegation). Demo pair: **JFK→LAX** (current verified anchor;
   re-verify morning-of).
2. **The booked trip appears on `/v1/cascade/`** — already works (`latest_trip_id`
   adoption within ~4 s; `?trip_id=` pinning as backup). No changes required beyond
   not breaking it.
3. **"Cancel flight → cascade" does two things only**: break the flight (screen turns
   red) and place **Call 1**, which describes the disruption and asks the traveler for
   consent to repair ("I can rebook it and recheck the rest of the trip — want me
   to?"). **No repairs launch at click time.**
4. **Consent comes from the call logs**: after Call 1 ends, a backend watcher polls
   the VB session logs for that call, reads the traveler's answer from
   `transcript_text`, and **launches the repair cascade only on a yes**. **The
   recovery clock starts here** — at the acknowledged go-ahead, never automatically
   at the break.
5. **Call 2 — the resolution callback** — when the backend's own repair tasks all
   land (~35 s), the call purpose is composed **from the actual repair results**
   (rebooked flight/leg details, price delta, impact from the bookings `detail`
   data) and the callback is placed: the agent "knows" because its script *is* the
   live state.

Quota: **2 calls per full run** (booking is web-voice, free).

### Surfaces (on `/v1/cascade/`)

| Surface | What it shows |
|---|---|
| **Voice orb** (center column, replaces the Phase 23 placeholder) | Live web-voice session: connect/disconnect, connection + latency state; the booking conversation happens here |
| **Conversation feed** | Traveler/Cascade turns from the on-page session, newest visible |
| **Sabre live-search log panel** | Recent live search operations — op, pair, mode (real/mock), outcome (N options / empty / fallback) |
| **Consent treatment** | Between break and consent: red disruption state + "waiting for the traveler's go-ahead," **no running clock**; declined/timeout surfaced as a stand-down message |

### Supporting backend

- **Split `/v1/demo/disrupt`**: break + Call 1 only; repairs move behind the consent
  watcher (new background task — the `launch_trip_repairs` seam unchanged).
- **Consent watcher**: poll `find_session` for Call 1's session until completed,
  LLM-classify the traveler's answer, launch repairs on yes; defined
  timeout/no-answer/declined behavior (stand down + surface on the page).
- **Completion watcher → Call 2**: await the repair tasks the backend launched, build
  the results purpose from the DB (`bookings.raw_response` → the `detail` derivation:
  why-chosen / price-delta / impact), `place_call`.
- **Purpose builders from real trip data for both calls** — kill the hardcoded
  MSP→SFO scripts in `demo.py` (`_DISRUPT_PURPOSE`, `_book_purpose`): a voice-booked
  JFK→LAX trip must get calls describing JFK→LAX. Builders read the trip/items (and
  for Call 2 the repair results) at placement time.
- **`trip_status` Concierge tool**: on-demand read of the pinned trip's current item
  statuses so any voice session answers "how's my trip?" honestly, even when repairs
  ran under another session id.
- **Optional, only if trivial** (interview decision): page-triggered disrupts pass
  the live web-voice session id so repairs also report into the session snapshot.
  Drop without discussion if it isn't a small change.

### Not in scope

- iOS changes of any kind (the in-review binary is untouched; the demo path is web).
- Sabre entitlement work — PNR writes stay mock permanently (2026-07-14 decision);
  the repair re-shop path is Phase 29's, reused as-is.
- External/durable session state — the consent/watcher registry is in-process memory
  (standing single-instance rule).
- Browser-automation tests — page JS behavior is scripted manual QA (standing
  decision, Phase 10).
- Changing the booking flow, repair tools, or status-poll contract beyond additive
  blocks.

## Decisions

- **Consent is LLM-parsed** (interview): a small classifier on the codebase's
  standard LLM path (OpenAI Agents SDK — `Agent` + `Runner.run`, default
  `gpt-5.4-mini`), fed Call 1's `transcript_text` (the USER turns are the signal),
  returning exactly one of **yes / no / ambiguous**. Robust to phrasing ("go ahead
  and fix it") at the cost of a model call in the demo's critical path — accepted.
  The classifier sits behind a plain-function seam so tests mock it hermetically.
- **Only an unambiguous yes launches repairs.** No, ambiguous, no-answer, and
  watcher timeout (~2–3 min after Call 1 placement) all **stand down**: no repairs,
  page keeps the red waiting state and surfaces the stand-down reason; the operator
  may click Cancel again to re-trigger (a fresh Call 1 — costs quota; the flight
  break is already idempotent).
- **Timer anchoring changes** (settled UI decision, Josh 2026-07-15): today the page
  starts the 60-second timer when any leg reads `broken`; after this phase it starts
  at repair launch (first `repairing` observed — which in this flow only happens
  after the consent watcher fires) and settles on all-clear, same as today. Between
  break and consent: red state, waiting treatment, no clock.
- **Consent state lives in an in-process registry** (module-level, keyed by
  trip_id: awaiting_call → awaiting_consent → granted / declined / timed_out, with
  timestamps and Call 1's call_id), surfaced to the page as an **additive,
  best-effort block** on `GET /v1/itinerary/status/{trip_id}` (the
  `detail`/`pending_options` precedent — omitted when there's nothing to say, a
  failure can never break the poll).
- **Sequencing is strict**: Call 1 → hang up → consent detected → repairs run →
  Call 2 **only after all repair tasks land**, its purpose from actual results.
- **Call-before-write invariant preserved** (Phase 12, tested): Call 1 fires before
  the flight break is written; a failed call means nothing was written. No payload
  ever carries the callee number or API key.
- **Spike facts to build on (resolved 2026-07-15, read-only probe)**: the VB session
  log payload carries full interleaved `AGENT:`/`USER:` transcripts in
  `transcript_text`, with `status`/`call_status: completed`, timestamps, and
  `duration_seconds`; `post_processing_status` may be null with the transcript
  already present (written by the live pipeline — poll cadence absorbs lag).
  Confirm while building, not blockers: whether `place_call`'s returned `call_id`
  equals the log's session `id` (`find_session` already matches both key shapes).
- **Search-log panel data**: a small module-level ring buffer recorded at the Sabre
  dispatcher boundary (op, pair/dates, mode, outcome, timestamp), exposed by a
  gated GET endpoint the page polls. In-process, demo-scale, no schema change.
- **Orb wiring must not drift**: the cascade page gets the same pinned VB CDN
  versions as `/v1/web_call/` — inject them at serve time in `cascade_ui.py` from
  the constants in `web_call.py` (the `mobile_voice.py` no-drift pattern), not
  copy-pasted into static HTML.
- **Testing is mock-first** (interview): every pytest is hermetic — `vb_cli`
  (`place_call`, `find_session`), `launch_trip_repairs`, and the consent-classifier
  seam mocked with canned payloads (including a real-shaped `transcript_text` with
  the traveler's "Yeah" consent). Manual validation budgets **1–2 live end-to-end
  runs** (2 calls each; 10/day quota, resets 00:00 UTC).

## Context

- **Design source of truth**: `about/ui_ideas/ui_mockup_2026_07_09.png` — the Phase
  21/22 pages already follow it; the center voice column is the last empty slot.
  Page conventions: self-contained HTML/CSS/JS in `backend/api/assets/cascade/`,
  no build step, read per request (`uvicorn --reload` doesn't watch HTML), `?code=`
  → `localStorage` → `X-Access-Code`, shell on the access-gate allowlist, driven by
  the 1.5 s status poll.
- **Key code seams** (mapped 2026-07-15): `demo.py:124-162` (disrupt flow, hardcoded
  purposes at 71-80/54-66), `vb_cli.py:115-150` (`place_call` → `{call_id,
  status}`), `vb_cli.py:179-195` (`find_session`, matches `id` and `session_id`),
  `sabre_tools.py:234-254` (`launch_trip_repairs`), `concurrency_core.py` (the
  asyncio background pattern), `itinerary_ui.py:126-197` (`detail` derivation from
  `bookings.raw_response` — Call 2's input), `concierge.py:637-681` (tool
  registration for `trip_status`), `web_call.py:58-107` (token mint) and 184-214
  (`/query`), `assets/cascade/page.html` (timer at 805-834, placeholder at 539-547,
  triggers at 1265-1319).
- **Standing rules that bind this phase**: background work is `asyncio.create_task`
  (never sequential await); blocking calls (BigQuery DML, `vb` CLI subprocess) in
  async paths go through `asyncio.to_thread`; DB stores UTC, edges speak Pacific
  labeled "PT"; every Concierge failure path returns a speakable string; tests are
  hermetic (no GCP creds, no `OPENAI_API_KEY`, no network).
- **Tone**: call scripts are the agent speaking to a stressed traveler — calm,
  concrete, first person, short sentences; state what happened, what can be done,
  and ask one clear question (Call 1) or report the fixed state plainly (Call 2).
  Page copy matches the existing dashboard voice ("waiting for the traveler's
  go-ahead"), sentence case, no jargon.
- **Quota discipline**: `place_call` blocks ~10–16 s until queued; the phone rings
  ~10–15 s later. Development against mocks; live runs are deliberate.
- **Process lesson carried in (Phase 30/22 close-outs)**: PR evidence goes in the
  description **pre-merge** — the `pr-evidence-guard` workflow enforces a non-empty
  description; validation.md's DoD lists the exact evidence to attach.
