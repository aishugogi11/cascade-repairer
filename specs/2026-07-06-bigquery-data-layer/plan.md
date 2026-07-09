# Plan — BigQuery Data Layer

Task groups are independently implementable in this order; each leaves the repo green (`cd backend && pytest`).

## 1. Donor cleanup

1.1 Delete donor scripts and schemas from `backend/promotion_scripts/`: `create_spreadsheet_conversions_table.sh`, `create_rag_embeddings_table.sh`, `rag_embeddings_schema.yaml`, `create_blonter_msg_history_table.sh`, `blonter_msg_history_schema.yaml`, `create_bq_monitoring_table.sh`, `run_setup.sh`, and the stale `__pycache__`.
1.2 Rewrite `backend/promotion_scripts/README.md` for this project: what `bqtk.py` is, how `create_vocal_bridge_tables.sh` (group 2) is run, the six tables it creates, and a pointer to `specs/tech-stack.md` § Data as the schema source of truth.

## 2. Schemas & creation script

2.1 Write six schema YAMLs in `backend/promotion_scripts/` (`trips_schema.yaml`, `itinerary_items_schema.yaml`, `bookings_schema.yaml`, `sessions_schema.yaml`, `turns_schema.yaml`, `eval_runs_schema.yaml`) matching the field table in `requirements.md`, in the `field_name`/`field_type`/`field_mode` format `bqtk.py --field-yaml-file` parses. `trips.destinations` is `field_mode: REPEATED`.
2.2 Write `create_vocal_bridge_tables.sh <project_id> <dataset_id>`: donor-wrapper style (arg check + usage), loops the six tables calling `bqtk.py create-table` with each YAML and a `--description`. Idempotent — `bqtk.py` already no-ops on Conflict. Make it executable.
2.3 Dry-run check: `./create_vocal_bridge_tables.sh` … with `--dry-run` plumbed through (add pass-through flag) or manually verify each YAML parses via `bqtk.py create-table … --dry-run`.

## 3. Helper write primitives

3.1 Extend `backend/api/helpers/bigquery_helper.py` with DML methods alongside `run_select`, same conventions (lazy client, log + return `Tuple[bool, Optional[str]]`, never raise):
   - `run_dml(query: str, params: list[bigquery.ScalarQueryParameter | ...]) -> Tuple[bool, Optional[str]]` — parameterized INSERT/UPDATE via query job, waits for completion.
   - Parameterize `run_select` (optional `params` arg, backward compatible) so repositories never interpolate values into SQL.
3.2 Keep the module import-safe with no credentials (no client construction at import time) — this is what keeps the test suite hermetic.

## 4. Repository layer

4.1 `backend/api/repositories/models.py`: pydantic models for the six tables with `Literal`/enum status fields (`TripStatus`, `ItemStatus` with the six repair-lifecycle values, `ItemType`, `BookingState`, `Role`, `Architecture`), UUID4 id defaults, and JSON fields as `dict`.
4.2 `backend/api/repositories/trips.py`: `create_trip`, `get_trip`, `update_trip_status`, `get_trip_with_items(trip_id)` (trip + its itinerary items in one call — Phase 9's poll read).
4.3 `backend/api/repositories/itinerary_items.py`: `create_item`, `get_item`, `list_items_for_trip`, `update_status(item_id, status)` — stamps `updated_at CURRENT_TIMESTAMP()`; this is the cascade's write path.
4.4 `backend/api/repositories/bookings.py`: `create_booking`, `get_booking`, `list_bookings_for_trip`, `update_state`.
4.5 `backend/api/repositories/sessions.py`: `create_session`, `end_session(session_id)` (stamps `ended_at`), `get_session`.
4.6 `backend/api/repositories/turns.py`: `create_turn`, `list_turns_for_session`; `audio_uri_for(session_id, turn_id)` path builder using the GCS convention `audio/<session_id>/<turn_id>.wav` (referencing `gcs_helper` bucket config, no new GCS ops).
4.7 `backend/api/repositories/eval_runs.py`: `create_run`, `list_runs(architecture=None, scenario=None)`.
4.8 All repository functions return `(success, result, error)`-style tuples consistent with the helper conventions; row dicts from `run_select` map back into pydantic models in one place (a shared `_row_to_model` per module or in `models.py`).

## 5. Tests

5.1 `backend/tests/test_bigquery_helper.py`: `run_dml`/parameterized `run_select` — mock the client, assert job invocation, parameter passing, and error-tuple behavior on exception.
5.2 `backend/tests/test_repositories.py` (or per-table files if large): for each table — create generates valid SQL + params and a UUID id; get/list map rows to models; `update_status` rejects invalid statuses (pydantic error) and stamps `updated_at`; status enums cover exactly the lifecycle values from `tech-stack.md`.
5.3 One lifecycle-shaped test: mocked sequence booked → broken → repairing → fixed on an itinerary item, asserting each transition issues an UPDATE with the right status param — the Phase 4/9 contract in miniature.
5.4 Confirm the whole suite runs with no GCP credentials in the environment (CI parity).

## 6. Docs touch-up

6.1 Update `specs/tech-stack.md` is **not** modified (working agreement: no `specs/` edits without instruction) — instead confirm `README.md`/`backend` docs don't reference the deleted donor scripts; fix if they do.
