# Validation Report — Concurrency Spike
**Branch:** vb/feature/concurrency-spike    **Commit:** d7401126fa8e47528bc32847f6bf54050b5e7cd4    **Date:** 2026-07-07T16:00:19Z

## Summary
Partial pass. The implementation proves the main concurrency claim: follow-up agent turns can return while background work is still running, N>=3 repair tasks overlap, endpoint tests are hermetic, edge cases are covered, and the rebuilt container test suite passes. The remaining gap is the manual cascade row-state claim: the code emits `repairing` -> `fixed` updates, but the endpoint does not prove those BigQuery updates affected existing rows or produced fresh `updated_at` stamps.

## Criterion-by-criterion results
- **Criterion:** Proof A: follow-up answer returns while the background fake call is still running.
- **Status:** PASS
- **Evidence:** `backend/api/concurrency_core.py:102` starts background tasks with `asyncio.create_task`; `backend/api/concurrency_spike.py:55` starts the slow call before `run_followup_turn`; `backend/tests/test_concurrency_spike.py::test_followup_answered_while_background_call_still_running`; `backend/tests/test_concurrency_spike.py::test_talk_endpoint_answers_before_tool_finishes`. Live curl returned `answered_before_tool_finished: true`, `followup_latency_seconds: 4.822` for a 10.0s slow call; a second live run returned in `TOTAL_TIME=1.253423`.
- **Notes:** This satisfies Pallavi's quick test over text transport.

- **Criterion:** Proof B: N>=3 repair intervals overlap, wall time is near the longest duration, and completions land by finish order.
- **Status:** PASS
- **Evidence:** `backend/api/concurrency_core.py:138` launches one task per repair spec; `backend/tests/test_concurrency_spike.py::test_repairs_overlap_and_complete_in_duration_order` asserts pairwise interval overlap, wall time below the sequential sum, and completion order `repair-2`, `repair-1`, `repair-0`. Live `/cascade?wait=true` with three items returned all events with overlapping monotonic intervals.
- **Notes:** Live completion order can be affected by real BigQuery DML overhead before/after the fake sleep; the hermetic timing proof passes with DML mocked.

- **Criterion:** Each repair emits `repairing` then `fixed` DML updates to `itinerary_items`.
- **Status:** PASS
- **Evidence:** `backend/api/concurrency_core.py:132` calls `itinerary_items.update_status(..., "repairing")`; `backend/api/concurrency_core.py:134` calls `update_status(..., "fixed")`; `backend/tests/test_concurrency_spike.py::test_each_repair_writes_repairing_then_fixed` asserts both statuses per item via mocked `bq_helper.run_dml`.
- **Notes:** This proves DML emission, not actual affected rows.

- **Criterion:** Both endpoints respond via `TestClient` with the LLM stubbed, with no network or credentials.
- **Status:** PASS
- **Evidence:** `backend/tests/test_concurrency_spike.py::test_talk_endpoint_answers_before_tool_finishes`, `test_talk_endpoint_without_key_is_structured_503`, `test_cascade_endpoint_wait_returns_full_event_log`, `test_cascade_endpoint_returns_immediately_without_wait`, and `test_cascade_endpoint_rejects_fewer_than_three_items`.
- **Notes:** The LLM turn is monkeypatched; BigQuery DML is mocked at `bq_helper`.

- **Criterion:** Whole suite stays green.
- **Status:** PASS
- **Evidence:** `docker compose build backend` succeeded. `docker run --rm vocal-bridge-training-backend python -m pytest tests/ -v` returned `68 passed, 4 skipped, 1 warning in 2.59s`.
- **Notes:** The literal host command `python -m pytest` from `backend/` could not run because this shell has no `python` executable. The README/CI-style container command passed.

- **Criterion:** Manual `POST /v1/concurrency_spike/talk_while_tool_runs` with real `OPENAI_API_KEY` answers before a 10-second fake API call finishes.
- **Status:** PASS
- **Evidence:** Live curl to `http://localhost:1019/v1/concurrency_spike/talk_while_tool_runs` returned `answered_before_tool_finished: true`, slow call state `running`, and `followup_latency_seconds: 4.822` for `slow_seconds: 10.0`. A later live run during an active cascade returned in `1.253423s` with `answered_before_tool_finished: true`.
- **Notes:** The running compose service had a usable OpenAI key; no secret value was printed.

- **Criterion:** Manual `POST /v1/concurrency_spike/cascade` runs N>=3 repairs in parallel, shows overlapping intervals, and the trip rows finish `fixed` with fresh `updated_at` stamps.
- **Status:** AMBIGUOUS
- **Evidence:** Live curl with three repairs and `wait=true` returned three completion events with overlapping intervals. Code routes status writes through `itinerary_items.update_status`, which stamps `updated_at` in SQL at `backend/api/repositories/itinerary_items.py:80`.
- **Notes:** I did not verify actual BigQuery rows. The endpoint accepts arbitrary item ids and reports repair success even if `update_status` returns `(success=False, ...)` or `(success=True, affected_rows=0, ...)`, because `_repair_one` ignores the return tuple. The row-state portion is therefore not independently proven.

