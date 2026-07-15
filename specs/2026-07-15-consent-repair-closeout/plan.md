# Plan — Phase 31: Phase 23 close-out — the consent flow works live

Ordered by demo criticality: the Call 2 blocker first, then the repair-quality and
race fixes, then the honesty/guard items. Groups 1–3 are independently shippable;
Group 4 is adoption + process.

## 1. The session join: `room_name` end to end (the Call 2 blocker)

1. `vb_cli.place_call`: the sanitized payload gains `"room_name":
   raw.get("room_name")` alongside `call_id`/`status` (room_name is a session
   identifier — the callee number and API key stay scrubbed; update the docstring's
   sanitization note).
2. `vb_cli.find_session`: the match tuple gains `session.get("room_name")` —
   additive, so the existing L4 `/status?session_id=` lookups keep working.
3. `demo.disrupt`: key the consent flow on `call.get("room_name") or
   call["call_id"]` — pass it to `consent.register_awaiting` and the watcher (the
   registry's `call_id` field stores whichever key is in use; add a comment).
4. Tests (`test_vb_cli.py`, `test_demo.py`, `test_outbound_call.py` if its shape
   assertions notice): `place_call` returns room_name from a canned `vb call` JSON;
   `find_session` finds a session by room_name against a **live-shaped payload**
   (`id` + `room_name`, `call_status`, `transcript_text`, and **no `call_id`
   key**); the watcher succeeds end to end when the call response's `call_id`
   deliberately differs from the log's `id` (the exact live failure, reproduced);
   disrupt registers the room_name key. Update the integration test's canned
   payloads to the live shape.

## 2. The rebooked flight must differ from the original

1. Verify `FlightOption` carries `airline`/`flight_number` (Phase 28's dedupe
   implies it); `concierge._booking_writes` stamps `details={"airline": ...,
   "flight_number": ...}` on the flight `ItineraryItem` (details is an existing
   JSON column — additive, no schema change).
2. Confirm `sabre_tools._cancelled_flight` now resolves the identity from those
   details (it already reads exactly these keys) and that
   `repair_tools._rebook_flight`'s exclusion filter hard-excludes the tuple.
3. Belt-and-braces in the re-shop selection: when no identity is available,
   exclude candidates whose depart **and** arrive times equal the original's;
   if exclusion empties the candidate pool, fall back to the unfiltered pick and
   log a warning naming the trip (never a crash, never a silent skip).
4. Tests: a voice-booked item carries the chosen option's identity in `details`;
   `_cancelled_flight` extracts it; a repair whose cache contains the original
   flight picks a different one (assert the rebooked `flight_number` ≠ original);
   the empty-pool fallback path logs and still books; times-equality exclusion
   covers the no-identity case (seed-trip shape).

## 3. Watcher race + honesty + the consent-window deferral

1. Race fix in `demo._watch_consent_then_repair`: move the items read before the
   gate, then `if not consent.resolve(trip_id, token, consent.GRANTED): return` —
   **no awaits between the resolve and `launch_trip_repairs`**. The items-read
   failure path still resolves `ERROR` (token-guarded).
2. `concierge.trip_status_impl`: suppress the "Everything is on track." tail when
   any item is `broken`, `repairing`, or **`cancelled`**.
3. `concierge.fix_trip_impl`: after `ensure_trip_context`, if the registry holds
   `awaiting_consent` for the pinned trip, return the speakable deferral ("I'm
   already asking you on the phone — just say yes on the call and I'll get
   started.") and launch nothing. Import is `from api import consent` (no cycle:
   consent imports nothing from concierge); read via a best-effort try so a
   registry hiccup can never kill the spoken turn.
4. Tests: adopt `test_validator_cascade_live_voice_demo.py` into the tracked suite
   — both validator tests must now pass; add fix_trip deferral tests (awaiting →
   deferral line + no launch; granted/declined window → normal launch; other
   trip's window → normal launch).

## 4. Guard hardening + close-out

1. `pr-evidence-guard`: locate the workflow (`.github/workflows/`) and require the
   three evidence sections in the PR body — mock-walkthrough, live-run, and pytest
   markers — failing on the generated-placeholder body verbatim. Keep the check
   dependency-free (shell/grep in the workflow). Add the workflow-unit test only
   if the repo already has a harness for workflow files; otherwise document the
   required section headings in the workflow's comment header and README.
2. Run the full validation pass (validation.md), including the one budgeted live
   rerun (2 calls) against the deployed merge; write the run notes into the PR
   description **before** merging.
3. While on the live rerun: confirm the Cloud Run service's max-instances setting
   is 1 (the in-process consent registry's standing assumption) — note it in the
   PR evidence; if it isn't, flag for Phase 24 rather than changing it here.
4. Mark Phase 31 complete in `specs/roadmap.md` per the SDD flow.
