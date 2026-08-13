"""Observe hops, generate actions, let the trained policy pick, then execute.

Google Maps / demo geometry describes routes. Simulated (or live) rideshare
providers supply quotes. The action forest scores (state, action) pairs.
Hard constraints live here. The LLM does not pick the winner.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ml.transport.maps import maps_source, route
from ml.transport.parse import geocode, venue_type
from ml.transport.policy import action_row
from ml.transport.policy_predict import policy_metrics, predict_action_utility
from ml.transport.predict import model_metrics, predict_quality
from ml.transport.rideshare import build_here_now, default_provider

MODE_LABELS = {
    "uber": "Uber",
    "lyft": "Lyft",
    "walk": "Walking",
    "transit": "Transit",
    "uber_alt_pickup": "Uber · alternate pickup",
}

PRIORITY_WEIGHTS = {
    "balanced": dict(ml=0.70, time=0.15, cost=0.15),
    "time": dict(ml=0.28, time=0.62, cost=0.10),
    "cost": dict(ml=0.30, time=0.10, cost=0.60),
    "walk": dict(ml=0.55, time=0.15, cost=0.30),
}


@dataclass
class Prefs:
    priority: str = "balanced"
    max_walk_minutes: Optional[int] = None
    min_buffer: Optional[int] = None
    frozen: tuple = ()

    def describe(self) -> str:
        bits = [self.priority]
        if self.max_walk_minutes is not None:
            bits.append(f"walk ≤ {self.max_walk_minutes} min")
        if self.min_buffer is not None:
            bits.append(f"arrive {self.min_buffer} min early")
        if self.frozen:
            bits.append("frozen: " + ", ".join(self.frozen))
        return ", ".join(bits)

    def is_frozen(self, title: str) -> bool:
        t = (title or "").lower()
        return any(f.lower() in t for f in self.frozen)


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


def _trip_minutes(stop: Dict[str, Any]) -> int:
    return int(stop.get("day") or 0) * 24 * 60 + _clock_minutes(stop.get("start_time") or "12:00")


def _ranking_cost(mode: str, miles: float, drive_min: float, eta: float) -> float:
    """Internal ranking cost — not a live Uber/Lyft quote."""
    if mode == "walk":
        return 0.0
    if mode == "transit":
        return 3.0
    return round(7.5 + 2.15 * miles + 0.28 * drive_min + 0.15 * eta, 2)


def _clock_minutes(clock: str) -> int:
    try:
        h, m = (clock or "12:00").split(":")
        return int(h) * 60 + int(m[:2])
    except (TypeError, ValueError):
        return 12 * 60


def _traffic(hour: int) -> float:
    if 7 <= hour <= 9 or 16 <= hour <= 19:
        return 0.72
    if 22 <= hour or hour < 6:
        return 0.22
    return 0.40


def _coords(stop: Dict[str, Any]) -> Tuple[float, float]:
    if stop.get("lat") is not None and stop.get("lon") is not None:
        return float(stop["lat"]), float(stop["lon"])
    return geocode(stop.get("title") or stop.get("location") or "")


def _candidate(
    *,
    mode: str,
    origin: Dict[str, Any],
    dest: Dict[str, Any],
    distance: float,
    hour: int,
    buffer: float,
    gap: float,
    prev_stops: int,
    backtrack: float,
    pickup_label: str,
    congestion: float,
    walking: float,
    eta: float,
    speed_mph: float,
    cost: float,
    extra_wait: float = 0.0,
) -> Dict[str, Any]:
    road = distance * (1.08 if mode == "walk" else 1.28)
    travel = walking / 3.0 * 60.0 + extra_wait + eta
    if mode == "walk":
        travel = distance / 3.0 * 60.0
        eta = 0.0
        cost = 0.0
    else:
        travel += distance / max(speed_mph, 2.5) * 60.0
    option = {
        "transportation_mode": mode,
        "label": MODE_LABELS[mode],
        "pickup_label": pickup_label,
        "dropoff_label": dest.get("title") or dest.get("location") or "destination",
        "distance_miles": round(distance, 3),
        "road_distance": round(road, 3),
        "walking_distance": round(walking, 3),
        "estimated_travel_time": round(travel, 1),
        "estimated_cost": round(cost, 2),
        "rideshare_eta": round(eta, 1),
        "time_of_day": hour,
        "day_of_week": 5,
        "traffic_level": _traffic(hour),
        "pickup_congestion": congestion,
        "dropoff_congestion": 0.55 if dest.get("venue_type") == "concert" else 0.32,
        "schedule_buffer": round(buffer, 1),
        "activity_duration": 90.0,
        "time_until_next_activity": round(gap, 1),
        "number_of_previous_stops": prev_stops,
        "route_backtracking_distance": round(backtrack, 3),
        "venue_type": dest.get("venue_type") or venue_type(dest.get("title") or ""),
        "origin_title": origin.get("title"),
        "dest_title": dest.get("title"),
    }
    return option


def generate_candidates(
    origin: Dict[str, Any],
    dest: Dict[str, Any],
    *,
    prev_stops: int = 0,
    next_stop: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    distance = max(0.12, haversine_miles(_coords(origin), _coords(dest)))
    hour = _trip_minutes(origin) // 60 % 24
    dest_min = _trip_minutes(dest)
    origin_min = _trip_minutes(origin)
    gap = max(15.0, float(dest_min - origin_min))
    drive = route(_coords(origin), _coords(dest), mode="driving", hour=hour)
    walk_rt = route(_coords(origin), _coords(dest), mode="walk", hour=hour)
    transit_rt = route(_coords(origin), _coords(dest), mode="transit", hour=hour)
    if drive.get("source") == "google_maps":
        distance = max(0.12, float(drive["miles"]))
    traffic = float(drive.get("traffic_level") or _traffic(hour))
    backtrack = 0.0
    if next_stop:
        direct = haversine_miles(_coords(origin), _coords(next_stop))
        via = distance + haversine_miles(_coords(dest), _coords(next_stop))
        backtrack = max(0.0, via - direct)

    main_cong = 0.62 if dest.get("venue_type") == "concert" else 0.42
    if dest.get("venue_type") == "museum":
        main_cong = 0.50
    alt_cong = max(0.12, main_cong - 0.32)
    drive_min = float(drive.get("duration_min") or (distance / 15.5 * 60))
    quotes = default_provider().get_quotes(
        _coords(origin), _coords(dest),
        hour=hour, congestion=main_cong, drive_min=drive_min, miles=distance,
    )
    by_prov = {(q["provider"], q["pickup"]): q for q in quotes}
    uber_q = by_prov.get(("uber", "Main entrance"), quotes[0])
    lyft_q = by_prov.get(("lyft", "Main entrance"), quotes[1] if len(quotes) > 1 else quotes[0])
    alt_q = by_prov.get(("uber", "Alternate pickup zone"), quotes[-1])
    alt_label = dest.get("alt_pickup_label") or origin.get("alt_pickup_label") or "Side-street pickup zone"

    walk_time = float(walk_rt.get("duration_min") or (distance / 3.0 * 60.0))
    transit_time = float(transit_rt.get("duration_min") or (distance / 11.0 * 60.0 + 8))
    env_source = drive.get("source") or "demo_geometry"
    cands = [
        _candidate(
            mode="walk", origin=origin, dest=dest, distance=distance, hour=hour,
            buffer=gap - walk_time, gap=gap, prev_stops=prev_stops, backtrack=backtrack,
            pickup_label="Walk the whole way", congestion=0.05, walking=distance,
            eta=0.0, speed_mph=3.0, cost=_ranking_cost("walk", distance, 0, 0),
        ),
        _candidate(
            mode="transit", origin=origin, dest=dest, distance=distance, hour=hour,
            buffer=gap - transit_time, gap=gap, prev_stops=prev_stops,
            backtrack=backtrack, pickup_label="Nearest station", congestion=0.25,
            walking=0.22, eta=0.0, speed_mph=11.0,
            cost=_ranking_cost("transit", distance, transit_time, 0), extra_wait=8.0,
        ),
        _candidate(
            mode="uber", origin=origin, dest=dest, distance=distance, hour=hour,
            buffer=gap - (drive_min + float(uber_q["eta_min"])), gap=gap, prev_stops=prev_stops,
            backtrack=backtrack, pickup_label=origin.get("pickup_label") or "Main entrance",
            congestion=main_cong, walking=0.07, eta=float(uber_q["eta_min"]),
            speed_mph=15.5,
            cost=_ranking_cost("uber", distance, drive_min, float(uber_q["eta_min"])),
        ),
        _candidate(
            mode="lyft", origin=origin, dest=dest, distance=distance, hour=hour,
            buffer=gap - (drive_min + float(lyft_q["eta_min"])), gap=gap, prev_stops=prev_stops,
            backtrack=backtrack, pickup_label=origin.get("pickup_label") or "Main entrance",
            congestion=max(0.12, main_cong - 0.08), walking=0.08,
            eta=float(lyft_q["eta_min"]), speed_mph=15.5,
            cost=_ranking_cost("lyft", distance, drive_min, float(lyft_q["eta_min"])),
        ),
        _candidate(
            mode="uber_alt_pickup", origin=origin, dest=dest, distance=distance, hour=hour,
            buffer=gap - (drive_min + float(alt_q["eta_min"]) + 3.6), gap=gap, prev_stops=prev_stops,
            backtrack=backtrack,
            pickup_label=alt_label,
            congestion=alt_cong, walking=0.18, eta=float(alt_q["eta_min"]),
            speed_mph=15.5,
            cost=_ranking_cost("uber", distance, drive_min, float(alt_q["eta_min"])),
        ),
    ]
    cands[0]["estimated_travel_time"] = round(walk_time, 1)
    cands[1]["estimated_travel_time"] = round(transit_time, 1)
    cands[2]["estimated_travel_time"] = round(drive_min + float(uber_q["eta_min"]) + 1.4, 1)
    cands[3]["estimated_travel_time"] = round(drive_min + float(lyft_q["eta_min"]) + 1.6, 1)
    cands[4]["estimated_travel_time"] = round(drive_min + float(alt_q["eta_min"]) + 3.6, 1)
    for cand in cands:
        cand["schedule_buffer"] = round(gap - float(cand["estimated_travel_time"]), 1)
        cand["route_source"] = env_source
        cand["route_summary"] = (
            walk_rt.get("summary") if cand["transportation_mode"] == "walk"
            else transit_rt.get("summary") if cand["transportation_mode"] == "transit"
            else drive.get("summary")
        )
        cand["rideshare_source"] = default_provider().source
        cand["price_available"] = False
        predicted = predict_quality(cand)
        cand["ml_score"] = predicted["score"]
        cand["ml_source"] = predicted["source"]
        cand["ml_factors"] = predicted["factors"]
    return cands


def _feasible(cand: Dict[str, Any], prefs: Prefs) -> bool:
    if prefs.max_walk_minutes is None:
        return True
    walk_min = float(cand["walking_distance"]) / 3.0 * 60.0
    if cand["transportation_mode"] == "walk":
        walk_min = float(cand["estimated_travel_time"])
    return walk_min <= prefs.max_walk_minutes + 0.5


def _blend(cand: Dict[str, Any], prefs: Prefs) -> float:
    weights = PRIORITY_WEIGHTS.get(prefs.priority, PRIORITY_WEIGHTS["balanced"])
    time_u = 1.0 - min(float(cand["estimated_travel_time"]) / 55.0, 1.0)
    cost_u = 1.0 - min(float(cand["estimated_cost"]) / 40.0, 1.0)
    return (
        weights["ml"] * float(cand["ml_score"])
        + weights["time"] * time_u
        + weights["cost"] * cost_u
    )


def rank_candidates(cands: Sequence[Dict[str, Any]], prefs: Prefs) -> List[Dict[str, Any]]:
    scored = []
    for cand in cands:
        row = dict(cand)
        row["feasible"] = _feasible(cand, prefs)
        scored.append(row)
    feasible = [c for c in scored if c["feasible"]]
    if feasible and prefs.priority == "time":
        fastest = min(float(c["estimated_travel_time"]) for c in feasible)
        for row in scored:
            if row["feasible"] and float(row["estimated_travel_time"]) > fastest + 4.0:
                row["feasible"] = False
    if feasible and prefs.priority == "cost":
        # Walk is $0; only apply the cost band among paid modes when walking
        # is slower than 12 minutes so we do not force a 3-mile walk.
        paid = [c for c in scored if c["feasible"] and float(c["estimated_cost"]) > 0.5]
        walkable = [
            c for c in scored
            if c["feasible"] and c["transportation_mode"] == "walk"
            and float(c["estimated_travel_time"]) <= 12
        ]
        if paid and not walkable:
            cheapest = min(float(c["estimated_cost"]) for c in paid)
            for row in scored:
                if row["feasible"] and float(row["estimated_cost"]) > cheapest + 5.0:
                    row["feasible"] = False
    for row in scored:
        row["final_score"] = round(_blend(row, prefs), 4) if row["feasible"] else -1.0
    scored.sort(key=lambda r: r["final_score"], reverse=True)
    return scored


def _baseline(cands: Sequence[Dict[str, Any]], prefs: Optional[Prefs] = None) -> Dict[str, Any]:
    """Planned default: walk only if it fits the walking cap, else Uber main entrance."""
    prefs = prefs or Prefs()
    by_mode = {c["transportation_mode"]: c for c in cands}
    walk = by_mode.get("walk")
    limit = prefs.max_walk_minutes if prefs.max_walk_minutes is not None else 10
    if walk and float(walk["estimated_travel_time"]) <= limit + 0.5:
        return walk
    return by_mode.get("uber") or cands[0]


def _why(rec: Dict[str, Any], current: Dict[str, Any]) -> List[str]:
    reasons = []
    if rec["transportation_mode"] != current["transportation_mode"]:
        reasons.append(f"Switched {current['label']} → {rec['label']}")
    if rec["pickup_label"] != current["pickup_label"]:
        reasons.append(f"Pickup {current['pickup_label']} → {rec['pickup_label']}")
    if rec["estimated_travel_time"] + 0.4 < current["estimated_travel_time"]:
        reasons.append("Shorter route")
    if rec["transportation_mode"] == "walk" and current["transportation_mode"] != "walk":
        reasons.append("Walking is within the walk cap and avoids a paid rideshare")
    if rec["transportation_mode"] != "walk" and current["transportation_mode"] == "walk":
        reasons.append("Walk exceeds the preferred limit — rideshare is the shortest feasible hop")
    if rec["estimated_cost"] + 0.4 < current["estimated_cost"]:
        reasons.append("Lower estimated cost")
    if rec["pickup_congestion"] + 0.05 < current["pickup_congestion"]:
        reasons.append("Lower predicted pickup congestion")
    if rec["rideshare_eta"] + 0.4 < current["rideshare_eta"]:
        reasons.append("Shorter predicted pickup wait")
    if rec["schedule_buffer"] > current["schedule_buffer"] + 1:
        reasons.append("Better schedule buffer")
    if rec["walking_distance"] + 0.05 < current["walking_distance"]:
        reasons.append("Less walking")
    elif rec["walking_distance"] > current["walking_distance"] + 0.08 and rec["ml_score"] > current["ml_score"]:
        reasons.append("Slightly more walking, still a better predicted outcome")
    for factor in rec.get("ml_factors") or []:
        if factor not in reasons:
            reasons.append(factor)
        if len(reasons) >= 4:
            break
    return reasons[:4]


def _path_miles(stops: Sequence[Dict[str, Any]]) -> float:
    total = 0.0
    for i in range(len(stops) - 1):
        total += haversine_miles(_coords(stops[i]), _coords(stops[i + 1]))
    return total


def suggest_reorder(stops: Sequence[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Try permutations of flexible interior stops. Keep anchored ends fixed."""
    from itertools import permutations

    if len(stops) < 4:
        return None
    original = list(stops)
    flexible = [i for i in range(1, len(original) - 1) if not original[i].get("anchored")]
    if len(flexible) < 2:
        return None
    if len(flexible) > 4:
        flexible = flexible[:4]
    start_miles = _path_miles(original)
    best = original
    best_miles = start_miles
    flex_stops = [original[i] for i in flexible]
    for perm in permutations(flex_stops):
        trial = list(original)
        for idx, stop in zip(flexible, perm):
            trial[idx] = stop
        miles = _path_miles(trial)
        if miles + 0.15 < best_miles:
            best_miles = miles
            best = trial
    if best is original or best_miles >= start_miles * 0.92:
        return None
    saved = start_miles - best_miles
    return {
        "kind": "route",
        "title": "Route order",
        "current_titles": [s["title"] for s in original],
        "recommended_titles": [s["title"] for s in best],
        "miles_saved": round(saved, 2),
        "predicted_improvement": f"Reduced route distance by {saved:.1f} miles",
        "stops": best,
    }


