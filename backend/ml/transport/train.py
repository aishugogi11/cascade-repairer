"""Train transportation-quality models and write ml/transport/artifacts/.

  python -m ml.transport.train
  python -m ml.transport.train --csv /path/to/hops.csv

Does not run at request time. The optimizer loads the saved forest.
"""
from __future__ import annotations

import argparse

from sklearn.model_selection import train_test_split

from ml.transport.data import DATASET_DISCLAIMER, dataset
from ml.transport.evaluate import evaluate
from ml.transport.features import FEATURE_COLUMNS, FEATURE_DOCS
from ml.transport.model import (
    build_forest,
    build_linear,
    feature_names,
    save_artifact,
)


def _top_importances(pipeline, k: int = 8) -> list:
    try:
        names = feature_names(pipeline)
        raw = pipeline.named_steps["reg"].feature_importances_
    except Exception:  # noqa: BLE001
        return []
    ranked = sorted(zip(names, raw), key=lambda p: p[1], reverse=True)
    out = []
    for name, weight in ranked[:k]:
        short = name.split("__", 1)[-1]
        if short.startswith("transportation_mode_"):
            label = "transportation mode"
        elif short.startswith("venue_type_"):
            label = "venue type"
        else:
            label = FEATURE_DOCS.get(short, short.replace("_", " "))
        out.append({"feature": short, "importance": float(weight), "why": label})
    return out


def train(csv_path: str | None = None, n: int = 12_000, seed: int = 42):
    frame = dataset(csv_path=csv_path, n=n, seed=seed)
    X = frame[FEATURE_COLUMNS]
    y = frame["transportation_quality_score"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=seed,
    )
    linear = build_linear()
    linear.fit(X_train, y_train)
    forest = build_forest(seed=seed)
    forest.fit(X_train, y_train)
    linear_metrics = evaluate(linear, X_test, y_test)
    linear_metrics["model"] = "LinearRegression"
    forest_metrics = evaluate(forest, X_test, y_test)
    forest_metrics["model"] = "RandomForestRegressor"
    metrics = {
        **forest_metrics,
        "n_train": int(len(X_train)),
        "features": FEATURE_COLUMNS,
        "n_features": len(FEATURE_COLUMNS),
        "expanded_features": feature_names(forest),
        "dataset": "synthetic_transport_quality",
        "dataset_disclaimer": DATASET_DISCLAIMER,
        "comparison": {
            "LinearRegression": {
                "mae": linear_metrics["mae"],
                "rmse": linear_metrics["rmse"],
                "r2": linear_metrics["r2"],
            },
            "RandomForestRegressor": {
                "mae": forest_metrics["mae"],
                "rmse": forest_metrics["rmse"],
                "r2": forest_metrics["r2"],
            },
        },
        "production_model": "RandomForestRegressor",
        "top_features": _top_importances(forest),
    }
    path = save_artifact(forest, metrics)
    return forest, metrics, path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=None, help="Optional labeled CSV")
    parser.add_argument("--n", type=int, default=12_000)
    args = parser.parse_args()
    _, metrics, path = train(csv_path=args.csv, n=args.n)
    print(f"saved {path}")
    print(metrics["dataset_disclaimer"])
    print(f"n_train: {metrics['n_train']}")
    print(f"n_test: {metrics['n_test']}")
    print(f"n_features: {metrics['n_features']}")
    for name, row in metrics["comparison"].items():
        print(
            f"{name:24s}  MAE {row['mae']:.4f}  RMSE {row['rmse']:.4f}  "
            f"R2 {row['r2']:.4f}"
        )


if __name__ == "__main__":
    main()
