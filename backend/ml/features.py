"""Shared feature schema for training and inference.

Numeric + binary columns are model inputs. Categorical airline is one-hot
encoded in preprocess.py. Airport identity is collapsed to a hub-pressure
flag so the model does not one-hot hundreds of IATA codes.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional

# BTS On-Time Performance consistently shows higher delay rates at a small
# set of congested US hubs. Used as a binary prior, not a live lookup.
HUB_AIRPORTS = {
    "ATL", "ORD", "DFW", "DEN", "CLT", "LAX", "IAH", "PHX", "SEA",
    "SFO", "EWR", "JFK", "LGA", "BOS", "MIA", "PHL", "DTW",
}

FEATURE_COLUMNS: List[str] = [
    "dep_hour",
    "arr_hour",
    "day_of_week",
    "month",
    "stops",
    "duration_minutes",
    "is_connection",
    "is_evening_dep",
    "is_early_dep",
    "origin_hub",
    "dest_hub",
    "airline",
]

CONSUMER_FACTORS = {
    "stops": "has a connection",
    "is_connection": "has a connection",
    "is_evening_dep": "evening departure",
    "is_early_dep": "very early departure",
    "origin_hub": "busy origin airport",
    "dest_hub": "busy destination airport",
    "duration_minutes": "longer scheduled time",
    "dep_hour": "departure time of day",
}


def _hour(clock: str) -> int:
    """'08:00', '8:00', or '08:00:00-05:00' → 8. Missing/garbage → 12."""
    if not clock:
        return 12
    try:
        return int(str(clock).strip()[:2].replace(":", "") or 12)
    except (TypeError, ValueError):
        return 12


def _parse_date(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def features_from_values(
    *,
    depart_time: str,
    arrive_time: str,
    depart_date: str,
    airline: str,
    origin: str,
    destination: str,
    stops: int,
    duration_minutes: int,
) -> Dict[str, Any]:
    """One row of model features. Unknown/missing fields degrade to
    conservative defaults — never raise, so a voice turn cannot die on a
    half-parsed Sabre itinerary."""
    dep_hour = _hour(depart_time)
    arr_hour = _hour(arrive_time)
    parsed = _parse_date(depart_date)
    stops_n = max(0, int(stops or 0))
    duration = int(duration_minutes or 0)
    if duration <= 0:
        # Typical US domestic block when Sabre omitted ElapsedTime.
        duration = 180 + 90 * stops_n
    origin_code = (origin or "").strip().upper()
    dest_code = (destination or "").strip().upper()
    carrier = (airline or "UNK").strip().upper() or "UNK"
    return {
        "dep_hour": dep_hour,
        "arr_hour": arr_hour,
        "day_of_week": parsed.weekday() if parsed else 3,
        "month": parsed.month if parsed else 7,
        "stops": stops_n,
        "duration_minutes": duration,
        "is_connection": int(stops_n > 0),
        "is_evening_dep": int(dep_hour >= 17),
        "is_early_dep": int(dep_hour < 7),
        "origin_hub": int(origin_code in HUB_AIRPORTS),
        "dest_hub": int(dest_code in HUB_AIRPORTS),
        "airline": carrier,
    }


def features_from_option(option: Any) -> Dict[str, Any]:
    """FlightOption (or any duck-typed option) → feature dict."""
    return features_from_values(
        depart_time=getattr(option, "depart_time", "") or "",
        arrive_time=getattr(option, "arrive_time", "") or "",
        depart_date=getattr(option, "depart_date", "") or "",
        airline=getattr(option, "airline", "") or "",
        origin=getattr(option, "origin", "") or "",
        destination=getattr(option, "destination", "") or "",
        stops=getattr(option, "stops", 0) or 0,
        duration_minutes=getattr(option, "duration_minutes", 0) or 0,
    )
