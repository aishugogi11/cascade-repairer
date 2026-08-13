"""Train the action-utility forest.

  python -m ml.transport.policy_train
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from ml.transport.data import DATASET_DISCLAIMER
from ml.transport.policy import (
    ACTION_CATEGORICAL,
    ACTION_COLUMNS,
    ACTION_NUMERIC,
    generate_action_dataset,
    rules_select,
)
from ml.transport.preprocess import build_preprocessor

ARTIFACT_DIR = Path(__file__).resolve().parent / "artifacts"
POLICY_PATH = ARTIFACT_DIR / "action_policy.joblib"
POLICY_METRICS_PATH = ARTIFACT_DIR / "policy_metrics.json"


def build_policy_forest(seed: int = 42) -> Pipeline:
    return Pipeline([
        ("prep", build_preprocessor(ACTION_NUMERIC, ACTION_CATEGORICAL)),
        ("reg", RandomForestRegressor(
            n_estimators=80, max_depth=12, min_samples_leaf=6,
            random_state=seed, n_jobs=-1,
        )),
    ])


def build_policy_linear() -> Pipeline:
    return Pipeline([
        ("prep", build_preprocessor(ACTION_NUMERIC, ACTION_CATEGORICAL)),
        ("reg", LinearRegression()),
    ])


def _action_accuracy(frame, pred) -> float:
    work = frame.copy()
    work["_pred"] = pred
    hits = 0
    groups = 0
    for _, grp in work.groupby("state_id"):
        true_best = grp.loc[grp["action_utility"].idxmax(), "action_type"]
        pred_best = grp.loc[grp["_pred"].idxmax(), "action_type"]
        hits += int(true_best == pred_best)
        groups += 1
    return hits / max(groups, 1)


def _rules_accuracy(frame) -> float:
    hits = 0
    groups = 0
    for _, grp in frame.groupby("state_id"):
        keep = grp[grp["action_type"] == "KEEP_CURRENT_PLAN"].iloc[0]
        guessed = rules_select(keep.to_dict(), priority=str(keep["priority"]))
        true_best = grp.loc[grp["action_utility"].idxmax(), "action_type"]
        hits += int(guessed == true_best)
        groups += 1
    return hits / max(groups, 1)


def train_policy(n_states: int = 3_000, seed: int = 42):
    frame = generate_action_dataset(n_states=n_states, seed=seed)
    states = frame["state_id"].unique()
    train_ids, test_ids = train_test_split(states, test_size=0.2, random_state=seed)
    train = frame[frame["state_id"].isin(train_ids)]
    test = frame[frame["state_id"].isin(test_ids)]
    X_train, y_train = train[ACTION_COLUMNS], train["action_utility"]
    X_test, y_test = test[ACTION_COLUMNS], test["action_utility"]
    linear = build_policy_linear()
    linear.fit(X_train, y_train)
    forest = build_policy_forest(seed=seed)
    forest.fit(X_train, y_train)
    lp = linear.predict(X_test)
    fp = forest.predict(X_test)

    def pack(name, pred):
        mse = mean_squared_error(y_test, pred)
        return {
            "mae": float(mean_absolute_error(y_test, pred)),
            "rmse": float(np.sqrt(mse)),
            "r2": float(r2_score(y_test, pred)),
            "action_accuracy": float(_action_accuracy(test, pred)),
        }

    metrics: Dict[str, Any] = {
        "n_train_rows": int(len(train)),
        "n_test_rows": int(len(test)),
        "n_train_states": int(len(train_ids)),
        "n_test_states": int(len(test_ids)),
        "n_features": len(ACTION_COLUMNS),
        "features": ACTION_COLUMNS,
        "target": "action_utility",
        "target_description": (
            "Predicted improvement vs keeping the current hop plan. "
            "The optimizer executes the feasible action with the highest score."
        ),
        "model": "RandomForestRegressor",
        "production_model": "RandomForestRegressor",
        "dataset": "synthetic_action_utility",
        "dataset_disclaimer": DATASET_DISCLAIMER,
        "comparison": {
            "RulesBaseline": {
                "action_accuracy": float(_rules_accuracy(test)),
                "mae": None,
                "r2": None,
            },
            "LinearRegression": pack("lr", lp),
            "RandomForestRegressor": pack("rf", fp),
        },
    }
    rf = metrics["comparison"]["RandomForestRegressor"]
    metrics["mae"] = rf["mae"]
    metrics["rmse"] = rf["rmse"]
    metrics["r2"] = rf["r2"]
    metrics["action_accuracy"] = rf["action_accuracy"]
    try:
        names = list(forest.named_steps["prep"].get_feature_names_out())
        weights = forest.named_steps["reg"].feature_importances_
        ranked = sorted(zip(names, weights), key=lambda p: p[1], reverse=True)
        metrics["top_features"] = [
            {"feature": n.split("__", 1)[-1], "importance": float(w)}
            for n, w in ranked[:8]
        ]
    except Exception:  # noqa: BLE001
        metrics["top_features"] = []
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": forest, "metrics": metrics}, POLICY_PATH, compress=3)
    POLICY_METRICS_PATH.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    return forest, metrics, POLICY_PATH


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=3_000)
    args = parser.parse_args()
    _, metrics, path = train_policy(n_states=args.n)
    print(f"saved {path}")
    print(metrics["dataset_disclaimer"])
    for name, row in metrics["comparison"].items():
        acc = row.get("action_accuracy")
        extra = ""
        if row.get("mae") is not None:
            extra = f"  MAE {row['mae']:.4f}  R2 {row['r2']:.4f}"
        print(f"{name:24s}  action-acc {acc:.3f}{extra}")


if __name__ == "__main__":
    main()
