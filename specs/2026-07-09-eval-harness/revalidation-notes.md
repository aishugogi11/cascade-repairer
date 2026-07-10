# Re-validation handoff — Evaluation Harness (Phase 11)

**Original report:** `specs/2026-07-09-eval-harness/validation-report.md` (FAIL, commit `5c724da`, 2026-07-09).
**State since:** openai pin merged as PR #10 (`2d208af`, deployed); MOS report-shape fix merged as PR #11 (`86b4eeb`) — re-test against the deploy from that merge or later.

## Issue 1 — Deployed 502 on `/v1/web_call/query` (report FAIL, criterion "deployed dry-run") — RESOLVED

Root cause was not harness code: `openai 2.45.0` (released ~2026-07-09) added a required
`InputTokensDetails.cache_write_tokens` field; `openai-agents` (verified from wheels through
0.18.0) constructs that object without it in `agents/usage.py`, so every `Runner.run()` raised a
pydantic ValidationError. `openai` was an unpinned transitive dep (`<3,>=2.36.0`), so the image
rebuilt on the PR #9 merge resolved 2.45.0 while older local images had 2.44.0. This also explains
the cascaded rows with NULL latency (usage accounting runs on every agent turn).

**Fix:** `openai==2.44.0` pinned in `backend/requirements.txt` (PR #10, deployed).
**Re-test:** `make eval ARGS="--dry-run"` — all 4 architecture × scenario pairs now measure
(observed: concierge ~1.5–3.2 s, cascaded ~6.6–9.1 s TTFB, WER 0.0/0.0625).

## Issue 2 — Zero persisted `eval_runs` rows (report FAIL, criterion "deployed non-dry run") — RESOLVED, new procedure

Josh's decision: **no GCP credentials on the local machine** (the ADC file present locally is a
zen-agents service account → 403; a compose creds-mount was tried and reverted). Persisted runs
now go through GCP itself: Cloud Run job **`vocal-bridge-eval-harness`** (us-west1, deployed
image, `gemini-service-account`, `GIT_SHA` env). Executed 2026-07-09: **4/4 rows persisted,
verified via `bq`** — both architectures × both scenarios, `git_sha=2d208af`, fresh `run_at`.

Local `make eval` without `--dry-run` is expected to fail at the write step; that is by design,
not a defect.

## Issue 3 — MOS leg returned no score (report UNTESTABLE) — root-caused, fix staged, live-verified

Two stacked causes found in manual QA:

- **Operator:** a `POST /call` **call_id** was pasted as `--vb-session`; `vb eval` needs the VB
  **session id** (from `vb logs list`). This is the known Phase 7 id-confusion; Phase 13 will
  link the ids.
- **Code bug:** the live `vb eval --json` report nests scoring under `result` (`result.score`,
  `result.verdict`, `result.suggested_prompt_improvements`); the harness parsed the flat
  L5-notebook shape, found no top-level `score`, and returned MOS None (reason visible only in
  row notes — display gap already flagged in the report).

**Fix (merged in PR #11):** `eval_vb_session` accepts both shapes;
new test `test_eval_vb_session_nested_result_shape`; suite 242 passed / 4 skipped.
**Live-verified:** session `358d54c3-…` vs the flight objective → MOS 1.4 rendered in the table
(low score is correct — that call's content is unrelated to the objective; judge verdict
confirms). The branch also carries the Makefile change passing host `GIT_SHA` into the container
(fixes `git_sha=none` on local runs).

## What to re-test (against the PR #11 deploy or later)

1. Hermetic suite in-container (note: service name is `backend` — see D1 below).
2. Deployed dry-run: 4 pairs, all measured, nothing written.
3. Persisted run via the Cloud Run job (update image tag + `GIT_SHA`; for a persisted MOS row
   also add `VOCAL_BRIDGE_API_KEY` to the job env and `--vb-session <id from vb logs list>` to
   its args — the job does not inherit the service's env).
4. `eval_runs` rows: per-pair rows with git SHA; at least one row with `mos_estimate` 1.0–5.0
   and judge verdict/suggestions in `notes`.

## Still open — decisions, not defects (TODO.md, unanswered)

- **D1** validation.md says `docker compose exec api …`; compose defines `backend` (spec
  correction is Josh's to make — validator will re-hit this).
- **D2** WER-only cascaded run counted as success (allowed NULL-latency rows during the outage).
- **D3** acceptable latency bounds per surface (cascaded ~7–9 s TTFB is structural: `/converse`
  runs STT→agent→TTS before first byte).
- **D4** canonical source of VB session ids for MOS runs (today: `vb logs list`; Phase 13 will
  persist).
- **D5** exit-code semantics on partial failure (currently exit 0 if any row survived).
- Report's three "missing tests": the nested-shape test is new but distinct;
  `test_failed_turn_error_appears_in_row_notes` is unblocked and still to add; the other two are
  blocked by D1/D2.
