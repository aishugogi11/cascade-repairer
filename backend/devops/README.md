# Devops — CI/CD & GCP setup

Project: `vocal-bridge-hackathon` · Region: `us-west1` · Service: `vocal-bridge-be-dev`

## One-time setup

### 1. Scripted (run once, safe to re-run)

Requires an authenticated `gcloud` CLI with access to the project.

```bash
bash backend/devops/scripts/gcp_project_setup.sh
```

Enables APIs (Cloud Run, Cloud Build, Artifact Registry, BigQuery, Cloud Storage),
creates the `gemini-service-account` with build + runtime roles, the
`vocal-bridge-be-artifacts-dev` Artifact Registry repo, the
`vocal-bridge-hackathon-audio` bucket, and the `vocal_bridge` BigQuery dataset.

### 2. Console-only: connect GitHub to Cloud Build

Cloud Build's GitHub App connection requires an interactive OAuth grant — console only:

1. Console → Cloud Build → **Repositories** → **Connect repository**.
2. Select **GitHub (Cloud Build GitHub App)**, authenticate, and pick the
   `vocal-bridge-training` repo. Install the app on the repo if prompted.

### 3. Create the PR trigger (console, or gcloud once the repo is connected)

Console → Cloud Build → **Triggers** → **Create trigger**:

- **Name**: `vocal-bridge-be-pr-to-dev`
- **Event**: Pull request
- **Source**: the connected repo; **Base branch**: `^vb/dev$`
- **Configuration**: Cloud Build configuration file — `backend/devops/cloudbuild.yaml`
- **Service account**: `gemini-service-account@vocal-bridge-hackathon.iam.gserviceaccount.com`
- Comment control: not required (team repo).

Equivalent gcloud (works only after step 2's connection exists):

```bash
gcloud builds triggers create github \
  --name=vocal-bridge-be-pr-to-dev \
  --repo-name=vocal-bridge-training \
  --repo-owner=zen-apps \
  --pull-request-pattern="^vb/dev$" \
  --build-config=backend/devops/cloudbuild.yaml \
  --service-account=projects/vocal-bridge-hackathon/serviceAccounts/gemini-service-account@vocal-bridge-hackathon.iam.gserviceaccount.com \
  --project=vocal-bridge-hackathon
```

> The trigger fires only on GitHub PRs into `vb/dev` (from `vb/feature/*`
> branches). Direct pushes to feature branches do not build.

### 4. Set the OpenAI key on the Cloud Run service (after first deploy)

The deploy step merges env vars (`--update-env-vars`), so this survives redeploys:

```bash
gcloud run services update vocal-bridge-be-dev \
  --region=us-west1 \
  --project=vocal-bridge-hackathon \
  --update-env-vars=OPENAI_API_KEY=<key>
```

`hello_world` and `gcp_check` work without it; the `/agents*` routes need it.

## The build (every PR into vb/dev)

`backend/devops/cloudbuild.yaml`, driven by `backend/config.yaml`:

1. **validate-and-extract-env** — validates `config.yaml`, writes `image.env`.
2. **setup-artifacts** — ensures the `vocal_bridge` BigQuery dataset exists
   (tables come in Phase 3).
3. **build-tag-and-push-image** — builds the Docker image, tags
   `latest`/`$SHORT_SHA`/version, pushes to Artifact Registry.
4. **run-pytest** — runs `pytest tests/ -v` inside the just-built image;
   a failure stops the deploy.
5. **deploy-to-cloud-run** — deploys `vocal-bridge-be-dev` to us-west1.

## Verify a deploy

```bash
curl https://<service-url>/v1/hello/hello_world
curl https://<service-url>/v1/hello/gcp_check

gcloud run services logs read vocal-bridge-be-dev \
  --region=us-west1 --project=vocal-bridge-hackathon --limit=20
```
