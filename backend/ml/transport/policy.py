"""Action-selection policy: (trip state + candidate action) → utility.

Synthetic labels use the same transportation DGP as the quality model.
Inference uses a trained forest — never the DGP.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from ml.transport.data import DATASET_DISCLAIMER, dgp_quality_from_row
from ml.transport.features import derived_features

ACTIONS = (
    "KEEP_CURRENT_PLAN",
    "CHANGE_RIDESHARE_PROVIDER",
    "CHANGE_PICKUP_LOCATION",
    "CHANGE_DROPOFF_LOCATION",
    "CHANGE_TRANSPORTATION_MODE",
    "CHANGE_DEPARTURE_TIME",
    "ADD_BUFFER",
    "REORDER_ACTIVITY",
    "REMOVE_UNNECESSARY_STOP",
    "CHANGE_ROUTE",
)

ACTION_NUMERIC: List[str] = [
    "distance_miles",
    "estimated_travel_time",
    "walking_distance",
    "rideshare_eta",
    "traffic_level",
    "pickup_congestion",
    "dropoff_congestion",
    "schedule_buffer",
    "time_of_day",
    "day_of_week",
    "time_until_next_activity",
    "number_of_previous_stops",
    "route_backtracking_distance",
    "delta_travel",
    "delta_walk",
    "delta_eta",
    "delta_congestion",
    "delta_buffer",
    "pickup_is_alt",
    "remaining_stops",
    "min_buffer_needed",
]

ACTION_CATEGORICAL: List[str] = [
    "action_type",
    "transportation_mode",
    "venue_type",
    "priority",
]

ACTION_COLUMNS = ACTION_NUMERIC + ACTION_CATEGORICAL


def action_row(
    current: Dict[str, Any],
    proposed: Dict[str, Any],
    *,
    action_type: str,
    priority: str = "balanced",
    remaining_stops: int = 2,
    min_buffer_needed: float = 0.0,
) -> Dict[str, Any]:
    cur_t = float(current.get("estimated_travel_time") or 20)
    prop_t = float(proposed.get("estimated_travel_time") or cur_t)
    cur_w = float(current.get("walking_distance") or 0.1)
    prop_w = float(proposed.get("walking_distance") or cur_w)
    cur_e = float(current.get("rideshare_eta") or 0)
    prop_e = float(proposed.get("rideshare_eta") or cur_e)
    cur_c = float(current.get("pickup_congestion") or 0.4)
    prop_c = float(proposed.get("pickup_congestion") or cur_c)
    cur_b = float(current.get("schedule_buffer") or 15)
    prop_b = float(proposed.get("schedule_buffer") or cur_b)
    pickup = str(proposed.get("pickup_label") or "")
    return {
        "distance_miles": float(proposed.get("distance_miles") or current.get("distance_miles") or 1.2),
        "estimated_travel_time": prop_t,
        "walking_distance": prop_w,
        "rideshare_eta": prop_e,
        "traffic_level": float(proposed.get("traffic_level") or current.get("traffic_level") or 0.4),
        "pickup_congestion": prop_c,
        "dropoff_congestion": float(proposed.get("dropoff_congestion") or 0.3),
        "schedule_buffer": prop_b,
        "time_of_day": int(proposed.get("time_of_day") or current.get("time_of_day") or 12),
        "day_of_week": int(proposed.get("day_of_week") or 5),
        "time_until_next_activity": float(proposed.get("time_until_next_activity") or 40),
        "number_of_previous_stops": int(proposed.get("number_of_previous_stops") or 0),
        "route_backtracking_distance": float(proposed.get("route_backtracking_distance") or 0),
        "delta_travel": cur_t - prop_t,
        "delta_walk": cur_w - prop_w,
        "delta_eta": cur_e - prop_e,
        "delta_congestion": cur_c - prop_c,
        "delta_buffer": prop_b - cur_b,
        "pickup_is_alt": 1.0 if "alt" in pickup.lower() or "zone" in pickup.lower() or "street" in pickup.lower() else 0.0,
        "remaining_stops": remaining_stops,
        "min_buffer_needed": float(min_buffer_needed or 0),
        "action_type": action_type,
        "transportation_mode": str(proposed.get("transportation_mode") or "uber"),
        "venue_type": str(proposed.get("venue_type") or "other"),
        "priority": priority,
    }


def _mutate(base: Dict[str, Any], **updates) -> Dict[str, Any]:
    row = dict(base)
    row.update(updates)
    derived = derived_features(
        distance_miles=float(row["distance_miles"]),
        road_distance=float(row.get("road_distance") or row["distance_miles"] * 1.2),
        walking_distance=float(row["walking_distance"]),
        estimated_travel_time=float(row["estimated_travel_time"]),
        estimated_cost=float(row.get("estimated_cost") or 0),
        schedule_buffer=float(row["schedule_buffer"]),
    )
    row.update(derived)
    return row


def generate_action_dataset(n_states: int = 3_000, seed: int = 42) -> pd.DataFrame:
    """Each state emits one row per action. Target is action_utility."""
    rng = np.random.default_rng(seed)
    from ml.transport.data import generate_transport_dataset
    hops = generate_transport_dataset(n=n_states, seed=seed)
    rows = []
    for i, hop in hops.iterrows():
        current = hop.to_dict()
        # Default traveler plan: walk if short else uber main entrance.
        if float(current["distance_miles"]) <= 0.7:
            current = _mutate(current, transportation_mode="walk",
                              estimated_cost=0.0, rideshare_eta=0.0,
                              walking_distance=float(current["distance_miles"]),
                              estimated_travel_time=float(current["distance_miles"]) / 3.0 * 60.0)
        else:
            current = _mutate(current, transportation_mode="uber",
                              pickup_label="Main entrance")
        q0 = dgp_quality_from_row(current)
        variants = {
            "KEEP_CURRENT_PLAN": current,
            "CHANGE_RIDESHARE_PROVIDER": _mutate(
                current, transportation_mode="lyft",
                rideshare_eta=max(2.0, float(current["rideshare_eta"]) - 1.2),
                pickup_congestion=max(0.1, float(current["pickup_congestion"]) - 0.06),
                estimated_travel_time=max(4.0, float(current["estimated_travel_time"]) - 1.0),
            ),
            "CHANGE_PICKUP_LOCATION": _mutate(
                current, transportation_mode="uber_alt_pickup",
                pickup_label="Alternate pickup zone",
                walking_distance=0.18,
                rideshare_eta=max(2.0, float(current["rideshare_eta"]) - 4.0),
                pickup_congestion=max(0.1, float(current["pickup_congestion"]) - 0.28),
                estimated_travel_time=max(5.0, float(current["estimated_travel_time"]) - 4.5),
            ),
            "CHANGE_DROPOFF_LOCATION": _mutate(
                current, dropoff_congestion=max(0.1, float(current["dropoff_congestion"]) - 0.18),
                walking_distance=float(current["walking_distance"]) + 0.08,
                estimated_travel_time=max(4.0, float(current["estimated_travel_time"]) - 1.5),
            ),
            "CHANGE_TRANSPORTATION_MODE": _mutate(
                current, transportation_mode="transit",
                estimated_cost=2.9, rideshare_eta=0.0,
                walking_distance=0.22,
                estimated_travel_time=float(current["distance_miles"]) / 11.0 * 60.0 + 8,
            ),
            "CHANGE_DEPARTURE_TIME": _mutate(
                current, schedule_buffer=float(current["schedule_buffer"]) + 10,
                time_until_next_activity=float(current["time_until_next_activity"]) + 10,
            ),
            "ADD_BUFFER": _mutate(
                current, schedule_buffer=float(current["schedule_buffer"]) + 15,
            ),
            "REORDER_ACTIVITY": _mutate(
                current, route_backtracking_distance=max(0.0, float(current["route_backtracking_distance"]) - 1.2),
                estimated_travel_time=max(4.0, float(current["estimated_travel_time"]) - 6.0),
            ),
            "REMOVE_UNNECESSARY_STOP": _mutate(
                current, estimated_travel_time=max(3.0, float(current["estimated_travel_time"]) - 8.0),
                route_backtracking_distance=0.0,
            ),
            "CHANGE_ROUTE": _mutate(
                current, traffic_level=max(0.1, float(current["traffic_level"]) - 0.2),
                estimated_travel_time=max(4.0, float(current["estimated_travel_time"]) - 3.0),
            ),
        }
        priority = str(rng.choice(["balanced", "time", "cost"]))
        remaining = int(current.get("number_of_previous_stops") or 0)
        for action, proposed in variants.items():
            feat = action_row(
                current, proposed, action_type=action, priority=priority,
                remaining_stops=max(1, 5 - remaining),
            )
            util = dgp_quality_from_row(proposed) - q0
            if action == "KEEP_CURRENT_PLAN":
                util = 0.0
            feat["action_utility"] = float(np.clip(util + rng.normal(0, 0.02), -0.5, 0.6))
            feat["state_id"] = int(i)
            rows.append(feat)
    return pd.DataFrame(rows)


def rules_select(current: Dict[str, Any], *, priority: str = "balanced",
                 max_walk_minutes: Optional[int] = None,
                 min_buffer: Optional[int] = None) -> str:
    """Simple baseline — not the ML model."""
    buffer = float(current.get("schedule_buffer") or 20)
    walk_min = float(current.get("walking_distance") or 0) / 3.0 * 60.0
    if current.get("transportation_mode") == "walk":
        walk_min = float(current.get("estimated_travel_time") or walk_min)
    cong = float(current.get("pickup_congestion") or 0)
    traffic = float(current.get("traffic_level") or 0)
    if min_buffer is not None and buffer < min_buffer:
        return "ADD_BUFFER"
    if buffer < 8:
        return "CHANGE_DEPARTURE_TIME"
    if max_walk_minutes is not None and walk_min > max_walk_minutes:
        return "CHANGE_TRANSPORTATION_MODE"
    if walk_min > 18:
        return "CHANGE_TRANSPORTATION_MODE"
    if cong > 0.55:
        return "CHANGE_PICKUP_LOCATION"
    if traffic > 0.7 and priority == "time":
        return "CHANGE_ROUTE"
    if current.get("transportation_mode") == "uber" and priority == "time":
        return "CHANGE_RIDESHARE_PROVIDER"
    return "KEEP_CURRENT_PLAN"
