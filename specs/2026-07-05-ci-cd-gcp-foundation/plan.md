# Plan — CI/CD Pipeline & GCP Foundation

Task groups are ordered but independently implementable where possible. Groups 1–2 are prerequisites for 5; 3 and 4 can proceed in parallel with 2.

## 1. One-time GCP project setup

1.1 Write `backend/devops/scripts/gcp_project_setup.sh` (modeled on `DEPLOYMENT_SAMPLE.md`): set project `vocal-bridge-hackathon`; enable `run`, `cloudbuild`, `artifactregistry`, `bigquery`, `storage` APIs; create `gemini-service-account` with roles `bigquery.admin`, `storage.admin`, `cloudbuild.builds.builder`, `run.admin`, `iam.serviceAccountUser`; idempotent (safe to re-run).
1.2 Extend the script to create the GCS bucket `vocal-bridge-hackathon-audio` (us-west1, uniform access — reuse the pattern from `promotion_scripts/create_gcs_bucket.sh`, whose `LOCATION` is hardcoded to us-east4) and the BigQuery dataset `vocal_bridge` (us-west1).
1.3 Run the script against the project; capture any console-only steps it can't cover.
1.4 Document the console-only steps in `backend/devops/README.md`: connecting the GitHub repo to Cloud Build, and creating the PR trigger (with the equivalent `gcloud builds triggers create github` command for reference).

## 2. Adapt config and build pipeline

2.1 Rewrite `backend/config.yaml`: `ai_service_name: vocal-bridge-be`, `bigquery_dataset_id: vocal_bridge`, GCS bucket name, `PROJECT_ID: vocal-bridge-hackathon`, `TARGET_AR: vocal-bridge-be-artifacts-dev`, `GCP_LOCATION: us-west1`, `APP_ENV: dev`. Strip donor-only metadata (spreadsheet conversions, RAG embeddings, msg history, diet tracker, SQL allowlist).
2.2 Update `backend/devops/cloudbuild.yaml`: build service account and `_PROJECT_ID` substitution → `vocal-bridge-hackathon`; deploy step → `gcloud run deploy vocal-bridge-be-$APP_ENV` with `--region=us-west1` (the donor hardcodes `--region=us-east4`) and `--service-account=gemini-service-account@vocal-bridge-hackathon.iam.gserviceaccount.com`; drop the Vertex AI / Teams-bot env vars and comments, keep `--update-env-vars` merge behavior and `--allow-unauthenticated`.
2.3 Walk `devops/scripts/validate_and_extract_env_vars.py`, `run_artifact_setup.sh`, and `ai_service_builder.sh` for hardcoded donor values (project, repo, service names); parameterize or update. Confirm `run_artifact_setup.sh` creates `vocal-bridge-be-artifacts-dev` when missing.

## 3. pytest in the loop

3.1 Add `pytest` and `httpx` to `backend/requirements.txt`.
3.2 Create `backend/tests/` with `test_hello.py`: FastAPI `TestClient` asserts `GET /v1/hello/hello_world` returns 200 with the expected body, and the app imports cleanly. No network or GCP dependency — tests must pass in a bare container.
3.3 Add a Cloud Build step after `build-tag-and-push-image` and before `deploy-to-cloud-run` that runs `pytest` inside the just-built image (`docker run $IMAGE_URL pytest tests/ -v`); a failure stops the deploy.
3.4 Verify locally: `docker compose build` then run the same pytest command against the local image.

## 4. GCP check endpoint

4.1 Add `GET /v1/hello/gcp_check` to `backend/api/hello.py`: runs `SELECT 1` via `bigquery_helper` and lists the audio bucket via `gcs_helper`; returns `{bigquery: ok|error, gcs: ok|error}` with error detail, never a 500 that hides which half failed.
4.2 Update `bigquery_helper.py` / `gcs_helper.py` only as needed for project/bucket/dataset names to come from `config.yaml` env — no new abstraction.
4.3 Unit test with mocked GCP clients so CI stays hermetic.

## 5. Trigger and end-to-end verification

5.1 In the console: connect the GitHub repo, create the Cloud Build PR trigger — base branch `^vb/dev$`, build config `backend/devops/cloudbuild.yaml`, service account `gemini-service-account`. (Per `AGENTS.md`, the trigger fires only on GitHub PRs from feature branches into `vb/dev`.)
5.2 Set `OPENAI_API_KEY` on the Cloud Run service once (first deploy may omit it; the hello_world and gcp_check routes don't need it).
5.3 Open the PR from `vb/feature/ci-cd-gcp-foundation` into `vb/dev`; watch the triggered build through: env validation → artifact setup → image build/push → pytest → deploy.
5.4 Hit the deployed service: `/v1/hello/hello_world` (200) and `/v1/hello/gcp_check` (both `ok`). Record the service URL and build ID in the PR.
5.5 Run `specs/2026-07-05-ci-cd-gcp-foundation/validation.md` end to end; fix and re-push until the loop is clean.
