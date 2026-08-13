"""Score one itinerary: P(arrival delay ≥ 15 minutes).

Loads the trained artifact once per process. If the file is missing or
sklearn cannot load it, a documented heuristic fallback keeps the voice
turn alive — the UI still shows a risk, tagged as fallback.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Dict, List, Tuple

import pandas as pd

from ml.features import CONSUMER_FACTORS, FEATURE_COLUMNS, features_from_option
from ml.model import MODEL_PATH, load_artifact

logger = logging.getLogger(__name__)


def _heuristic_risk(row: Dict[str, Any]) -> float:
    """Same directional effects the synthetic labels used — not the model."""
    p = 0.14
    p += 0.09 * int(row.get("stops") or 0)
    p += 0.07 * int(row.get("is_evening_dep") or 0)
    p -= 0.02 * int(row.get("is_early_dep") or 0)
    p += 0.05 * int(row.get("origin_hub") or 0)
    p += 0.03 * int(row.get("dest_hub") or 0)
    airline = (row.get("airline") or "").upper()
    p += {"NK": 0.10, "F9": 0.08, "B6": 0.04, "WN": 0.03}.get(airline, 0.0)
    p -= {"DL": 0.03, "AS": 0.03}.get(airline, 0.0)
    return float(min(0.72, max(0.05, p)))


@lru_cache(maxsize=1)
def _loaded() -> Tuple[Any, Dict[str, Any]] | Tuple[None, Dict[str, Any]]:
    if not MODEL_PATH.exists():
        logger.warning("delay-risk artifact missing at %s; using heuristic", MODEL_PATH)
        return None, {"source": "heuristic_fallback"}
    try:
        payload = load_artifact()
        return payload["pipeline"], payload.get("metrics") or {}
    except Exception:  # noqa: BLE001 — scoring cannot take down a voice turn
        logger.exception("delay-risk artifact failed to load; using heuristic")
        return None, {"source": "heuristic_fallback"}


def model_metrics() -> Dict[str, Any]:
    _, metrics = _loaded()
    out = dict(metrics)
    out["source"] = "trained_artifact" if _loaded()[0] is not None else "heuristic_fallback"
    out["artifact"] = str(MODEL_PATH)
    return out


def _top_factors(pipeline, row: Dict[str, Any], k: int = 3) -> List[str]:
    """Largest-magnitude signed contributions on this row, in traveler words."""
    try:
        clf = pipeline.named_steps["clf"]
        prep = pipeline.named_steps["prep"]
        names = list(prep.get_feature_names_out())
        x = prep.transform(pd.DataFrame([row], columns=FEATURE_COLUMNS))[0]
        contrib = clf.coef_[0] * x
        ranked = sorted(zip(names, contrib), key=lambda p: abs(p[1]), reverse=True)
    except Exception:  # noqa: BLE001
        ranked = []
    labels: List[str] = []
    for name, weight in ranked:
        if weight <= 0:
            continue  # only risk-raising factors in the "why this risk" line
        short = name.split("__", 1)[-1]
        for key, label in CONSUMER_FACTORS.items():
            if short == key or short.startswith(key):
                if label not in labels:
                    labels.append(label)
                break
        else:
            if short.startswith("airline_"):
                code = short.split("_", 1)[-1]
                labels.append(f"{code} historical delay rate")
        if len(labels) >= k:
            break
    if int(row.get("stops") or 0) > 0 and "has a connection" not in labels:
        labels.insert(0, "has a connection")
    return labels[:k]


def predict_delay_risk(option: Any) -> Dict[str, Any]:
    """Return delay_risk in [0, 1], percent, contributing factors, source."""
    row = features_from_option(option)
    pipeline, _metrics = _loaded()
    if pipeline is None:
        risk = _heuristic_risk(row)
        factors = []
        if row["stops"]:
            factors.append("has a connection")
        if row["is_evening_dep"]:
            factors.append("evening departure")
        if row["origin_hub"] or row["dest_hub"]:
            factors.append("busy hub airport")
        return {
            "delay_risk": risk,
            "delay_risk_pct": int(round(risk * 100)),
            "factors": factors,
            "source": "heuristic_fallback",
        }
    proba = float(pipeline.predict_proba(
        pd.DataFrame([row], columns=FEATURE_COLUMNS)
    )[0, 1])
    proba = min(0.95, max(0.02, proba))
    return {
        "delay_risk": proba,
        "delay_risk_pct": int(round(proba * 100)),
        "factors": _top_factors(pipeline, row),
        "source": "trained_artifact",
    }
