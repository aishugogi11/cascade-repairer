# Validation — Phase 31: Phase 23 close-out — the consent flow works live

Posture: hermetic-first, then **one budgeted live rerun (2 calls)** against the
deployed merge — the rerun is both this phase's proof and Phase 23's outstanding
live-run evidence. Its notes go in the PR description **pre-merge** (the hardened
guard enforces this).

## Automated

```
docker compose exec backend pytest
```

- [ ] Bare suite green **including the two adopted validator tests**
      (`test_validator_cascade_live_voice_demo.py` — both were CONFIRMED failing
      pre-phase; they must now pass unmodified in their assertions).
- [ ] No new skips; the only `RuntimeWarning`s remain the six pre-existing
      Phase 24-debt entries.

Specific assertions that must exist and pass:

- [ ] **Session join**: `place_call` returns `room_name`; `find_session` matches a
      session by `room_name` against a live-shaped payload (`id` + `room_name`,
      no `call_id` key); the watcher reaches `granted` end to end **when the call
      response's `call_id` differs from the log's `id`** — the reproduced live
      failure; the sanitized payload still never carries the callee number or API
      key.
- [ ] **Different-flight guarantee**: a voice-booked flight item carries
      `details.airline`/`details.flight_number`; the repair re-shop excludes that
      identity (rebooked flight number ≠ original in a cache containing the
      original); the no-identity path excludes equal depart+arrive times; an
      exclusion that empties the pool falls back with a warning and still books.
- [ ] **Race closed**: registering a fresh wait during the stale watcher's
      classification leaves exactly zero repair launches and zero Call 2s from
      the stale watcher (the validator's test), and the resolve-before-launch
      ordering has no awaits between gate and launch.
- [ ] **trip_status honesty**: a `cancelled` leg is spoken without any
      "on track" claim (the validator's test); broken/repairing still suppress
      it; the pure all-clear trip keeps it.
- [ ] **fix_trip deferral**: during `awaiting_consent` for the pinned trip,
      fix_trip returns the deferral line and launches nothing; resolved windows
      and other trips launch normally; a registry read failure never kills the
      turn.
- [ ] **Integration test updated**: the end-to-end mocked flow now uses
      live-shaped session payloads and passes through the room_name join.

## Manual

- [ ] **The live rerun** (deployed merge, 2 calls, JFK→LAX or the morning's
      verified pair): book by voice via the orb → Cancel → Call 1 asks consent →
      say **"yes"** → `consent.state` flips `awaiting_consent → granted` (status
      poll via curl) → repairs animate with the timer anchored at the go-ahead →
      **Call 2 arrives** and speaks the rebooked details — **and the rebooked
      flight differs from the original** (different flight number and/or time on
      the flight card).
- [ ] During the wait window, ask the orb to fix the trip — hear the deferral
      line, see no repairs start.
- [ ] Confirm the Cloud Run service's max-instances is 1; note it in the PR
      evidence (flag to Phase 24 if not — do not change it here).
- [ ] Guard check: a draft PR with the placeholder body fails
      `pr-evidence-guard`; the real body with all three sections passes.

## Tone check

- [ ] The fix_trip deferral line is Concierge voice: short, first person, one
      clear instruction, no jargon ("I'm already asking you on the phone — just
      say yes on the call and I'll get started.").
- [ ] Call 2 (unchanged copy, now actually delivered) speaks the *different*
      rebooked flight plainly — verified by ear on the live rerun.

## Definition of done

- [ ] All automated checks green in the bare suite and CI's in-image run.
- [ ] The live rerun completed against the deployed merge with all boxes above.
- [ ] **PR description carries, pre-merge**: the pytest tail, the live-rerun
      notes (date, pair, both call outcomes, the differing rebooked flight), and
      the mock-walkthrough/verification summary — the hardened guard's three
      required sections.
- [ ] Phase 31 marked `[x] COMPLETE` in `specs/roadmap.md`; Phase 23's
      "manual QA pending" qualifier resolved by this rerun (update its heading
      note accordingly).
