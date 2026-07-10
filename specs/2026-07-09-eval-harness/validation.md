# Validation — Evaluation Harness (Phase 11, L5 port)

## Automated

Run inside the backend container (the repo's standing pattern; D1 resolved
2026-07-09 — the compose service is named `backend`):

```bash
docker compose exec backend pytest tests/ -q
```

All tests pass, including the new `tests/test_eval_harness.py`, with **no GCP
credentials, no `OPENAI_API_KEY`, and no `vb` binary** available — the suite
must stay hermetic (CI runs it inside the built image on every deploy).

Specific assertions required:

- **WER**: identical strings → 0.0; a single substitution in a five-word
  reference → 0.2; empty hypothesis vs non-empty reference → 1.0; case and
  punctuation differences alone → 0.0.
- **MOS mapping**: `vb eval` score 0 → 1.0, 10 → 5.0; out-of-range scores
  clamp instead of extrapolating.
- **Fixtures**: every YAML file checked into
  `backend/api/eval_harness/scenarios/` loads through the pydantic model
  without error; a fixture missing `ground_truth` or `objective` fails with
  an error naming the file.
- **Runner resilience**: with a mocked HTTP transport, one failing turn is
  recorded in the run's notes and the remaining turns still execute; the
  process does not raise.
- **Persistence discipline**: `--dry-run` never calls
  `eval_runs.create_run` (mock asserted not called); a non-dry run calls it
  once per architecture × scenario with an enum-valid `architecture` and the
  fixture's `scenario` name.
- **Import hermeticity**: importing `api.eval_harness` (and running
  `--help`) requires no credentials and no network.

## Manual

Walkthrough (deployed stack — the default target):

1. `make eval ARGS="--dry-run"` → a results table prints for every
   architecture × scenario pair with plausible numbers: TTFB and e2e in the
   hundreds-to-low-thousands of ms, WER between 0.0 and ~0.3, MOS column
   empty (no `--vb-session` given), and a note naming the base URL. No
   BigQuery row is written.
2. `make eval` (no dry-run) → same table, then confirm real rows landed:
   `eval_runs` shows one row per pair with `git_sha` populated, `scenario`
   matching the fixture names, and `run_at` fresh (BigQuery console or a
   quick `list_runs` call).
3. MOS leg: place or reuse a completed Vocal Bridge call (Phase 7 outbound
   flow or the L4/L5 notebooks), then
   `make eval ARGS="--vb-session <id> --scenario flight-cancel-readback"` →
   `mos_estimate` lands between 1.0 and 5.0 and the judge's summary/
   suggestions appear in `notes`.
4. Local fallback: `make eval ARGS="--base-url http://localhost:8080 --dry-run"`
   against the docker compose stack → runs succeed with local latencies.

Edge cases:

- Backend unreachable (bad `--base-url`) → per-run failure is reported in the
  table and the process exits non-zero; no partial garbage row is written for
  a run with zero successful turns.
- `--vb-session` given but the `vb` CLI errors (bad id, missing key) → the
  run still completes; `mos_estimate` is NULL and `notes` says why.
- `--scenario` naming a nonexistent fixture → clear error listing available
  scenario names.
- Running from a detached-HEAD or non-git context (`GIT_SHA` unset, no repo)
  → row written with `git_sha` NULL, not a crash.

## Tone check

Not applicable — no user-facing copy. CLI output is terse team-facing text;
keep it factual (numbers, names, errors), no decoration.

## Definition of done

- All automated assertions above pass hermetically inside the container.
- Manual walkthrough steps 1–2 verified against the deployed Cloud Run
  service; step 3 verified at least once with a real Vocal Bridge session.
- `eval_runs` contains real measured rows for `cascaded` and `concierge`
  across all checked-in scenarios, stamped with the git SHA that produced
  them — the numbers the Phase 12 rehearsal will be judged against.
- `specs/roadmap.md` Phase 11 heading marked `[x] COMPLETE`.
