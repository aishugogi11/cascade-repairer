"""Score one transportation option with the trained forest.

Loads the artifact once per process. If it is missing, a documented
heuristic fallback keeps the page alive — tagged so we never pretend
the forest ran.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Dict, List, Tuple

import pandas as pd

from ml.transport.data import DATASET_DISCLAIMER
from ml.transport.features import CONSUMER_LABELS, FEATURE_COLUMNS, row_from_option
from ml.transport.model import load_artifact
from ml.transport import model as transport_model

logger = logging.getLogger(__name__)


def _heuristic_score(row: Dict[str, Any]) -> float:
    """Directional stand-in only — not the trained model."""
    q = 0.62
    q -= 0.012 * float(row.get("estimated_travel_time") or 20)
    q -= 0.008 * float(row.get("estimated_cost") or 10)
    q -= 0.15 * float(row.get("pickup_congestion") or 0.4)
    q -= 0.12 * float(row.get("walking_ratio") or 0.2)
    q += 0.04 * float(row.get("buffer_ratio") or 1.0)
    mode = row.get("transportation_mode") or "uber"
    if mode == "walk" and float(row.get("distance_miles") or 1) > 1.0:
        q -= 0.18
    return float(min(0.95, max(0.05, q)))


@lru_cache(maxsize=1)
def _loaded() -> Tuple[Any, Dict[str, Any]]:
    if not transport_model.MODEL_PATH.exists():
        logger.warning("transport artifact missing at %s; using heuristic", transport_model.MODEL_PATH)
        return None, {"source": "heuristic_fallback", "dataset_disclaimer": DATASET_DISCLAIMER}
    try:
        payload = load_artifact()
        return payload["pipeline"], payload.get("metrics") or {}
    except Exception:  # noqa: BLE001
        logger.exception("transport artifact failed to load; using heuristic")
        return None, {"source": "heuristic_fallback", "dataset_disclaimer": DATASET_DISCLAIMER}


def model_metrics() -> Dict[str, Any]:
    pipeline, metrics = _loaded()
    out = dict(metrics)
    out["source"] = "trained_artifact" if pipeline is not None else "heuristic_fallback"
    out["artifact"] = str(transport_model.MODEL_PATH)
    out.setdefault("dataset_disclaimer", DATASET_DISCLAIMER)
    return out


def reset_cache() -> None:
    _loaded.cache_clear()


def predict_quality(option: Dict[str, Any]) -> Dict[str, Any]:
    row = row_from_option(option)
    pipeline, metrics = _loaded()
    if pipeline is None:
        score = _heuristic_score(row)
        return {
            "score": round(score, 4),
            "source": "heuristic_fallback",
            "factors": ["model artifact missing — heuristic score"],
            "row": row,
        }
    frame = pd.DataFrame([row], columns=FEATURE_COLUMNS)
    score = float(pipeline.predict(frame)[0])
    score = max(0.0, min(1.0, score))
    return {
        "score": round(score, 4),
        "source": "trained_artifact",
        "model": metrics.get("production_model") or "RandomForestRegressor",
        "factors": _local_factors(pipeline, row),
        "row": row,
    }


def _local_factors(pipeline, row: Dict[str, Any], k: int = 4) -> List[str]:
    """Global importances, phrased for the hop the traveler is looking at."""
    try:
        names = list(pipeline.named_steps["prep"].get_feature_names_out())
        weights = pipeline.named_steps["reg"].feature_importances_
    except Exception:  # noqa: BLE001
        return []
    ranked = sorted(zip(names, weights), key=lambda p: p[1], reverse=True)
    labels: List[str] = []
    for name, _ in ranked:
        short = name.split("__", 1)[-1]
        if short.startswith("transportation_mode_"):
            label = f"{row.get('transportation_mode', 'this mode')} vs other modes"
        elif short.startswith("venue_type_"):
            continue
        else:
            label = CONSUMER_LABELS.get(short, short.replace("_", " "))
        if label not in labels:
            labels.append(label)
        if len(labels) >= k:
            break
    return labels
