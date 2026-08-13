"""Turn pasted text, a PDF, or an image caption into structured stops.

Heuristic parser is the default (hermetic tests, no API). OpenAI vision
and pypdf are optional upgrades when the traveler uploads a file.
"""
from __future__ import annotations

import base64
import io
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Alex Morgan's San Francisco weekend from sample_tripwise_itinerary.pdf
SAMPLE_ITINERARY = """Saturday, August 22
08:00 Breakfast — Union Square
09:30 Golden Gate Bridge Welcome Center
12:00 Lunch — Fisherman's Wharf
13:30 Alcatraz Ferry — Pier 33
16:30 Shopping — Union Square
18:00 Dinner — Mission District
19:30 Concert — Chase Center
22:45 Return to hotel — Union Square

Sunday, August 23
08:30 Breakfast — Union Square
10:00 Exploratorium — Pier 15
12:30 Lunch — North Beach
14:00 Lombard Street
15:30 Painted Ladies — Alamo Square
17:00 Hotel checkout — Union Square
18:30 Dinner — Hayes Valley
20:00 Airport departure — SFO
"""

SAMPLE_PREFS = {
    "priority": "time",
    "max_walk_minutes": 10,
    "min_buffer": 30,
    "frozen": ("alcatraz", "concert", "checkout"),
}

# SFO → New York business trip used as Cascade's optimization demo case.
SAMPLE_NYC_BUSINESS = """Monday, September 14
08:00 Flight UA 215 SFO-JFK
16:30 Airport transfer — JFK
18:00 Hotel check-in — Midtown
19:30 Dinner — Rockefeller Center

Tuesday, September 15
09:00 Client meeting — Financial District
12:00 Rockefeller Center — Midtown
15:00 Lunch — SoHo
17:00 Central Park
19:00 Dinner — Midtown

Wednesday, September 16
09:00 Hotel checkout — Midtown
11:00 Airport transfer — JFK
"""

# Crow-flies coords. Unknown titles fall back to Union Square (this demo city).
VENUE_COORDS: Dict[str, Tuple[float, float]] = {
    "union square": (37.7880, -122.4075),
    "hotel": (37.7880, -122.4075),
    "golden gate bridge": (37.8079, -122.4750),
    "golden gate bridge welcome center": (37.8079, -122.4750),
    "welcome center": (37.8079, -122.4750),
    "fisherman's wharf": (37.8080, -122.4177),
    "fishermans wharf": (37.8080, -122.4177),
    "pier 33": (37.8067, -122.4056),
    "alcatraz": (37.8067, -122.4056),
    "alcatraz ferry": (37.8067, -122.4056),
    "mission district": (37.7599, -122.4148),
    "mission": (37.7599, -122.4148),
    "chase center": (37.7680, -122.3877),
    "exploratorium": (37.8010, -122.3973),
    "pier 15": (37.8010, -122.3973),
    "north beach": (37.8002, -122.4096),
    "lombard street": (37.8021, -122.4187),
    "lombard": (37.8021, -122.4187),
    "painted ladies": (37.7763, -122.4328),
    "alamo square": (37.7763, -122.4328),
    "hayes valley": (37.7765, -122.4245),
    "sfo": (37.6213, -122.3790),
    "sfo airport": (37.6213, -122.3790),
    "airport": (37.6213, -122.3790),
    "the plaza": (40.7644, -73.9742),
    "plaza hotel": (40.7644, -73.9742),
    "moma": (40.7614, -73.9776),
    "museum of modern art": (40.7614, -73.9776),
    "the met": (40.7794, -73.9632),
    "metropolitan museum": (40.7794, -73.9632),
    "metropolitan museum of art": (40.7794, -73.9632),
    "standard grill": (40.7408, -74.0080),
    "the standard grill": (40.7408, -74.0080),
    "madison square garden": (40.7505, -73.9934),
    "msg": (40.7505, -73.9934),
    "jfk": (40.6413, -73.7781),
    "jfk airport": (40.6413, -73.7781),
    "lga": (40.7769, -73.8740),
    "laguardia": (40.7769, -73.8740),
    "ewr": (40.6895, -74.1745),
    "newark": (40.6895, -74.1745),
    "manhattan": (40.7580, -73.9855),
    "midtown": (40.7549, -73.9840),
    "times square": (40.7580, -73.9855),
    "financial district": (40.7075, -74.0113),
    "fidi": (40.7075, -74.0113),
    "soho": (40.7233, -74.0030),
    "soho lunch": (40.7233, -74.0030),
    "rockefeller": (40.7587, -73.9787),
    "rockefeller center": (40.7587, -73.9787),
    "central park": (40.7829, -73.9654),
}

