# Requirements — CI/CD Pipeline & GCP Foundation

Phase 1 of the roadmap. Get the existing FastAPI backend shipping through the production path — PR → Cloud Build → container build → pytest → Cloud Run — before any feature work, and confirm GCS/BigQuery are reachable from the deployed service.

## Scope

**In scope (full roadmap scope, confirmed by Josh):**

- Adapt `backend/config.yaml`, `backend/devops/cloudbuild.yaml`, and the devops/promotion scripts from the donor project (`zen-general-377713` / `blonter-be`) to this project's GCP setup.
- A one-time GCP project setup shell script in `backend/devops/scripts/` (APIs, service account + IAM, GCS bucket, BigQuery dataset), modeled on `DEPLOYMENT_SAMPLE.md`.
- Cloud Build GitHub PR trigger: PRs from `vb/feature/*` into `vb/dev` fire the build (trigger + GitHub connection created in the console; the equivalent `gcloud` command documented).
- pytest wired into the Cloud Build pipeline — the donor pipeline has **no test step**; this phase adds one, plus a minimal test suite so it has something real to run.
- Verified full loop: PR → Cloud Build → container build → pytest → Cloud Run test instance serving `GET /v1/hello/hello_world`.
- GCS bucket provisioned; BigQuery access confirmed **from the deployed Cloud Run service** via a lightweight check endpoint.

**Out of scope:**

- The BigQuery trip/session/eval table schemas (`trips`, `turns`, etc.) — Phase 3.
- Any voice, agent, or Sabre feature work.
- Production/promotion environment — a single `dev` Cloud Run instance is the target; promotion scripts are adapted only as far as Phase 1 needs them.
- Deleting donor-specific promotion scripts (spreadsheet conversions, RAG embeddings, msg history tables) — they are left in place but must not run; Phase 3 replaces them.

### Configuration values

| Setting | Donor value | This project |
|---|---|---|
| GCP project | `zen-general-377713` | `vocal-bridge-hackathon` (brand new) |
| Service name | `blonter-be` → `blonter-be-dev` | `vocal-bridge-be` → `vocal-bridge-be-dev` |
| Artifact Registry repo | `blonter-be-artifacts-dev` | `vocal-bridge-be-artifacts-dev` |
| Region | `us-east4` | `us-west1` — hackathon is in the SF Bay Area; serve from the West Coast for latency |
| Service account | `gemini-service-account@zen-general-377713…` | `gemini-service-account@vocal-bridge-hackathon.iam.gserviceaccount.com` (per `DEPLOYMENT_SAMPLE.md`) |
| BigQuery dataset | `blonter_be_dataset` | `vocal_bridge` |
| GCS bucket | `blonter_be` | `vocal-bridge-hackathon-audio` (project-prefixed for global uniqueness) |
| Trigger | branch push on `main` | GitHub **PR** trigger, base branch `^vb/dev$` |

## Decisions

- **Brand-new GCP project `vocal-bridge-hackathon`** — Josh has already created it; everything else (APIs, SA, AR repo, bucket, dataset, trigger) is stood up by this phase. `DEPLOYMENT_SAMPLE.md` is the reference for the manual/console steps and the gcloud equivalents.
- **Console OK for one-time setup, scripts preferred.** GitHub connection and trigger creation happen in the console (documented step-by-step); everything scriptable lands in a new `backend/devops/scripts/gcp_project_setup.sh` so the setup is reproducible.
- **pytest runs inside the built container** as a Cloud Build step between image build and deploy — matching the roadmap's "container build → pytest → Cloud Run" order and testing the exact artifact that ships.
- **`OPENAI_API_KEY` is set once on the Cloud Run service** (console or `gcloud run services update`); the deploy step keeps the donor's `--update-env-vars` merge behavior so the key survives redeploys. No secrets in the repo or in `config.yaml`.
- **BigQuery/GCS verification is an endpoint, not a manual check**: a small `GET /v1/hello/gcp_check` route that runs a trivial BigQuery query and lists the GCS bucket, returning status for each — so "confirmed from the deployed service" is a URL you can hit.
- **Everything lives in `us-west1`** — Cloud Run service, Artifact Registry repo, GCS bucket, and BigQuery dataset. The event is in Mountain View/San Francisco, so a West Coast region minimizes round-trip latency for the live voice demo. Donor scripts hardcode `us-east4`; every occurrence gets updated.
- **Donor-specific config is stripped, not ported**: the Teams-bot, diet-tracker, RAG, and spreadsheet-conversion metadata in `config.yaml`, the Vertex AI env vars in the deploy step, and `setup_deflow_scheduler.sh` do not apply here.

## Context

- Constitution: `specs/mission.md` (deploy early, production-grade path is success criterion #2), `specs/tech-stack.md` (§ Deployment & CI/CD).
- Donor artifacts to adapt: `backend/config.yaml`, `backend/devops/cloudbuild.yaml`, `backend/devops/scripts/` (`run_artifact_setup.sh`, `ai_service_builder.sh`, `validate_and_extract_env_vars.py`), `backend/promotion_scripts/create_gcs_bucket.sh`.
- Manual-setup reference: `DEPLOYMENT_SAMPLE.md` at the repo root.
- The FastAPI app entry is `backend/main.py`; the health route is `GET /v1/hello/hello_world` in `backend/api/hello.py`. GCP helpers live in `backend/api/helpers/` (`bigquery_helper.py`, `gcs_helper.py`).
- `backend/requirements.txt` currently lacks `pytest` (and an HTTP test client); this phase adds test dependencies.
- Copy/tone: devops scripts and docs stay terse and imperative, matching the existing script style (usage functions, explicit echo of what's happening).
