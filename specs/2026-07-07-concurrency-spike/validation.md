# Validation — Concurrency Spike (Phase 5)

## Automated

Run from `backend/` (also runs in CI inside the built container; failure
blocks deploy):

```bash
python -m pytest
```

Required assertions, all hermetic (no `OPENAI_API_KEY`, no GCP credentials,
BigQuery mocked at the `bq_helper` boundary):

- [ ] **Proof A:** the follow-up turn's answer returns while the background
      fake call is still running — `answered_before_tool_finished is True`,
      and follow-up latency is well under the background call's duration.
- [ ] **Proof B:** ≥3 repair tasks' `[started_at, finished_at]` intervals
      overlap — total wall time ≈ the longest single duration, not the sum —
      and completion events land as each task finishes (duration order, not
      launch order).
- [ ] Each repair emitted `repairing` then `fixed` DML updates to
      `itinerary_items` for its item id (asserted on the mocked
      `bq_helper.run_dml`).
- [ ] Both endpoints respond via `TestClient` with the LLM stubbed — no
      network, no credentials.
- [ ] The whole suite stays green (`python -m pytest` exits 0), including all
      pre-existing tests.

## Manual

Live walkthrough with a real `OPENAI_API_KEY` (locally via docker-compose or
against the Cloud Run deploy):

- [ ] `POST /v1/concurrency_spike/talk_while_tool_runs` — **Pallavi's test
      verbatim:** the agent responds to the follow-up while the 10-second fake
      API call is still in flight. The response's timestamps show the answer
      landed at `t < 10s` after the slow call started.
- [ ] `POST /v1/concurrency_spike/cascade` — N≥3 repairs run in parallel;
      the completion log shows overlapping intervals, and the trip's rows in
      `itinerary_items` finish `fixed` with fresh `updated_at` stamps.
- [ ] While a cascade is running, a second follow-up request still answers
      promptly (the event loop is not blocked).
- [ ] Endpoints return a clear, structured error (not a 500 traceback) when
      `OPENAI_API_KEY` is absent.

## Edge cases

- [ ] A repair task that raises (inject one failing fake) does not kill the
      other tasks or the session; its item does not flip to `fixed` and the
      failure is visible in the event log.
- [ ] Two overlapping cascade requests don't cross-contaminate each other's
      event logs (session-keyed registry).

## Tone check

`findings.md` and endpoint response copy read as plain engineering prose for
the team thread: measured numbers, direct answer to Pallavi's flag, no
marketing language.

## Definition of done

- All automated assertions pass in CI (pytest inside the built image).
- The manual walkthrough has been run at least once with a real key and the
  10-second timings captured.
- `specs/2026-07-07-concurrency-spike/findings.md` exists and states whether
  voice-as-a-tool needs a rewire, with the measured evidence.
- Phase 5 marked `[x] COMPLETE` in `specs/roadmap.md`.