ALT_PICKUPS: Dict[str, str] = {
    "chase center": "Chase Center East Entrance / Terry A Francois Blvd",
    "golden gate": "Welcome Center lower lot (not the plaza curb)",
    "fisherman": "Taylor Street side street",
    "union square": "Geary / Stockton side street",
    "alcatraz": "The Embarcadero / Pier 33 side curb",
    "pier 33": "The Embarcadero / Pier 33 side curb",
    "exploratorium": "The Embarcadero / Pier 15 side curb",
    "sfo": "Departures upper level — airline curb",
    "mission": "Valencia / 20th side street",
    "hayes": "Hayes / Laguna side street",
    "lombard": "Hyde Street downhill pickup",
    "alamo": "Steiner / Hayes side street",
    "painted ladies": "Steiner / Hayes side street",
    "madison square garden": "8th Avenue / 31st Street",
    "museum of modern art": "53rd Street pickup zone",
    "jfk": "Terminal arrivals curb — follow rideshare signs",
    "financial district": "Broadway / Pine side street",
    "soho": "West Broadway / Spring side street",
    "midtown": "6th Avenue / 49th side street",
    "rockefeller": "49th Street / 6th Avenue side street",
    "central park": "5th Avenue / 72nd Street",
}

# Colon times, or "9am" / "9 AM". Avoid matching years and bare dates.
_TIME_TOKEN = re.compile(
    r"(?<!\d)(\d{1,2}):(\d{2})(?:\s*([ap]\.?m\.?))?"
    r"|(?<!\d)(\d{1,2})\s*([ap]\.?m\.?)\b",
    re.I,
)
_DAY_HEADER = re.compile(
    r"^(saturday|sunday|monday|tuesday|wednesday|thursday|friday)"
    r"(,?\s+\w+\s+\d{1,2})?\s*$",
    re.I,
)
_TRANSPORT_TAIL = re.compile(
    r"\s*(walk\s*/\s*rideshare|rideshare|walk|transit|uber|lyft)\s*$",
    re.I,
)
_SKIP_TITLES = {
    "time", "activity", "location", "planned transportation",
    "time activity location planned transportation",
    "trip overview", "traveler preferences", "known constraints",
}

_WEEKDAY_INDEX = {
    "saturday": 0, "sunday": 1, "monday": 2, "tuesday": 3,
    "wednesday": 4, "thursday": 5, "friday": 6,
}


def _hour_minute(hour: int, minute: int, ampm: Optional[str]) -> str:
    if ampm:
        ampm = ampm.lower()
        if ampm == "am":
            hour = 0 if hour == 12 else hour
        elif ampm == "pm":
            hour = hour if hour == 12 else hour + 12
    hour = max(0, min(23, hour))
    minute = max(0, min(59, minute))
    return f"{hour:02d}:{minute:02d}"


_NYC_HINTS = (
    "jfk", "lga", "ewr", "manhattan", "midtown", "soho", "fidi",
    "financial", "rockefeller", "central park", "times square",
    "plaza", "moma", "newark",
)
_SF_FALLBACK = (37.7880, -122.4075)
_NYC_FALLBACK = (40.7549, -73.9840)


def geocode(title: str) -> Tuple[float, float]:
    key = (title or "").strip().lower()
    if key in VENUE_COORDS:
        return VENUE_COORDS[key]
    # Longer names first so "rockefeller center" wins over "center".
    for name, coords in sorted(VENUE_COORDS.items(), key=lambda kv: -len(kv[0])):
        if name in key or key in name:
            return coords
    if any(hint in key for hint in _NYC_HINTS):
        return _NYC_FALLBACK
    return _SF_FALLBACK


def alt_pickup_label(title: str) -> str:
    key = (title or "").strip().lower()
    for name, label in ALT_PICKUPS.items():
        if name in key:
            return label
    return "Side-street pickup zone"


