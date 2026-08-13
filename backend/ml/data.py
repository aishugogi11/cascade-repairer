"""BTS-calibrated synthetic flight-delay rows.

Public BTS On-Time Performance files are large and not hermetic for CI, so
training data is generated from published delay patterns (national ~18% of
flights delayed ≥15 minutes; evening banks, connections, and congested hubs
run hotter; Delta/Alaska typically better than Ultra-LCCs). `train.py` can
also ingest a real CSV with the same column names if one is supplied.
"""
from typing import List, Optional

import numpy as np
import pandas as pd

from ml.features import FEATURE_COLUMNS, HUB_AIRPORTS

AIRLINES = ["AA", "DL", "UA", "B6", "WN", "AS", "NK", "F9", "HA", "G4"]
AIRPORTS = sorted(HUB_AIRPORTS | {"MSP", "SAN", "AUS", "RDU", "PDX", "SLC"})

# Carrier intercepts on the log-odds of a ≥15 min arrival delay, centered
# so the mixed population lands near the BTS national rate.
_AIRLINE_LOGIT = {
    "DL": -0.35, "AS": -0.30, "HA": -0.25, "AA": -0.05, "UA": 0.00,
    "WN": 0.10, "B6": 0.20, "F9": 0.45, "NK": 0.55, "G4": 0.40,
}

_RNG_SEED = 42


def _logit_to_prob(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(z, -12, 12)))


def generate_delay_dataset(n: int = 12_000, seed: int = _RNG_SEED) -> pd.DataFrame:
    """n labeled flights. Target `delayed_15` is 1 when arrival delay ≥ 15
    minutes — the BTS On-Time definition."""
    rng = np.random.default_rng(seed)
    dep_hour = rng.integers(5, 23, size=n)
    block = rng.integers(70, 380, size=n)
    arr_hour = (dep_hour + np.maximum(1, block // 60)) % 24
    day_of_week = rng.integers(0, 7, size=n)
    month = rng.integers(1, 13, size=n)
    stops = rng.choice([0, 0, 0, 1, 1, 2], size=n)
    airline = rng.choice(AIRLINES, size=n)
    origin = rng.choice(AIRPORTS, size=n)
    dest = rng.choice(AIRPORTS, size=n)

    airline_z = np.array([_AIRLINE_LOGIT[a] for a in airline])
    evening = (dep_hour >= 17).astype(float)
    early = (dep_hour < 7).astype(float)
    winter = np.isin(month, [12, 1, 2]).astype(float)
    origin_hub = np.isin(origin, list(HUB_AIRPORTS)).astype(float)
    dest_hub = np.isin(dest, list(HUB_AIRPORTS)).astype(float)

    # Intercept chosen so mean P(delay) ≈ 0.18 (BTS national rate).
    z = (
        -3.15
        + airline_z
        + 1.15 * stops
        + 0.70 * evening
        - 0.25 * early
        + 0.40 * winter
        + 0.50 * origin_hub
        + 0.30 * dest_hub
        + 0.15 * ((day_of_week >= 4).astype(float))  # Fri–Sun
        + 0.002 * (block - 180)
    )
    delayed = rng.binomial(1, _logit_to_prob(z))

    frame = pd.DataFrame({
        "dep_hour": dep_hour,
        "arr_hour": arr_hour,
        "day_of_week": day_of_week,
        "month": month,
        "stops": stops,
        "duration_minutes": block,
        "is_connection": (stops > 0).astype(int),
        "is_evening_dep": evening.astype(int),
        "is_early_dep": early.astype(int),
        "origin_hub": origin_hub.astype(int),
        "dest_hub": dest_hub.astype(int),
        "airline": airline,
        "origin": origin,
        "destination": dest,
        "delayed_15": delayed,
    })
    return frame


def load_csv(path: str) -> pd.DataFrame:
    """Optional real-data path. Requires `delayed_15` plus FEATURE_COLUMNS."""
    frame = pd.read_csv(path)
    missing = [c for c in FEATURE_COLUMNS + ["delayed_15"] if c not in frame.columns]
    if missing:
        raise ValueError(f"delay CSV missing columns: {missing}")
    return frame


def dataset(csv_path: Optional[str] = None, n: int = 12_000) -> pd.DataFrame:
    if csv_path:
        return load_csv(csv_path)
    return generate_delay_dataset(n=n)
