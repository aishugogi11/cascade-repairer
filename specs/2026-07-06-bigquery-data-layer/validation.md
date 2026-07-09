# Validation — BigQuery Data Layer

## Automated

Run from `backend/`: `pytest` (same command CI runs inside the built container). All of the following must hold:

- Full suite passes **with no GCP credentials and no `OPENAI_API_KEY` in the environment** — importing helpers and repositories must not construct a GCP client.
- Helper tests assert: `run_dml` executes a parameterized query job and waits; both `run_dml` and `run_select` return `(False, …, error_message)` on client exceptions instead of raising.
- Repository tests assert, per table: create issues INSERT with query parameters (no value interpolation into SQL) and generates a UUID id; reads map BigQuery row dicts into the pydantic models; list functions filter by the right parent key (trip_id / session_id).
- `itinerary_items.update_status` accepts exactly `planned/booked/broken/repairing/fixed/cancelled`, rejects anything else with a validation error, and its UPDATE stamps `updated_at`.
- The lifecycle sequence test passes: booked → broken → repairing → fixed issues four UPDATEs with the correct status parameter each time.
- Existing tests (`test_gcp_check.py`, `test_hello.py`, validators) still pass — the helper changes are backward compatible.

## Manual

> **Note (2026-07-06, replan):** mid-phase, table creation moved into CI per Josh — the Cloud Build `setup-artifacts` step now runs `create_vocal_bridge_tables.sh` with table ids from `config.yaml` metadata on every build. QA was confirmed via the PR #8 build logs and the BigQuery console (all six tables present in `vocal_bridge`). The walkthrough below is kept for ad-hoc/local use.

One-time walkthrough against the real `vocal-bridge-hackathon` / `vocal_bridge` dataset (needs local gcloud auth):

1. `cd backend/promotion_scripts && ./create_vocal_bridge_tables.sh vocal-bridge-hackathon vocal_bridge` — six "created" lines.
2. Re-run the same command — six "already exists" lines, exit 0 (idempotent).
3. `bq ls vocal-bridge-hackathon:vocal_bridge` shows exactly: `trips`, `itinerary_items`, `bookings`, `sessions`, `turns`, `eval_runs`. Spot-check one schema (`bq show --schema` on `itinerary_items`) against `specs/tech-stack.md` § Schema — including JSON `details` and `updated_at`.
4. From a Python shell in `backend/` (real credentials): `create_trip` → `create_item` (status `booked`) → `update_status(item_id, "broken")` → `update_status(item_id, "repairing")` → `update_status(item_id, "fixed")` — each call succeeds **immediately** (no streaming-buffer error), then `get_trip_with_items` returns the trip with the item in status `fixed` and a fresh `updated_at`.
5. Deployed check unchanged: `GET /v1/hello/gcp_check` on the Cloud Run service still reports BigQuery and GCS reachable.

### Edge cases

- Creation script with a missing arg prints usage and exits non-zero.
- `update_status` on a nonexistent item_id returns a failure/no-op result, not an exception.
- A trip with multiple `destinations` (REPEATED field) round-trips through create + get.
- `run_select` callers that predate the `params` argument still work (gcp_check endpoint).

## Tone check

No user-facing copy in this phase. Scripts and README stay terse and imperative, matching the existing devops style.

## Definition of done

- Donor table scripts/YAMLs and `run_setup.sh` are gone; `promotion_scripts/README.md` describes only this project's tables.
- Six tables exist in the real dataset, created by the idempotent script, matching the tech-stack schema.
- All six repositories importable and typed; the status-transition path proven immediately updatable (the Phase 4/5/9 contract).
- `pytest` green hermetically, locally and in the Cloud Build container step, on the PR from `vb/feature/bigquery-data-layer` into `vb/dev`.