def venue_type(title: str) -> str:
    t = (title or "").lower()
    if any(w in t for w in ("concert", "show", "chase center", "msg", "theatre", "theater")):
        return "concert"
    if any(w in t for w in ("museum", "moma", "met", "gallery", "exploratorium")):
        return "museum"
    if any(w in t for w in ("lunch", "dinner", "breakfast", "restaurant", "grill", "cafe", "pizza")):
        return "dining"
    if any(w in t for w in ("checkout", "check-out", "check-in", "return to hotel")):
        return "hotel"
    if "hotel" in t:
        return "hotel"
    if any(w in t for w in ("park", "lombard", "painted ladies", "alamo", "bridge", "central park")):
        return "park"
    if any(w in t for w in ("jfk", "lga", "ewr", "sfo", "airport", "flight")):
        return "airport"
    if any(w in t for w in ("meeting", "client")):
        return "meeting"
    return "other"


def is_anchored(title: str) -> bool:
    t = (title or "").lower()
    return any(w in t for w in (
        "concert", "chase center", "alcatraz", "ferry", "show", "flight",
        "reservation", "check-in", "check-out", "checkout", "airport", "sfo",
        "jfk", "meeting", "client",
    ))


def _clean_title(raw: str) -> str:
    text = raw.strip().strip("-–—:|•*")
    text = re.sub(
        r"^(on\s+)?(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b[:,]?\s*",
        "",
        text,
        flags=re.I,
    )
    text = _TRANSPORT_TAIL.sub("", text)
    text = re.sub(r"^(hotel|lunch|dinner|breakfast|concert)\s+at\s+", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    return text[:80]


def _clock_from_match(match: re.Match) -> str:
    if match.group(1) is not None:
        return _hour_minute(int(match.group(1)), int(match.group(2)), match.group(3))
    return _hour_minute(int(match.group(4)), 0, match.group(5))


def _make_stop(title: str, clock: str, day: int = 0) -> Dict[str, Any]:
    lat, lon = geocode(title)
    return {
        "title": title,
        "start_time": clock,
        "day": day,
        "location": title,
        "lat": lat,
        "lon": lon,
        "venue_type": venue_type(title),
        "anchored": is_anchored(title) or venue_type(title) in ("concert", "airport"),
        "pickup_label": "Main entrance",
        "alt_pickup_label": alt_pickup_label(title),
    }


def parse_text(text: str) -> List[Dict[str, Any]]:
    """Extract timed stops from pasted or PDF-extracted itinerary text."""
    lines = [ln.strip() for ln in (text or "").replace("\r", "\n").split("\n")]
    stops: List[Dict[str, Any]] = []
    i = 0
    day = 0
    last_minutes = -1
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line:
            continue
        if line.lower().startswith("traveler preferences") or line.lower().startswith("known constraints"):
            break
        if _DAY_HEADER.match(line):
            name = line.split(",", 1)[0].strip().lower()
            day = _WEEKDAY_INDEX.get(name, day)
            last_minutes = -1
            continue
        match = _TIME_TOKEN.search(line)
        if not match:
            continue
        clock = _clock_from_match(match)
        title = (line[:match.start()] + " " + line[match.end():]).strip()
        title = _clean_title(title)
        if len(title) < 2:
            while i < len(lines) and not lines[i]:
                i += 1
            if i < len(lines) and not _TIME_TOKEN.search(lines[i]) and not _DAY_HEADER.match(lines[i]):
                title = _clean_title(lines[i])
                i += 1
            while i < len(lines) and not lines[i]:
                i += 1
            if i < len(lines) and not _TIME_TOKEN.search(lines[i]) and not _DAY_HEADER.match(lines[i] or ""):
                nxt = lines[i].strip()
                if _TRANSPORT_TAIL.fullmatch(nxt) or nxt.lower() in {"walk", "rideshare", "transit"}:
                    i += 1
                elif nxt.lower() not in _SKIP_TITLES:
                    loc = _clean_title(nxt)
                    if loc and loc.lower() != title.lower():
                        title = f"{title} — {loc}"
                    i += 1
                    while i < len(lines) and not lines[i]:
                        i += 1
                    if i < len(lines) and (
                        _TRANSPORT_TAIL.fullmatch(lines[i].strip())
                        or lines[i].strip().lower() in {"walk", "rideshare", "transit"}
                    ):
                        i += 1
        if len(title) < 2 or re.fullmatch(r"[\d\s\-/#]+", title):
            continue
        if title.lower() in _SKIP_TITLES or title.lower() in {"am", "pm", "confirmation", "page"}:
            continue
        if len(title) > 70 or "fixed at" in title.lower() or "must arrive" in title.lower():
            continue
        minutes = int(clock[:2]) * 60 + int(clock[3:5])
        if last_minutes >= 0 and minutes + 8 * 60 < last_minutes:
            day += 1
        last_minutes = minutes
        stops.append(_make_stop(title, clock, day=day))
    deduped: List[Dict[str, Any]] = []
    seen = set()
    for stop in stops:
        key = (stop["day"], stop["start_time"], stop["title"].lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(stop)
    return deduped


def extract_pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        logger.info("pypdf not installed; cannot read PDF bytes")
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            chunk = page.extract_text() or ""
            if len(chunk.strip()) < 20:
                try:
                    chunk = page.extract_text(extraction_mode="layout") or chunk
                except TypeError:
                    pass
            pages.append(chunk)
        return "\n".join(pages)
    except Exception:  # noqa: BLE001
        logger.exception("PDF extract failed")
        return ""


def parse_pdf_bytes(data: bytes) -> List[Dict[str, Any]]:
    return parse_text(extract_pdf_text(data))


def _decode_b64(raw: str) -> bytes:
    blob = (raw or "").strip()
    if blob.lower().startswith("data:") and "," in blob:
        blob = blob.split(",", 1)[1]
    return base64.b64decode(blob)


def structure_with_llm(text: str) -> List[Dict[str, Any]]:
    """Turn messy extracted PDF/OCR text into timed lines, then parse_text."""
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        return []
    snippet = (text or "").strip()[:8000]
    if len(snippet) < 20:
        return []
    try:
        from openai import OpenAI
        client = OpenAI()
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{
                "role": "user",
                "content": (
                    "Extract the traveler's timed itinerary from this document text. "
                    "Return ONLY lines like '11:00 Museum of Modern Art'. "
                    "Use 24-hour times. Skip prices, confirmation numbers, and ads.\n\n"
                    + snippet
                ),
            }],
            max_tokens=500,
            temperature=0,
        )
        return parse_text((resp.choices[0].message.content or "").strip())
    except Exception:  # noqa: BLE001
        logger.exception("LLM itinerary structure failed")
        return []


