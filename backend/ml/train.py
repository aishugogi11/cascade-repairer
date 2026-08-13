"""Train the delay-risk model and write ml/artifacts/.

  python -m ml.train
  python -m ml.train --csv /path/to/flights.csv

Does not run at request time. The Concierge loads the saved artifact.
"""
from __future__ import annotations

import argparse

from sklearn.model_selection import train_test_split

from ml.data import dataset
from ml.evaluate import evaluate
from ml.features import FEATURE_COLUMNS
from ml.model import build_model, feature_names, save_artifact


def train(csv_path: str | None = None, n: int = 12_000, seed: int = 42):
    frame = dataset(csv_path=csv_path, n=n)
    X = frame[FEATURE_COLUMNS]
    y = frame["delayed_15"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=seed, stratify=y,
    )
    pipeline = build_model()
    pipeline.fit(X_train, y_train)
    metrics = evaluate(pipeline, X_test, y_test)
    metrics["n_train"] = int(len(X_train))
    metrics["features"] = FEATURE_COLUMNS
    metrics["expanded_features"] = feature_names(pipeline)
    path = save_artifact(pipeline, metrics)
    return pipeline, metrics, path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=None, help="Optional labeled CSV")
    parser.add_argument("--n", type=int, default=12_000)
    args = parser.parse_args()
    _, metrics, path = train(csv_path=args.csv, n=args.n)
    print(f"saved {path}")
    for key in ("n_train", "n_test", "accuracy", "precision", "recall",
                "f1", "roc_auc", "positive_rate"):
        print(f"{key}: {metrics[key]}")


if __name__ == "__main__":
    main()
