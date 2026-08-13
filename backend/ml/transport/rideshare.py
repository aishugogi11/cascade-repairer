"""Rideshare provider interface.

Simulated quotes are labeled `demo_simulated` and must never be shown as
live prices. Live Uber estimates are used only when Uber actually returns them.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Protocol, Tuple

import requests

from ml.transport.maps import route
from ml.transport.parse import geocode

logger = logging.getLogger(__name__)


class RideshareProvider(Protocol):
    name: str
    source: str

    def get_quotes(
        self,
        origin: Tuple[float, float],
        dest: Tuple[float, float],
        *,
        hour: int,
        congestion: float,
        drive_min: float,
        miles: float,
    ) -> List[Dict[str, Any]]:
        ...


class SimulatedRideshare:
    """Internal ETA/congestion model for the action policy — not live quotes."""

    name = "simulated"
    source = "demo_simulated"

    def get_quotes(
        self,
        origin: Tuple[float, float],
        dest: Tuple[float, float],
        *,
        hour: int,
        congestion: float,
        drive_min: float,
        miles: float,
    ) -> List[Dict[str, Any]]:
        eta_uber = 6.0 + 12.0 * congestion
        eta_lyft = 5.5 + 10.0 * max(0.12, congestion - 0.08)
        eta_alt = 3.5 + 4.0 * max(0.12, congestion - 0.32)
        return [
            {
                "provider": "uber",
                "pickup": "Main entrance",
                "dropoff": "Main entrance",
                "eta_min": round(eta_uber, 1),
                "drive_min": round(drive_min, 1),
                "walk_min": 1.4,
                "congestion": congestion,
                "price": None,
                "price_available": False,
                "source": self.source,
            },
            {
                "provider": "lyft",
                "pickup": "Main entrance",
                "dropoff": "Main entrance",
                "eta_min": round(eta_lyft, 1),
                "drive_min": round(drive_min, 1),
                "walk_min": 1.6,
                "congestion": max(0.12, congestion - 0.08),
                "price": None,
                "price_available": False,
                "source": self.source,
            },
            {
                "provider": "uber",
                "pickup": "Alternate pickup zone",
                "dropoff": "Main entrance",
                "eta_min": round(eta_alt, 1),
                "drive_min": round(drive_min, 1),
                "walk_min": 3.6,
                "congestion": max(0.12, congestion - 0.32),
                "price": None,
                "price_available": False,
                "source": self.source,
            },
        ]


def default_provider() -> SimulatedRideshare:
    return SimulatedRideshare()


def _coords(stop: Dict[str, Any]) -> Tuple[float, float]:
    if stop.get("lat") is not None and stop.get("lon") is not None:
        return float(stop["lat"]), float(stop["lon"])
    return geocode(stop.get("title") or stop.get("location") or "")


def uber_deeplink(origin: Tuple[float, float], dest: Tuple[float, float]) -> str:
    return (
        "https://m.uber.com/ul/?action=setPickup"
        f"&pickup[latitude]={origin[0]}&pickup[longitude]={origin[1]}"
        f"&dropoff[latitude]={dest[0]}&dropoff[longitude]={dest[1]}"
    )


def uber_configured() -> bool:
    return bool(
        os.environ.get("UBER_SERVER_TOKEN", "").strip()
        or os.environ.get("UBER_ACCESS_TOKEN", "").strip()
    )


def fetch_uber_live(
    origin: Tuple[float, float],
    dest: Tuple[float, float],
) -> List[Dict[str, Any]]:
    """Live Uber price/time estimates. Empty unless Uber actually responds."""
    server = os.environ.get("UBER_SERVER_TOKEN", "").strip()
    access = os.environ.get("UBER_ACCESS_TOKEN", "").strip()
    token = server or access
    if not token:
        return []
    scheme = "Token" if server else "Bearer"
    headers = {
        "Authorization": f"{scheme} {token}",
        "Accept-Language": "en_US",
    }
    params = {
        "start_latitude": origin[0],
        "start_longitude": origin[1],
        "end_latitude": dest[0],
        "end_longitude": dest[1],
    }
    try:
        price_resp = requests.get(
            "https://api.uber.com/v1.2/estimates/price",
            headers=headers,
            params=params,
            timeout=4,
        )
        time_resp = requests.get(
            "https://api.uber.com/v1.2/estimates/time",
            headers={"Authorization": f"{scheme} {token}", "Accept-Language": "en_US"},
            params={"start_latitude": origin[0], "start_longitude": origin[1]},
            timeout=4,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Uber estimates request failed")
        return []
    if price_resp.status_code >= 400:
        logger.info("Uber price estimates HTTP %s", price_resp.status_code)
        return []
    prices = (price_resp.json() or {}).get("prices") or []
    times = {}
    if time_resp.ok:
        for row in (time_resp.json() or {}).get("times") or []:
            times[str(row.get("product_id") or row.get("display_name") or "")] = row
    out: List[Dict[str, Any]] = []
    for row in prices:
        pid = str(row.get("product_id") or "")
        timed = times.get(pid) or times.get(str(row.get("display_name") or "")) or {}
        eta_sec = timed.get("estimate")
        low = row.get("low_estimate")
        high = row.get("high_estimate")
        has_price = low is not None or bool(row.get("estimate"))
        out.append({
            "provider": "uber",
            "product": row.get("localized_display_name") or row.get("display_name") or "Uber",
            "product_id": pid,
            "estimate": row.get("estimate"),
            "low": float(low) if low is not None else None,
            "high": float(high) if high is not None else None,
            "currency": row.get("currency_code") or "USD",
            "eta_min": round(float(eta_sec) / 60.0, 1) if eta_sec else None,
            "trip_min": round(float(row["duration"]) / 60.0, 1) if row.get("duration") else None,
            "miles": float(row["distance"]) if row.get("distance") is not None else None,
            "price_available": bool(has_price),
            "source": "uber_live",
        })
    priced = [q for q in out if q.get("low") is not None]
    priced.sort(key=lambda q: (q["low"], q.get("eta_min") or 99))
    rest = [q for q in out if q.get("low") is None]
    return priced + rest


def build_here_now(
    origin: Dict[str, Any],
    dest: Dict[str, Any],
    *,
    max_walk_minutes: Optional[int] = None,
) -> Dict[str, Any]:
    """Live first-stop context: person is standing at origin, heading to dest."""
    o = _coords(origin)
    d = _coords(dest)
    walk = route(o, d, mode="walk")
    drive = route(o, d, mode="driving")
    quotes = fetch_uber_live(o, d)
    priced = [
        q for q in quotes
        if q.get("price_available") and q.get("low") is not None
    ]
    priced.sort(key=lambda q: (float(q["low"]), q.get("eta_min") or 99))
    cheapest = priced[0] if priced else (quotes[0] if quotes else None)
    walk_min = float(walk.get("duration_min") or 0)
    drive_min = float(drive.get("duration_min") or 0)
    over_walk = max_walk_minutes is not None and walk_min > max_walk_minutes + 0.5
    speak = (
        f"You're at {origin.get('title')}, as if you're standing there now. "
        f"Next stop is {dest.get('title')}. "
        f"Walking is {walk_min:.0f} minutes ({walk.get('source')}). "
        f"Driving is {drive_min:.0f} minutes ({drive.get('source')}). "
    )
    if over_walk:
        speak += (
            f"That's over your {max_walk_minutes}-minute walk cap, "
            "so rideshare is the move from this curb. "
        )
    if cheapest and cheapest.get("price_available") and cheapest.get("estimate"):
        eta = cheapest.get("eta_min")
        eta_bit = f", about {eta:.0f} minutes away" if eta else ""
        speak += (
            f"The cheapest live Uber from here is {cheapest.get('product')}, "
            f"{cheapest.get('estimate')}{eta_bit}."
        )
    elif cheapest and cheapest.get("product") and not cheapest.get("price_available"):
        speak += f"Uber offered {cheapest.get('product')} but did not return a fare."
    else:
        speak += (
            "I don't have a live Uber fare for this curb. "
            "Open Uber from this pin to see the cheapest product right now."
        )
    return {
        "at": origin.get("title"),
        "next": dest.get("title"),
        "at_time": origin.get("start_time"),
        "origin": {"lat": o[0], "lon": o[1]},
        "destination": {"lat": d[0], "lon": d[1]},
        "walk_min": round(walk_min, 1),
        "drive_min": round(drive_min, 1),
        "maps_source": drive.get("source") or walk.get("source"),
        "max_walk_minutes": max_walk_minutes,
        "over_walk_cap": over_walk,
        "uber_quotes": quotes,
        "cheapest": cheapest,
        "uber_source": "uber_live" if quotes else "uber_unavailable",
        "deeplink": uber_deeplink(o, d),
        "speak": speak.strip(),
    }
