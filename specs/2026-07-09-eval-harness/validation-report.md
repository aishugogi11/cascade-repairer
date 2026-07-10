# Validation Report — Evaluation Harness (Phase 11, L5 port)
**Branch:** vb/dev    **Commit:** c4bc3d6    **Date:** 2026-07-09

## Summary
PASS. All automated assertions pass hermetically inside the `backend` container — verified twice: once as prescribed (`docker compose exec backend pytest tests/ -q` → 243 passed, 4 skipped, all skips unrelated container-path tests) and once under a fully wiped environment (`env -i`, no `OPENAI_API_KEY`, no GCP credentials, no `vb` or `git` on PATH → identical 243 passed). The manual walkthrough is verified: dry-run against the deployed Cloud Run service prints all four architecture × scenario pairs and writes nothing; BigQuery `vocal_bridge.eval_runs` holds real rows for both architectures across both checked-in scenarios with `git_sha` populated; a persisted MOS row exists (mos_estimate 1.4, judge verdict/summary/suggestions in `notes`) produced by the `vocal-bridge-eval-harness` Cloud Run job (execution completed 2026-07-10T00:06Z). All four edge cases behave as specified. Two minor observations: cascaded latencies (~7.5 s TTFB deployed) exceed the "hundreds-to-low-thousands of ms" plausibility band validation.md predicted, and the roadmap Phase 11 heading carries a now-stale "(implementation; manual QA pending)" annotation.

## Criterion-by-criterion results

### Automated

- **Criterion:** Full suite passes in the backend container with no GCP credentials, no `OPENAI_API_KEY`, no `vb` binary
- **Status:** PASS
- **Evidence:** `docker compose exec backend pytest tests/ -q` → `243 passed, 4 skipped` (skips are `test_validator_docs_contract.py`/`test_validator_skill_sync.py` repo-root-absent guards, unrelated). Because the dev container actually has `OPENAI_API_KEY` and `/usr/local/bin/vb`, hermeticity was proven separately: `env -i HOME=/tmp PATH=/tmp/hermbin python -m pytest tests/ -q` with a PATH containing only `python`/`pytest`/`sh` (no `vb`, no `git`) → `243 passed, 4 skipped`.
- **Notes:** `tests/test_eval_harness.py` contributes 35 tests, all passing in 0.42 s.

- **Criterion:** WER — identical → 0.0; one substitution in five words → 0.2; empty hypothesis → 1.0; case/punctuation-only differences → 0.0
- **Status:** PASS
- **Evidence:** `backend/tests/test_eval_harness.py::test_wer_identical_is_zero`, `test_wer_single_substitution_in_five_words`, `test_wer_empty_hypothesis_is_one`, `test_wer_case_and_punctuation_invariant` (plus both-empty and >1.0 cases). Implementation is a stdlib two-row word-level Levenshtein in `backend/api/eval_harness/metrics.py` with lowercase/punctuation-stripping normalization.

- **Criterion:** MOS mapping — 0 → 1.0, 10 → 5.0, out-of-range clamps
- **Status:** PASS
- **Evidence:** `test_mos_score_zero_maps_to_one`, `test_mos_score_ten_maps_to_five`, `test_mos_out_of_range_clamps` (−3 → 1.0, 14 → 5.0), `test_mos_midpoint`. `metrics.mos_from_vb_score` clamps to [0, 10] before the linear 1–5 projection.

- **Criterion:** Fixtures — every checked-in YAML loads through the pydantic model; missing `ground_truth`/`objective` fails naming the file
- **Status:** PASS
- **Evidence:** `test_every_checked_in_fixture_loads` (loads `backend/api/eval_harness/scenarios/` — both `flight-cancel-readback.yaml` and `repair-status-query.yaml` present and valid), `test_missing_field_fails_naming_the_file` (`pytest.raises(ScenarioError, match="broken.yaml")`), plus non-mapping-YAML and blank-turn rejection tests. `scenario_loader.load_scenario` prefixes every error with `path.name`.

- **Criterion:** Runner resilience — with a mocked HTTP transport, one failing turn is recorded in notes and remaining turns execute; no raise
- **Status:** PASS
- **Evidence:** `test_run_cascaded_failed_turn_recorded_not_raised` — turn 1 returns HTTP 502 via `httpx.MockTransport`; exactly one `TurnTiming.error` containing "502", the other turn still measured (`ttfb_samples` length 1), `result.failed` is False. Turn errors flow into the persisted row's `notes.turns[].error` via `__main__._build_row`. `test_run_cascaded_unreachable_backend_fails_cleanly` covers the all-turns-fail case without raising.

