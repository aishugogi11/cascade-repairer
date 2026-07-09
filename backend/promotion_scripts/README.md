# BigQuery Table Promotion Scripts

Scripts to create the BigQuery tables for the vocal-bridge backend. The schema
source of truth is `specs/tech-stack.md` § Data — the YAMLs here implement it.

## Tools

- `bqtk.py` — click CLI wrapping the BigQuery client: `create-dataset`,
  `create-table` (schema via `--field`/`--field-yaml-file`), `truncate-table`,
  `drop-table`. Dataset and table creation are idempotent (Conflict → no-op).
- `create_gcs_bucket.sh` — one-time GCS bucket creation (used by project setup).

## Create the trip tables

Creates all six tables in one run (idempotent — safe to re-run; existing
tables are never dropped):

```bash
./create_vocal_bridge_tables.sh --project-id <project_id> --dataset-id <dataset_id>
```

Example:

```bash
./create_vocal_bridge_tables.sh --project-id vocal-bridge-hackathon --dataset-id vocal_bridge
```

Table ids default to the canonical names below and can be overridden per
table (`--trips-table-id`, `--itinerary-items-table-id`, …); in CI they come
from `config.yaml` `metadata:` (`trips_table_id` etc.) via `image.env`. Add
`--dry-run` to validate the schema YAMLs without creating anything:

```bash
./create_vocal_bridge_tables.sh --project-id vocal-bridge-hackathon --dataset-id vocal_bridge --dry-run
```

Tables created (schema YAML per table alongside this README):

| Table | Purpose |
|---|---|
| `trips` | One row per trip; status draft/booked/active/complete |
| `itinerary_items` | Trip legs (flight/hotel/ground/dining/experience); `status` carries the repair lifecycle planned/booked/broken/repairing/fixed/cancelled |
| `bookings` | Provider bookings per item, incl. Sabre confirmation ref and raw response |
| `sessions` | Voice conversation sessions per architecture |
| `turns` | Per-turn transcripts, audio GCS URIs, latency metrics |
| `eval_runs` | Evaluation harness results (TTFB, e2e latency, WER, MOS) |

The dataset itself (`vocal_bridge`, us-west1) is created by
`backend/devops/scripts/gcp_project_setup.sh`. Cloud Build's `setup-artifacts`
step (`run_artifact_setup.sh`) ensures the dataset **and runs this table
script** on every build, so CI/CD keeps all six tables in place — the manual
invocation above is only for ad-hoc/local use. Creation is idempotent, so if a
schema changes pre-hackathon, drop and recreate:

```bash
python bqtk.py drop-table <project_id> <dataset_id> <table_id> --force
```

## Requirements

- `pip install click pyyaml google-cloud-bigquery`
- `gcloud auth application-default login` (or a service account) with BigQuery
  permissions on the target project
