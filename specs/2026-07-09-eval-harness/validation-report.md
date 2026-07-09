# Validation Report — Evaluation Harness
**Branch:** vb/feature/eval-harness    **Commit:** 5c724dad24f563586755e635b3d177e957444865    **Date:** 2026-07-09

## Summary
FAIL. The hermetic backend test suite passes against the actual `backend` compose service, and the local fallback eval can produce rows, but the acceptance criteria are not met: the exact automated command in `validation.md` targets a non-running/nonexistent `api` service, the required default deployed dry-run does not produce results for every architecture x scenario, and BigQuery currently has zero persisted `eval_runs` rows for the checked-in scenarios.

## Criterion-by-criterion results
- **Criterion:** Automated command from `validation.md` runs inside the api container: `docker compose exec api pytest tests/ -q`.
- **Status:** FAIL
- **Evidence:** `validation.md:5-13` names service `api`; `docker-compose.yml:1-18` defines service `backend`. Command output: `service "api" is not running`.
- **Notes:** Equivalent repo service command `docker compose exec backend pytest tests/ -q` passed: `241 passed, 4 skipped, 6 warnings in 9.20s`.

- **Criterion:** WER assertions: identical strings 0.0; single substitution in five-word reference 0.2; empty hypothesis vs non-empty reference 1.0; case/punctuation-only differences 0.0.
- **Status:** PASS
- **Evidence:** `backend/tests/test_eval_harness.py:36-49`; implementation in `backend/api/eval_harness/metrics.py`. Covered by passing `docker compose exec backend pytest tests/ -q`.
- **Notes:** Additional tests cover both-empty and WER > 1.0 cases.

- **Criterion:** MOS mapping: `vb eval` score 0 maps to 1.0, 10 maps to 5.0, and out-of-range scores clamp.
- **Status:** PASS
- **Evidence:** `backend/tests/test_eval_harness.py:63-77`; implementation in `backend/api/eval_harness/metrics.py`. Covered by passing pytest run.
- **Notes:** None.

- **Criterion:** Fixtures: checked-in scenario YAML files load through pydantic; fixtures missing `ground_truth` or `objective` fail with an error naming the file.
- **Status:** PASS
- **Evidence:** `backend/tests/test_eval_harness.py:97-113`; loader behavior in `backend/api/eval_harness/scenario_loader.py`; checked fixtures are `flight-cancel-readback.yaml` and `repair-status-query.yaml`.
- **Notes:** None.

- **Criterion:** Runner resilience: with mocked HTTP transport, one failing turn is recorded and remaining turns still execute; process does not raise.
- **Status:** PASS
- **Evidence:** `backend/tests/test_eval_harness.py:180-188`; `_build_row` includes per-turn errors in notes at `backend/api/eval_harness/__main__.py:37-45`.
- **Notes:** The test checks result state; row-notes inclusion is covered by code inspection, not a direct test assertion for the failing-turn case.

- **Criterion:** Persistence discipline: `--dry-run` never calls `eval_runs.create_run`; non-dry run calls once per architecture x scenario with enum-valid architecture and fixture scenario name.
- **Status:** PASS
- **Evidence:** `backend/tests/test_eval_harness.py:279-302`; CLI persistence code at `backend/api/eval_harness/__main__.py:162-173`.
- **Notes:** This is unit-tested with repository mocking, not live BigQuery.

- **Criterion:** Import hermeticity: importing `api.eval_harness` and running `--help` requires no credentials and no network.
- **Status:** PASS
- **Evidence:** `docker compose exec backend python -m api.eval_harness --help` exited 0 and printed CLI help; `docker compose exec backend python -c 'import api.eval_harness; ...'` exited 0. Test coverage at `backend/tests/test_eval_harness.py:361-365`.
- **Notes:** None.

- **Criterion:** Manual deployed dry-run: `make eval ARGS="--dry-run"` prints every architecture x scenario pair with plausible TTFB/e2e, WER, empty MOS, base URL note, and writes no BigQuery row.
- **Status:** FAIL
- **Evidence:** Command output against default `https://vocal-bridge-be-dev-24105435206.us-west1.run.app`: only two cascaded rows printed, both with `ttfb_ms` and `e2e_ms` as `-`; both concierge runs failed with `no successful measurements`; dry run wrote no rows.
- **Notes:** Direct deployed probe `POST /v1/web_call/query` returned HTTP 502: `agent query failed: 1 validation error for InputTokensDetails cache_write_tokens Field required`.

- **Criterion:** Manual deployed non-dry run: `make eval` writes one real `eval_runs` row per architecture x scenario with populated `git_sha`, matching scenario, and fresh `run_at`.
- **Status:** FAIL
- **Evidence:** I did not run non-dry after the default dry-run failed because it would persist partial/bad rows. BigQuery query returned `row_count=0`, `cascaded_count=0`, `concierge_count=0`, `latest_run_at=NULL` for scenarios `flight-cancel-readback` and `repair-status-query`.
- **Notes:** Definition of done requires persisted rows; current table has none for these scenarios.

- **Criterion:** MOS leg with a completed Vocal Bridge session writes `mos_estimate` 1.0-5.0 and judge summary/suggestions in notes.
- **Status:** UNTESTABLE
- **Evidence:** No completed Vocal Bridge session id was available in this validation session. Unit tests cover successful MOS attachment at `backend/tests/test_eval_harness.py:325-337`; CLI fake-session dry-run against local backend completed with MOS shown as `-`.
- **Notes:** Because BigQuery has zero rows for the checked-in scenarios, there is no persisted MOS evidence.

