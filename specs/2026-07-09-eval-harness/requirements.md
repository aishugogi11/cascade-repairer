# Requirements — Evaluation Harness (Phase 11, L5 port)

## Scope

An on-demand CLI evaluation harness that measures voice-pipeline quality for the
shipped architectures and persists results to the existing `eval_runs` BigQuery
table, stamped with git SHA and scenario. This is the L5 course port: latency,
WER, and MOS-style quality — measured, not guessed — ahead of the Phase 12
dress rehearsal.

### In scope

- **All three metric families** (user decision):
  - **TTFB / e2e latency** — wall-clock timing of real HTTP round trips against
    a running backend, per architecture.
  - **WER** — word error rate of the STT transcript against a ground-truth
    transcript, computed with a pure-Python word-level Levenshtein (no new
    dependency).
  - **MOS-style quality estimate** — the L5 pattern: `vb eval <session_id>
    --objective … --json` scores a completed Vocal Bridge call 0–10 via a
    multimodal LLM judge; the harness maps that score onto a 1–5 MOS-style
    scale. Optional per run (requires a completed VB session id); NULL with an
    explanatory note when not supplied.
- **Architectures under test**: `cascaded` (via `/v1/cascade_demo/*`) and
  `concierge` (via `/v1/web_call/delegated_query`). `realtime` stays a valid
  enum value but has no runner — the real-time port is a post-rehearsal
  stretch goal.
- **Checked-in scenario fixtures** with ground-truth transcripts (user
  decision) — small YAML files, no audio binaries: WER audio is synthesized at
  run time by round-tripping the ground-truth text through the backend's own
  TTS then STT endpoints.
- **Targets the deployed Cloud Run stack by default**, local docker as
  fallback (user decision) — the base URL is a CLI flag/env var, defaulting to
  the deployed service.
- **Persistence**: one `eval_runs` row per architecture × scenario via the
  existing repository (`api/repositories/eval_runs.py`), which already exists
  from Phase 3 along with the schema yaml and `config.yaml` metadata entry —
  no data-layer work needed beyond using it.
- A `--dry-run` mode that prints the rows without writing to BigQuery.

### Out of scope

- A FastAPI endpoint for triggering evals (CLI-only, user decision).
- Evaluating the `realtime` architecture (not ported; stretch).
- Automated regression gates in CI — the harness is run on demand; CI keeps
  running only the hermetic pytest suite.
- Building or scoring against real phone-call audio fixtures; MOS relies on
  `vb eval` over an existing VB session rather than local audio analysis.
- Dashboarding/visualization of `eval_runs` rows.

### Data written (`eval_runs`, existing schema)

| Field | Source |
|---|---|
| run_id | uuid, generated per row |
| architecture | `cascaded` / `concierge` (enum-validated by the repository) |
| git_sha | `GIT_SHA` env var if set, else `git rev-parse --short HEAD`, else NULL |
| scenario | fixture name (e.g. `flight-cancel-readback`) |
| ttfb_ms | measured, mean across the scenario's turns |
| e2e_latency_ms | measured, mean across the scenario's turns |
| wer | 0.0–1.0+, STT output vs ground truth (cascaded only; NULL for concierge) |
| mos_estimate | 1.0–5.0 mapped from `vb eval` score, or NULL |
| notes | compact JSON string: per-turn timings, transcript pairs, vb eval summary, target base URL |
| run_at | insert time (SQL default) |

## Decisions

- **CLI + BigQuery** (user decision): invoked as `python -m api.eval_harness`
  from `backend/`, wrapped by a `make eval` target that runs it inside the api
  container via `docker compose exec` (matching how tests run locally).
  Results land in `eval_runs` through the existing repository — the same
  config-driven table-id pattern as the other six tables.
- **Deployed stack + fixtures** (user decision): default base URL is the Cloud
  Run service so measured latency reflects what judges will experience;
  `--base-url http://api:8080` (or localhost) exercises the local stack. The
  harness treats the backend as a black box over HTTP — it measures the
  product, not a copy of its internals.
- **WER without audio fixtures**: synthesize speech from the ground-truth text
  with `POST /v1/cascade_demo/text_to_speech`, feed the audio to
  `POST /v1/cascade_demo/speech_to_text`, compute WER between the STT output
  and the original text. This keeps fixtures as reviewable text, exercises the
  real STT/TTS models, and needs no committed binaries. Known caveat (record
  in notes): this measures the TTS→STT round trip, not human speech — it is a
  consistency floor, not a human-WER estimate.
- **MOS via `vb eval`** (the actual L5 pattern): reuse `api/vb_cli.py`'s
  `run_vb` tuple-convention wrapper — no new subprocess code, no raising on
  transport failure. Score mapping: `mos = 1 + (score / 10) * 4`. The
  scenario fixture carries the `--objective` string, because "without one, the
  LLM is grading vibes" (L5).
- **Latency measurement points**: for `cascaded`, `POST /converse` timed
  client-side (TTFB = time to response headers/first byte, e2e = full body);
  for `concierge`, `POST /v1/web_call/delegated_query` (text turn; TTFB ≈ e2e
  for a JSON response — recorded as such in notes).
- **No new dependencies**: WER is ~25 lines of stdlib Levenshtein; HTTP uses
  `httpx` (already pinned); YAML fixtures use `pyyaml` (already pinned).
- **Hermetic tests stay hermetic**: metrics, fixture loading, row assembly,
  and runner logic are unit-tested with mocked HTTP and mocked repositories —
  no GCP credentials, no `OPENAI_API_KEY`, no `vb` binary, per the standing CI
  rule.

## Context

- **Reference source**: `jupyter_notebook/training_course/L5/` (`L5.ipynb`,
  `helpers.py`). The backend port must align with the module's eval-driven
  loop: *build → call → eval → suggest → patch → call → eval*. The harness is
  the "eval" step made repeatable; its `notes` field should preserve the
  judge's suggestions so the loop can close.
- **Existing patterns to follow**:
  - Repository tuple convention `(success, payload, error)` — never raise
    across the helper boundary (`api/repositories/eval_runs.py`,
    `api/vb_cli.py`).
  - Env read per call, module import needs no credentials/network
    (`vb_cli.py`, helpers).
  - Blocking work off the event loop is a non-issue here: the CLI is a plain
    synchronous script, deliberately outside the FastAPI process.
  - Docstrings that say what deviates from the course notebook and why
    (`vb_cli.py` header is the model).
- **Why now**: Phase 12's rehearsal must capture eval metrics ("Run it through
  the deployed stack … with eval metrics captured"), and mission success
  criterion #2 requires "real latency and quality metrics observed."
- **Tone**: none user-facing — CLI output is terse tabular text for the team;
  the itinerary UI and agent copy are untouched.
- **Constraint**: hackathon timeline (July 18). Keep the harness small and
  boring; it exists to produce trustworthy numbers for the rehearsal, not to
  become a product.
