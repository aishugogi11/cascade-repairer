# Validation — Pacific-time discipline & pin the displayed trip

## Automated

Full suite in the container (hermetic — no GCP creds, no `OPENAI_API_KEY`):

```
docker compose exec -T backend python -m pytest tests/ -q
```

All tests green, including these specific assertions:

- [ ] A `06:15` mock departure written by `_booking_writes` stores an instant equal
      to `13:15Z` for a July date (Pacific wall-clock declared, PDT = UTC−7).
- [ ] `_completion_items` and `_SEED_ITEMS` timestamps convert the same way.
- [ ] `answer_query(session, query, trip_id=…)` on a non-empty trips table pins the
      passed trip (its summary reaches the agent instructions).
- [ ] A pinned session queried with a different `trip_id` keeps its original pin
      (pin-only-if-unpinned).
- [ ] `answer_query` with **no** `trip_id` still reaches `search_flights` — the
      Phase 18 booking regression test passes unmodified.
- [ ] `POST /v1/web_call/query` forwards `trip_id` to the seam; omitting the field
      is byte-identical to today's behavior.

No typecheck gate exists in this repo; CI = pytest inside the built image.

## Manual

Restart the container before page checks (`uvicorn --reload` ignores HTML edits).

**Timezone walkthrough (mock mode, local or deployed):**

- [x] Voice-book a flight via `/v1/web_call/?code=…` (or curl the `/query` seam):
      the agent speaks a departure time; open `/v1/itinerary/?trip_id=…` — the card
      shows the **same wall-clock time**, labeled PT.
- [x] Repeat the check on `/v1/demo/` cards and both pages' repair-feed clocks.
- [ ] Viewer-independence: switch the OS/browser timezone (Josh is CDT — the
      original failure mode) and reload; displayed times do not move.I'm not going to do this. You can just handle that. 
- [ ] Seeded trip (`POST /v1/sabre_tools/seed_trip`): card times match `_SEED_ITEMS`
      wall clocks (e.g. flight 8:00 AM PT), not shifted. Yeah, can't test that one either because I need an access code. Here's the response I got. You'll have to check this one yourself. 
      Curl

curl -X 'POST' \
  'https://vocal-bridge-be-dev-24105435206.us-west1.run.app/v1/sabre_tools/seed_trip' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
  "user_id": "demo-traveler",
  "title": "The Complete Trip — hackathon demo"
}'
Request URL
https://vocal-bridge-be-dev-24105435206.us-west1.run.app/v1/sabre_tools/seed_trip
Server response
Code	Details
401
Undocumented
Error: response status is 401

Response body
Download
{
  "error": "missing or invalid access code"
}
Response
- [ ] Known cosmetic fallout accepted: pre-fix dev rows display ~7 h off — confirm
      and ignore, do not chase.  Yeah, I'm done chasing. Let's just get this shit done. 

**Trip-pin walkthrough:**

- [ ] Desktop parity: `/v1/web_call/?code=…&trip_id=<seed trip>` — first turn
      “where am I staying?” answers from that trip without any booking step.
- [ ] iOS simulator or Xcode install on device (**never** an App Store Connect
      upload — a binary is in App Review and must not be replaced this phase):
      with the seed trip displayed, ask the orb about the trip — the agent answers
      instead of denying a trip; then “my flight was cancelled, fix it” launches
      repairs (in-app `fix_trip` works again).
- [ ] **Bridge check with the unchanged binary**: on the app version currently
      installed (no new build — the one predating this branch's iOS changes),
      after the backend deploys, ask the orb about the displayed trip — the page
      bridge supplies `latest_trip_id` and the agent answers. This is the check
      that proves the in-review binary is fixed by backend deploy alone.
- [ ] Bridge doesn't break booking: on the unchanged binary with a **fresh/empty**
      trips context (no latest trip resolvable), the voice session still connects
      and guided booking still runs — a failed/empty `latest_trip_id` fetch must
      silently omit the pin.
- [ ] No-clobber on device: voice-book a new trip in-session, then ask a follow-up —
      answers come from the just-booked trip, not the previously displayed one.
- [ ] Fresh-user path intact: a session with no `trip_id` and no pin still gets
      guided booking (Act 1 — the Phase 18 fix must not regress).

## Tone check

- [ ] Every rendered time label reads “PT” (or “Pacific time” in prose) — never
      “PST”, never an unlabeled time.
- [ ] Any new agent-facing failure string is speakable (no codes, no jargon).

## Definition of done

- Automated suite green in the container; the six assertions above exist and pass.
- Both manual walkthroughs pass end to end in `SABRE_MODE=mock`.
- Spoken, stored-as-UTC, and displayed times agree for a fresh booking.
- No build archived or uploaded to App Store Connect — the in-review binary is
  untouched; the iOS changes ride in the first post-approval update.
- The mobile_voice page bridge is commented as temporary with its removal
  condition (native `vbSetTrip` shipping in v1.0.1), and a removal reminder is
  left in `TODO.md`.
- PR into `vb/dev` notes the iOS no-time-rendering verification (plan 4.3) and the
  accepted old-row display skew; Phase 19 marked `[x] COMPLETE` in
  `specs/roadmap.md` after merge.