- **Criterion:** Local fallback: `make eval ARGS="--base-url http://localhost:8080 --dry-run"` against docker compose stack runs successfully with local latencies.
- **Status:** PASS
- **Evidence:** Command exited 0 and printed four rows: cascaded `flight-cancel-readback` 19220.3/19221.8 ms WER 0.0625; concierge `flight-cancel-readback` 5173.4/5194.6 ms; cascaded `repair-status-query` 17354.0/17355.3 ms WER 0.0; concierge `repair-status-query` 5119.9/5142.2 ms.
- **Notes:** Local latencies are successful but much higher than the deployed-walkthrough "hundreds-to-low-thousands" target stated for step 1.

- **Criterion:** Backend unreachable edge case reports per-run failure, exits non-zero, and writes no partial garbage row for a run with zero successful turns.
- **Status:** PASS
- **Evidence:** `make eval ARGS="--base-url http://localhost:9 --dry-run"` printed four `FAILED: ... no successful measurements` rows plus `every run failed; nothing to persist`, and `make` exited non-zero.
- **Notes:** None.

- **Criterion:** `--vb-session` given but `vb` CLI errors: run still completes; `mos_estimate` is NULL and notes say why.
- **Status:** PASS
- **Evidence:** `backend/tests/test_eval_harness.py:233-236` covers `vb CLI not found`; `backend/api/eval_harness/runner.py:189-208` returns `(None, reason)` without raising; `backend/api/eval_harness/__main__.py:145-154` continues building rows.
- **Notes:** CLI output does not display notes, so the reason is only visible in the row payload.

- **Criterion:** `--scenario` naming a nonexistent fixture gives a clear error listing available scenario names.
- **Status:** PASS
- **Evidence:** `docker compose exec backend python -m api.eval_harness --scenario does-not-exist --dry-run` exited 2 and printed `unknown scenario 'does-not-exist'; available: flight-cancel-readback, repair-status-query`. Test coverage at `backend/tests/test_eval_harness.py:305-310`.
- **Notes:** None.

- **Criterion:** Detached-HEAD or non-git context writes row with `git_sha` NULL, not a crash.
- **Status:** PASS
- **Evidence:** `backend/tests/test_eval_harness.py:245-255`; implementation at `backend/api/eval_harness/runner.py:211-226`.
- **Notes:** Covered with subprocess mocked to raise `OSError`.

- **Criterion:** Tone check: CLI output is terse, factual team-facing text.
- **Status:** PASS
- **Evidence:** CLI outputs tabular numeric rows and `FAILED:` lines from `backend/api/eval_harness/__main__.py:65-78`.
- **Notes:** None.

- **Criterion:** Definition of done: automated assertions pass hermetically, deployed manual steps 1-2 verified, MOS verified once, `eval_runs` contains real measured rows for cascaded and concierge across checked-in scenarios with git SHA, roadmap marks Phase 11 complete.
- **Status:** FAIL
- **Evidence:** Automated assertions pass only via `backend` service, not exact `api` command. Deployed dry-run fails for concierge and has missing cascaded latency. BigQuery has zero matching rows. `specs/roadmap.md` marks Phase 11 `[x] COMPLETE`.
- **Notes:** Roadmap completion is ahead of validation evidence.

## Missing tests
- Add `backend/tests/test_eval_harness_validator_deployed_failures.py::test_partial_architecture_run_without_latency_is_failure`: mocked cascaded run with WER but zero successful latency turns should be treated as failed, so deployed `/converse` breakage cannot produce a passing row with `ttfb_ms=NULL`.
- Add `backend/tests/test_eval_harness_validator_commands.py::test_documented_compose_service_name_matches_compose_file`: assert the documented validation/make service name exists in `docker-compose.yml`, or update validation.md to `backend`.
- Add `backend/tests/test_eval_harness.py::test_failed_turn_error_appears_in_row_notes`: build a row from a result with one failed turn and assert `notes.turns[*].error` contains the failure.

## Gaps in validation.md
- Should the automated command use `backend` instead of `api`, since `docker-compose.yml` defines `backend` and `make eval` also uses `backend`?
- Should a cascaded run with successful WER but zero successful `/converse` turns be considered failed? Current code treats it as a row, which allowed the deployed dry-run to print cascaded rows with no latency.
- What deployed latency range is acceptable for local fallback? The local dry-run succeeds but reported 4-19 second latencies.
- Where should validators find or record the completed Vocal Bridge session id required for MOS verification?

## Risks not covered by validation.md
- Deployed `/v1/web_call/query` currently fails with an OpenAI/Agents SDK response validation error (`InputTokensDetails.cache_write_tokens` missing). This blocks concierge evals and likely blocks the live web-call path.
- The CLI exits 0 for a dry-run with partial failures if any row exists. That can mask deployed breakage in manual QA and could permit partial non-dry persistence.
- Pytest passes with runtime warnings in `tests/test_sabre_tools.py::test_repair_trip_failed_write_surfaces_as_error_event` about unawaited repair coroutines; unrelated to this feature, but worth tracking before rehearsal.
