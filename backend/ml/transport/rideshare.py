"""Rideshare provider interface.

Simulated quotes are labeled `demo_simulated` and must never be shown as
live prices. Live Uber estimates are used only when Uber actually returns them.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple
from urllib.parse import urlencode

import requests

from ml.transport.maps import haversine_miles, route
from ml.transport.parse import geocode, venue_type

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


def _short_name(stop: Dict[str, Any]) -> str:
    text = (stop.get("title") or stop.get("location") or "this stop").strip()
    if "airport transfer" in text.lower():
        airport = re.search(r"\b([A-Z]{3})\b", text)
        if airport:
            return f"{airport.group(1)} Airport"
    for separator in (" — ", " – ", " - "):
        if separator in text:
            text = text.split(separator, 1)[-1]
            break
    return text[:80] or "this stop"


def first_rideshare_pair(
    stops: Sequence[Dict[str, Any]],
) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """First city hop a traveler can actually Uber — skip flights and long-haul."""
    cleaned = [s for s in stops if s]
    for i in range(len(cleaned) - 1):
        origin, dest = cleaned[i], cleaned[i + 1]
        title = (origin.get("title") or origin.get("location") or "").lower()
        if origin.get("kind") == "flight" or "flight" in title:
            continue
        o_type = origin.get("venue_type") or venue_type(origin.get("title") or "")
        d_type = dest.get("venue_type") or venue_type(dest.get("title") or "")
        if o_type == "airport" and d_type == "airport":
            continue
        o, d = _coords(origin), _coords(dest)
        if haversine_miles(o, d) > 50:
            continue
        return origin, dest
    if len(cleaned) >= 2:
        return cleaned[0], cleaned[1]
    return None


def uber_deeplink(
    origin: Tuple[float, float],
    dest: Tuple[float, float],
    *,
    pickup_name: str = "",
    dropoff_name: str = "",
    product_id: str = "",
) -> str:
    """Open Uber's looking screen with this pickup/dropoff so available rides show."""
    pickup = {
        "latitude": round(float(origin[0]), 6),
        "longitude": round(float(origin[1]), 6),
        "addressLine1": (pickup_name or "Pickup")[:80],
    }
    drop = {
        "latitude": round(float(dest[0]), 6),
        "longitude": round(float(dest[1]), 6),
        "addressLine1": (dropoff_name or "Next stop")[:80],
    }
    params: List[Tuple[str, str]] = [
        ("pickup", json.dumps(pickup, separators=(",", ":"))),
        ("drop[0]", json.dumps(drop, separators=(",", ":"))),
    ]
    client = os.environ.get("UBER_CLIENT_ID", "").strip()
    if client:
        params.append(("client_id", client))
    if product_id:
        params.append(("product_id", product_id))
    return "https://m.uber.com/looking?" + urlencode(params)


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
    at = _short_name(origin)
    nxt = _short_name(dest)
    speak = (
        f"You're at the first stop, {at}, as if you're standing there now. "
        f"Next stop is {nxt}. "
        f"Walking is {walk_min:.0f} minutes. "
        f"Driving is {drive_min:.0f} minutes. "
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
            f"The cheapest Uber from the first stop is {cheapest.get('product')}, "
            f"{cheapest.get('estimate')}{eta_bit}."
        )
        extras = [
            q for q in priced[1:3]
            if q.get("product") and q.get("estimate")
        ]
        if extras:
            speak += " Also available: " + ", ".join(
                f"{q['product']} {q['estimate']}" for q in extras
            ) + "."
        speak += " I put a See available Ubers link on the first-stop card."
    else:
        speak += (
            "Use the See available Ubers link to open Uber with this pickup "
            "and dropoff and view the rides currently available."
        )
    return {
        "at": at,
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
        "deeplink": uber_deeplink(
            o, d,
            pickup_name=at,
            dropoff_name=nxt,
        ),
        "speak": speak.strip(),
    }
