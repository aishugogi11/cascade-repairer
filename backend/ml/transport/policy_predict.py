"""Score a candidate action with the trained policy forest."""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Dict, List, Sequence, Tuple

import pandas as pd

from ml.transport.data import DATASET_DISCLAIMER
from ml.transport.policy import ACTION_COLUMNS, action_row
from ml.transport.policy_train import POLICY_PATH

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _loaded() -> Tuple[Any, Dict[str, Any]]:
    if not POLICY_PATH.exists():
        logger.warning("action policy artifact missing at %s", POLICY_PATH)
        return None, {"source": "heuristic_fallback", "dataset_disclaimer": DATASET_DISCLAIMER}
    try:
        import joblib
        payload = joblib.load(POLICY_PATH)
        return payload["pipeline"], payload.get("metrics") or {}
    except Exception:  # noqa: BLE001
        logger.exception("action policy failed to load")
        return None, {"source": "heuristic_fallback", "dataset_disclaimer": DATASET_DISCLAIMER}


def reset_cache() -> None:
    _loaded.cache_clear()


def policy_metrics() -> Dict[str, Any]:
    pipeline, metrics = _loaded()
    out = dict(metrics)
    out["source"] = "trained_artifact" if pipeline is not None else "heuristic_fallback"
    out["artifact"] = str(POLICY_PATH)
    out.setdefault("dataset_disclaimer", DATASET_DISCLAIMER)
    return out


def predict_action_utility(row: Dict[str, Any]) -> Dict[str, Any]:
    return predict_action_utility_many([row])[0]


def predict_action_utility_many(rows: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not rows:
        return []
    pipeline, metrics = _loaded()
    if pipeline is None:
        out = []
        for row in rows:
            score = (
                0.02 * float(row.get("delta_travel") or 0)
                + 0.01 * float(row.get("delta_congestion") or 0)
            )
            if row.get("action_type") == "KEEP_CURRENT_PLAN":
                score = 0.0
            out.append({"utility": round(score, 4), "source": "heuristic_fallback"})
        return out
    frame = pd.DataFrame(list(rows), columns=ACTION_COLUMNS)
    utils = pipeline.predict(frame)
    model = metrics.get("production_model") or "RandomForestRegressor"
    return [
        {"utility": round(float(util), 4), "source": "trained_artifact", "model": model}
        for util in utils
    ]
