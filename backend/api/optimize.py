"""Optimize My Trip — sessions, parse, ML ranking, voice prefs.

The voice/LLM layer extracts preferences and explains results. Ranking
always comes from ml.transport.optimize (trained model + constraints).
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from api import memory_trips
from api.pdf_itinerary import build_from_stops
from api.saily import plan_for_trip
from ml.transport.optimize import Prefs, optimize_stops, rebuild_after_undo
from ml.transport.parse import SAMPLE_ITINERARY, SAMPLE_PREFS, parse_upload
from ml.transport.predict import model_metrics

logger = logging.getLogger(__name__)

_SESSIONS: Dict[str, Dict[str, Any]] = {}
_CANONICAL: Optional[str] = None


def _blank_session() -> Dict[str, Any]:
    return {
        "stops": [],
        "parsed_stops": [],
        "prefs": Prefs(priority="time", max_walk_minutes=10),
        "result": None,
        "applied": False,
        "snapshots": [],
        "trip_id": None,
    }


def _has_trip(sess: Dict[str, Any]) -> bool:
    return len(sess.get("parsed_stops") or sess.get("stops") or []) >= 2


_CITY_DEST = {
    "JFK": "New York",
    "LGA": "New York",
    "EWR": "New York",
    "SFO": "San Francisco",
    "SJC": "San Jose",
    "OAK": "Oakland",
    "LAX": "Los Angeles",
    "MSP": "Minneapolis",
}


def _short_title(title: str) -> str:
    text = (title or "").strip()
    for sep in (" — ", " – ", " - "):
        if sep in text:
            text = text.split(sep, 1)[-1].strip()
            break
    return text or "this stop"


def _cascade_title(stops: list) -> str:
    """Prefer the flight route (SFO → New York) over first→last stop titles."""
    for stop in stops or []:
        title = (stop.get("title") or stop.get("location") or "").strip()
        if not title:
            continue
        route = re.search(
            r"\b([A-Z]{3})\s*(?:-|–|—|to|→)\s*([A-Z]{3})\b", title
        )
        if not route:
            continue
        if "flight" not in title.lower() and not re.search(
            r"\b[A-Z]{2}\s*\d{1,4}\b", title
        ):
            continue
        origin, dest = route.group(1), route.group(2)
        return f"{origin} → {_CITY_DEST.get(dest, dest)}"
    first = _short_title((stops[0] or {}).get("title") or "Uploaded trip")
    last = _short_title((stops[-1] or {}).get("title") or "")
    if last and last.lower() != first.lower() and last != "this stop":
        return f"{first} → {last}"
    return first if first != "this stop" else "Uploaded trip"


def _publish_cascade(sess: Dict[str, Any]) -> Optional[str]:
    """Write the uploaded/optimized stops onto the Cascade itinerary store."""
    stops = sess.get("stops") or sess.get("parsed_stops") or []
    if len(stops) < 2:
        return None
    built = build_from_stops(
        user_id="optimize-upload",
        title=_cascade_title(stops),
        stops=stops,
        trip_id=sess.get("trip_id") or "",
    )
    if built is None:
        return None
    trip, items = built
    trip.created_at = datetime.now(timezone.utc)
    seeded = memory_trips.put(trip, items)
    trip_id = seeded.get("trip_id") or trip.trip_id
    sess["trip_id"] = trip_id
    return trip_id


def _session(session_id: str) -> Dict[str, Any]:
    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = _blank_session()
    return _SESSIONS[session_id]


def _attach(session_id: str, trip_id: str = "") -> Dict[str, Any]:
    """Page UUID and Vocal Bridge room ids must share the same trip."""
    global _CANONICAL
    want = (trip_id or "").strip()
    sess = _session(session_id)
    if want:
        _ensure_stops(sess, want)
        if _has_trip(sess):
            _CANONICAL = session_id
            return sess
    if _has_trip(sess):
        _CANONICAL = session_id
        return sess
    if _CANONICAL and _CANONICAL in _SESSIONS and _has_trip(_SESSIONS[_CANONICAL]):
        _SESSIONS[session_id] = _SESSIONS[_CANONICAL]
        return _SESSIONS[session_id]
    for sid, other in reversed(list(_SESSIONS.items())):
        if sid != session_id and _has_trip(other):
            _SESSIONS[session_id] = other
            _CANONICAL = sid
            return other
    # uvicorn --reload (and Cloud Run cold starts) wipe _SESSIONS while the
    # uploaded trip still lives in memory_trips — adopt it so voice does not
    # claim the itinerary is missing.
    _ensure_stops(sess)
    if _has_trip(sess):
        _CANONICAL = session_id
    return sess


def _remember(session_id: str) -> None:
    global _CANONICAL
    _CANONICAL = session_id


def clear_sessions() -> None:
    global _CANONICAL
    _SESSIONS.clear()
    _CANONICAL = None


def _items_to_stops(items: list) -> list:
    from zoneinfo import ZoneInfo

    from ml.transport.parse import geocode, venue_type

    pacific = ZoneInfo("America/Los_Angeles")
    stops = []
    base_day = None
    for item in items:
        details = item.details or {}
        title = (details.get("title") or item.location or item.type or "").strip()
        if not title:
            continue
        lat = details.get("lat")
        lon = details.get("lon")
        if lat is None or lon is None:
            lat, lon = geocode(title)
        start_time = ""
        day = 0
        if item.start_ts is not None:
            local = (
                item.start_ts.astimezone(pacific)
                if item.start_ts.tzinfo
                else item.start_ts.replace(tzinfo=pacific)
            )
            start_time = f"{local.hour:02d}:{local.minute:02d}"
            if base_day is None:
                base_day = local.date()
            day = max((local.date() - base_day).days, 0)
        stops.append({
            "title": title,
            "location": item.location or title,
            "lat": lat,
            "lon": lon,
            "kind": item.type,
            "venue_type": venue_type(title),
            "start_time": start_time,
            "day": day,
        })
    return stops


def _stops_from_memory(trip_id: str = "") -> tuple:
    """Return (stops, trip_id) from Cascade memory, preferring Optimize uploads."""
    want = (trip_id or "").strip()
    if want:
        view = memory_trips.get(want)
        if view is not None and len(view.items) >= 2:
            return _items_to_stops(view.items), want
    preferred = []
    other = []
    for trip in memory_trips.list_recent():
        view = memory_trips.get(trip.trip_id)
        if view is None or len(view.items) < 2:
            continue
        bucket = preferred if (trip.user_id or "").startswith("optimize") else other
        bucket.append((trip.trip_id, view))
    for tid, view in preferred + other:
        return _items_to_stops(view.items), tid
    return [], None


def _ensure_stops(sess: Dict[str, Any], trip_id: str = "") -> Dict[str, Any]:
    """Hydrate an empty optimize session from a Cascade memory trip."""
    want = (trip_id or "").strip()
    if _has_trip(sess) and (not want or sess.get("trip_id") == want):
        return sess
    stops, bound_id = _stops_from_memory(want)
    if len(stops) < 2:
        return sess
    sess["parsed_stops"] = [dict(s) for s in stops]
    sess["stops"] = list(stops)
    if bound_id:
        sess["trip_id"] = bound_id
    sess["result"] = None
    sess["applied"] = False
    try:
        result = optimize_stops(sess["parsed_stops"], sess["prefs"])
        sess["snapshots"] = result.pop("snapshots", [])
        sess["result"] = result
        if result.get("optimized_stops"):
            sess["stops"] = result["optimized_stops"]
            sess["applied"] = True
    except Exception:  # noqa: BLE001 — still expose the loaded stops
        logger.exception("optimize recover from memory failed")
    return sess


def speak_first_stop_uber(session_id: str = "", trip_id: str = "") -> str:
    """Speak cheapest Uber from the first city hop on the loaded itinerary."""
    from ml.transport.rideshare import build_here_now, first_rideshare_pair

    sid = (session_id or "").strip() or "opt-voice"
    sess = _attach(sid, trip_id=trip_id)
    stops = sess.get("parsed_stops") or sess.get("stops") or []
    if len(stops) < 2:
        return (
            "I don't see your itinerary loaded yet. Open it on Cascade or "
            "Optimize My Trip, then ask again about the first stop."
        )
    pair = first_rideshare_pair(stops)
    if not pair:
        return "I need two nearby stops to look up an Uber from the first one."
    here = build_here_now(
        pair[0], pair[1],
        max_walk_minutes=sess["prefs"].max_walk_minutes,
    )
    if sess.get("result") is None:
        sess["result"] = {}
    sess["result"]["here_now"] = here
    return here.get("speak") or "I have your first-stop Uber context."


def parse_prefs(text: str, existing: Optional[Prefs] = None) -> Prefs:
    prefs = existing or Prefs()
    lower = (text or "").lower()
    priority = prefs.priority
    if any(w in lower for w in (
        "as fast", "fastest", "optimize for time", "optimize my trip for time",
        "save time", "quicker", "make this trip as fast",
        "don't care about price", "dont care about price",
        "don't mind spending", "dont mind spending",
        "spend more if it saves", "spend more to save",
    )):
        priority = "time"
    elif any(w in lower for w in (
        "cheap", "cost", "budget", "save money", "affordable",
        "cheapest rideshare", "stay under", "under $",
    )):
        priority = "cost"
    elif "walk" in lower and any(w in lower for w in ("prefer", "fine", "ok with", "don't mind")):
        priority = "walk"
    elif "balanced" in lower or "convenience" in lower:
        priority = "balanced"
    max_walk = prefs.max_walk_minutes
    if any(w in lower for w in ("hate walking", "hate to walk", "don't like walking", "dont like walking", "no walking")):
        max_walk = 4 if max_walk is None else min(max_walk, 4)
    match = re.search(r"(?:walk|walking)\s+(?:more than|over|over than|longer than)?\s*(\d+)\s*min", lower)
    if not match:
        match = re.search(r"(?:don't|do not|dont)\s+want to walk more than\s*(\d+)", lower)
    if not match:
        match = re.search(r"walk(?:ing)?\s*(?:≤|<=|under|max(?:imum)?)\s*(\d+)", lower)
    if match:
        max_walk = int(match.group(1))
    min_buffer = prefs.min_buffer
    buf = re.search(r"(\d+)\s*min(?:utes)?\s*(?:early|before|buffer)", lower)
    if buf:
        min_buffer = int(buf.group(1))
    frozen = list(prefs.frozen)
    if "don't change" in lower or "do not change" in lower or "dont change" in lower:
        for word in ("restaurant", "concert", "reservation", "hotel", "museum"):
            if word in lower and word not in frozen:
                frozen.append(word)
    return Prefs(
        priority=priority,
        max_walk_minutes=max_walk,
        min_buffer=min_buffer,
        frozen=tuple(frozen),
    )


def _hop_phrase(result: Dict[str, Any], hop: Any) -> str:
    stops = result.get("original_stops") or result.get("optimized_stops") or []
    if not isinstance(hop, int) or hop < 0 or hop + 1 >= len(stops):
        return ""
    a = _short_title(stops[hop].get("title") or "")
    b = _short_title(stops[hop + 1].get("title") or "")
    return f"from {a} to {b}"


def speak_recommendations(result: Dict[str, Any], prefs: Optional[Prefs] = None) -> str:
    """Voice-ready explanation of what the model changed and what the traveler should do."""
    intel = result.get("intelligence") or {}
    hist = [a for a in (result.get("action_history") or []) if (a.get("action") or "") != "KEEP_CURRENT_PLAN"]
    trans = result.get("transitions") or []
    here = result.get("here_now") or {}
    saved = intel.get("travel_time_saved_min") or 0
    n = intel.get("potential_improvements")
    if n is None:
        n = len(hist)
    orig_min = intel.get("original_travel_min")
    opt_min = intel.get("optimized_travel_min")

    if not n:
        return (
            "The action model kept your current transportation plan. "
            "Nothing needs to change unless you want a different walk cap or priority."
        )

    parts: list[str] = []
    headline = (
        f"Here's what I recommend. The model made {n} transportation change"
        f"{'' if n == 1 else 's'}"
    )
    days = intel.get("travel_by_day") or []
    per_day = " per day" if len(days) > 1 else ""
    if saved:
        headline += f", cutting travel time by about {saved} minutes{per_day}"
        if orig_min is not None and opt_min is not None:
            headline += f", from {orig_min} down to {opt_min}"
    parts.append(headline + ".")

    changed: list[str] = []
    for action in hist[:3]:
        hop = _hop_phrase(result, action.get("hop"))
        fr = action.get("from_value")
        to = action.get("to_value")
        label = (action.get("label") or "change").lower()
        if fr and to and hop:
            changed.append(f"{label} {hop}, {fr} to {to}")
        elif fr and to:
            changed.append(f"{label}: {fr} to {to}")
        elif hop:
            changed.append(f"{label} {hop}")
        else:
            changed.append(label)
    extra = n - len(changed)
    if changed:
        sentence = "What changed: " + "; ".join(changed)
        if extra > 0:
            sentence += f"; plus {extra} more on later hops"
        parts.append(sentence + ".")

    first = next((t for t in trans if t.get("changed")), None)
    if first:
        rec = first.get("recommended") or {}
        cur = first.get("current") or {}
        why = ((first.get("why") or [""])[0] or "").replace(" → ", " to ")
        hop_line = (
            f"The first hop that needs a change is {_short_title(first.get('from_title') or '')} "
            f"to {_short_title(first.get('to_title') or '')}: "
            f"use {rec.get('label') or 'the recommended mode'} instead of "
            f"{cur.get('label') or 'the current plan'}."
        )
        if why:
            hop_line += f" {why}."
        parts.append(hop_line)

    walk = next((t for t in trans if t.get("maps_url")), None)
    if walk:
        parts.append(
            f"There's a walking hop from {_short_title(walk.get('from_title') or '')} "
            f"to {_short_title(walk.get('to_title') or '')} — open the Google Maps "
            "route on the After timeline."
        )

    need: list[str] = []
    if here.get("over_walk_cap") and prefs and prefs.max_walk_minutes is not None:
        need.append(
            f"From {_short_title(here.get('at') or 'the first stop')}, don't walk — "
            f"it's over your {prefs.max_walk_minutes}-minute cap, so rideshare to "
            f"{_short_title(here.get('next') or 'the next stop')}"
        )
    elif prefs and prefs.max_walk_minutes is not None:
        walk_hops = intel.get("walk_hops")
        ride_hops = intel.get("rideshare_hops")
        if walk_hops is not None and ride_hops is not None:
            need.append(
                f"Walk only when it's under {prefs.max_walk_minutes} minutes "
                f"({walk_hops} walking hops, {ride_hops} rideshare)"
            )
    if any(a.get("action") in ("CHANGE_DEPARTURE_TIME", "ADD_BUFFER") for a in hist):
        mins = prefs.min_buffer if prefs and prefs.min_buffer else 15
        need.append(f"leave a few minutes earlier so you still arrive {mins} minutes early")
    if prefs and prefs.frozen:
        need.append("leave " + ", ".join(prefs.frozen) + " on their original times")
    if need:
        parts.append("What you need to do: " + "; ".join(need) + ".")
    return " ".join(p.strip() for p in parts if p.strip())


def _payload(session_id: str, reply: str, **extra: Any) -> Dict[str, Any]:
    sess = _session(session_id)
    result = sess.get("result") or {}
    body = {
        "reply": reply,
        "session_id": session_id,
        "stops": sess.get("stops") or [],
        "prefs": {
            "priority": sess["prefs"].priority,
            "max_walk_minutes": sess["prefs"].max_walk_minutes,
            "min_buffer": sess["prefs"].min_buffer,
            "frozen": list(sess["prefs"].frozen),
        },
        "applied": sess.get("applied", False),
        "trip_id": sess.get("trip_id"),
        "cascade_path": (
            f"/v1/cascade/?trip_id={sess['trip_id']}" if sess.get("trip_id") else ""
        ),
        **result,
        **extra,
    }
    body.pop("snapshots", None)
    stops = body.get("stops") or []
    dests = [s.get("title") or s.get("location") or "" for s in stops]
    origin = next(
        (s.get("location") or "" for s in stops if s.get("kind") == "flight"),
        "",
    )
    body["saily"] = plan_for_trip(
        origin=origin, destinations=dests, extra_places=dests,
    )
    return body


def ingest(
    session_id: str,
    *,
    text: str = "",
    pdf_base64: str = "",
    image_base64: str = "",
    mime: str = "image/png",
    sample: bool = False,
    sample_kind: str = "",
) -> Dict[str, Any]:
    sess = _session(session_id)
    parsed = parse_upload(
        text=text,
        pdf_base64=pdf_base64,
        image_base64=image_base64,
        mime=mime,
        sample=sample,
        sample_kind=sample_kind,
    )
    if not parsed["ok"]:
        hint = (
            "I need a timed itinerary — at least two lines like "
            "'11:00 Museum of Modern Art'. You can paste text, upload a PDF, "
            "or try the sample San Francisco weekend."
        )
        excerpt = (parsed.get("raw_excerpt") or "").strip()
        if parsed["source"] in ("image",):
            hint = (
                "I couldn't read timed stops from that image. Paste the "
                "itinerary as text, or try the sample trip."
            )
        elif parsed["source"] in ("pdf", "pdf_llm"):
            if not excerpt:
                hint = (
                    "That PDF looks like a scan or image — I couldn't extract "
                    "text. Upload a screenshot of the timeline, or paste the "
                    "times and places as text."
                )
            else:
                hint = (
                    "I read the PDF but couldn't find two timed stops "
                    "(like '11:00 Museum of Modern Art'). Paste the itinerary "
                    "as text if the times are in a table or graphic."
                )
        return _payload(
            session_id, hint, ok=False, parse_source=parsed["source"],
            raw_excerpt=excerpt,
        )
    sess["stops"] = parsed["stops"]
    sess["parsed_stops"] = [dict(s) for s in parsed["stops"]]
    sess["applied"] = False
    titles = " ".join(s.get("title") or "" for s in parsed["stops"]).lower()
    if sample or "chase center" in titles or "alcatraz" in titles:
        sess["prefs"] = Prefs(
            priority=SAMPLE_PREFS["priority"],
            max_walk_minutes=SAMPLE_PREFS["max_walk_minutes"],
            min_buffer=SAMPLE_PREFS["min_buffer"],
            frozen=tuple(SAMPLE_PREFS["frozen"]),
        )
    result = optimize_stops(sess["parsed_stops"], sess["prefs"])
    sess["snapshots"] = result.pop("snapshots", [])
    sess["result"] = result
    if result.get("optimized_stops"):
        sess["stops"] = result["optimized_stops"]
        sess["applied"] = True
    _publish_cascade(sess)
    _remember(session_id)
    opener = f"I extracted {len(parsed['stops'])} stops. "
    reply = opener + speak_recommendations(result, sess["prefs"])
    return _payload(session_id, reply, ok=True, parse_source=parsed["source"])


def reoptimize(session_id: str, prefs: Optional[Prefs] = None) -> Dict[str, Any]:
    sess = _attach(session_id)
    if prefs is not None:
        sess["prefs"] = prefs
    base = sess.get("parsed_stops") or sess.get("stops") or []
    if len(base) < 2:
        if prefs is not None:
            _session(session_id)["prefs"] = prefs
        loaded = ingest(session_id, sample=True)
        if loaded.get("ok"):
            loaded["reply"] = (
                "Loaded the sample San Francisco weekend. " + (loaded.get("reply") or "")
            )
        return loaded
    sess["result"] = optimize_stops(base, sess["prefs"])
    sess["snapshots"] = sess["result"].pop("snapshots", [])
    sess["applied"] = False
    if sess["result"].get("optimized_stops"):
        sess["stops"] = sess["result"]["optimized_stops"]
        sess["applied"] = True
    _publish_cascade(sess)
    reply = (
        f"Re-ran the action loop with {sess['prefs'].describe()}. "
        + speak_recommendations(sess["result"], sess["prefs"])
    )
    return _payload(session_id, reply, ok=True)


def apply_recommendations(session_id: str) -> Dict[str, Any]:
    sess = _attach(session_id)
    result = sess.get("result")
    if not result:
        return ingest(session_id, sample=True)
    if result.get("optimized_stops"):
        sess["stops"] = result["optimized_stops"]
    sess["applied"] = True
    _publish_cascade(sess)
    return _payload(
        session_id,
        speak_recommendations(result, sess["prefs"])
        + " The itinerary on screen is the updated trip. Say undo to roll back the last action.",
        ok=True,
    )


def undo_last(session_id: str) -> Dict[str, Any]:
    sess = _attach(session_id)
    result = sess.get("result") or {}
    history = list(result.get("action_history") or [])
    snaps = list(sess.get("snapshots") or [])
    if not history or not snaps:
        return _payload(session_id, "Nothing to undo.", ok=False)
    snap = snaps.pop()
    last = history.pop()
    sess["snapshots"] = snaps
    rebuilt = rebuild_after_undo(result, snap, history, sess["prefs"], snaps)
    if snap.get("stops"):
        sess["stops"] = snap["stops"]
    sess["result"] = rebuilt
    sess["applied"] = True
    return _payload(
        session_id,
        f"Undid {last.get('label') or last.get('action')}. The itinerary is back one step.",
        ok=True,
    )


def _wants_itinerary_confirm(text: str) -> bool:
    lower = (text or "").lower()
    if not any(w in lower for w in ("itinerary", "my trip", "my plan", "my stops")):
        return False
    return any(w in lower for w in (
        "have my", "got my", "see my", "get my", "getting my",
        "know my", "loaded", "on file", "do you have", "can you see",
        "what's on", "what is on", "tell me about",
    ))


def _confirm_itinerary_reply(sess: Dict[str, Any]) -> str:
    stops = sess.get("parsed_stops") or sess.get("stops") or []
    n = len(stops)
    title = _cascade_title(stops) if n >= 2 else "your trip"
    first = _short_title((stops[0] or {}).get("title") or "") if stops else ""
    last = _short_title((stops[-1] or {}).get("title") or "") if n > 1 else ""
    span = f" from {first} to {last}" if first and last and first != last else ""
    return (
        f"Yes — I have your {title} itinerary with {n} stops{span}. "
        "Ask what I recommend, or say Uber from the first stop."
    )


async def apply_turn(
    session_id: str, message: str, trip_id: str = "",
) -> Dict[str, Any]:
    text = (message or "").strip()
    lower = text.lower()
    sess = _attach(session_id, trip_id=trip_id)

    if lower in ("sample", "try sample", "demo trip", "use the sample"):
        return ingest(session_id, sample=True)

    wants_here = any(w in lower for w in (
        "cheapest uber", "cheap uber", "uber from here", "uber should i",
        "what uber", "live uber", "first stop", "from the first",
        "from union square", "uber from the first",
        "i'm at the first", "im at the first", "standing at",
        "best option", "best way", "best rideshare", "from this stop",
    ))
    wants_run = any(w in lower for w in (
        "optimize", "improve", "better pickup", "best rideshare",
        "as fast", "cheapest", "apply", "do it", "go ahead",
    ))
    if any(w in lower for w in ("undo", "roll back", "revert")):
        return undo_last(session_id)

    if _wants_itinerary_confirm(text):
        if not _has_trip(sess):
            return _payload(
                session_id,
                "I don't see an itinerary on this page yet. Upload or paste "
                "your trip, or say 'try sample'.",
                ok=False,
            )
        return _payload(session_id, _confirm_itinerary_reply(sess), ok=True)

    if wants_here:
        mem_stops, _ = _stops_from_memory()
        if not _has_trip(sess) and not mem_stops:
            ingest(session_id, sample=True)
        reply = speak_first_stop_uber(session_id)
        ok = "Load the itinerary" not in reply and "need two" not in reply.lower()
        return _payload(session_id, reply, ok=ok)

    if wants_run and not _has_trip(sess):
        ingest(session_id, sample=True)
        sess = _attach(session_id, trip_id=trip_id)

    if any(w in lower for w in (
        "why did you", "why lyft", "why uber", "why that pickup",
        "what's the best rideshare", "best rideshare",
        "what changed", "what did you change", "what's recommended",
        "what is recommended", "what do you recommend", "any recommendation",
        "explain the", "walk me through", "what do i need", "what should i do",
        "what's the plan", "the recommendation", "what needs to",
    )):
        result = sess.get("result") or {}
        if result.get("action_history") or result.get("transitions"):
            return _payload(
                session_id,
                speak_recommendations(result, sess["prefs"]),
                ok=True,
            )
        return _payload(
            session_id,
            "Upload an itinerary or say 'try sample', then I can explain what the model recommends.",
            ok=False,
        )

    if any(w in lower for w in ("apply", "do it", "make the change", "optimize it", "go ahead", "find a better pickup")):
        if sess.get("result"):
            prefs = parse_prefs(text, sess["prefs"])
            if prefs.priority != sess["prefs"].priority or "pickup" in lower or "optimize" in lower:
                ranked = reoptimize(session_id, prefs)
                applied = apply_recommendations(session_id)
                applied["reply"] = ranked["reply"] + " " + applied["reply"]
                return applied
            return apply_recommendations(session_id)

    looks_timed = bool(re.search(r"\b\d{1,2}:\d{2}\b", text))
    if looks_timed:
        return ingest(session_id, text=text)

    prefs = parse_prefs(text, sess["prefs"])
    prefs_changed = (
        prefs.priority != sess["prefs"].priority
        or prefs.max_walk_minutes != sess["prefs"].max_walk_minutes
        or prefs.min_buffer != sess["prefs"].min_buffer
        or prefs.frozen != sess["prefs"].frozen
    )
    if prefs_changed and sess.get("stops"):
        out = reoptimize(session_id, prefs)
        if any(w in lower for w in ("optimize", "apply", "do it")):
            applied = apply_recommendations(session_id)
            out["reply"] = out["reply"] + " " + applied["reply"]
            out["applied"] = True
        return out

    if not sess.get("stops"):
        return _payload(
            session_id,
            "I don't see an itinerary on this page yet. Upload or paste your "
            "trip, or say 'try sample', and I'll score every hop.",
            ok=False,
        )

    intel = (sess.get("result") or {}).get("intelligence") or {}
    result = sess.get("result") or {}
    if result.get("action_history") or result.get("transitions"):
        return _payload(
            session_id,
            speak_recommendations(result, sess["prefs"])
            + " Ask me about the cheapest Uber from the first stop, or say undo.",
            ok=True,
        )
    return _payload(
        session_id,
        f"This trip’s model score is {intel.get('optimization_score', '—')} / 100 "
        f"with {intel.get('potential_improvements', 0)} executed actions. "
        "Say 'what do you recommend', 'cheapest Uber from the first stop', or 'undo'.",
        ok=True,
    )


def session_state(session_id: str) -> Dict[str, Any]:
    return _payload(session_id, "", ok=True)


def metrics() -> Dict[str, Any]:
    return model_metrics()


def sample_text() -> str:
    return SAMPLE_ITINERARY
