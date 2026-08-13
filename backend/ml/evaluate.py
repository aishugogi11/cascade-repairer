"""Hold-out metrics for the delay-risk classifier."""
from typing import Any, Dict

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)


def evaluate(pipeline, X, y) -> Dict[str, Any]:
    proba = pipeline.predict_proba(X)[:, 1]
    pred = (proba >= 0.5).astype(int)
    y_arr = np.asarray(y)
    return {
        "n_test": int(len(y_arr)),
        "positive_rate": float(y_arr.mean()),
        "accuracy": float(accuracy_score(y_arr, pred)),
        "precision": float(precision_score(y_arr, pred, zero_division=0)),
        "recall": float(recall_score(y_arr, pred, zero_division=0)),
        "f1": float(f1_score(y_arr, pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_arr, proba)),
        "threshold": 0.5,
        "target": "delayed_15",
        "target_description": (
            "Probability a flight arrives 15+ minutes late (BTS On-Time)."
        ),
        "model": "LogisticRegression",
        "dataset": "bts_calibrated_synthetic",
    }
