# Validation Report — Evaluation Harness Re-validation
**Branch:** vb/dev    **Commit:** 86b4eebb4c09a9d54fd017f790f9e8eb5f289cc9    **Date:** 2026-07-09

## Summary
PARTIAL. The deployed 502 is fixed, the hermetic suite passes on the actual `backend` compose service, default deployed dry-run now measures all four architecture x scenario pairs, and a current-image Cloud Run job persisted four fresh `eval_runs` rows with `git_sha=86b4eeb`. The feature is still not fully validated because `validation.md` still names the nonexistent/non-running `api` service, no persisted MOS row exists, and the MOS walkthrough could not be independently verified without a real completed Vocal Bridge session id.

## Criterion-by-criterion results
- **Criterion:** Automated command from `validation.md` runs inside the api container: `docker compose exec api pytest tests/ -q`.
- **Status:** FAIL
- **Evidence:** Command output: `service "api" is not running`. `docker-compose.yml` defines service `backend`; `revalidation-notes.md` also marks this as open decision D1.
- **Notes:** Equivalent actual command `docker compose exec backend pytest tests/ -q` passed: `242 passed, 4 skipped, 6 warnings in 6.26s`.

- **Criterion:** WER assertions: identical strings 0.0; single substitution in five-word reference 0.2; empty hypothesis vs non-empty reference 1.0; case/punctuation-only differences 0.0.
- **Status:** PASS
- **Evidence:** `backend/tests/test_eval_harness.py` covers the required WER cases; included in passing backend-service pytest run.
- **Notes:** None.

- **Criterion:** MOS mapping: `vb eval` score 0 maps to 1.0, 10 maps to 5.0, and out-of-range scores clamp.
- **Status:** PASS
- **Evidence:** `backend/tests/test_eval_harness.py` covers zero, ten, out-of-range, and midpoint mapping; included in passing backend-service pytest run.
- **Notes:** None.

- **Criterion:** Fixtures: checked-in scenario YAML files load through pydantic; fixtures missing `ground_truth` or `objective` fail with an error naming the file.
- **Status:** PASS
- **Evidence:** `backend/tests/test_eval_harness.py` fixture-loader tests passed; checked-in scenarios `flight-cancel-readback` and `repair-status-query` loaded during dry-run/job execution.
- **Notes:** None.

- **Criterion:** Runner resilience: with mocked HTTP transport, one failing turn is recorded in notes and remaining turns still execute; process does not raise.
- **Status:** PASS
- **Evidence:** Mocked failing-turn test passes; `_build_row` serializes per-turn error fields into `notes.turns`.
- **Notes:** The previously suggested direct assertion for row notes remains a useful missing test.

- **Criterion:** Persistence discipline: `--dry-run` never calls `eval_runs.create_run`; non-dry run calls once per architecture x scenario with enum-valid architecture and fixture scenario name.
- **Status:** PASS
- **Evidence:** Mocked repository tests passed. Live dry-run output ended with `dry run: 4 row(s) not written`. Cloud Run job execution `vocal-bridge-eval-harness-xz8qs` completed successfully and BigQuery shows 4 rows for `git_sha=86b4eeb`: 2 cascaded and 2 concierge.
- **Notes:** Per `revalidation-notes.md`, local non-dry `make eval` is expected to fail without local GCP credentials; persistence is validated through the Cloud Run job.

- **Criterion:** Import hermeticity: importing `api.eval_harness` and running `--help` requires no credentials and no network.
- **Status:** PASS
- **Evidence:** `docker compose exec backend python -m api.eval_harness --help` exited 0 and printed CLI help. `docker compose exec backend python -c 'import api.eval_harness; ...'` exited 0.
- **Notes:** None.

- **Criterion:** Manual deployed dry-run: `make eval ARGS="--dry-run"` prints every architecture x scenario pair with plausible TTFB/e2e, WER, empty MOS, base URL note, and writes no BigQuery row.
- **Status:** PASS
- **Evidence:** Command exited 0 against `https://vocal-bridge-be-dev-24105435206.us-west1.run.app` and printed all 4 rows: cascaded `flight-cancel-readback` 8298.8/8355.5 ms WER 0.0625; concierge `flight-cancel-readback` 3848.9/3850.8 ms; cascaded `repair-status-query` 7583.1/7673.0 ms WER 0.0; concierge `repair-status-query` 1865.6/1867.2 ms; `dry run: 4 row(s) not written`.
- **Notes:** The prior deployed `/v1/web_call/query` 502 is resolved; direct probe returned HTTP 200. Cascaded latency is above the "hundreds-to-low-thousands" wording, but `revalidation-notes.md` records ~7-9 s as structural/open D3 rather than a current defect.

- **Criterion:** Manual deployed non-dry run writes one real `eval_runs` row per architecture x scenario with populated `git_sha`, matching scenario, and fresh `run_at`.
- **Status:** PASS
- **Evidence:** Revalidation procedure used Cloud Run job `vocal-bridge-eval-harness`: updated to image tag/GIT_SHA `86b4eeb`, executed `vocal-bridge-eval-harness-xz8qs`, status completed successfully in 1m13s. BigQuery returned 4 rows for `git_sha=86b4eeb`, scenarios `flight-cancel-readback` and `repair-status-query`, latest `run_at` 2026-07-09 23:44:48.
- **Notes:** This validates the new GCP-side persistence path from `revalidation-notes.md`; it does not validate local credentialed writes.

