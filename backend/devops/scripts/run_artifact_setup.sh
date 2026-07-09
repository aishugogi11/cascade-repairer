#!/bin/bash

# STRUCTURE ASSUMPTION
# /ROOT
#   /devops/scripts (HERE)
#   /promotion_scripts

script_path=$(realpath "$0" | sed 's|\(.*\)/.*|\1|')
source $script_path/logging.sh

assert_file() {
    if [ ! -f "$1" ]; then
        log_error "MISSING FILE: $1"
        exit 1
    fi
}

# Ensure image.env exists
assert_file "image.env"

# Load environment variables
set -a
source image.env
set +a

PROJECT_ID="$1"
PROMOTION_SCRIPT_DIR=$(realpath "$script_path/../../promotion_scripts")

# Validate required environment variables
[ -z "$PROJECT_ID" ] && log_error "PROJECT_ID argument is not set or empty" && exit 1
[ -z "$METADATA_BIGQUERY_DATASET_ID" ] && log_error "METADATA_BIGQUERY_DATASET_ID is not set or empty" && exit 1
[ -z "$GCP_LOCATION" ] && log_error "GCP_LOCATION is not set or empty" && exit 1

echo "CONFIRMED DATASET=$METADATA_BIGQUERY_DATASET_ID LOCATION=$GCP_LOCATION"

# Table ids come from config.yaml metadata via image.env (optional, defaults
# match the canonical names in specs/tech-stack.md).
TRIPS_TABLE_ID="${METADATA_TRIPS_TABLE_ID:-trips}"
ITINERARY_ITEMS_TABLE_ID="${METADATA_ITINERARY_ITEMS_TABLE_ID:-itinerary_items}"
BOOKINGS_TABLE_ID="${METADATA_BOOKINGS_TABLE_ID:-bookings}"
SESSIONS_TABLE_ID="${METADATA_SESSIONS_TABLE_ID:-sessions}"
TURNS_TABLE_ID="${METADATA_TURNS_TABLE_ID:-turns}"
EVAL_RUNS_TABLE_ID="${METADATA_EVAL_RUNS_TABLE_ID:-eval_runs}"
echo "TRIPS_TABLE_ID=$TRIPS_TABLE_ID"
echo "ITINERARY_ITEMS_TABLE_ID=$ITINERARY_ITEMS_TABLE_ID"
echo "BOOKINGS_TABLE_ID=$BOOKINGS_TABLE_ID"
echo "SESSIONS_TABLE_ID=$SESSIONS_TABLE_ID"
echo "TURNS_TABLE_ID=$TURNS_TABLE_ID"
echo "EVAL_RUNS_TABLE_ID=$EVAL_RUNS_TABLE_ID"

# Ensure the BigQuery dataset exists (idempotent).
python "$PROMOTION_SCRIPT_DIR/bqtk.py" create-dataset \
  "$PROJECT_ID" "$METADATA_BIGQUERY_DATASET_ID" --location "$GCP_LOCATION"

if [ $? -ne 0 ]; then
  log_error "Dataset setup failed for $PROJECT_ID:$METADATA_BIGQUERY_DATASET_ID"
  exit 1
fi

log_info "Dataset $PROJECT_ID:$METADATA_BIGQUERY_DATASET_ID ready"

# Ensure the six trip tables exist (idempotent — existing tables are never
# dropped, so trip data survives every deploy).
bash "$PROMOTION_SCRIPT_DIR/create_vocal_bridge_tables.sh" \
  --project-id "$PROJECT_ID" \
  --dataset-id "$METADATA_BIGQUERY_DATASET_ID" \
  --trips-table-id "$TRIPS_TABLE_ID" \
  --itinerary-items-table-id "$ITINERARY_ITEMS_TABLE_ID" \
  --bookings-table-id "$BOOKINGS_TABLE_ID" \
  --sessions-table-id "$SESSIONS_TABLE_ID" \
  --turns-table-id "$TURNS_TABLE_ID" \
  --eval-runs-table-id "$EVAL_RUNS_TABLE_ID"

if [ $? -ne 0 ]; then
  log_error "Table setup failed for $PROJECT_ID:$METADATA_BIGQUERY_DATASET_ID"
  exit 1
fi

log_info "Tables in $PROJECT_ID:$METADATA_BIGQUERY_DATASET_ID ready"