- **Criterion:** While a cascade is running, a second follow-up request still answers promptly.
- **Status:** PASS
- **Evidence:** Live curl started `session_id=validator-live-cascade` with three 8.0-9.0s repairs and `wait=false`, returning pending tasks immediately. A subsequent live `talk_while_tool_runs` request returned in `TOTAL_TIME=1.253423` with its own slow call still running.
- **Notes:** This verifies the event loop is not blocked by the launched cascade.

- **Criterion:** Endpoints return a clear structured error, not a 500 traceback, when `OPENAI_API_KEY` is absent.
- **Status:** PASS
- **Evidence:** `backend/api/concurrency_spike.py:44` raises `HTTPException(status_code=503, detail=...)`; `backend/tests/test_concurrency_spike.py::test_talk_endpoint_without_key_is_structured_503` asserts status 503 and `OPENAI_API_KEY` in the JSON detail.
- **Notes:** The running compose service had a key, so this was verified through TestClient, not live runtime.

- **Criterion:** A repair task that raises does not kill siblings or the session; its item does not flip to `fixed`; failure is visible in the event log.
- **Status:** PASS
- **Evidence:** `backend/api/concurrency_core.py:88` captures exceptions into `CompletionEvent(status="error")`; `backend/tests/test_concurrency_spike.py::test_failing_repair_does_not_kill_siblings_or_flip_fixed` asserts the failing item only receives `repairing`, siblings receive `repairing` then `fixed`, and the error event includes `RuntimeError`. Live curl with `fail_one=true` returned one `status: "error"` event and two `status: "ok"` sibling events.
- **Notes:** This criterion is covered both hermetically and by live endpoint behavior.

- **Criterion:** Two overlapping cascade requests do not cross-contaminate event logs.
- **Status:** PASS
- **Evidence:** `backend/tests/test_concurrency_spike.py::test_concurrent_sessions_do_not_cross_contaminate` launches repairs for `s-one` and `s-two` and asserts each session has exactly three events. The registry is keyed by session id in `backend/api/concurrency_core.py:51`.
- **Notes:** There is no read-only endpoint for inspecting an existing session log, so live cross-session inspection is not available without launching more work.

- **Criterion:** `findings.md` and endpoint copy use plain engineering prose.
- **Status:** PASS
- **Evidence:** `specs/2026-07-07-concurrency-spike/findings.md` states the measured answer directly, includes timing numbers, and lists sharp edges. Endpoint error/detail text in `backend/api/concurrency_spike.py:47` is direct and operational.
- **Notes:** No marketing-language issue found.

- **Criterion:** Definition of done: findings exist and Phase 5 is marked complete in the roadmap.
- **Status:** PASS
- **Evidence:** `specs/2026-07-07-concurrency-spike/findings.md` exists and records measured evidence. `specs/roadmap.md` marks Phase 5 `[x] COMPLETE (implementation; manual QA pending)`.
- **Notes:** The roadmap wording itself says manual QA pending, which conflicts mildly with validation.md's done language that the manual walkthrough has been run.

## Missing tests
- `backend/tests/test_concurrency_spike.py::test_followup_remains_prompt_while_cascade_tasks_run` — start a long mocked cascade, then call the talk endpoint with `run_followup_turn` stubbed and assert the response returns before cascade tasks complete.
- `backend/tests/test_concurrency_spike.py::test_cascade_reports_status_update_failure` — monkeypatch `itinerary_items.update_status` to return `(False, 0, "boom")` or `(True, 0, None)` and assert the completion event does not report `ok` as if the itinerary row were fixed.
- `backend/tests/test_concurrency_spike.py::test_findings_and_roadmap_done_contract` — assert `findings.md` exists and the roadmap Phase 5 heading is marked complete if those are intended to stay part of automated done criteria.

## Gaps in validation.md
- Should `/cascade` be required to prove actual BigQuery row state, or is emitting repository DML calls enough for this spike?
- How should validators verify "fresh `updated_at` stamps" without seeded itinerary rows, a read endpoint, or an explicit BigQuery query procedure?
- Is local rebuilt-image pytest acceptable for "CI", or must the Cloud Build PR trigger have completed before validation passes?
- Is the roadmap label "manual QA pending" acceptable when validation.md says the manual walkthrough is part of done?

## Risks not covered by validation.md
- `_repair_one` ignores the return value from `itinerary_items.update_status`; the event log can say a repair is `ok` even when the row update failed or affected zero rows.
- Real BigQuery DML latency can dominate short fake durations, so live completion order may not match configured repair durations even though tasks overlap.
- The session registry is process-local memory. That is acceptable for this spike, but sessions would disappear on process restart and would not be shared across multiple Cloud Run instances.
