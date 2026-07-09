# Validation — Concierge hybrid architecture (Phase 9)

## Automated

From `backend/`: `python -m pytest` passes hermetically (no `OPENAI_API_KEY`, no
GCP credentials, no network — the CI bar). Assertions that must exist and pass:

- **Seam**: `POST /v1/web_call/query` contract unchanged (422 blank, 503 missing
  key, 200 reply, 502 on failure, per-session memory, isolation) with the
  Concierge behind it.
- **Snapshot**: the agent built for a turn carries the session snapshot in its
  instructions — pending and finished repair names present, authoritative marker
  present.
- **Launch inversion**: `fix_trip` returns while launched repair tasks are still
  pending (asserted, not assumed); its return value names every launched repair;
  no-trip and repository-failure paths return speakable strings, never raise.
- **Talk-while-repairing (the acceptance shape)**: with slow fake repairs in
  flight, a second `/query` turn completes and answers; completion events land in
  the session event log afterwards with correct ok/error statuses.
- **Single writer**: the five repair tools no longer write itinerary status
  (bookings row only); items still reach `repairing` → `fixed` through
  `_repair_one`; a failed/0-row status write still surfaces as an error event.
- **Endpoint parity**: `POST /v1/sabre_tools/repair_trip` behaves exactly as
  before through the extracted `launch_trip_repairs`.
- No regressions across the full suite.

## Manual (deployed via the normal PR → `vb/dev` flow)

The roadmap acceptance, verbatim: *the foreground agent holds a voice
conversation while multiple background repair tools execute in parallel —
Phase 5's test, now over voice.*

1. **Setup**: `POST /v1/sabre_tools/seed_trip`, then
   `POST /v1/disruption/break_flight` for that trip. Confirm the flight item is
   `broken` in BigQuery.
2. **The moment**: open `/v1/web_call/`, Connect, and say *"my flight was just
   cancelled — can you fix my trip?"* Expect: a spoken launch confirmation within
   the bridge-line window naming the repairs, while the VB layer covers the wait.
3. **Talk while it works**: immediately ask something else (*"what should I do
   when I land?"*), then *"how are the repairs coming?"* Expect: prompt answers
   throughout — repairs named with pending/finished status, no clarifying
   question, no dead air. This is the acceptance moment; if the agent stalls
   until repairs finish, the phase fails.
4. **The rows**: in the BigQuery console, the trip's five `itinerary_items` flip
   broken/booked → `repairing` → `fixed` with fresh `updated_at`, and five new
   `bookings` rows exist. Note rough wall-clock: seed-to-all-fixed should be in
   the Phase 6 ballpark (~35 s), concurrent with speech.
5. **Read-back**: ask *"so is everything sorted?"* — the agent summarizes the
   repaired trip from the snapshot.
6. **Edge**: disconnect mid-repair and reconnect (new VB session): the new
   session starts clean and the old session's background repairs still complete
   in BigQuery.
7. **Timing note for Phase 11**: record approximate spoken-answer latency per
   turn (the ~2–6 s target) — this becomes the eval baseline.
8. **Sessions/turns**: the conversation logged with client `vb_web`; VB session
   log shows the call `completed` afterwards (`vb logs list` — watch the
   minutes, end the call).

## Tone check

Spoken replies stay one–two conversational sentences; the launch line sounds
like a capable human ("I'm already rebooking your flight and fixing the other
four — ask me anything while I work"), not a job scheduler; no markdown, ids, or
tool names spoken aloud.

## Definition of done

- Automated suite green in CI inside the built container.
- Manual steps 2–4 pass live on Cloud Run: conversation continues while five
  real repairs run concurrently and the BigQuery lifecycle completes — the
  roadmap acceptance for Phase 9.
- `_repair_one` is the single writer of itinerary status transitions.
- Roadmap Phase 9 marked complete by the implement step.
