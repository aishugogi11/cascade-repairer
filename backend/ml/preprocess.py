"""Column transformer shared by train and inference.

Airline is one-hot with unknown-ignore so a new Sabre carrier does not
crash scoring. Numerics are median-imputed then scaled.
"""
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

NUMERIC = [
    "dep_hour", "arr_hour", "day_of_week", "month", "stops",
    "duration_minutes", "is_connection", "is_evening_dep", "is_early_dep",
    "origin_hub", "dest_hub",
]
CATEGORICAL = ["airline"]


def build_preprocessor() -> ColumnTransformer:
    numeric = Pipeline([
        ("impute", SimpleImputer(strategy="median")),
        ("scale", StandardScaler()),
    ])
    categorical = Pipeline([
        ("impute", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    return ColumnTransformer(
        [
            ("num", numeric, NUMERIC),
            ("cat", categorical, CATEGORICAL),
        ],
        remainder="drop",
    )
