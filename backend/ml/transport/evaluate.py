"""Hold-out regression metrics for transportation quality."""
from typing import Any, Dict

import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


def evaluate(pipeline, X, y) -> Dict[str, Any]:
    pred = np.asarray(pipeline.predict(X), dtype=float)
    y_arr = np.asarray(y, dtype=float)
    mse = mean_squared_error(y_arr, pred)
    return {
        "n_test": int(len(y_arr)),
        "mae": float(mean_absolute_error(y_arr, pred)),
        "rmse": float(np.sqrt(mse)),
        "r2": float(r2_score(y_arr, pred)),
        "y_mean": float(y_arr.mean()),
        "pred_mean": float(pred.mean()),
        "target": "transportation_quality_score",
        "target_description": (
            "Higher is a better transportation outcome for this hop "
            "(time, cost, walking, congestion, schedule fit)."
        ),
    }
