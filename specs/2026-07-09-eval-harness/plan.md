# Plan — Evaluation Harness (Phase 11, L5 port)

Module layout: `backend/api/eval_harness/` (package) with `__main__.py` so the
whole thing runs as `python -m api.eval_harness`. The data layer (`eval_runs`
table, schema yaml, config metadata, repository) shipped in Phase 3 — no
changes there.

## 1. Metrics core (pure functions, no I/O)

1.1 Create `backend/api/eval_harness/metrics.py`:
    - `wer(reference: str, hypothesis: str) -> float` — normalize (lowercase,
      strip punctuation, collapse whitespace), word-level Levenshtein via
      stdlib dynamic programming, return `edits / len(reference_words)`.
      Empty-reference guard returns 0.0 when both empty, 1.0 otherwise.
    - `mos_from_vb_score(score: float) -> float` — clamp score to [0, 10],
      map to `1 + (score / 10) * 4`.
    - `summarize_latencies(samples_ms: list[float]) -> dict` — mean, p50,
      max, count (mean feeds the row; the rest go in notes).

## 2. Scenario fixtures & loader

2.1 Create `backend/api/eval_harness/scenarios/` with 2–3 starter YAML
    fixtures aligned with the Cascade Repairer demo, e.g.
    `flight-cancel-readback.yaml`, `repair-status-query.yaml`:
    - `name`, `description`
    - `turns`: list of user utterances (text)
    - `ground_truth`: transcript text used for the TTS→STT WER round trip
    - `objective`: the `vb eval` objective string (L5: the objective is what
      makes evals meaningful)
2.2 Create `backend/api/eval_harness/scenario_loader.py`:
    - Pydantic `Scenario` model mirroring the YAML shape; loader reads one
      file or globs the directory, validation errors name the file.

## 3. Runner — drive the target stack over HTTP

3.1 Create `backend/api/eval_harness/runner.py` (synchronous, `httpx`):
    - `run_cascaded(base_url, scenario) -> ArchitectureResult`:
      - WER leg: `POST /v1/cascade_demo/text_to_speech` with `ground_truth`,
        pipe returned audio into `POST /v1/cascade_demo/speech_to_text`,
        compute WER.
      - Latency leg: for each turn, `POST /v1/cascade_demo/converse` timed —
        TTFB from response start, e2e from full body read (httpx streaming).
    - `run_concierge(base_url, scenario) -> ArchitectureResult`:
      - For each turn, `POST /v1/web_call/delegated_query` timed; WER = None.
    - Each result carries per-turn samples plus failures; a failed turn is
      recorded in notes, never a crash of the whole run.
3.2 MOS leg in `runner.py`: `eval_vb_session(session_id, objective)` calling
    `run_vb("eval", session_id, "--objective", objective, json_output=True)`
    from `api/vb_cli.py`; returns `(mos, judge_summary)` or `(None, reason)`.
3.3 Git SHA resolution: `GIT_SHA` env var, else
    `git rev-parse --short HEAD` via subprocess (tolerate failure → None).

## 4. Persistence & CLI entrypoint

4.1 Create `backend/api/eval_harness/__main__.py`:
    - Args (argparse): `--base-url` (default: deployed Cloud Run URL, env
      `EVAL_BASE_URL` overrides), `--architecture {cascaded,concierge,all}`
      (default all), `--scenario <name>` (default all fixtures),
      `--vb-session <id>` (optional, enables the MOS leg), `--dry-run`.
    - Assemble one `EvalRun` per architecture × scenario (notes = compact
      JSON: per-turn timings, transcript pair, judge summary, base URL).
    - Write via `eval_runs.create_run` unless `--dry-run`; print a terse
      results table either way; exit non-zero if every run failed.
4.2 Add `make eval` target (`docker compose exec api python -m api.eval_harness`,
    pass-through args via `ARGS=`), documented next to the existing targets.

## 5. Tests (hermetic, `backend/tests/test_eval_harness.py`)

5.1 Metrics: WER known cases (identical → 0.0, one substitution in five words
    → 0.2, empty hypothesis → 1.0, punctuation/case invariance); MOS mapping
    endpoints (0 → 1.0, 10 → 5.0, clamping); latency summary math.
5.2 Scenario loader: valid fixture parses; missing field fails naming the
    file; every checked-in fixture in `scenarios/` loads clean.
5.3 Runner: mock `httpx` transport — TTFB/e2e captured, failed turn lands in
    notes without aborting; MOS leg with `run_vb` mocked (success and
    CLI-missing paths).
5.4 CLI: `--dry-run` writes nothing (repository mocked, assert not called);
    a normal run calls `create_run` with enum-valid architecture and the
    scenario name; import of the package needs no credentials.
