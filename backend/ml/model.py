"""Logistic regression delay classifier + on-disk artifact.

Chosen because coefficients are readable in a demo (which features raise
delay risk) and it trains in seconds on the synthetic BTS-calibrated set.
"""
from pathlib import Path
from typing import Any, Dict, List

import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from ml.preprocess import build_preprocessor

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = ARTIFACT_DIR / "delay_risk.joblib"
METRICS_PATH = ARTIFACT_DIR / "metrics.json"


def build_model() -> Pipeline:
    return Pipeline([
        ("prep", build_preprocessor()),
        ("clf", LogisticRegression(
            max_iter=500,
            class_weight="balanced",
            solver="lbfgs",
        )),
    ])


def save_artifact(pipeline: Pipeline, metrics: Dict[str, Any]) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"pipeline": pipeline, "metrics": metrics}
    joblib.dump(payload, MODEL_PATH)
    METRICS_PATH.write_text(
        __import__("json").dumps(metrics, indent=2) + "\n", encoding="utf-8"
    )
    return MODEL_PATH


def load_artifact(path: Path = MODEL_PATH) -> Dict[str, Any]:
    return joblib.load(path)


def feature_names(pipeline: Pipeline) -> List[str]:
    """Expanded names after one-hot — used to explain a single prediction."""
    prep = pipeline.named_steps["prep"]
    return list(prep.get_feature_names_out())
