# Validation — CI/CD Pipeline & GCP Foundation

## Automated

- `pytest tests/ -v` passes inside the built container locally (`docker compose build` then run pytest in the image) — the same invocation Cloud Build uses.
- Required assertions:
  - `GET /v1/hello/hello_world` returns 200 with the expected body via FastAPI `TestClient`.
  - The FastAPI app imports and constructs without GCP credentials or an `OPENAI_API_KEY` present (hermetic CI).
  - `GET /v1/hello/gcp_check` unit test passes with mocked BigQuery/GCS clients, covering both the all-ok and one-side-failing responses.
- The Cloud Build run triggered by the PR completes green with the pytest step present **between image build and deploy** — verify in the build log that a test failure would block deployment (the step order, not just the green run).

## Manual walkthrough

1. `gcp_project_setup.sh` re-runs cleanly against `vocal-bridge-hackathon` (idempotent — no errors on existing SA/bucket/dataset).
2. Open a GitHub PR from `vb/feature/ci-cd-gcp-foundation` into `vb/dev` → the Cloud Build trigger fires automatically (no manual build submission).
3. Build passes all steps: env validation → artifact setup → docker build/push to `vocal-bridge-be-artifacts-dev` → pytest → Cloud Run deploy.
4. `curl https://<service-url>/v1/hello/hello_world` returns 200.
5. `curl https://<service-url>/v1/hello/gcp_check` returns `bigquery: ok` and `gcs: ok` — BigQuery and GCS confirmed from the deployed service, not a laptop.
6. `gcloud run services logs read vocal-bridge-be-dev --region=us-west1 --project=vocal-bridge-hackathon --limit=20` shows the request logs.

## Edge cases

- A commit that breaks a test: push it to the PR branch and confirm Cloud Build fails at the pytest step and does **not** deploy; then revert.
- Redeploy preserves service env vars: after setting `OPENAI_API_KEY` on the service, a subsequent build must not wipe it (`--update-env-vars` merge behavior).
- `gcp_check` with a wrong dataset/bucket name reports the failing half with error detail instead of a bare 500.
- Push directly to `vb/feature/*` (no PR): trigger must NOT fire — it is PR-into-`vb/dev` only.

## Tone check

No user-facing copy in this phase. Script output and `backend/devops/README.md` follow the existing terse, imperative devops style; no secrets or keys appear in any committed file.

## Definition of done

- [ ] One-time setup scripted (`gcp_project_setup.sh`) with console-only steps documented in `backend/devops/README.md`.
- [ ] `config.yaml` / `cloudbuild.yaml` / devops scripts carry no donor-project values (`zen-general-377713`, `blonter`, `us-east4`, spreadsheet/RAG/msg-history metadata) — all regions read `us-west1`.
- [ ] PR into `vb/dev` → green Cloud Build (build → pytest → deploy) with no manual intervention.
- [ ] Deployed Cloud Run instance serves `hello_world` and `gcp_check` returns both `ok`.
- [ ] Broken-test edge case demonstrated: failing pytest blocks the deploy.
- [ ] Phase 1 marked `[x] COMPLETE` in `specs/roadmap.md` (done during implementation wrap-up, not by this spec).
