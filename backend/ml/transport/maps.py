"""Google Maps as environment data — never the decision-maker.

If GOOGLE_MAPS_API_KEY is set, Directions (and optional Geocoding) are live.
Otherwise we fall back to haversine geometry and label it DEMO — we do not
pretend those numbers came from Google.
"""
from __future__ import annotations

import logging
import math
import os
from typing import Any, Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

_CACHE: Dict[str, Dict[str, Any]] = {}
MAPS_MODES = {
    "walk": "walking",
    "walking": "walking",
    "transit": "transit",
    "uber": "driving",
    "lyft": "driving",
    "uber_alt_pickup": "driving",
    "driving": "driving",
}


def maps_configured() -> bool:
    return bool(os.environ.get("GOOGLE_MAPS_API_KEY", "").strip())


def maps_source() -> str:
    return "google_maps" if maps_configured() else "demo_geometry"


def haversine_miles(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    lat1, lon1 = a
    lat2, lon2 = b
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    h = (
        math.sin(dphi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    )
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def _demo_route(
    origin: Tuple[float, float],
    dest: Tuple[float, float],
    mode: str,
    hour: int = 12,
) -> Dict[str, Any]:
    miles = max(0.12, haversine_miles(origin, dest))
    road = miles * (1.08 if mode in ("walk", "walking") else 1.28)
    if mode in ("walk", "walking"):
        duration = miles / 3.0 * 60.0
        traffic = 0.1
    elif mode == "transit":
        duration = miles / 11.0 * 60.0 + 8.0
        traffic = 0.25
    else:
        rush = 0.72 if (7 <= hour <= 9 or 16 <= hour <= 19) else 0.40
        speed = 15.5 * (1.12 - 0.5 * rush)
        duration = miles / max(speed, 2.5) * 60.0
        traffic = rush
    return {
        "miles": round(miles, 3),
        "road_miles": round(road, 3),
        "duration_min": round(duration, 1),
        "traffic_level": traffic,
        "summary": "straight-line geometry (no Google Maps key)",
        "source": "demo_geometry",
        "alternatives": 1,
    }


def route(
    origin: Tuple[float, float],
    dest: Tuple[float, float],
    *,
    mode: str = "driving",
    hour: int = 12,
) -> Dict[str, Any]:
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    travel = MAPS_MODES.get(mode, "driving")
    cache_key = f"{origin[0]:.4f},{origin[1]:.4f}|{dest[0]:.4f},{dest[1]:.4f}|{travel}"
    if cache_key in _CACHE:
        return dict(_CACHE[cache_key])
    if not key:
        out = _demo_route(origin, dest, mode, hour=hour)
        _CACHE[cache_key] = out
        return dict(out)
    try:
        params = {
            "origin": f"{origin[0]},{origin[1]}",
            "destination": f"{dest[0]},{dest[1]}",
            "mode": travel,
            "alternatives": "true",
            "key": key,
        }
        if travel == "driving":
            params["departure_time"] = "now"
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/directions/json",
            params=params,
            timeout=4,
        )
        data = resp.json() if resp.ok else {}
        routes = data.get("routes") or []
        if data.get("status") != "OK" or not routes:
            logger.info("Google Maps directions %s; using geometry", data.get("status"))
            out = _demo_route(origin, dest, mode, hour=hour)
            out["maps_status"] = data.get("status")
            _CACHE[cache_key] = out
            return dict(out)
        leg = routes[0]["legs"][0]
        meters = float(leg["distance"]["value"])
        seconds = float(
            (leg.get("duration_in_traffic") or leg["duration"])["value"]
        )
        out = {
            "miles": round(meters / 1609.34, 3),
            "road_miles": round(meters / 1609.34, 3),
            "duration_min": round(seconds / 60.0, 1),
            "traffic_level": 0.7 if "duration_in_traffic" in leg else 0.4,
            "summary": routes[0].get("summary") or "Google Maps route",
            "source": "google_maps",
            "alternatives": len(routes),
        }
        _CACHE[cache_key] = out
        return dict(out)
    except Exception:  # noqa: BLE001
        logger.exception("Google Maps directions failed")
        return _demo_route(origin, dest, mode, hour=hour)


def geocode_query(query: str) -> Optional[Tuple[float, float]]:
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    if not key or not (query or "").strip():
        return None
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": query, "key": key},
            timeout=4,
        )
        data = resp.json() if resp.ok else {}
        results = data.get("results") or []
        if not results:
            return None
        loc = results[0]["geometry"]["location"]
        return float(loc["lat"]), float(loc["lng"])
    except Exception:  # noqa: BLE001
        logger.exception("Google Maps geocode failed")
        return None