def _hop_actions(
    current: Dict[str, Any],
    cands: Sequence[Dict[str, Any]],
    prefs: Prefs,
    *,
    hop: int,
    remaining: int,
    dest_title: str = "",
    dest_anchored: bool = False,
) -> List[Dict[str, Any]]:
    by_mode = {c["transportation_mode"]: c for c in cands}
    out: List[Dict[str, Any]] = []

    def add(action: str, proposed: Dict[str, Any], **meta: Any) -> None:
        feat = action_row(
            current, proposed, action_type=action,
            priority=prefs.priority, remaining_stops=remaining,
            min_buffer_needed=float(prefs.min_buffer or 0),
        )
        pred = predict_action_utility(feat)
        walk_ok = _feasible(proposed, prefs)
        frozen = prefs.is_frozen(str(proposed.get("dest_title") or ""))
        if action in ("REORDER_ACTIVITY", "REMOVE_UNNECESSARY_STOP", "CHANGE_DEPARTURE_TIME") and frozen:
            walk_ok = False
        if prefs.min_buffer is not None and action == "KEEP_CURRENT_PLAN":
            if float(current.get("schedule_buffer") or 0) < prefs.min_buffer:
                walk_ok = False
        out.append({
            "action": action,
            "label": action.replace("_", " ").title(),
            "proposed": proposed,
            "utility": pred["utility"],
            "ml_source": pred["source"],
            "feasible": walk_ok,
            "hop": hop,
            "why": _why(proposed, current) if action != "KEEP_CURRENT_PLAN" else ["Keep the current plan"],
            **meta,
        })

    add("KEEP_CURRENT_PLAN", current)
    lyft = by_mode.get("lyft")
    if lyft and current.get("transportation_mode") != "lyft":
        add("CHANGE_RIDESHARE_PROVIDER", lyft, from_value=current.get("label"), to_value="Lyft")
    uber = by_mode.get("uber")
    if uber and current.get("transportation_mode") == "lyft":
        add("CHANGE_RIDESHARE_PROVIDER", uber, from_value="Lyft", to_value="Uber")
    alt = by_mode.get("uber_alt_pickup")
    if alt and current.get("pickup_label") != alt.get("pickup_label"):
        add("CHANGE_PICKUP_LOCATION", alt,
            from_value=current.get("pickup_label"), to_value=alt.get("pickup_label"))
    drop = dict(current)
    drop["dropoff_label"] = "Alternate entrance"
    drop["dropoff_congestion"] = max(0.1, float(current.get("dropoff_congestion") or 0.3) - 0.18)
    drop["walking_distance"] = float(current.get("walking_distance") or 0.1) + 0.08
    drop["estimated_travel_time"] = max(4.0, float(current.get("estimated_travel_time") or 20) - 1.5)
    add("CHANGE_DROPOFF_LOCATION", drop,
        from_value=current.get("dropoff_label"), to_value="Alternate entrance")
    for mode in ("walk", "uber"):
        opt = by_mode.get(mode)
        if opt and opt["transportation_mode"] != current.get("transportation_mode"):
            add("CHANGE_TRANSPORTATION_MODE", opt,
                from_value=current.get("label"), to_value=opt.get("label"))
    earlier = dict(current)
    earlier["schedule_buffer"] = float(current.get("schedule_buffer") or 0) + 10
    earlier["leave_minutes_earlier"] = 10
    add("CHANGE_DEPARTURE_TIME", earlier, from_value="on time", to_value="10 min earlier")
    buffered = dict(current)
    buffered["schedule_buffer"] = float(current.get("schedule_buffer") or 0) + 15
    buffered["leave_minutes_earlier"] = 15
    add("ADD_BUFFER", buffered, from_value="current buffer", to_value="+15 min")
    reroute = dict(current)
    reroute["traffic_level"] = max(0.1, float(current.get("traffic_level") or 0.4) - 0.22)
    reroute["estimated_travel_time"] = max(4.0, float(current.get("estimated_travel_time") or 20) - 3.0)
    reroute["route_label"] = "Lower-traffic alternative"
    add("CHANGE_ROUTE", reroute, from_value="current route", to_value="lower-traffic alternative")
    return out


