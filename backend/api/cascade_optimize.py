"""Cascade itinerary optimization — recommendations on the existing trip.

Uses the existing itinerary items and the existing transport scorer
(ml.transport.optimize). The LLM does not pick the winner. Changes are
never applied until the traveler accepts.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from api import memory_trips
from api.optimize import parse_prefs
from api.repositories import itinerary_items
from api.repositories.models import ItineraryItem
from ml.transport.maps import maps_source
from ml.transport.optimize import (
    Prefs,
    optimize_stops,
)
from ml.transport.parse import alt_pickup_label, geocode, is_anchored, venue_type
from ml.transport.rideshare import default_provider

logger = logging.getLogger(__name__)

# User-facing weight profiles. The scorer still uses PRIORITY_WEIGHTS in
# ml.transport.optimize; these are the explainable TIME/COST/BALANCED knobs.
WEIGHT_PROFILES = {
    "time": {
        "time_weight": 0.55,
        "cost_weight": 0.20,
        "convenience_weight": 0.15,
        "schedule_weight": 0.10,
    },
    "cost": {
        "time_weight": 0.20,
        "cost_weight": 0.55,
        "convenience_weight": 0.15,
        "schedule_weight": 0.10,
    },
    "walk": {
        "time_weight": 0.25,
        "cost_weight": 0.25,
        "convenience_weight": 0.40,
        "schedule_weight": 0.10,
    },
    "balanced": {
        "time_weight": 0.35,
        "cost_weight": 0.35,
        "convenience_weight": 0.20,
        "schedule_weight": 0.10,
    },
}

_ANALYSES: Dict[str, Dict[str, Any]] = {}
_PREFS: Dict[str, Prefs] = {}
_REJECTED: Dict[str, set] = {}
_FEEDBACK: List[Dict[str, Any]] = []


def clear() -> None:
    _ANALYSES.clear()
    _PREFS.clear()
    _REJECTED.clear()
    _FEEDBACK.clear()


def prefs_for(trip_id: str) -> Prefs:
    return _PREFS.get(trip_id) or Prefs(priority="balanced")


def set_prefs(trip_id: str, prefs: Prefs) -> Prefs:
    _PREFS[trip_id] = prefs
    return prefs


def merge_pref_text(trip_id: str, text: str) -> Prefs:
    prefs = parse_prefs(text, prefs_for(trip_id))
    return set_prefs(trip_id, prefs)


def cached(trip_id: str) -> Optional[Dict[str, Any]]:
    return _ANALYSES.get(trip_id)


def feedback_log() -> List[Dict[str, Any]]:
    return list(_FEEDBACK)


def _clock(ts: Optional[datetime]) -> str:
    if ts is None:
        return "12:00"
    local = ts.astimezone() if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    return f"{local.hour:02d}:{local.minute:02d}"


def _day_offset(first: Optional[datetime], ts: Optional[datetime]) -> int:
    if first is None or ts is None:
        return 0
    a = first.date() if hasattr(first, "date") else first
    b = ts.date() if hasattr(ts, "date") else ts
    try:
        return max(0, (b - a).days)
    except TypeError:
        return 0


def _title_of(item: ItineraryItem) -> str:
    details = item.details or {}
    return (details.get("title") or item.location or item.type or "stop").strip()


def _location_of(item: ItineraryItem) -> str:
    if item.type == "flight" and item.location and "-" in item.location:
        return item.location.split("-", 1)[1].strip()
    return (item.location or _title_of(item)).strip()


def items_to_stops(items: Sequence[ItineraryItem]) -> List[Dict[str, Any]]:
    """Project the existing Cascade itinerary into transport stops."""
    ordered = sorted(
        items,
        key=lambda i: i.start_ts or datetime.min.replace(tzinfo=timezone.utc),
    )
    first_ts = next((i.start_ts for i in ordered if i.start_ts), None)
    stops: List[Dict[str, Any]] = []
    for item in ordered:
        title = _title_of(item)
        loc = _location_of(item)
        if item.type == "hotel":
            title = f"Hotel — {loc}" if loc else "Hotel"
        if item.type == "flight":
            title = f"Flight arrival — {loc}" if loc else title
        lat, lon = geocode(f"{title} {loc}")
        details = item.details or {}
        anchored = (
            item.type in ("flight", "hotel")
            or bool(details.get("must_keep"))
            or details.get("importance") == "must_keep"
            or is_anchored(title)
            or is_anchored(loc)
        )
        start = item.start_ts
        end = item.end_ts
        duration_min = 90
        if start and end:
            duration_min = max(15, int((end - start).total_seconds() / 60))
        stops.append({
            "item_id": item.item_id,
            "item_type": item.type,
            "title": title,
            "location": loc,
            "start_time": _clock(start),
            "end_time": _clock(end) if end else None,
            "day": _day_offset(first_ts, start),
            "lat": lat,
            "lon": lon,
            "venue_type": venue_type(title) or venue_type(loc),
            "anchored": anchored,
            "flexible": (not anchored) and details.get("flexibility") != "none",
            "pickup_label": "Main entrance",
            "alt_pickup_label": alt_pickup_label(title) or alt_pickup_label(loc),
            "activity_duration": duration_min,
        })
    return stops


def _short(title: str) -> str:
    text = (title or "").strip()
    if " — " in text:
        text = text.split(" — ", 1)[-1]
    if text.lower().startswith("flight arrival"):
        text = text.replace("Flight arrival — ", "").replace("Flight arrival ", "")
    return text or "this stop"


def _fingerprint(rec: Dict[str, Any]) -> str:
    key = "|".join([
        str(rec.get("type") or ""),
        ",".join(rec.get("current_titles") or []),
        ",".join(rec.get("recommended_titles") or []),
        str(rec.get("from_mode") or ""),
        str(rec.get("to_mode") or ""),
        str(rec.get("hop") or ""),
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _cost_label(value: Optional[float], estimated: bool) -> Optional[str]:
    if value is None:
        return None
    prefix = "~$" if estimated else "$"
    return f"{prefix}{value:.0f}" if abs(value - round(value)) < 0.05 else f"{prefix}{value:.2f}"


def _three_ways(ranked: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    feasible = [c for c in ranked if c.get("feasible") is not False]
    pool = feasible or list(ranked)
    if not pool:
        return {}
    estimated = any(
        (c.get("rideshare_source") or "") != "live" or not c.get("price_available")
        for c in pool
    )
    cheapest = min(pool, key=lambda c: float(c.get("estimated_cost") or 0))
    fastest = min(pool, key=lambda c: float(c.get("estimated_travel_time") or 999))
    best_value = max(pool, key=lambda c: float(c.get("final_score") or c.get("ml_score") or 0))

    def pack(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "mode": row.get("transportation_mode"),
            "label": row.get("label"),
            "travel_time": row.get("estimated_travel_time"),
            "cost": row.get("estimated_cost"),
            "cost_label": _cost_label(row.get("estimated_cost"), estimated),
            "walking_minutes": round(
                float(row.get("walking_distance") or 0) / 3.0 * 60.0, 1
            ),
            "distance": row.get("distance_miles"),
            "transfers": 1 if row.get("transportation_mode") == "transit" else 0,
            "schedule_buffer": row.get("schedule_buffer"),
            "estimated": estimated,
        }

    return {
        "cheapest": pack(cheapest),
        "fastest": pack(fastest),
        "best_value": pack(best_value),
        "cascade_pick": pack(best_value),
        "estimated": estimated,
    }


def _primary_factor(rec: Dict[str, Any], current: Dict[str, Any], prefs: Prefs) -> Tuple[str, str, str]:
    dt = float(current.get("estimated_travel_time") or 0) - float(rec.get("estimated_travel_time") or 0)
    dc = float(current.get("estimated_cost") or 0) - float(rec.get("estimated_cost") or 0)
    if prefs.priority == "cost" and abs(dc) >= 0.5:
        primary = "cost"
        secondary = "travel_time" if abs(dt) >= 1 else "convenience"
    elif abs(dt) >= abs(dc) * 2 or prefs.priority == "time":
        primary = "travel_time"
        secondary = "cost" if abs(dc) >= 0.5 else "schedule"
    else:
        primary = "cost" if abs(dc) >= 0.5 else "convenience"
        secondary = "travel_time"
    if dc < -0.4 and dt > 0.4:
        tradeoff = f"Costs about ${abs(dc):.0f} more but saves about {dt:.0f} minutes"
    elif dc > 0.4 and dt < -0.4:
        tradeoff = f"Saves about ${dc:.0f} but takes about {abs(dt):.0f} more minutes"
    elif dt > 0.4:
        tradeoff = f"Saves about {dt:.0f} minutes"
    elif dc > 0.4:
        tradeoff = f"Saves about ${dc:.0f}"
    else:
        tradeoff = "Closer match to your preferences"
    return primary, secondary, tradeoff


def _transport_rec(
    hop: int,
    transition: Dict[str, Any],
    prefs: Prefs,
    *,
    rec_type: str,
) -> Dict[str, Any]:
    current = transition.get("current") or {}
    recommended = transition.get("recommended") or {}
    ranked = transition.get("ranked") or []
    trio = _three_ways(ranked)
    pick = trio.get("cascade_pick") or {}
    primary, secondary, tradeoff = _primary_factor(recommended, current, prefs)
    dt = float(current.get("estimated_travel_time") or 0) - float(recommended.get("estimated_travel_time") or 0)
    dc = float(current.get("estimated_cost") or 0) - float(recommended.get("estimated_cost") or 0)
    estimated = bool(trio.get("estimated"))
    origin = _short(transition.get("from_title") or "")
    dest = _short(transition.get("to_title") or "")
    title = {
        "cheaper_transportation": "Cheaper way between stops",
        "faster_transportation": "Faster way between stops",
        "airport_transfer": "Better airport transfer",
        "better_value_transportation": "Better-value ride",
    }.get(rec_type, "Better transportation")
    rec = {
        "id": str(uuid.uuid4()),
        "type": rec_type,
        "title": title,
        "recommendation": (
            f"Take {pick.get('label') or recommended.get('label') or 'the recommended option'} "
            f"from {origin} to {dest}"
        ),
        "time_saved_minutes": round(max(0.0, dt)) if dt > 0.4 else None,
        "estimated_cost_saved": round(max(0.0, dc), 2) if dc > 0.4 else None,
        "cost_is_estimated": estimated,
        "reason": (transition.get("why") or ["Better fit for your preferences"])[0],
        "confidence": min(0.92, 0.62 + abs(float(recommended.get("final_score") or 0.2)) * 0.2),
        "current_titles": [origin, dest],
        "recommended_titles": [origin, dest],
        "from_mode": current.get("label"),
        "to_mode": recommended.get("label"),
        "hop": hop,
        "transport_options": trio,
        "map": {
            "current": {
                "from": origin,
                "to": dest,
                "minutes": current.get("estimated_travel_time"),
                "miles": current.get("distance_miles"),
                "mode": current.get("label"),
            },
            "recommended": {
                "from": origin,
                "to": dest,
                "minutes": recommended.get("estimated_travel_time"),
                "miles": recommended.get("distance_miles"),
                "mode": recommended.get("label"),
            },
            "source": current.get("route_source") or maps_source(),
        },
        "explanation": {
            "selected_option": recommended.get("label"),
            "alternatives": [
                r.get("label") for r in ranked[:4]
                if r.get("label") != recommended.get("label")
            ],
            "primary_factor": primary,
            "secondary_factor": secondary,
            "tradeoff": tradeoff,
            "time_difference": round(dt, 1),
            "cost_difference": round(dc, 2),
            "user_preference": prefs.priority,
            "schedule_constraints": {
                "min_buffer": prefs.min_buffer,
                "max_walk_minutes": prefs.max_walk_minutes,
            },
        },
        "item_ids": [],
    }
    rec["fingerprint"] = _fingerprint(rec)
    return rec


def _reorder_rec(reorder: Dict[str, Any], result: Dict[str, Any], prefs: Prefs) -> Dict[str, Any]:
    current = [_short(t) for t in (reorder.get("current_titles") or [])]
    recommended = [_short(t) for t in (reorder.get("recommended_titles") or [])]
    intel = result.get("intelligence") or {}
    miles = float(reorder.get("miles_saved") or 0)
    time_saved = intel.get("travel_time_saved_min")
    if time_saved is None and miles:
        time_saved = round(miles / 12.0 * 60.0)
    orig_stops = result.get("original_stops") or []
    opt_stops = reorder.get("stops") or result.get("optimized_stops") or []
    orig_legs = max(0, len(orig_stops) - 1)
    opt_legs = max(0, len(opt_stops) - 1)
    legs_removed = max(0, orig_legs - opt_legs)
    rec = {
        "id": str(uuid.uuid4()),
        "type": "route_optimization",
        "title": "Reduce afternoon backtracking",
        "recommendation": (
            "Visit " + " then ".join(recommended[1:-1] or recommended)
            if recommended else "Group closer destinations together"
        ),
        "time_saved_minutes": int(time_saved) if time_saved else None,
        "estimated_cost_saved": (result.get("intelligence") or {}).get("cost_saved_estimate"),
        "cost_is_estimated": True,
        "legs_removed": legs_removed or None,
        "reason": "Groups geographically closer destinations together",
        "confidence": 0.84 if miles >= 1 else 0.7,
        "current_titles": current,
        "recommended_titles": recommended,
        "miles_saved": miles or None,
        "map": {
            "current": {"stops": current, "source": maps_source()},
            "recommended": {"stops": recommended, "source": maps_source()},
            "source": maps_source(),
        },
        "explanation": {
            "selected_option": " → ".join(recommended),
            "alternatives": [" → ".join(current)],
            "primary_factor": "route_efficiency",
            "secondary_factor": "travel_time",
            "tradeoff": reorder.get("predicted_improvement") or "Shorter path between stops",
            "user_preference": prefs.priority,
        },
        "item_ids": [s.get("item_id") for s in opt_stops if s.get("item_id")],
        "original_item_ids": [s.get("item_id") for s in orig_stops if s.get("item_id")],
    }
    rec["fingerprint"] = _fingerprint(rec)
    return rec


def _airport_hop(transition: Dict[str, Any]) -> bool:
    blob = " ".join([
        str(transition.get("from_title") or ""),
        str(transition.get("to_title") or ""),
    ]).lower()
    return any(w in blob for w in ("jfk", "lga", "ewr", "sfo", "airport", "flight arrival"))


def _build_recommendations(result: Dict[str, Any], prefs: Prefs) -> List[Dict[str, Any]]:
    recs: List[Dict[str, Any]] = []
    rejected = set()
    reorder = result.get("reorder")
    if reorder:
        recs.append(_reorder_rec(reorder, result, prefs))
    transitions = result.get("transitions") or []
    airport = next(
        ((i, t) for i, t in enumerate(transitions) if _airport_hop(t) and t.get("changed")),
        None,
    )
    if airport is None:
        airport = next(((i, t) for i, t in enumerate(transitions) if _airport_hop(t)), None)
    if airport:
        recs.append(_transport_rec(airport[0], airport[1], prefs, rec_type="airport_transfer"))
    changed = [(i, t) for i, t in enumerate(transitions) if t.get("changed") and not _airport_hop(t)]
    if changed:
        i, t = max(
            changed,
            key=lambda pair: abs(float(pair[1].get("time_delta_min") or 0))
            + abs(float(pair[1].get("cost_delta") or 0)),
        )
        rec_type = "better_value_transportation"
        if float(t.get("cost_delta") or 0) > 1 and float(t.get("time_delta_min") or 0) < 2:
            rec_type = "cheaper_transportation"
        elif float(t.get("time_delta_min") or 0) > 2:
            rec_type = "faster_transportation"
        recs.append(_transport_rec(i, t, prefs, rec_type=rec_type))
    elif transitions and not airport:
        best = max(
            enumerate(transitions),
            key=lambda pair: abs(float(pair[1].get("time_delta_min") or 0)),
        )
        recs.append(_transport_rec(best[0], best[1], prefs, rec_type="better_value_transportation"))

    intel = result.get("intelligence") or {}
    orig_min = intel.get("original_travel_min")
    opt_min = intel.get("optimized_travel_min")
    if orig_min and opt_min and orig_min - opt_min >= 8 and not any(
        r["type"] == "route_optimization" for r in recs
    ):
        recs.append({
            "id": str(uuid.uuid4()),
            "type": "schedule_optimization",
            "title": "Tighten the day's travel",
            "recommendation": "Use the scored transportation plan to cut idle travel",
            "time_saved_minutes": int(orig_min - opt_min),
            "estimated_cost_saved": intel.get("cost_saved_estimate"),
            "cost_is_estimated": True,
            "reason": "The scored plan reduces total travel time across the day",
            "confidence": 0.72,
            "current_titles": [],
            "recommended_titles": [],
            "explanation": {
                "primary_factor": "travel_time",
                "secondary_factor": "cost",
                "tradeoff": f"About {int(orig_min - opt_min)} minutes less travel",
                "user_preference": prefs.priority,
            },
        })
        recs[-1]["fingerprint"] = _fingerprint(recs[-1])

    scored = []
    for rec in recs:
        if rec.get("fingerprint") in rejected:
            continue
        impact = (rec.get("time_saved_minutes") or 0) + (rec.get("estimated_cost_saved") or 0)
        rec["impact"] = impact
        scored.append(rec)
    scored.sort(key=lambda r: float(r.get("impact") or 0), reverse=True)
    return scored[:5]


def _summary(result: Dict[str, Any]) -> Dict[str, Any]:
    intel = result.get("intelligence") or {}
    transitions = result.get("transitions") or []
    orig_legs = len(transitions)
    opt_legs = orig_legs
    reorder = result.get("reorder")
    if reorder and reorder.get("stops"):
        opt_legs = max(0, len(reorder["stops"]) - 1)
    maps = (result.get("data_sources") or {}).get("maps") or maps_source()
    rideshare = (result.get("data_sources") or {}).get("rideshare") or default_provider().source
    time_saved = intel.get("travel_time_saved_min")
    cost_saved = intel.get("cost_saved_estimate")
    return {
        "original_travel_min": intel.get("original_travel_min"),
        "optimized_travel_min": intel.get("optimized_travel_min"),
        "potential_time_saved_min": time_saved if time_saved else None,
        "original_cost_estimate": None,
        "optimized_cost_estimate": None,
        "potential_cost_saved": cost_saved if cost_saved else None,
        "cost_is_estimated": True,
        "cost_estimate_source": intel.get("cost_estimate_source") or "demo_ranking",
        "original_legs": orig_legs,
        "optimized_legs": opt_legs,
        "maps_source": maps,
        "rideshare_source": rideshare,
        "show_time_saved": bool(time_saved),
        "show_cost_saved": bool(cost_saved) and rideshare != "unavailable",
    }


def speak_analysis(payload: Dict[str, Any]) -> str:
    recs = [r for r in (payload.get("recommendations") or []) if r.get("status") != "rejected"]
    if not recs:
        return (
            "I looked over your itinerary. The current order and rides already "
            "look reasonable — I don't have a change I'd recommend right now."
        )
    n = len(recs)
    parts = [f"I analyzed your itinerary and found {n} way{'s' if n != 1 else ''} to improve it."]
    for i, rec in enumerate(recs[:3], start=1):
        line = rec.get("recommendation") or rec.get("title")
        saved = rec.get("time_saved_minutes")
        if saved:
            line += f" That should save around {int(saved)} minutes"
            if rec.get("estimated_cost_saved"):
                line += f" and about ${float(rec['estimated_cost_saved']):.0f}"
                if rec.get("cost_is_estimated"):
                    line += " estimated"
            line += "."
        elif rec.get("reason"):
            line += f" {rec['reason']}."
        parts.append(f"{i}. {line}")
    parts.append("Want me to apply the first one, or keep your current plan?")
    return " ".join(parts)


def _public_rec(rec: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(rec)
    out.pop("original_item_ids", None)
    return out


def _payload(trip_id: str, result: Dict[str, Any], recs: List[Dict[str, Any]], prefs: Prefs) -> Dict[str, Any]:
    rejected = _REJECTED.get(trip_id) or set()
    visible = []
    for rec in recs:
        if rec.get("fingerprint") in rejected:
            rec = dict(rec)
            rec["status"] = "rejected"
        visible.append(rec)
    open_recs = [r for r in visible if r.get("status") != "rejected"]
    body = {
        "trip_id": trip_id,
        "ok": True,
        "prefs": {
            "priority": prefs.priority,
            "max_walk_minutes": prefs.max_walk_minutes,
            "min_buffer": prefs.min_buffer,
            "frozen": list(prefs.frozen),
            "weights": WEIGHT_PROFILES.get(prefs.priority, WEIGHT_PROFILES["balanced"]),
        },
        "model": {
            "kind": "weighted_scorer_plus_transport_forest",
            "disclaimer": (
                "Transparent weighted scoring plus a trained transportation "
                "quality model — not a neural network."
            ),
            "maps_source": maps_source(),
            "rideshare_source": default_provider().source,
        },
        "summary": _summary(result),
        "recommendations": [_public_rec(r) for r in open_recs],
        "all_recommendations": [_public_rec(r) for r in visible],
        "spoken": speak_analysis({"recommendations": open_recs}),
        "map": {
            "current_stops": [
                {
                    "title": _short(s.get("title") or ""),
                    "lat": s.get("lat"),
                    "lon": s.get("lon"),
                }
                for s in (result.get("original_stops") or [])
            ],
            "recommended_stops": [
                {
                    "title": _short(s.get("title") or ""),
                    "lat": s.get("lat"),
                    "lon": s.get("lon"),
                }
                for s in (
                    ((result.get("reorder") or {}).get("stops"))
                    or result.get("optimized_stops")
                    or []
                )
            ],
            "source": maps_source(),
        },
    }
    return body


def analyze_trip(trip_id: str, items: Sequence[ItineraryItem], *, prefs: Optional[Prefs] = None) -> Dict[str, Any]:
    prefs = prefs or prefs_for(trip_id)
    set_prefs(trip_id, prefs)
    stops = items_to_stops(items)
    if len(stops) < 2:
        body = {
            "trip_id": trip_id,
            "ok": False,
            "recommendations": [],
            "summary": {},
            "spoken": (
                "I need at least two timed stops on this itinerary before I "
                "can compare routes."
            ),
        }
        _ANALYSES[trip_id] = body
        return body
    result = optimize_stops(stops, prefs)
    result.pop("snapshots", None)
    recs = _build_recommendations(result, prefs)
    rejected = _REJECTED.get(trip_id) or set()
    recs = [r for r in recs if r.get("fingerprint") not in rejected]
    body = _payload(trip_id, result, recs, prefs)
    body["_result"] = result
    body["_recs"] = recs
    _ANALYSES[trip_id] = body
    return {k: v for k, v in body.items() if not k.startswith("_")}


def public_view(trip_id: str) -> Optional[Dict[str, Any]]:
    raw = _ANALYSES.get(trip_id)
    if not raw:
        return None
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def _load_items(trip_id: str) -> List[ItineraryItem]:
    view = memory_trips.get(trip_id)
    if view is not None:
        return list(view.items)
    success, items, _error = itinerary_items.list_items_for_trip(trip_id)
    if not success:
        return []
    return list(items)


def analyze_by_id(trip_id: str, *, pref_text: str = "") -> Dict[str, Any]:
    items = _load_items(trip_id)
    if not items:
        return {
            "ok": False,
            "trip_id": trip_id,
            "recommendations": [],
            "spoken": "I don't see a booked itinerary to optimize yet.",
        }
    prefs = merge_pref_text(trip_id, pref_text) if pref_text else prefs_for(trip_id)
    return analyze_trip(trip_id, items, prefs=prefs)


def _rec_by_ref(trip_id: str, rec_id: str) -> Optional[Dict[str, Any]]:
    raw = _ANALYSES.get(trip_id) or {}
    recs = raw.get("_recs") or raw.get("recommendations") or []
    rec_id = str(rec_id or "").strip()
    if rec_id.isdigit():
        idx = int(rec_id) - 1
        open_recs = [r for r in recs if r.get("status") != "rejected"]
        if 0 <= idx < len(open_recs):
            return open_recs[idx]
    for rec in recs:
        if rec.get("id") == rec_id:
            return rec
    return None


def log_feedback(
    trip_id: str,
    *,
    action: str,
    rec: Optional[Dict[str, Any]] = None,
    chosen: str = "",
    rejected: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    row = {
        "trip_id": trip_id,
        "action": action,
        "chosen": chosen or (rec or {}).get("to_mode") or (rec or {}).get("type"),
        "rejected": rejected or (rec or {}).get("from_mode"),
        "time_difference": (rec or {}).get("time_saved_minutes")
        or ((rec or {}).get("explanation") or {}).get("time_difference"),
        "cost_difference": (rec or {}).get("estimated_cost_saved")
        or ((rec or {}).get("explanation") or {}).get("cost_difference"),
        "preference": prefs_for(trip_id).priority,
        "recommendation_type": (rec or {}).get("type"),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        row.update(extra)
    _FEEDBACK.append(row)
    return row


def _stamp_details(item: ItineraryItem, patch: Dict[str, Any]) -> dict:
    details = dict(item.details or {})
    details.update(patch)
    return details


def _write_item(item: ItineraryItem) -> None:
    mem = memory_trips.update_item_fields(
        item.item_id,
        start_ts=item.start_ts,
        end_ts=item.end_ts,
        location=item.location,
        details=item.details,
    )
    if mem is not None:
        return
    itinerary_items.update_item_fields(
        item.item_id,
        start_ts=item.start_ts,
        end_ts=item.end_ts,
        location=item.location,
        details=item.details,
        price=item.price,
        currency=item.currency,
    )


def _apply_reorder(trip_id: str, rec: Dict[str, Any]) -> Tuple[bool, str]:
    items = _load_items(trip_id)
    by_id = {i.item_id: i for i in items}
    raw = _ANALYSES.get(trip_id) or {}
    result = raw.get("_result") or {}
    orig_stops = result.get("original_stops") or []
    new_stops = ((result.get("reorder") or {}).get("stops")) or []
    if not orig_stops or not new_stops:
        return False, "I couldn't match that reorder to the current itinerary."
    orig_ids = [s.get("item_id") for s in orig_stops if s.get("item_id")]
    new_ids = [s.get("item_id") for s in new_stops if s.get("item_id")]
    if len(orig_ids) != len(new_ids) or not all(i in by_id for i in new_ids):
        return False, "That reorder no longer matches this itinerary."
    slots = [(by_id[i].start_ts, by_id[i].end_ts) for i in orig_ids]
    for item_id, (start, end) in zip(new_ids, slots):
        item = by_id[item_id]
        duration = None
        if item.start_ts and item.end_ts:
            duration = item.end_ts - item.start_ts
        item.start_ts = start
        item.end_ts = (start + duration) if start and duration else end
        item.details = _stamp_details(item, {
            "optimization_applied": rec.get("type"),
            "optimization_id": rec.get("id"),
        })
        _write_item(item)
    return True, "Applied. I reordered the flexible stops and kept the fixed ones in place."


def _apply_transport(trip_id: str, rec: Dict[str, Any]) -> Tuple[bool, str]:
    items = _load_items(trip_id)
    raw = _ANALYSES.get(trip_id) or {}
    result = raw.get("_result") or {}
    transitions = result.get("transitions") or []
    hop = rec.get("hop")
    if not isinstance(hop, int) or hop < 0 or hop >= len(transitions):
        return False, "I couldn't find that transportation change anymore."
    dest_title = transitions[hop].get("to_title") or ""
    dest_item = None
    for item in items:
        title = _title_of(item)
        loc = _location_of(item)
        if dest_title and (dest_title == title or dest_title.endswith(loc) or loc in dest_title):
            dest_item = item
            break
    if dest_item is None and hop + 1 < len(items):
        ordered = sorted(
            items,
            key=lambda i: i.start_ts or datetime.min.replace(tzinfo=timezone.utc),
        )
        if hop + 1 < len(ordered):
            dest_item = ordered[hop + 1]
    if dest_item is None:
        return False, "I couldn't attach that ride to a stop on the itinerary."
    pick = ((rec.get("transport_options") or {}).get("cascade_pick") or {})
    dest_item.details = _stamp_details(dest_item, {
        "transport_mode": pick.get("mode") or rec.get("to_mode"),
        "transport_label": pick.get("label") or rec.get("to_mode"),
        "transport_minutes": pick.get("travel_time"),
        "transport_cost_estimate": pick.get("cost"),
        "transport_cost_estimated": bool(pick.get("estimated") or rec.get("cost_is_estimated")),
        "optimization_applied": rec.get("type"),
        "optimization_id": rec.get("id"),
    })
    _write_item(dest_item)
    label = pick.get("label") or rec.get("to_mode") or "the recommended ride"
    return True, f"Applied. I'll use {label} for that leg."


def apply_recommendation(trip_id: str, rec_id: str) -> Dict[str, Any]:
    rec = _rec_by_ref(trip_id, rec_id)
    if rec is None:
        return {
            "ok": False,
            "spoken": "I don't have that recommendation on the table anymore.",
        }
    if rec.get("type") == "route_optimization":
        ok, spoken = _apply_reorder(trip_id, rec)
    else:
        ok, spoken = _apply_transport(trip_id, rec)
    if not ok:
        return {"ok": False, "spoken": spoken, "recommendation_id": rec.get("id")}
    rec["status"] = "applied"
    _REJECTED.setdefault(trip_id, set()).add(rec.get("fingerprint") or rec.get("id"))
    log_feedback(trip_id, action="accept", rec=rec, chosen=rec.get("to_mode") or rec.get("type"))
    refreshed = analyze_by_id(trip_id)
    refreshed["spoken"] = spoken + " I recalculated the rest of the day."
    refreshed["applied_id"] = rec.get("id")
    return refreshed


def reject_recommendation(trip_id: str, rec_id: str) -> Dict[str, Any]:
    rec = _rec_by_ref(trip_id, rec_id)
    if rec is None:
        return {
            "ok": False,
            "spoken": "I don't have that recommendation on the table anymore.",
        }
    _REJECTED.setdefault(trip_id, set()).add(rec.get("fingerprint") or rec.get("id"))
    rec["status"] = "rejected"
    log_feedback(trip_id, action="reject", rec=rec, rejected=rec.get("type"))
    raw = _ANALYSES.get(trip_id)
    if raw and raw.get("_result") is not None:
        body = _payload(trip_id, raw["_result"], raw.get("_recs") or [], prefs_for(trip_id))
        body["_result"] = raw["_result"]
        body["_recs"] = raw.get("_recs") or []
        _ANALYSES[trip_id] = body
        public = {k: v for k, v in body.items() if not k.startswith("_")}
    else:
        public = analyze_by_id(trip_id)
    public["spoken"] = "Okay — I'll keep your current plan and won't suggest that same change again."
    public["rejected_id"] = rec.get("id")
    return public
