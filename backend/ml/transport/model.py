"""Random Forest (production) and Linear Regression (baseline) artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import joblib
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline

from ml.transport.preprocess import build_preprocessor

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "transport_quality.joblib"
METRICS_PATH = ARTIFACT_DIR / "metrics.json"


def build_forest(seed: int = 42) -> Pipeline:
    return Pipeline([
        ("prep", build_preprocessor()),
        ("reg", RandomForestRegressor(
            n_estimators=80,
            max_depth=12,
            min_samples_leaf=6,
            random_state=seed,
            n_jobs=-1,
        )),
    ])


def build_linear() -> Pipeline:
    return Pipeline([
        ("prep", build_preprocessor()),
        ("reg", LinearRegression()),
    ])


def save_artifact(pipeline: Pipeline, metrics: Dict[str, Any]) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": pipeline, "metrics": metrics}, MODEL_PATH, compress=3)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    return MODEL_PATH


def load_artifact(path: Path | None = None) -> Dict[str, Any]:
    return joblib.load(path or MODEL_PATH)


def feature_names(pipeline: Pipeline) -> List[str]:
    prep = pipeline.named_steps["prep"]
    return list(prep.get_feature_names_out())
