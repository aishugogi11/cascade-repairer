"""Feature schema for the transportation-quality model.

Each feature exists because it changes how good a hop between two
itinerary stops is — time, money, walking, congestion, reliability, or
schedule fit. Derived ratios keep the model from treating a $12 / 0.4 mi
hop the same as a $12 / 8 mi hop.
"""
from __future__ import annotations

from typing import Any, Dict, List

MODES = ("uber", "lyft", "walk", "transit", "uber_alt_pickup")
VENUE_TYPES = (
    "hotel", "museum", "dining", "concert", "park", "airport", "other",
)

# Raw + derived columns the model sees. Order is the training schema.
NUMERIC: List[str] = [
    "distance_miles",
    "road_distance",
    "walking_distance",
    "estimated_travel_time",
    "estimated_cost",
    "rideshare_eta",
    "time_of_day",
    "day_of_week",
    "traffic_level",
    "pickup_congestion",
    "dropoff_congestion",
    "schedule_buffer",
    "activity_duration",
    "time_until_next_activity",
    "number_of_previous_stops",
    "route_backtracking_distance",
    "cost_per_mile",
    "time_per_mile",
    "buffer_ratio",
    "walking_ratio",
    "route_efficiency",
]

CATEGORICAL: List[str] = [
    "transportation_mode",
    "venue_type",
]

FEATURE_COLUMNS: List[str] = NUMERIC + CATEGORICAL

FEATURE_DOCS: Dict[str, str] = {
    "distance_miles": "Straight-line miles between origin and destination.",
    "road_distance": "Routed road miles (always ≥ crow-flies). Captures detours.",
    "walking_distance": "Miles walked to/from pickup or the whole hop if walking.",
    "estimated_travel_time": "Door-to-door minutes including wait.",
    "estimated_cost": "Traveler-paid dollars for this option.",
    "rideshare_eta": "Minutes until a car arrives. Zero for walk/transit.",
    "time_of_day": "Hour 0–23. Late night changes rideshare vs transit quality.",
    "day_of_week": "0=Mon … 6=Sun. Weekend traffic and transit frequency.",
    "traffic_level": "0–1 congestion on the road, not at the curb.",
    "pickup_congestion": "0–1 curb/wait pain at the pickup spot.",
    "dropoff_congestion": "0–1 curb pain at the drop-off.",
    "schedule_buffer": "Minutes of slack before the next activity starts.",
    "activity_duration": "Minutes the current activity is expected to last.",
    "time_until_next_activity": "Clock gap to the next stop, before travel.",
    "number_of_previous_stops": "How far into the day this hop is (fatigue prior).",
    "route_backtracking_distance": "Extra miles vs a more direct sequence.",
    "transportation_mode": "uber / lyft / walk / transit / uber_alt_pickup.",
    "venue_type": "What the traveler is arriving at (concerts have worse curbs).",
    "cost_per_mile": "Cost divided by distance — expensive short hops look worse.",
    "time_per_mile": "Minutes per mile — a speed/efficiency signal.",
    "buffer_ratio": "Slack relative to travel time. Tight connections hurt.",
    "walking_ratio": "Walk share of the hop. Tiny walks are fine; long ones are not.",
    "route_efficiency": "Crow-flies / road distance. Lower means a wiggly route.",
}

CONSUMER_LABELS: Dict[str, str] = {
    "estimated_travel_time": "travel time",
    "pickup_congestion": "pickup congestion",
    "schedule_buffer": "schedule buffer",
    "walking_distance": "walking distance",
    "estimated_cost": "estimated cost",
    "traffic_level": "traffic",
    "rideshare_eta": "pickup wait",
    "route_efficiency": "route efficiency",
    "buffer_ratio": "buffer vs travel time",
    "walking_ratio": "walking share",
    "dropoff_congestion": "drop-off congestion",
    "route_backtracking_distance": "backtracking",
    "cost_per_mile": "cost per mile",
    "time_per_mile": "time per mile",
    "transportation_mode": "transportation mode",
    "time_of_day": "time of day",
}


def derived_features(
    *,
    distance_miles: float,
    road_distance: float,
    walking_distance: float,
    estimated_travel_time: float,
    estimated_cost: float,
    schedule_buffer: float,
) -> Dict[str, float]:
    dist = max(float(distance_miles), 0.05)
    road = max(float(road_distance), dist)
    travel = max(float(estimated_travel_time), 1.0)
    return {
        "cost_per_mile": float(estimated_cost) / dist,
        "time_per_mile": travel / dist,
        "buffer_ratio": float(schedule_buffer) / travel,
        "walking_ratio": float(walking_distance) / dist,
        "route_efficiency": dist / road,
    }


def row_from_option(option: Dict[str, Any]) -> Dict[str, Any]:
    """Build one model row. Missing fields degrade to conservative defaults."""
    distance = float(option.get("distance_miles") or 1.2)
    road = float(option.get("road_distance") or distance * 1.2)
    walking = float(option.get("walking_distance") or 0.12)
    travel = float(option.get("estimated_travel_time") or 18.0)
    cost = float(option.get("estimated_cost") or 12.0)
    buffer = float(option.get("schedule_buffer") or 20.0)
    derived = derived_features(
        distance_miles=distance,
        road_distance=road,
        walking_distance=walking,
        estimated_travel_time=travel,
        estimated_cost=cost,
        schedule_buffer=buffer,
    )
    mode = str(option.get("transportation_mode") or "uber")
    if mode not in MODES:
        mode = "uber"
    venue = str(option.get("venue_type") or "other")
    if venue not in VENUE_TYPES:
        venue = "other"
    row = {
        "distance_miles": distance,
        "road_distance": road,
        "walking_distance": walking,
        "estimated_travel_time": travel,
        "estimated_cost": cost,
        "rideshare_eta": float(option.get("rideshare_eta") or 0.0),
        "time_of_day": int(option.get("time_of_day") or 12),
        "day_of_week": int(option.get("day_of_week") or 5),
        "traffic_level": float(option.get("traffic_level") or 0.4),
        "pickup_congestion": float(option.get("pickup_congestion") or 0.4),
        "dropoff_congestion": float(option.get("dropoff_congestion") or 0.3),
        "schedule_buffer": buffer,
        "activity_duration": float(option.get("activity_duration") or 90.0),
        "time_until_next_activity": float(
            option.get("time_until_next_activity") or (travel + buffer)
        ),
        "number_of_previous_stops": int(option.get("number_of_previous_stops") or 0),
        "route_backtracking_distance": float(
            option.get("route_backtracking_distance") or 0.0
        ),
        "transportation_mode": mode,
        "venue_type": venue,
        **derived,
    }
    return row
