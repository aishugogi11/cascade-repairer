"""Preference-aware ranking on top of ML delay risk.

The classifier predicts disruption risk. This layer mixes that prediction
with the traveler's stated priorities and the Sabre itinerary fields so
the recommended flight changes when they say "price matters more" or
"I need to arrive before 9."
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, List, Optional, Sequence

from ml.inference import predict_delay_risk

PRIORITIES = {
    "risk": "lowest disruption risk",
    "price": "lowest price",
    "arrival": "earliest arrival",
    "nonstop": "nonstop flights",
    "duration": "shortest travel time",
}

# Weights sum to 1. The named priority takes the large share; delay risk
# always keeps a residual so a cheap high-risk connection cannot win a
# "price" rerank unchallenged.
_WEIGHTS = {
    "risk":     dict(risk=0.50, price=0.12, arrival=0.18, stops=0.12, duration=0.08),
    "price":    dict(risk=0.12, price=0.65, arrival=0.08, stops=0.10, duration=0.05),
    "arrival":  dict(risk=0.22, price=0.10, arrival=0.50, stops=0.10, duration=0.08),
    "nonstop":  dict(risk=0.22, price=0.10, arrival=0.13, stops=0.47, duration=0.08),
    "duration": dict(risk=0.22, price=0.10, arrival=0.13, stops=0.10, duration=0.45),
}


@dataclass
class TravelerPrefs:
    priority: str = "risk"
    arrive_before: Optional[str] = None  # "HH:MM" Pacific
    avoid_connections: bool = False

    def describe(self) -> str:
        bits = [PRIORITIES.get(self.priority, PRIORITIES["risk"])]
        if self.arrive_before:
            bits.append(f"arrive by {_clock_spoken(self.arrive_before)}")
        if self.avoid_connections:
            bits.append("avoid connections")
        return ", ".join(bits)


def parse_clock(value: str) -> Optional[str]:
    """'9', '9 AM', '09:00', '9:00am' → '09:00'. None if unparseable."""
    if not value:
        return None
    raw = value.strip().lower().replace(".", "")
    if not raw:
        return None
    ampm = None
    if raw.endswith("am") or raw.endswith("a.m"):
        ampm = "am"
        raw = raw[:-2].strip()
    elif raw.endswith("pm") or raw.endswith("p.m"):
        ampm = "pm"
        raw = raw[:-2].strip()
    raw = raw.replace(" ", "")
    try:
        if ":" in raw:
            h_s, m_s = raw.split(":", 1)
            hour, minute = int(h_s), int(m_s[:2])
        else:
            hour, minute = int(raw), 0
    except ValueError:
        return None
    if ampm == "am":
        hour = 0 if hour == 12 else hour
    elif ampm == "pm":
        hour = hour if hour == 12 else hour + 12
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def _minutes(clock: str) -> int:
    try:
        return int(clock[:2]) * 60 + int(clock[3:5])
    except (TypeError, ValueError):
        return 12 * 60


def _clock_spoken(clock: str) -> str:
    hour, minute = int(clock[:2]), int(clock[3:5])
    ampm = "AM" if hour < 12 else "PM"
    hour12 = hour % 12 or 12
    if minute:
        return f"{hour12}:{minute:02d} {ampm}"
    return f"{hour12} {ampm}"


def _minmax(values: Sequence[float], invert: bool) -> List[float]:
    """0 = worst in the set, 1 = best. Constant column → 1.0 for everyone."""
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [1.0] * len(values)
    scaled = [(v - lo) / (hi - lo) for v in values]
    if invert:
        return [1.0 - s for s in scaled]
    return scaled


@dataclass
class RankedFlight:
    option: Any
    delay_risk: float
    delay_risk_pct: int
    score: float
    recommended: bool
    why: List[str]
    factors: List[str]
    source: str
    misses_arrival_window: bool


def rank_options(
    options: Sequence[Any],
    prefs: Optional[TravelerPrefs] = None,
    arrive_target: Optional[str] = None,
) -> List[RankedFlight]:
    """Highest score first. Empty in → empty out. `arrive_target` (repair
    path) scores arrival as closeness to the cancelled flight's arrival
    instead of 'earliest wins'."""
    prefs = prefs or TravelerPrefs()
    if prefs.priority not in _WEIGHTS:
        prefs = replace(prefs, priority="risk")
    if not options:
        return []

    predictions = [predict_delay_risk(o) for o in options]
    prices = [float(getattr(o, "price", 0) or 0) for o in options]
    durations = [float(getattr(o, "duration_minutes", 0) or 0) for o in options]
    stops = [int(getattr(o, "stops", 0) or 0) for o in options]
    arrivals = [_minutes(getattr(o, "arrive_time", "12:00") or "12:00") for o in options]

    if arrive_target:
        target = _minutes(arrive_target)
        arrival_raw = [min(abs(a - target), 1440 - abs(a - target)) for a in arrivals]
        arrival_good = _minmax(arrival_raw, invert=True)
    else:
        arrival_good = _minmax(arrivals, invert=True)  # earlier is better

    price_good = _minmax(prices, invert=True)
    duration_good = _minmax(durations, invert=True)
    stops_good = [1.0 if s == 0 else (0.35 if s == 1 else 0.1) for s in stops]
    risk_good = [1.0 - p["delay_risk"] for p in predictions]

    cutoff = _minutes(prefs.arrive_before) if prefs.arrive_before else None
    weights = _WEIGHTS[prefs.priority]
    ranked: List[RankedFlight] = []
    for i, option in enumerate(options):
        score = (
            weights["risk"] * risk_good[i]
            + weights["price"] * price_good[i]
            + weights["arrival"] * arrival_good[i]
            + weights["stops"] * stops_good[i]
            + weights["duration"] * duration_good[i]
        )
        misses = False
        if cutoff is not None and arrivals[i] > cutoff:
            score *= 0.35
            misses = True
        if prefs.avoid_connections and stops[i] > 0:
            score *= 0.45
        ranked.append(RankedFlight(
            option=option,
            delay_risk=predictions[i]["delay_risk"],
            delay_risk_pct=predictions[i]["delay_risk_pct"],
            score=round(float(score), 4),
            recommended=False,
            why=[],
            factors=predictions[i]["factors"],
            source=predictions[i]["source"],
            misses_arrival_window=misses,
        ))

    ranked.sort(key=lambda r: (-r.score, r.delay_risk, float(getattr(r.option, "price", 0) or 0)))
    if ranked:
        ranked[0].recommended = True
        _fill_why(ranked, prefs, prices)
    return ranked


def _fill_why(ranked: List[RankedFlight], prefs: TravelerPrefs, prices: List[float]) -> None:
    cheapest = min(prices) if prices else 0
    pick = ranked[0]
    option = pick.option
    stops = int(getattr(option, "stops", 0) or 0)
    price = float(getattr(option, "price", 0) or 0)
    why = []
    if stops == 0:
        why.append("Nonstop")
    else:
        layovers = getattr(option, "layover_airports", None) or []
        if layovers:
            why.append("Connects in " + ", ".join(layovers))
        else:
            why.append("Has a connection")
    why.append(f"{pick.delay_risk_pct}% predicted disruption risk")
    if prefs.arrive_before:
        if pick.misses_arrival_window:
            why.append(f"Lands after {_clock_spoken(prefs.arrive_before)}")
        else:
            why.append(f"Arrives before {_clock_spoken(prefs.arrive_before)}")
    if price and cheapest and price - cheapest <= 30:
        extra = round(price - cheapest)
        if extra <= 0:
            why.append("Lowest fare in this set")
        else:
            why.append(f"Only ${extra} more than the cheapest option")
    elif price == cheapest:
        why.append("Lowest fare in this set")
    pick.why = why

    # Contrast line against a cheaper-but-riskier alternative, when one exists.
    for other in ranked[1:]:
        o_price = float(getattr(other.option, "price", 0) or 0)
        if o_price + 1 < price and other.delay_risk_pct >= pick.delay_risk_pct + 8:
            o_name = getattr(other.option, "airline_name", None) or "The cheaper option"
            pick.why.append(
                f"{o_name} is cheaper but at {other.delay_risk_pct}% delay risk"
            )
            break


def spoken_recommendation(ranked: List[RankedFlight], prefs: Optional[TravelerPrefs] = None) -> str:
    """The clause the Concierge reads before the numbered options."""
    prefs = prefs or TravelerPrefs()
    if not ranked:
        return ""
    n = len(ranked)
    count = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}.get(n, str(n))
    pick = ranked[0]
    goal = prefs.describe()
    if n == 1:
        lead = "I found one alternative."
    else:
        lead = f"I found {count} alternatives."
    return (
        f"{lead} Based on {goal}, I recommend option one"
        f" — {pick.delay_risk_pct} percent disruption risk."
    )