def optimize_stops(stops: Sequence[Dict[str, Any]], prefs: Optional[Prefs] = None) -> Dict[str, Any]:
    """Observe → score actions → execute the best valid one → repeat."""
    prefs = prefs or Prefs()
    original = [dict(s) for s in stops]
    working = [dict(s) for s in stops]
    stages = [
        {"id": "parsed", "label": "Itinerary understood", "state": "done"},
        {"id": "mapped", "label": "Destinations mapped", "state": "done",
         "detail": maps_source()},
        {"id": "segments", "label": "Transportation segments identified", "state": "done"},
        {"id": "routes", "label": "Routes analyzed", "state": "done",
         "detail": maps_source()},
        {"id": "rideshare", "label": "Rideshare options evaluated", "state": "done",
         "detail": default_provider().source},
        {"id": "ml", "label": "ML action selection", "state": "active"},
    ]

    hop_plan: List[Dict[str, Any]] = []
    for i in range(len(working) - 1):
        nxt = working[i + 2] if i + 2 < len(working) else None
        cands = generate_candidates(working[i], working[i + 1], prev_stops=i, next_stop=nxt)
        hop_plan.append(_baseline(cands, prefs))

    history: List[Dict[str, Any]] = []
    snapshots = []
    n_evaluated = 0
    for _step in range(5):
        pool: List[Dict[str, Any]] = []
        remaining = max(1, len(working) - 1)
        for i in range(len(working) - 1):
            nxt = working[i + 2] if i + 2 < len(working) else None
            cands = generate_candidates(working[i], working[i + 1], prev_stops=i, next_stop=nxt)
            current = hop_plan[i] if i < len(hop_plan) else _baseline(cands, prefs)
            pool.extend(_hop_actions(
                current, cands, prefs, hop=i, remaining=remaining,
                dest_title=str(working[i + 1].get("title") or ""),
                dest_anchored=bool(working[i + 1].get("anchored")),
            ))
        reorder = suggest_reorder(working)
        if reorder and not any(prefs.is_frozen(t) for t in (reorder.get("recommended_titles") or [])):
            dummy = hop_plan[0] if hop_plan else {}
            proposed = dict(dummy)
            proposed["estimated_travel_time"] = max(4.0, float(dummy.get("estimated_travel_time") or 20) - 6)
            feat = action_row(dummy, proposed, action_type="REORDER_ACTIVITY",
                              priority=prefs.priority, remaining_stops=remaining)
            pred = predict_action_utility(feat)
            pool.append({
                "action": "REORDER_ACTIVITY",
                "label": "Reorder Activity",
                "proposed": proposed,
                "utility": pred["utility"],
                "ml_source": pred["source"],
                "feasible": True,
                "hop": -1,
                "why": [reorder.get("predicted_improvement") or "Shorter route"],
                "reorder": reorder,
            })
        feasible = [a for a in pool if a.get("feasible")]
        n_evaluated = max(n_evaluated, len(pool))
        if not feasible:
            break
        best = max(feasible, key=lambda a: float(a["utility"]))
        if best["action"] == "KEEP_CURRENT_PLAN" or float(best["utility"]) < 0.012:
            break
        snapshots.append({
            "stops": [dict(s) for s in working],
            "plan": [dict(p) for p in hop_plan],
        })
        if best["action"] == "REORDER_ACTIVITY" and best.get("reorder"):
            working = [dict(s) for s in best["reorder"]["stops"]]
            hop_plan = []
            for i in range(len(working) - 1):
                nxt = working[i + 2] if i + 2 < len(working) else None
                cands = generate_candidates(working[i], working[i + 1], prev_stops=i, next_stop=nxt)
                hop_plan.append(_baseline(cands, prefs))
        elif best["action"] == "REMOVE_UNNECESSARY_STOP" and 1 < best["hop"] < len(working) - 1:
            del working[best["hop"]]
            hop_plan = []
            for i in range(len(working) - 1):
                nxt = working[i + 2] if i + 2 < len(working) else None
                cands = generate_candidates(working[i], working[i + 1], prev_stops=i, next_stop=nxt)
                hop_plan.append(_baseline(cands, prefs))
        else:
            hop_i = int(best["hop"])
            if 0 <= hop_i < len(hop_plan):
                hop_plan[hop_i] = dict(best["proposed"])
                if best["proposed"].get("leave_minutes_earlier"):
                    mins = int(best["proposed"]["leave_minutes_earlier"])
                    clock = working[hop_i].get("start_time") or "12:00"
                    t = max(0, _clock_minutes(clock) - mins)
                    working[hop_i]["start_time"] = f"{t // 60:02d}:{t % 60:02d}"
                if best["action"] == "CHANGE_PICKUP_LOCATION":
                    working[hop_i]["pickup_label"] = best["proposed"].get("pickup_label")
                working[hop_i]["leg_mode"] = best["proposed"].get("label")
        history.append({
            "action": best["action"],
            "label": best["label"],
            "utility": best["utility"],
            "hop": best["hop"],
            "from_value": best.get("from_value"),
            "to_value": best.get("to_value"),
            "why": best.get("why") or [],
            "ml_source": best.get("ml_source"),
        })

    stages[-1]["state"] = "done"
    stages.append({"id": "improvements", "label": "Trip improvements found", "state": "done",
                   "detail": str(len(history))})
    packed = _pack_result(
        original, working, hop_plan, history, prefs,
        n_evaluated=n_evaluated, snapshots=snapshots, stages=stages,
    )
    return packed


