"""Synthetic transportation-quality labels with a documented data-generating process.

Real labeled "how good was this Uber vs walking" outcomes are not in this
repo. Rows are generated from realistic urban travel relationships
(distance, traffic, curb congestion, mode, schedule buffer) plus noise.

This is NOT real-world labeled data. The architecture is designed to be
retrained on actual trip outcomes (completed-ride ratings, on-time
arrival, realized walk/wait) when those labels exist.

`python -m ml.transport.train --csv path.csv` can ingest a real file with
the same column names, including `transportation_quality_score`.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from ml.transport.features import (
    FEATURE_COLUMNS,
    MODES,
    VENUE_TYPES,
    derived_features,
)

_RNG_SEED = 42

DATASET_DISCLAIMER = (
    "Initial model trained on a synthetic transportation dataset designed "
    "around realistic travel constraints. The architecture is designed to "
    "be retrained on real-world trip outcomes."
)


def _quality_from_arrays(
    *,
    mode: np.ndarray,
    distance: np.ndarray,
    travel: np.ndarray,
    cost: np.ndarray,
    walking: np.ndarray,
    eta: np.ndarray,
    hour: np.ndarray,
    traffic: np.ndarray,
    pickup: np.ndarray,
    dropoff: np.ndarray,
    buffer: np.ndarray,
    backtrack: np.ndarray,
    route_eff: np.ndarray,
    venue: np.ndarray,
) -> np.ndarray:
    """Nonlinear target. Interactions are why a forest should beat linear."""
    walk = (mode == "walk").astype(float)
    transit = (mode == "transit").astype(float)
    rideshare = np.isin(mode, ["uber", "lyft", "uber_alt_pickup"]).astype(float)
    alt = (mode == "uber_alt_pickup").astype(float)
    lyft = (mode == "lyft").astype(float)
    concert = (venue == "concert").astype(float)
    late = ((hour >= 22) | (hour < 6)).astype(float)
    midday = ((hour >= 9) & (hour <= 19)).astype(float)
    short = (distance < 0.55).astype(float)
    long_walk = (walking > 0.45).astype(float)

    q = np.full(distance.shape, 0.58, dtype=float)
    q -= 0.16 * np.minimum(travel / 40.0, 1.25)
    q -= 0.10 * np.maximum(travel - 22.0, 0.0) / 25.0
    q -= 0.11 * np.minimum(cost / 32.0, 1.4)
    q -= 0.28 * (walking / np.maximum(distance, 0.15)) ** 2
    q += 0.10 * walk * short
    q -= 0.18 * walk * (distance > 1.1).astype(float)
    q -= 0.12 * long_walk
    q -= 0.24 * pickup * traffic * rideshare
    q += 0.16 * alt * pickup
    q -= 0.07 * eta / 12.0 * rideshare
    q -= 0.18 * transit * late
    q += 0.09 * transit * midday * (distance > 1.4).astype(float)
    q += 0.08 * np.clip(buffer / np.maximum(travel, 1.0), 0.0, 1.4)
    q -= 0.17 * (buffer < 8).astype(float)
    q += 0.07 * route_eff
    q -= 0.09 * np.minimum(backtrack / 2.0, 1.2)
    q -= 0.08 * dropoff * concert
    q += 0.03 * lyft  # slightly easier pickup in the DGP, not a brand claim
    return q


def dgp_quality_from_row(row: dict) -> float:
    """Same DGP as training labels — used to label action utility, not inference."""
    import numpy as np
    q = _quality_from_arrays(
        mode=np.array([str(row.get("transportation_mode") or "uber")]),
        distance=np.array([float(row.get("distance_miles") or 1.2)]),
        travel=np.array([float(row.get("estimated_travel_time") or 18.0)]),
        cost=np.array([float(row.get("estimated_cost") or 12.0)]),
        walking=np.array([float(row.get("walking_distance") or 0.12)]),
        eta=np.array([float(row.get("rideshare_eta") or 0.0)]),
        hour=np.array([int(row.get("time_of_day") or 12)]),
        traffic=np.array([float(row.get("traffic_level") or 0.4)]),
        pickup=np.array([float(row.get("pickup_congestion") or 0.4)]),
        dropoff=np.array([float(row.get("dropoff_congestion") or 0.3)]),
        buffer=np.array([float(row.get("schedule_buffer") or 20.0)]),
        backtrack=np.array([float(row.get("route_backtracking_distance") or 0.0)]),
        route_eff=np.array([float(row.get("route_efficiency") or 0.8)]),
        venue=np.array([str(row.get("venue_type") or "other")]),
    )[0]
    return float(np.clip(q, 0.03, 0.97))


def generate_transport_dataset(n: int = 12_000, seed: int = _RNG_SEED) -> pd.DataFrame:
    """n labeled hops. Target is transportation_quality_score in (0, 1)."""
    rng = np.random.default_rng(seed)
    mode = rng.choice(np.array(MODES), size=n)
    venue = rng.choice(np.array(VENUE_TYPES), size=n, p=[
        0.12, 0.18, 0.18, 0.12, 0.12, 0.08, 0.20,
    ])
    distance = np.clip(rng.lognormal(mean=0.15, sigma=0.75, size=n), 0.15, 14.0)
    road = distance * rng.uniform(1.05, 1.55, size=n)
    hour = rng.integers(6, 24, size=n)
    dow = rng.integers(0, 7, size=n)
    rush = ((hour >= 7) & (hour <= 9) | (hour >= 16) & (hour <= 19)).astype(float)
    traffic = np.clip(0.18 + 0.45 * rush + rng.normal(0, 0.12, n), 0.05, 0.98)
    pickup = np.clip(rng.beta(2.0, 3.2, size=n) + 0.15 * (venue == "concert"), 0.05, 0.98)
    dropoff = np.clip(rng.beta(2.2, 3.4, size=n), 0.05, 0.95)

    walking = np.where(
        mode == "walk",
        distance,
        np.where(
            mode == "uber_alt_pickup",
            rng.uniform(0.18, 0.38, size=n),
            rng.uniform(0.04, 0.22, size=n),
        ),
    )
    walking = np.where(mode == "transit", rng.uniform(0.12, 0.45, size=n), walking)

    speed_mph = np.where(
        mode == "walk",
        3.0,
        np.where(mode == "transit", 11.0, 16.0 * (1.15 - 0.55 * traffic)),
    )
    eta = np.where(
        np.isin(mode, ["uber", "lyft", "uber_alt_pickup"]),
        np.clip(rng.normal(6.5, 2.4, n) + 4.0 * pickup, 2.0, 18.0),
        0.0,
    )
    wait = np.where(mode == "transit", rng.uniform(4.0, 14.0, n), eta)
    travel = walking / 3.0 * 60.0 + distance / np.maximum(speed_mph, 2.5) * 60.0 + wait
    travel = np.where(mode == "walk", distance / 3.0 * 60.0, travel)
    travel = np.clip(travel, 3.0, 120.0)

    cost = np.zeros(n)
    cost = np.where(mode == "walk", 0.0, cost)
    cost = np.where(mode == "transit", 2.9, cost)
    fare = 3.8 + 2.15 * road + 4.5 * traffic
    cost = np.where(np.isin(mode, ["uber", "lyft"]), fare, cost)
    cost = np.where(mode == "uber_alt_pickup", fare * 0.94, cost)
    cost = np.where(mode == "lyft", fare * 0.97, cost)

    gap = rng.uniform(25.0, 140.0, size=n)
    buffer = np.clip(gap - travel, -5.0, 90.0)
    duration = rng.uniform(40.0, 150.0, size=n)
    prev_stops = rng.integers(0, 6, size=n)
    backtrack = rng.choice([0.0, 0.0, 0.0, 0.4, 1.1, 2.2], size=n)

    route_eff = distance / np.maximum(road, 0.1)
    quality = _quality_from_arrays(
        mode=mode,
        distance=distance,
        travel=travel,
        cost=cost,
        walking=walking,
        eta=eta,
        hour=hour,
        traffic=traffic,
        pickup=pickup,
        dropoff=dropoff,
        buffer=buffer,
        backtrack=backtrack,
        route_eff=route_eff,
        venue=venue,
    )
    quality = np.clip(quality + rng.normal(0.0, 0.045, n), 0.03, 0.97)

    rows = []
    for i in range(n):
        derived = derived_features(
            distance_miles=float(distance[i]),
            road_distance=float(road[i]),
            walking_distance=float(walking[i]),
            estimated_travel_time=float(travel[i]),
            estimated_cost=float(cost[i]),
            schedule_buffer=float(buffer[i]),
        )
        rows.append({
            "distance_miles": float(distance[i]),
            "road_distance": float(road[i]),
            "walking_distance": float(walking[i]),
            "estimated_travel_time": float(travel[i]),
            "estimated_cost": float(cost[i]),
            "rideshare_eta": float(eta[i]),
            "time_of_day": int(hour[i]),
            "day_of_week": int(dow[i]),
            "traffic_level": float(traffic[i]),
            "pickup_congestion": float(pickup[i]),
            "dropoff_congestion": float(dropoff[i]),
            "schedule_buffer": float(buffer[i]),
            "activity_duration": float(duration[i]),
            "time_until_next_activity": float(gap[i]),
            "number_of_previous_stops": int(prev_stops[i]),
            "route_backtracking_distance": float(backtrack[i]),
            "transportation_mode": str(mode[i]),
            "venue_type": str(venue[i]),
            **derived,
            "transportation_quality_score": float(quality[i]),
        })
    return pd.DataFrame(rows)


def dataset(csv_path: Optional[str] = None, n: int = 12_000, seed: int = _RNG_SEED) -> pd.DataFrame:
    if csv_path:
        frame = pd.read_csv(csv_path)
        missing = [c for c in FEATURE_COLUMNS + ["transportation_quality_score"] if c not in frame.columns]
        if missing:
            raise ValueError(f"CSV missing columns: {missing}")
        return frame
    return generate_transport_dataset(n=n, seed=seed)
