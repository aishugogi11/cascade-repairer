# Validation — Phase 23: live voice surfaces + the consent-gated demo flow

Testing posture (interview decision): **mock-first** — every automated test is
hermetic; manual validation budgets **1–2 live end-to-end runs** (2 calls each,
10/day quota, resets 00:00 UTC / 5 PM PDT).

## Automated

Run inside the container (host Python is not the target):

```
docker compose exec backend pytest
```

- [ ] Bare suite green (405 tests pre-phase; all new tests pass, none skipped
      accidentally) — hermetic: no GCP creds, no `OPENAI_API_KEY`, no network, and
      **no new unawaited-coroutine `RuntimeWarning`s** (the watchers are exactly the
      kind of async code Phase 24's hygiene item worries about).

Specific assertions that must exist and pass:

- [ ] **Disrupt split**: `POST /v1/demo/disrupt` places Call 1 **before**
      `break_trip_flight` (invariant preserved), launches **zero** repairs at click
      time, registers `awaiting_consent`, and spawns the consent watcher; a failed
      call writes nothing and spawns nothing.
- [ ] **Consent outcomes** (canned `transcript_text` payloads, classifier seam
      mocked): unambiguous yes → `launch_trip_repairs` called + registry `granted`;
      no → stand down (no repairs, speakable message); ambiguous → stand down;
      watcher timeout / never-completed session → `timed_out`, no repairs;
      transcript-lag case (session completed, `transcript_text` arrives on a later
      poll) still resolves.
- [ ] **Sequencing**: Call 2 is placed only **after** all launched repair tasks
      land, and its purpose is built from the post-repair `detail` data (rebooked
      route, price delta present in the string from a canned `raw_response`).
- [ ] **Real-data purposes**: for a JFK→LAX trip, both call purposes name the real
      route and **never** contain "Minneapolis"/"San Francisco"; missing `detail`
      degrades gracefully (never raises); no purpose/payload carries the callee
      number or API key.
- [ ] **Timer/consent surface**: `GET /v1/itinerary/status/{trip_id}` carries the
      additive `consent` block when a registry entry exists, omits it otherwise,
      and a registry failure cannot break the poll; the page markup has no
      timer-start-on-`broken` logic and carries the waiting-treatment copy.
- [ ] **Orb wiring**: cascade page served with the pinned VB CDN versions equal to
      `web_call.py`'s constants (no-drift test), and carries `/v1/web_call/token` +
      `/v1/web_call/query` wiring, feed and search-log containers.
- [ ] **`trip_status` tool**: registered on the agent, answers honestly across
      sessions (repairs run under a different session id), speakable failure
      strings for no-pin/no-trip.
- [ ] **Access gate**: new/changed endpoints (`/v1/demo/disrupt`,
      `/v1/sabre_tools/search_log`) appear in `test_access_gate.py`'s gated list.

## Manual

Local first (mock mode, zero quota — note: `uvicorn --reload` doesn't watch HTML;
restart or rely on per-request read):

- [ ] `SABRE_MODE=mock` walkthrough on `/v1/cascade/`: connect the orb, book by
      voice (mock fares), trip auto-appears (~4 s), conversation feed shows the
      turns, search-log panel shows the mock searches.
- [ ] Mock disrupt path with `place_call`/`find_session` stubbed or a dev seam:
      Cancel → red + "waiting for the traveler's go-ahead" with **no running
      clock**; consent yes → timer starts at first `repairing`, broken → repairing
      → fixed animates, timer settles on all-clear; declined/timeout path shows the
      stand-down message and Cancel is re-armable.

Live (Cloud Run, deployed from this branch's merge; **1–2 runs, 2 calls each**):

- [ ] Full contract end-to-end: book JFK→LAX by voice via the on-page orb (re-verify
      the anchor pair first — README day-of probe loop, unique `session_name` per
      call) → trip appears → Cancel → phone rings, Call 1 describes **the real
      booked trip** and asks consent → answer "yes" → repairs animate, timer runs
      from consent → Call 2 arrives after all-clear and speaks the **actual**
      rebooked details/price delta.
- [ ] During the live session, ask "how's my trip?" mid-repair — `trip_status`
      answers with the current statuses.
- [ ] Latency/connection state on the orb reflects reality (connecting → live;
      pull network to see error state if convenient).
- [ ] If quota allows a second run: answer "no" to Call 1 — no repairs launch, the
      page shows the stand-down, no Call 2 fires.

Edge cases:

- [ ] Clicking Cancel twice on the same trip: second click supersedes the first
      watcher (no double repairs, no double Call 2).
- [ ] Consent watcher with the phone unanswered → `timed_out` surfaces on the page.
- [ ] Status poll for a trip with no consent entry is byte-compatible with today
      (additive-only change).

## Tone check

- [ ] Call 1 script (spoken): calm, concrete, first person; states the
      cancellation, what the agent can do, and asks **one** clear consent question.
      No jargon, no codes read aloud (rounded prices, plain city names, PT-labeled
      times if spoken).
- [ ] Call 2 script: reports the fixed state plainly from real data — rebooked
      flight, price delta, downstream legs re-checked.
- [ ] Page copy ("waiting for the traveler's go-ahead", stand-down messages)
      matches the dashboard's existing voice; sentence case; "PT" never "PST".

## Definition of done

- [ ] All automated checks above green in the bare suite (and CI's in-image run on
      the PR merge).
- [ ] Local mock walkthrough and at least **one** full live run completed and noted.
- [ ] **PR description carries the evidence pre-merge** (Phase 30 lesson;
      `pr-evidence-guard` enforces non-empty): the mock-walkthrough summary, the
      live-run notes (date, pair, both call outcomes), and the pytest tail — before
      the merge button, not after.
- [ ] Deployed to Cloud Run via the `vb/dev` merge (re-run the trigger if the
      webhook is missed) and the live run above was against that deploy.
- [ ] Phase 23 marked `[x] COMPLETE` in `specs/roadmap.md`; TODO.md's promoted
      contract section already removed (done at spec time).
