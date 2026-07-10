# Cascade Repairer — demo runbook

The 60-second moment, scripted. Two operator actions, both buttons on the
demo page. Everything else is watched, not driven.

## Preconditions (run these the morning of, not five minutes before)

1. **Service healthy**: `GET https://<cloud-run-url>/v1/hello/gcp_check`
   reports BigQuery and GCS both reachable.
2. **Voice env present**: `POST https://<cloud-run-url>/v1/demo/book` would
   need `VOCAL_BRIDGE_API_KEY`, `VOCAL_BRIDGE_CALLER_AGENT_ID`, and
   `VOCAL_BRIDGE_CALLEE_PHONE` on the service. Dry-check without placing a
   call: `GET /v1/outbound_call/status` — a **503 names the missing var**;
   a 200/404 means the voice env is set.
3. **Outbound call credits**: Vocal Bridge credits can run out per
   destination (observed locally 2026-07-10: "Outbound call credit exhausted
   for this destination" → 502, no data written). Place one throwaway test
   call well before showtime; top up if it 502s.
4. **Sabre mode**: `SABRE_MODE` unset or `mock` for rehearsal (event day:
   flip to `real`; mocks remain the per-call fallback).
5. **The callee phone** (the "traveler") is unmuted, has signal, and is in
   the presenter's hand — not the operator's. The agent calls *it*, that's
   the show.
6. **The demo page** `https://<cloud-run-url>/v1/demo/` is loaded on the
   projector **fresh** (no `?trip_id=` in the URL — a leftover param means
   it will resume an old trip; strip it and reload).
7. Phone audio is on speaker or routed to the room's sound.
8. **No page-restyling extensions** on the projector browser: Dark Reader
   inverts the projector-calibrated light palette despite the page's
   `color-scheme: only light` opt-out (observed 2026-07-10). Disable it for
   the Cloud Run domain or use a clean profile.

## The script

### Beat 1 — the trip books itself over a phone call (~45–60 s, before the "moment")

| Step | Operator does | Audience sees / hears |
|------|---------------|----------------------|
| 1.1 | Press **📞 Trigger call** | Phone card: "Dialing the traveler…"; presenter's phone rings seconds later |
| 1.2 | Presenter answers, on speaker | Agent narrates the booked trip: MSP→SFO flight July 17, Mountain View hotel, airport ride, Castro Street dinner, museum tour |
| 1.3 | — (nothing) | Five itinerary cards fill in as **booked** while the agent is still talking; pill reads "Trip on track" |
| 1.4 | Wait for **⚠️ Flight canceled** to light up | The page armed itself once the booking rendered |

Talk track while it books: "No app, no form — the trip was booked and the
traveler heard about it on a phone call."

### Beat 2 — the cascade (the 60-second moment)

| Step | Operator does | Audience sees / hears |
|------|---------------|----------------------|
| 2.1 | Press **⚠️ Flight canceled** | Phone rings again — *the agent is calling first* |
| 2.2 | Presenter answers | "Your flight was just cancelled — I'm already rebooking it and rechecking the rest of your trip. Give me about thirty seconds." |
| 2.3 | — (nothing) | Flight card flips **broken** (red); recovery timer starts; cards move broken → **repairing** (amber, pulsing) → **fixed** (green); repair feed narrates each leg |
| 2.4 | — | Pill flips "Trip repaired"; timer freezes green **under 60.0s** |
| 2.5 | Presenter (on the still-open call) | Agent confirms the repaired plan; hang up |

## Timings (fill during rehearsal runs)

| Run (date/time) | Beat 1: dial → phone rings | Beat 1: book → 5 cards booked | Beat 2: dial → phone rings | Beat 2: broken → all fixed (page timer) | Clean? | Notes |
|---|---|---|---|---|---|---|
| 2026-07-10 ~11:39 UTC (data path only, Cloud Run) | n/a — calls blocked | seed → 5 booked, immediate | n/a — calls blocked | **24.0 s** (curl-measured, break → all_clear) | partial | Outbound calls 502: "credit exhausted for this destination" — voice beats unproven. Data path clean: 5× fixed, fresh updated_at, 7 confirmed bookings, no orphan trips from failed /book. Page verified rendering the trip on the deployed URL. |
| 2026-07-10 ~12:0x UTC (full voice run, Cloud Run, post Developer-plan upgrade) | /book returned in **16 s** (CLI blocks until call queued); phone rang, call completed | 5 booked by the time /book returned | /disrupt returned in **6.6 s**; call completed ~30 s in, cancellation script + "already rebooking" delivered (transcript verified) | **20.8 s** (curl-measured from disrupt response → all_clear) | **yes** | Both calls real (curl-driven, not page buttons). Callee number scrubbed from /status; recording available; 7 confirmed bookings. Findings: (1) plan-side outbound requires Developer tier — Starter has none; (2) /book's 16 s is dead air after the button press — presenter should vamp or we pre-dial; (3) beat 2 agent restarted its opening several times when talked over — answer, then let it finish the first sentence; (4) /status transcript JSON carries a raw control char — strict JSON parsers need strict=False. |
| | | | | | | |

Reference points from earlier phases: five repairs completed in ~35 s on
Cloud Run (Phase 6 walkthrough); itinerary page polls every 1.5 s, so add up
to ~1.5 s of render lag on top of any write.

## Recovery moves (when a beat misfires)

- **Call not answered / voicemail**: the data side still ran — the booking
  landed or the repairs are running, the screen tells the story. Presenter
  ad-libs ("the agent left me a voicemail — and look, it fixed the trip
  anyway"), operator checks `GET /v1/outbound_call/status` after.
- **`/book` or `/disrupt` returns an error**: it renders in the red strip on
  the page. 503 = env var missing on the service (see preconditions);
  502 = Vocal Bridge call failed — press the button again (a second `/book`
  creates a second trip; that's fine, the page follows the new one — but do
  NOT re-press mid-working-demo, only after a visible failure).
- **A repair sticks in `repairing`**: give it 10 s past the usual ~35 s; if
  stuck, say so honestly, and re-run the repair without a new call:
  `POST /v1/sabre_tools/repair_trip {"trip_id": "<id>", "wait": false}`.
- **Page stalls / accidental refresh**: the URL carries `?trip_id=` — a
  refresh resumes the same trip within one poll (1.5 s). The feed history
  and the timer restart from the current statuses; if the trip is
  mid-repair the timer restarts, so quote the wall clock, not the timer, if
  this happens during the moment.
- **Total do-over**: reload the page without `?trip_id=` and start from
  Beat 1 — each run seeds a fresh trip, old ones don't interfere.

## Open question — settle during rehearsal

Call ordering inside `/disrupt` is currently **call first, then break**
(phone rings while the screen changes). If rehearsal shows the ring lags the
red flip badly (or vice versa) and the beat feels off, note the observed gap
here and whether the order should swap:

- Observed gap, run 1 (2026-07-10, curl-driven): call placed ~6 s before the
  break wrote; the flight rendered broken within ~1 s of the /disrupt
  response — ring and red-flip land close together. Stage feel with real
  hands on the button still to be judged on the projector.
- Verdict: keep call-first unless the projector run says otherwise.