- **Criterion:** Persistence discipline — `--dry-run` never calls `eval_runs.create_run`; non-dry calls it once per architecture × scenario with enum-valid `architecture` and the fixture's `scenario`
- **Status:** PASS
- **Evidence:** `test_cli_dry_run_never_writes` (`create_run.assert_not_called()`), `test_cli_writes_one_row_per_architecture_x_scenario` (len(written) == fixtures × RUNNERS; `row.architecture in ("cascaded", "concierge")`; `row.scenario in fixture_names`; notes valid JSON). `EvalRun.architecture` is `Literal["cascaded", "realtime", "concierge"]` (`backend/api/repositories/models.py:21`), so pydantic enforces enum validity at construction.

- **Criterion:** Import hermeticity — importing `api.eval_harness` and running `--help` needs no credentials/network
- **Status:** PASS
- **Evidence:** `test_package_imports_credential_free`, plus a live check under `env -i` with no credentials: `python -c "import api.eval_harness; import api.eval_harness.__main__"` → ok; `python -m api.eval_harness --help` → exit 0. `__main__.main` reads env inside the function body, not at import.

### Manual

- **Criterion:** Walkthrough 1 — `make eval ARGS="--dry-run"` prints a table for every architecture × scenario pair with plausible numbers, MOS empty, base URL named, no BigQuery row
- **Status:** PASS (with one deviation noted)
- **Evidence:** Ran it. Table printed all 4 pairs against `https://vocal-bridge-be-dev-24105435206.us-west1.run.app`: cascaded 7467/7597 ms TTFB with WER 0.0625/0.0, concierge 2695/1641 ms, MOS column `-` throughout, `dry run: 4 row(s) not written`, exit 0. BigQuery row count and `MAX(run_at)` unchanged after the run (11 rows, latest 2026-07-10 00:05:56).
- **Notes:** Deviation: cascaded TTFB/e2e ≈ 7.5 s exceeds the criterion's "hundreds-to-low-thousands of ms" band (concierge is within it). WER is within 0.0–0.3. The numbers are real measurements of a live STT→agent→TTS chain, so this reads as an optimistic prediction in validation.md rather than a harness defect — see Gaps.

