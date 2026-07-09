#!/bin/bash

# Create the six vocal-bridge tables (Phase 3 data layer). Called by
# devops/scripts/run_artifact_setup.sh on every Cloud Build with the table ids
# from config.yaml metadata (via image.env), or run by hand for ad-hoc setup.
#
# Idempotent: bqtk.py no-ops on tables that already exist. Tables are
# deliberately NEVER dropped here — trip data must survive every deploy; a
# schema change requires a manual `bqtk.py drop-table --force` first.

script_path=$(realpath "$0" | sed 's|\(.*\)/.*|\1|')

usage() {
  echo "Usage: $0 --project-id <id> --dataset-id <id> [options]"
  echo
  echo "Required Arguments:"
  echo "  --project-id <id>                GCP Project ID."
  echo "  --dataset-id <id>                BigQuery Dataset ID."
  echo
  echo "Optional Table Arguments:"
  echo "  --trips-table-id <id>            (default: trips)"
  echo "  --itinerary-items-table-id <id>  (default: itinerary_items)"
  echo "  --bookings-table-id <id>         (default: bookings)"
  echo "  --sessions-table-id <id>         (default: sessions)"
  echo "  --turns-table-id <id>            (default: turns)"
  echo "  --eval-runs-table-id <id>        (default: eval_runs)"
  echo
  echo "Other Options:"
  echo "  --dry-run                        Validate schemas without creating."
  echo "  -h, --help                       Display this help message."
  exit 1
}

DRY_RUN_FLAG=""

while [[ "$#" -gt 0 ]]; do
  case $1 in
    --project-id) PROJECT_ID="$2"; shift ;;
    --dataset-id) BIGQUERY_DATASET_ID="$2"; shift ;;
    --trips-table-id) TRIPS_TABLE_ID="$2"; shift ;;
    --itinerary-items-table-id) ITINERARY_ITEMS_TABLE_ID="$2"; shift ;;
    --bookings-table-id) BOOKINGS_TABLE_ID="$2"; shift ;;
    --sessions-table-id) SESSIONS_TABLE_ID="$2"; shift ;;
    --turns-table-id) TURNS_TABLE_ID="$2"; shift ;;
    --eval-runs-table-id) EVAL_RUNS_TABLE_ID="$2"; shift ;;
    --dry-run) DRY_RUN_FLAG="--dry-run" ;;
    -h|--help) usage ;;
    *) echo "Unknown parameter passed: $1"; usage ;;
  esac
  shift
done

TRIPS_TABLE_ID=${TRIPS_TABLE_ID:-"trips"}
ITINERARY_ITEMS_TABLE_ID=${ITINERARY_ITEMS_TABLE_ID:-"itinerary_items"}
BOOKINGS_TABLE_ID=${BOOKINGS_TABLE_ID:-"bookings"}
SESSIONS_TABLE_ID=${SESSIONS_TABLE_ID:-"sessions"}
TURNS_TABLE_ID=${TURNS_TABLE_ID:-"turns"}
EVAL_RUNS_TABLE_ID=${EVAL_RUNS_TABLE_ID:-"eval_runs"}

if [ -z "$PROJECT_ID" ] || [ -z "$BIGQUERY_DATASET_ID" ]; then
  echo "Error: Missing one or more required arguments."
  usage
fi

echo "Setting up BigQuery tables with the following configuration:"
echo "---------------------------------------------------------------"
echo "Project ID:            $PROJECT_ID"
echo "Dataset ID:            $BIGQUERY_DATASET_ID"
echo "Trips Table:           $TRIPS_TABLE_ID"
echo "Itinerary Items Table: $ITINERARY_ITEMS_TABLE_ID"
echo "Bookings Table:        $BOOKINGS_TABLE_ID"
echo "Sessions Table:        $SESSIONS_TABLE_ID"
echo "Turns Table:           $TURNS_TABLE_ID"
echo "Eval Runs Table:       $EVAL_RUNS_TABLE_ID"
echo "Dry Run:               ${DRY_RUN_FLAG:-no}"
echo "---------------------------------------------------------------"
echo

# --- Function to create a table and check for errors ---
# $1 = schema file basename (fixed), $2 = table id (configurable), $3 = description
create_table() {
  local schema_name=$1
  local table_id=$2
  local table_description=$3

  echo "Creating table: $table_id..."
  python3 "$script_path/bqtk.py" create-table \
    "$PROJECT_ID" "$BIGQUERY_DATASET_ID" "$table_id" \
    --field-yaml-file "$script_path/${schema_name}_schema.yaml" \
    --description "$table_description" \
    --verbose \
    $DRY_RUN_FLAG

  if [ $? -ne 0 ]; then
    echo "ERROR: Table creation failed for $table_id!"
    exit 1
  fi

  echo "Successfully ensured $table_id."
  echo ""
}

create_table "trips" "$TRIPS_TABLE_ID" "One row per trip; status draft/booked/active/complete"
create_table "itinerary_items" "$ITINERARY_ITEMS_TABLE_ID" "Trip legs; status carries the repair lifecycle planned/booked/broken/repairing/fixed/cancelled"
create_table "bookings" "$BOOKINGS_TABLE_ID" "Provider bookings per itinerary item, incl. Sabre confirmation ref"
create_table "sessions" "$SESSIONS_TABLE_ID" "Voice conversation sessions per architecture"
create_table "turns" "$TURNS_TABLE_ID" "Per-turn transcripts, audio GCS URIs, latency metrics"
create_table "eval_runs" "$EVAL_RUNS_TABLE_ID" "Evaluation harness results (TTFB, e2e latency, WER, MOS)"

echo "Setup complete. All 6 tables ensured in $PROJECT_ID.$BIGQUERY_DATASET_ID"
