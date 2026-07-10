# Phase 12: Dress rehearsal — validation

## Automated

Run from the repo root (the project's standing pattern — see
`vocal-bridge-local-testing` memory / `Makefile`):

```
docker compose exec vocal-bridge-be pytest
```

All tests pass with **no** GCP credentials, `OPENAI_API_KEY`, or
`VOCAL_BRIDGE_*` env vars in the container. Specific assertions required:

- [ ] `POST /v1/demo/book` and `POST /v1/demo/disrupt` return **503** naming
      the missing env var when any of `VOCAL_BRIDGE_API_KEY`,
      `VOCAL_BRIDGE_CALLER_AGENT_ID`, `VOCAL_BRIDGE_CALLEE_PHONE` is unset.
- [ ] `/book` happy path (mocked `vb_cli.place_call` + seed seam): the call is
      placed **before** the trip write, the injected purpose contains the trip
      narrative, and the response is exactly `{trip_id, call_id, call_status}`
      — no phone number, no API key anywhere in the payload.
- [ ] `/book` with `place_call` failing returns **502** with the error
      scrubbed and does **not** seed a trip.
- [ ] `/disrupt` happy path: flight flipped via the extracted
      `break_trip_flight`, repairs launched through `launch_trip_repairs`
      without awaiting, response carries `repair_session_id` and `launched`
      (five names).
- [ ] `/disrupt` against a trip with no flight item returns **404**.
- [ ] `GET /v1/demo/` serves the page HTML (200, `text/html`).
- [ ] Pre-existing suites still pass untouched — especially
      `seed_trip`/`break_flight` endpoint tests after the extraction refactor.

No typecheck gate exists in this repo; pytest inside the built container (CI)
is the automated bar.

## Manual — deployed rehearsal (strict)

All manual validation runs against the **deployed Cloud Run service**
(`vocal-bridge-be-dev`), `SABRE_MODE=mock`, operator's phone as
`VOCAL_BRIDGE_CALLEE_PHONE`. Local-only runs do not count.

Walkthrough (the runbook is the script; this is the acceptance summary):

1. [ ] Open `https://<cloud-run-url>/v1/demo/` — page renders with "Trigger
       call" enabled and "Flight canceled" disabled.
2. [ ] **Beat 1**: press "Trigger call" → operator's phone rings; the agent
       narrates the booking; within a few polls the five itinerary cards
       render as `booked`; "Flight canceled" becomes enabled.
3. [ ] **Beat 2**: press "Flight canceled" → phone rings again; agent opens
       with the cancellation + already-rebooking line; the flight card flips
       `broken`, cards move through `repairing` → `fixed`, the repair feed
       narrates, and the recovery timer runs.
4. [ ] **Hard gate: broken → all five `fixed` in under 60 seconds** on the
       page's own timer. Over 60 s = phase not done, no exceptions (user
       decision: strict).
5. [ ] BigQuery spot check: `itinerary_items` rows show fresh `updated_at`
       for the flips; `bookings` rows exist for the repairs (Phase 6
       invariants still hold through the new path).
6. [ ] `GET /v1/outbound_call/status` after each beat returns the session
       with a transcript and no leaked phone number / API key.

Edge cases:

- [ ] Pressing "Trigger call" twice does not create a second trip mid-demo
      (button disabled after first success).
- [ ] "Flight canceled" before a trip is live is impossible (disabled) or
      safely rejected.
- [ ] A failed beat (e.g. Vocal Bridge 502) shows an on-page error the
      operator can read from the projector — never a silently dead button.
- [ ] `/v1/disruption/break_flight` still works standalone (curl) — the
      injector contract is unchanged.

## Tone check

- [ ] Page copy is traveler-voiced and projector-legible; matches the
      itinerary page's register ("Your flight was cancelled — already
      rebooking"), no debug jargon visible.
- [ ] Both call purposes read as a calm, concrete agent: what happened, what's
      being done, a time promise. No internal ids or tool names spoken.

## Definition of done

- Automated suite green in CI (pytest inside the built image) and locally.
- One clean, uninterrupted two-beat run on the deployed stack with the
  under-60-seconds recovery gate met, timings recorded in the runbook.
- Runbook complete: preconditions, script, measured timings, recovery moves,
  and the empirically-settled call-ordering note.
- Phase 12 marked `[x] COMPLETE` in `specs/roadmap.md`.
