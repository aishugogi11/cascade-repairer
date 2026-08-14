"""Google Maps as environment data — never the decision-maker.

If GOOGLE_MAPS_API_KEY is set, Directions (and optional Geocoding) are live.
Otherwise we fall back to haversine geometry and label it DEMO — we do not
pretend those numbers came from Google.
"""
from __future__ import annotations

import logging
import math
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional, Sequence, Tuple
from urllib.parse import urlencode

import requests

logger = logging.getLogger(__name__)

_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_LOCK = threading.Lock()
_PREFETCH_WORKERS = 8
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


def directions_url(
    origin: Tuple[float, float],
    dest: Tuple[float, float],
    *,
    mode: str = "walking",
    origin_query: str = "",
    dest_query: str = "",
) -> str:
    """Preset Google Maps Directions link. Place names beat raw pins."""
    travel = MAPS_MODES.get(mode, "walking")
    return "https://www.google.com/maps/dir/?" + urlencode({
        "api": "1",
        "origin": origin_query or f"{origin[0]},{origin[1]}",
        "destination": dest_query or f"{dest[0]},{dest[1]}",
        "travelmode": travel,
    })


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


def _sane_duration_min(duration_min: float, miles: float) -> float:
    """Maps `value` is seconds. If a city hop claims 8+ hours, it was left in seconds."""
    minutes = float(duration_min or 0)
    if minutes > 8 * 60 and miles < 80:
        minutes = minutes / 60.0
    return round(minutes, 1)


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
        "duration_min": _sane_duration_min(duration, miles),
        "traffic_level": traffic,
        "summary": "straight-line geometry (no Google Maps key)",
        "source": "demo_geometry",
        "alternatives": 1,
    }


def _cache_key(
    origin: Tuple[float, float],
    dest: Tuple[float, float],
    travel: str,
) -> str:
    return f"{origin[0]:.4f},{origin[1]:.4f}|{dest[0]:.4f},{dest[1]:.4f}|{travel}"


def prefetch(
    pairs: Sequence[Tuple[Tuple[float, float], Tuple[float, float], int]],
) -> None:
    """Warm the route cache. Live Maps hops are fetched concurrently."""
    if not maps_configured() or not pairs:
        return
    jobs = []
    seen = set()
    for origin, dest, hour in pairs:
        for mode in ("driving", "walk", "transit"):
            key = _cache_key(origin, dest, MAPS_MODES[mode])
            with _CACHE_LOCK:
                cached = key in _CACHE
            if cached or key in seen:
                continue
            seen.add(key)
            jobs.append((origin, dest, mode, hour))
    if not jobs:
        return
    workers = min(_PREFETCH_WORKERS, len(jobs))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda job: route(job[0], job[1], mode=job[2], hour=job[3]), jobs))


def route(
    origin: Tuple[float, float],
    dest: Tuple[float, float],
    *,
    mode: str = "driving",
    hour: int = 12,
) -> Dict[str, Any]:
    key = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
    travel = MAPS_MODES.get(mode, "driving")
    cache_key = _cache_key(origin, dest, travel)
    with _CACHE_LOCK:
        hit = _CACHE.get(cache_key)
    if hit:
        miles = float(hit.get("miles") or haversine_miles(origin, dest))
        hit = dict(hit)
        hit["duration_min"] = _sane_duration_min(hit.get("duration_min") or 0, miles)
        return hit
    if not key:
        out = _demo_route(origin, dest, mode, hour=hour)
        with _CACHE_LOCK:
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
            with _CACHE_LOCK:
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
            "duration_min": _sane_duration_min(seconds / 60.0, meters / 1609.34),
            "traffic_level": 0.7 if "duration_in_traffic" in leg else 0.4,
            "summary": routes[0].get("summary") or "Google Maps route",
            "source": "google_maps",
            "alternatives": len(routes),
        }
        with _CACHE_LOCK:
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