def rebuild_after_undo(
    result: Dict[str, Any],
    snap: Dict[str, Any],
    history: List[Dict[str, Any]],
    prefs: Prefs,
    snapshots: List[Dict[str, Any]],
) -> Dict[str, Any]:
    original = result.get("original_stops") or snap.get("stops") or []
    working = snap.get("stops") or original
    hop_plan = snap.get("plan") or []
    packed = _pack_result(
        original, working, hop_plan, history, prefs,
        n_evaluated=int((result.get("intelligence") or {}).get("actions_evaluated") or 0),
        snapshots=snapshots,
        stages=result.get("analysis_stages") or [],
    )
    packed.pop("snapshots", None)
    return packed


def _pack_result(
    original: Sequence[Dict[str, Any]],
    working: Sequence[Dict[str, Any]],
    hop_plan: Sequence[Dict[str, Any]],
    history: Sequence[Dict[str, Any]],
    prefs: Prefs,
    *,
    n_evaluated: int,
    snapshots: Sequence[Dict[str, Any]],
    stages: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    transitions = []
    rec_scores = []
    cur_scores = []
    for i in range(len(original) - 1):
        nxt = original[i + 2] if i + 2 < len(original) else None
        cands = generate_candidates(original[i], original[i + 1], prev_stops=i, next_stop=nxt)
        ranked = rank_candidates(cands, prefs)
        current = _baseline(cands, prefs)
        rec = hop_plan[i] if i < len(hop_plan) else (ranked[0] if ranked else current)
        rec_scores.append(float(rec.get("ml_score") or 0))
        cur_scores.append(float(current.get("ml_score") or 0))
        dt = float(current["estimated_travel_time"]) - float(rec.get("estimated_travel_time") or current["estimated_travel_time"])
        dc = float(current.get("estimated_cost") or 0) - float(rec.get("estimated_cost") or 0)
        kind = "mode"
        if rec.get("pickup_label") != current.get("pickup_label"):
            kind = "pickup"
        if rec.get("transportation_mode") == "walk" and current.get("transportation_mode") != "walk":
            kind = "walk"
        elif rec.get("transportation_mode") != "walk" and current.get("transportation_mode") == "walk":
            kind = "rideshare"
        changed = bool(
            rec.get("transportation_mode") != current.get("transportation_mode")
            or rec.get("pickup_label") != current.get("pickup_label")
            or rec.get("dropoff_label") != current.get("dropoff_label")
            or rec.get("leave_minutes_earlier")
            or rec.get("route_label")
        )
        transitions.append({
            "from_title": original[i]["title"],
            "to_title": original[i + 1]["title"],
            "kind": kind,
            "current": current,
            "recommended": rec,
            "ranked": ranked,
            "why": _why(rec, current),
            "changed": changed,
            "time_delta_min": round(dt, 1),
            "cost_delta": round(dc, 2),
        })

    orig_time = sum(float(t["current"]["estimated_travel_time"]) for t in transitions) if transitions else 0.0
    opt_time = sum(float(t["recommended"].get("estimated_travel_time") or 0) for t in transitions) if transitions else 0.0
    orig_cost = sum(float(t["current"].get("estimated_cost") or 0) for t in transitions) if transitions else 0.0
    opt_cost = sum(float(t["recommended"].get("estimated_cost") or 0) for t in transitions) if transitions else 0.0
    walk_hops = sum(1 for t in transitions if t["recommended"].get("transportation_mode") == "walk")
    rideshare_hops = sum(
        1 for t in transitions
        if t["recommended"].get("transportation_mode") in ("uber", "lyft", "uber_alt_pickup")
    )
    rideshare_card = None
    for tr in transitions:
        rec = tr["recommended"]
        if rec.get("transportation_mode") in ("uber", "lyft", "uber_alt_pickup"):
            card = {
                "provider": "Lyft" if rec.get("transportation_mode") == "lyft" else "Uber",
                "pickup": rec.get("pickup_label"),
                "dropoff": rec.get("dropoff_label"),
                "travel_min": rec.get("estimated_travel_time"),
                "walking_min": round(float(rec.get("walking_distance") or 0) / 3.0 * 60.0, 1),
                "price": rec.get("estimated_cost") if rec.get("price_available") else None,
                "price_available": bool(rec.get("price_available")),
                "score": rec.get("ml_score"),
                "why": tr["why"],
                "data_source": rec.get("rideshare_source") or "demo_simulated",
            }
            if tr["changed"] or rideshare_card is None:
                rideshare_card = card
            if tr["changed"]:
                break

    orig_score = round(100 * (sum(cur_scores) / len(cur_scores))) if cur_scores else 0
    opt_score = round(100 * (sum(rec_scores) / len(rec_scores))) if rec_scores else 0
    quality = model_metrics()
    policy = policy_metrics()
    stamped = [dict(s) for s in working]
    for i, rec in enumerate(hop_plan):
        if i < len(stamped):
            stamped[i]["leg_mode"] = rec.get("label")
            if rec.get("transportation_mode") != "walk":
                stamped[i]["pickup_label"] = rec.get("pickup_label")
    here_now = (
        build_here_now(
            original[0], original[1],
            max_walk_minutes=prefs.max_walk_minutes,
        )
        if len(original) >= 2 else None
    )
    return {
        "original_stops": list(original),
        "optimized_stops": stamped,
        "reorder": suggest_reorder(original),
        "transitions": transitions,
        "action_history": list(history),
        "analysis_stages": list(stages),
        "rideshare_card": rideshare_card,
        "here_now": here_now,
        "data_sources": {
            "maps": maps_source(),
            "rideshare": default_provider().source,
            "uber": (here_now or {}).get("uber_source") or "uber_unavailable",
        },
        "prefs": {
            "priority": prefs.priority,
            "max_walk_minutes": prefs.max_walk_minutes,
            "min_buffer": prefs.min_buffer,
            "frozen": list(prefs.frozen),
        },
        "intelligence": {
            "optimization_score": opt_score,
            "original_score": orig_score,
            "potential_improvements": len(history),
            "travel_time_saved_min": round(max(0.0, orig_time - opt_time)),
            "original_travel_min": round(orig_time),
            "optimized_travel_min": round(opt_time),
            "actions_evaluated": n_evaluated,
            "cost_saved": None,
            "cost_saved_estimate": round(max(0.0, orig_cost - opt_cost)),
            "cost_estimate_source": "demo_ranking",
            "walk_hops": walk_hops,
            "rideshare_hops": rideshare_hops,
        },
        "model": {**quality, "policy": policy},
        "undo_available": bool(snapshots),
        "snapshots": list(snapshots),
    }
