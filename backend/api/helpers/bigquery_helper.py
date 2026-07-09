"""BigQuery helper — config-driven client, query runner, and DML runner.

The typed repository functions in `api/repositories/` sit on top of this;
they pass fully parameterized SQL so no caller ever interpolates values.
Writes go through `run_dml` (query-job DML, not streaming inserts) so rows
are immediately UPDATE-able — the repair lifecycle flips an item's status
seconds after insert, which the streaming buffer would reject.
"""
from google.cloud import bigquery
from typing import Optional, Tuple
import logging
import os
import yaml
from pathlib import Path

logger = logging.getLogger(__name__)

# Load config
config_path = Path(__file__).parent.parent.parent / "config.yaml"
with open(config_path, "r") as f:
    config = yaml.safe_load(f)

PROJECT_ID = config["build_env_vars"]["PROJECT_ID"]
DATASET_ID = config["metadata"]["bigquery_dataset_id"]

# Logical table name → configured table id, from config.yaml metadata
# (<name>_table_id). The same entries drive CI table creation via
# run_artifact_setup.sh, so runtime and setup can never disagree.
TABLE_NAMES = ("trips", "itinerary_items", "bookings", "sessions", "turns", "eval_runs")
TABLE_IDS = {name: config["metadata"][f"{name}_table_id"] for name in TABLE_NAMES}


class BigQueryHelper:
    """Helper class for BigQuery operations"""

    def __init__(self):
        self._client = None
        self.project_id = os.getenv("GCP_PROJECT_ID", PROJECT_ID)
        self.dataset_id = os.getenv("BIGQUERY_DATASET_ID", DATASET_ID)
        # Env-overridable per table (e.g. TRIPS_TABLE_ID), matching the
        # project/dataset override convention above.
        self.table_ids = {
            name: os.getenv(f"{name.upper()}_TABLE_ID", table_id)
            for name, table_id in TABLE_IDS.items()
        }

    @property
    def client(self) -> bigquery.Client:
        """Lazy client so importing this module (and unit tests) never needs
        GCP credentials."""
        if self._client is None:
            self._client = bigquery.Client(project=self.project_id)
        return self._client

    def get_table_reference(self, table_name: str) -> str:
        """Full table reference for a logical table name, resolving the
        table id configured in config.yaml metadata (<name>_table_id).
        Unknown names pass through unchanged."""
        table_id = self.table_ids.get(table_name, table_name)
        return f"{self.project_id}.{self.dataset_id}.{table_id}"

    def run_select(
        self, query: str, params: Optional[list] = None
    ) -> Tuple[bool, list, Optional[str]]:
        """Execute a read-only SELECT and return its rows.

        Args:
            query: SELECT statement, with @name placeholders when ``params``
                is given.
            params: Optional query parameters (Scalar/ArrayQueryParameter).

        Returns:
            Tuple of (success, rows, error). ``rows`` is a list of plain dicts
            (column → value); empty on failure. Never raises — failures are
            returned in the tuple so callers can surface them.
        """
        try:
            job_config = (
                bigquery.QueryJobConfig(query_parameters=params) if params else None
            )
            query_job = self.client.query(query, job_config=job_config)
            results = query_job.result()
            rows = [dict(row.items()) for row in results]
            return True, rows, None
        except Exception as e:
            logger.error(f"Error running select: {e}")
            return False, [], str(e)

    def run_dml(
        self, query: str, params: Optional[list] = None
    ) -> Tuple[bool, int, Optional[str]]:
        """Execute a parameterized DML statement (INSERT/UPDATE) and wait.

        Returns:
            Tuple of (success, affected_rows, error). ``affected_rows`` is the
            job's num_dml_affected_rows (0 when unreported); 0 on failure.
            Never raises — failures are returned in the tuple.
        """
        try:
            job_config = (
                bigquery.QueryJobConfig(query_parameters=params) if params else None
            )
            query_job = self.client.query(query, job_config=job_config)
            query_job.result()
            affected = query_job.num_dml_affected_rows or 0
            return True, affected, None
        except Exception as e:
            logger.error(f"Error running dml: {e}")
            return False, 0, str(e)


# Create singleton instance
bq_helper = BigQueryHelper()