- **Criterion:** MOS leg with a completed Vocal Bridge session writes `mos_estimate` 1.0-5.0 and judge summary/suggestions in notes.
- **Status:** FAIL
- **Evidence:** No completed Vocal Bridge session id was available to run the manual MOS command. BigQuery query `WHERE mos_estimate IS NOT NULL` returned `[]`; the fresh `86b4eeb` rows have `mos_estimate=NULL`.
- **Notes:** Code-level fix is present and tested for both flat and nested `vb eval --json` shapes, including `test_eval_vb_session_nested_result_shape`, but the validation criterion requires live persisted MOS evidence.

- **Criterion:** Local fallback: `make eval ARGS="--base-url http://localhost:8080 --dry-run"` against docker compose stack runs successfully with local latencies.
- **Status:** PASS
- **Evidence:** Command exited 0 and printed all 4 rows: cascaded `flight-cancel-readback` 20356.2/20368.2 ms WER 0.0625; concierge `flight-cancel-readback` 4452.4/4468.4 ms; cascaded `repair-status-query` 18740.6/18742.8 ms WER 0.0; concierge `repair-status-query` 4628.8/4695.1 ms.
- **Notes:** Local cascaded latency is high but the acceptance text only requires the local fallback to run successfully with local latencies.

- **Criterion:** Backend unreachable edge case reports per-run failure, exits non-zero, and writes no partial garbage row for a run with zero successful turns.
- **Status:** PASS
- **Evidence:** `make eval ARGS="--base-url http://localhost:9 --dry-run"` printed four `FAILED: ... no successful measurements` lines, `every run failed; nothing to persist`, and `make` exited non-zero.
- **Notes:** None.

- **Criterion:** `--vb-session` given but the `vb` CLI errors: run still completes; `mos_estimate` is NULL and notes say why.
- **Status:** PASS
- **Evidence:** Unit test for missing `vb` CLI passed; runner returns `(None, reason)` without raising. CLI row construction attaches `mos` notes when `eval_vb_session` returns a note.
- **Notes:** The CLI table still does not display the MOS failure reason; it is only in persisted/dry-run row notes.

- **Criterion:** `--scenario` naming a nonexistent fixture gives a clear error listing available scenario names.
- **Status:** PASS
- **Evidence:** `docker compose exec backend python -m api.eval_harness --scenario does-not-exist --dry-run` exited 2 and printed `unknown scenario 'does-not-exist'; available: flight-cancel-readback, repair-status-query`.
- **Notes:** None.

- **Criterion:** Detached-HEAD or non-git context writes row with `git_sha` NULL, not a crash.
- **Status:** PASS
- **Evidence:** Unit test for missing git/GIT_SHA passed; current `make eval` also passes host `GIT_SHA` into the container for normal local runs.
- **Notes:** None.

- **Criterion:** Tone check: CLI output is terse, factual team-facing text.
- **Status:** PASS
- **Evidence:** CLI output is a compact table plus explicit `FAILED:` lines for bad-base runs.
- **Notes:** None.

- **Criterion:** Definition of done: automated assertions pass hermetically, deployed manual steps 1-2 verified, MOS verified once, `eval_runs` contains real measured rows for cascaded and concierge across checked-in scenarios with git SHA, roadmap marks Phase 11 complete.
- **Status:** FAIL
- **Evidence:** Automated assertions pass through actual `backend` service, deployed dry-run passes, and `eval_runs` contains current `86b4eeb` rows for both architectures and both scenarios. MOS remains unverified/persisted: no row has `mos_estimate IS NOT NULL`. The exact validation command still fails on service `api`.
- **Notes:** Roadmap is marked `[x] COMPLETE`; validation evidence is still incomplete because of MOS and the documented service-name mismatch.

## Missing tests
- Add `backend/tests/test_eval_harness.py::test_failed_turn_error_appears_in_row_notes`: build a row from a result with one failed turn and assert `notes.turns[*].error` contains the failure.
- Add a test for operator-visible MOS failure feedback, e.g. `backend/tests/test_eval_harness.py::test_cli_prints_vb_eval_failure_reason`, so bad session ids are visible without inspecting JSON notes.
- The previous proposed tests for documented compose service name and WER-only cascaded success remain blocked by open decisions D1/D2 in `revalidation-notes.md`.

## Gaps in validation.md
- Should the automated command be corrected from `docker compose exec api ...` to `docker compose exec backend ...`?
- Should the validation procedure explicitly name the Cloud Run job path for non-dry persistence, since local non-dry writes are intentionally unsupported without local GCP credentials?
- Should the MOS step specify how validators obtain a valid completed Vocal Bridge session id and whether a persisted MOS row is required for definition of done?
- Should the dry-run latency expectation be revised for cascaded `/converse`, since observed deployed TTFB is ~7-9 seconds and local TTFB is ~18-20 seconds?

## Risks not covered by validation.md
- The Cloud Run eval job had to be manually updated from `2d208af` to `86b4eeb`; if the job is not kept in sync with the deployed service, persisted eval evidence can lag the actual release.
- No MOS rows exist in `eval_runs`, so Phase 12 still lacks persisted quality-judge evidence even though latency/WER rows are present.
- Pytest still passes with runtime warnings in `tests/test_sabre_tools.py::test_repair_trip_failed_write_surfaces_as_error_event` about unawaited repair coroutines; unrelated to the eval harness, but still rehearsal risk.
