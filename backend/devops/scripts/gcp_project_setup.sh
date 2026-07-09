#!/bin/bash

# One-time GCP project setup for vocal-bridge-hackathon.
# Idempotent: safe to re-run; existing resources are reported and skipped.
#
# Covers everything scriptable from DEPLOYMENT_SAMPLE.md. Console-only steps
# (GitHub connection, Cloud Build PR trigger) are documented in
# backend/devops/README.md.

script_path=$(realpath "$0" | sed 's|\(.*\)/.*|\1|')
source "$script_path/logging.sh"

PROJECT_ID="vocal-bridge-hackathon"
REGION="us-west1"
SERVICE_ACCOUNT_NAME="gemini-service-account"
SERVICE_ACCOUNT="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
AR_REPO="vocal-bridge-be-artifacts-dev"
GCS_BUCKET="vocal-bridge-hackathon-audio"
BQ_DATASET="vocal_bridge"

usage() {
  echo "Usage: $0 [--project-id <id>] [--region <region>]"
  echo
  echo "Options:"
  echo "  --project-id <id>    GCP Project ID (default: ${PROJECT_ID})."
  echo "  --region <region>    Region for AR repo, bucket, dataset (default: ${REGION})."
  echo "  -h, --help           Display this help message."
  exit 1
}

while [[ "$#" -gt 0 ]]; do
  case $1 in
    --project-id) PROJECT_ID="$2"; SERVICE_ACCOUNT="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"; shift ;;
    --region) REGION="$2"; shift ;;
    -h|--help) usage ;;
    *) echo "Unknown parameter passed: $1"; usage ;;
  esac
  shift
done

log_info "Project:         $PROJECT_ID"
log_info "Region:          $REGION"
log_info "Service account: $SERVICE_ACCOUNT"
log_info "AR repo:         $AR_REPO"
log_info "GCS bucket:      gs://$GCS_BUCKET"
log_info "BQ dataset:      $BQ_DATASET"
echo

# --- 1. Active project -------------------------------------------------------
log_info "Setting active project..."
gcloud config set project "$PROJECT_ID" || { log_error "Failed to set project"; exit 1; }

# --- 2. Enable required APIs -------------------------------------------------
log_info "Enabling required APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  bigquery.googleapis.com \
  storage.googleapis.com \
  --project="$PROJECT_ID" || { log_error "Failed to enable APIs"; exit 1; }

# --- 3. Service account ------------------------------------------------------
if gcloud iam service-accounts describe "$SERVICE_ACCOUNT" --project="$PROJECT_ID" >/dev/null 2>&1; then
  log_info "Service account $SERVICE_ACCOUNT already exists"
else
  log_info "Creating service account $SERVICE_ACCOUNT_NAME..."
  gcloud iam service-accounts create "$SERVICE_ACCOUNT_NAME" \
    --display-name="Vocal Bridge build + runtime service account" \
    --project="$PROJECT_ID" || { log_error "Failed to create service account"; exit 1; }
fi

# --- 4. IAM roles ------------------------------------------------------------
# bigquery.admin / storage.admin  -> runtime data access (BQ, GCS)
# cloudbuild.builds.builder       -> run as the Cloud Build build SA
# artifactregistry.writer         -> push images during the build
# run.admin                       -> deploy the Cloud Run service
# iam.serviceAccountUser          -> deploy step actAs the runtime SA
ROLES=(
  "roles/bigquery.admin"
  "roles/storage.admin"
  "roles/cloudbuild.builds.builder"
  "roles/artifactregistry.writer"
  "roles/run.admin"
  "roles/iam.serviceAccountUser"
)
for ROLE in "${ROLES[@]}"; do
  log_info "Granting $ROLE..."
  gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="$ROLE" \
    --condition=None \
    --quiet >/dev/null || { log_error "Failed to grant $ROLE"; exit 1; }
done

# --- 5. Artifact Registry repo -----------------------------------------------
if gcloud artifacts repositories describe "$AR_REPO" --location="$REGION" --project="$PROJECT_ID" >/dev/null 2>&1; then
  log_info "Artifact Registry repo $AR_REPO already exists"
else
  log_info "Creating Artifact Registry repo $AR_REPO..."
  gcloud artifacts repositories create "$AR_REPO" \
    --repository-format=docker \
    --location="$REGION" \
    --project="$PROJECT_ID" \
    --description="Vocal Bridge backend images (dev)" || { log_error "Failed to create AR repo"; exit 1; }
fi

# --- 6. GCS bucket -----------------------------------------------------------
if gcloud storage buckets describe "gs://$GCS_BUCKET" --project="$PROJECT_ID" >/dev/null 2>&1; then
  log_info "Bucket gs://$GCS_BUCKET already exists"
else
  log_info "Creating bucket gs://$GCS_BUCKET..."
  gcloud storage buckets create "gs://$GCS_BUCKET" \
    --project="$PROJECT_ID" \
    --location="$REGION" \
    --uniform-bucket-level-access || { log_error "Failed to create bucket"; exit 1; }
fi

# --- 7. BigQuery dataset -----------------------------------------------------
if bq show --project_id="$PROJECT_ID" "$BQ_DATASET" >/dev/null 2>&1; then
  log_info "Dataset $PROJECT_ID:$BQ_DATASET already exists"
else
  log_info "Creating dataset $PROJECT_ID:$BQ_DATASET..."
  bq mk --location="$REGION" --dataset "$PROJECT_ID:$BQ_DATASET" || { log_error "Failed to create dataset"; exit 1; }
fi

echo
log_info "✅ Project setup complete."
log_info "Console-only steps remain (GitHub connection + Cloud Build PR trigger):"
log_info "see backend/devops/README.md"