def parse_image_via_openai(image_b64: str, mime: str = "image/png") -> List[Dict[str, Any]]:
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        return []
    try:
        from openai import OpenAI
        client = OpenAI()
        prompt = (
            "Extract the timed itinerary from this image. "
            "Return plain lines like '11:00 Museum of Modern Art'. "
            "No commentary."
        )
        resp = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{image_b64}"},
                    },
                ],
            }],
            max_tokens=400,
        )
        text = (resp.choices[0].message.content or "").strip()
        return parse_text(text)
    except Exception:  # noqa: BLE001
        logger.exception("vision itinerary extract failed")
        return []


def parse_upload(
    *,
    text: str = "",
    pdf_base64: str = "",
    image_base64: str = "",
    mime: str = "image/png",
    sample: bool = False,
    sample_kind: str = "",
) -> Dict[str, Any]:
    source = "text"
    raw = text or ""
    stops: List[Dict[str, Any]] = []
    kind = (sample_kind or "").strip().lower()
    if kind == "nyc" or (sample and kind == "nyc"):
        source = "sample_nyc"
        raw = SAMPLE_NYC_BUSINESS
        stops = parse_text(SAMPLE_NYC_BUSINESS)
    elif sample:
        source = "sample"
        raw = SAMPLE_ITINERARY
        stops = parse_text(SAMPLE_ITINERARY)
    elif pdf_base64:
        source = "pdf"
        try:
            raw = extract_pdf_text(_decode_b64(pdf_base64))
        except Exception:  # noqa: BLE001
            logger.exception("PDF base64 decode failed")
            raw = ""
        stops = parse_text(raw)
        if len(stops) < 2 and raw.strip():
            llm_stops = structure_with_llm(raw)
            if len(llm_stops) >= 2:
                stops = llm_stops
                source = "pdf_llm"
    elif image_base64:
        source = "image"
        stops = parse_image_via_openai(image_base64, mime=mime)
    if len(stops) < 2 and text and source != "sample":
        source = "text"
        raw = text
        stops = parse_text(text)
        if len(stops) < 2:
            llm_stops = structure_with_llm(text)
            if len(llm_stops) >= 2:
                stops = llm_stops
                source = "text_llm"
    return {
        "stops": stops,
        "source": source,
        "raw_text": raw,
        "raw_excerpt": (raw or "").strip()[:400],
        "ok": len(stops) >= 2,
    }