- **Criterion:** Walkthrough 2 — non-dry run lands one row per pair in `eval_runs` with `git_sha` populated, `scenario` matching fixtures, fresh `run_at`
- **Status:** PASS
- **Evidence:** `bq query` against `vocal-bridge-hackathon.vocal_bridge.eval_runs`: rows for all four pairs (cascaded/concierge × flight-cancel-readback/repair-status-query) at `git_sha=86b4eeb`, `run_at` 2026-07-09 23:44 – 2026-07-10 00:05 UTC; earlier full set at `2d208af`. 11 rows total. The Cloud Run job `vocal-bridge-eval-harness` (us-west1) exists; latest execution `vocal-bridge-eval-harness-lwzzf` completed 2026-07-10T00:06:01Z, matching the newest rows.
- **Notes:** I did not fire a fresh non-dry run to avoid polluting the baseline table; evidence is the persisted rows plus the job execution record. The persisted rows are stamped `86b4eeb`/`2d208af`, i.e. the SHAs that produced them — commits after that (55ccb1a "harness bug fix runner", PR #12 agent-context) have no persisted rows yet.

- **Criterion:** Walkthrough 3 — MOS leg with a real Vocal Bridge session: `mos_estimate` in [1.0, 5.0], judge summary/suggestions in `notes`
- **Status:** PASS
- **Evidence:** Row at 2026-07-10 00:05:56 (`concierge × flight-cancel-readback`, git_sha 86b4eeb): `mos_estimate=1.4` (judge score 1 → 1.4 on the 1–5 scale) with `notes.mos` containing `vb_session=358d54c3-…`, `verdict: "fail"`, a full judge summary, and `suggestions` (prompt-improvement text). Verified via `bq query` on the notes column.
- **Notes:** The low score reflects the evaluated call's content (agent went off-objective), not a harness fault — the leg mechanically works end to end.

- **Criterion:** Walkthrough 4 — local fallback `--base-url http://localhost:8080 --dry-run` succeeds with local latencies
- **Status:** PASS
- **Evidence:** Ran `make eval ARGS="--base-url http://localhost:8080 --dry-run --scenario repair-status-query"`: both architectures measured (cascaded 21130 ms, concierge 4520 ms, WER 0.0), `dry run: 2 row(s) not written`, exit 0.

### Edge cases

- **Criterion:** Unreachable `--base-url` → per-run failure in the table, non-zero exit, no partial garbage row
- **Status:** PASS
- **Evidence:** `--base-url http://localhost:9 --dry-run --scenario repair-status-query` → both pairs print `FAILED: … no successful measurements`, exit code 1. Code path: `result.failed` runs are never turned into rows (`__main__.main`), and `test_cli_all_runs_failed_exits_nonzero` asserts `create_run` not called.

- **Criterion:** `--vb-session` given but `vb` errors → run completes, `mos_estimate` NULL, `notes` says why
- **Status:** PASS
- **Evidence:** Live in-container check: `eval_vb_session("bogus-session-id", "test objective")` → `(None, "vb eval failed: vb eval bogus-session-id … failed: usage: vb …")` — no raise, reason captured. Unit coverage: `test_eval_vb_session_cli_missing`, `test_eval_vb_session_non_numeric_score`. `_build_row` writes the reason into `notes.mos` while `mos_estimate` stays None.
- **Notes:** No CLI-level test asserts the row is still written with `mos_estimate=None` on judge failure — see Missing tests.

- **Criterion:** `--scenario` naming a nonexistent fixture → clear error listing available names
- **Status:** PASS
- **Evidence:** Live run: `--scenario nope --dry-run` → `unknown scenario 'nope'; available: flight-cancel-readback, repair-status-query` on stderr, exit 2. Test: `test_cli_unknown_scenario_lists_available`.

- **Criterion:** Detached-HEAD / non-git context → row written with `git_sha` NULL, not a crash
- **Status:** PASS
- **Evidence:** `test_resolve_git_sha_no_git_no_crash` (subprocess raising OSError → None) and `test_resolve_git_sha_env_wins`; `EvalRun.git_sha` is `Optional[str]`; the full suite passed under `env -i` with no `git` on PATH. `test_cli_base_url_flag_reaches_runner` exercises the CLI with `resolve_git_sha() → None`.

### Definition of done

- **Automated assertions pass hermetically in the container:** PASS (above).
- **Manual 1–2 verified against deployed Cloud Run; step 3 with a real VB session:** PASS (step 1 re-executed by this validator; steps 2–3 evidenced by persisted rows + job execution).
- **`eval_runs` contains real measured rows for cascaded and concierge across all checked-in scenarios, stamped with the producing git SHA:** PASS — complete 2×2 sets at `2d208af` and `86b4eeb`.
- **`specs/roadmap.md` Phase 11 heading marked `[x] COMPLETE`:** PASS with a caveat — the heading reads `[x] COMPLETE (implementation; manual QA pending)`. The checkbox is set, but the "manual QA pending" annotation is now stale given the persisted MOS row and this walkthrough; it should be cleaned up.

## Missing tests
- CLI-level judge-failure persistence: no test asserts that when `eval_vb_session` returns `(None, reason)`, `main([])` still writes rows with `mos_estimate is None` and `reason` in `notes["mos"]`. Propose `backend/tests/test_eval_harness.py::test_cli_vb_session_failure_still_writes_row_with_reason` (monkeypatch `eval_vb_session` → `(None, "vb eval failed: …")`, mock `create_run`, assert row written with `mos_estimate None` and the reason inside `json.loads(row.notes)["mos"]`). Not written by the validator — the behavior is verified live and at unit level; this is hardening, not a coverage hole against a stated automated criterion.
- All stated automated criteria have direct tests; no validator tests were needed.

## Gaps in validation.md
- The dry-run plausibility band ("TTFB and e2e in the hundreds-to-low-thousands of ms") does not hold for the cascaded architecture against the deployed service (~7.5 s TTFB; ~21 s locally). Should the criterion state per-architecture bands (concierge ≈ 1.5–3.5 s; cascaded ≈ 6–9 s deployed), or is sub-low-thousands cascaded latency itself a Phase 12 requirement someone should be working toward?
- "a note naming the base URL" in walkthrough 1: the base URL appears in the per-run progress lines and in each row's `notes` JSON, but not in the printed dry-run table itself. Is the progress line sufficient, or should the table footer name the target?
- The definition of done says rows are "stamped with the git SHA that produced them" — satisfied — but the newest persisted rows predate the final two commits on this branch (55ccb1a, PR #12). If the intent is "baseline rows at the SHA Phase 12 will demo from," a re-run at HEAD is needed; the spec is silent on this.

## Risks not covered by validation.md
- `__main__.main` returns exit 0 when at least one row persists (`return 1 if written == 0 else 0`), so a run where some BigQuery inserts fail still exits 0 (failures are printed to stderr). No criterion addresses partial persistence failure.
- The MOS verdict rides on every architecture row of the invocation for a given scenario (one `vb eval` per scenario, attached to both `cascaded` and `concierge` rows), so `mos_estimate` is not architecture-specific; consumers comparing architectures by MOS would double-count one judged call. `notes.mos.vb_session` disambiguates provenance.
- `run_cascaded`'s WER leg synthesizes ground truth with the backend's own TTS, so WER is a TTS→STT consistency floor (the code says so in `notes.wer_leg`); anyone reading `eval_runs.wer` as human-speech WER will over-trust it.
- The `env -i` hermetic run proves no ambient credentials are needed, but the suite still runs with network available; nothing technically blocks a future test from calling out. Low risk given all HTTP goes through `MockTransport` today.
