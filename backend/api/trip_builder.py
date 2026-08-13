"""Build My Trip — conversational extract, real research, structured itinerary.

Drafts live in-process (the concierge session pattern). Saving writes a
Trip + itinerary_items through the existing repositories so Cascade
Repairer can disrupt and recover the same trip.
"""
from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from api.flight_options import _PACIFIC, _parse_instaflights_options
from api.repositories import itinerary_items, trips
from api.repositories.models import ItineraryItem, Trip
from api.sabre import client as sabre_client
from api.sabre import shapes

logger = logging.getLogger(__name__)

_DRAFTS: Dict[str, "TripDraft"] = {}
_PROGRESS: Dict[str, List[dict]] = {}

CITY_ALIASES = {
    "nyc": "New York", "new york": "New York", "new york city": "New York",
    "sf": "San Francisco", "san francisco": "San Francisco",
    "la": "Los Angeles", "los angeles": "Los Angeles", "lax": "Los Angeles",
    "chi": "Chicago", "chicago": "Chicago",
    "sea": "Seattle", "seattle": "Seattle",
    "bos": "Boston", "boston": "Boston",
    "mia": "Miami", "miami": "Miami",
    "sfo": "San Francisco", "jfk": "New York",
}

ORIGIN_AIRPORTS = {
    "New York": "JFK", "San Francisco": "SFO", "Los Angeles": "LAX",
    "Chicago": "ORD", "Seattle": "SEA", "Boston": "BOS", "Miami": "MIA",
}

_WORD_DAYS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

INTEREST_WORDS = {
    "museum": "museums", "museums": "museums",
    "food": "food", "restaurant": "food", "restaurants": "food",
    "eat": "food", "dining": "food",
    "walk": "walking", "walking": "walking",
    "hike": "hiking", "hiking": "hiking",
    "beach": "beaches", "art": "art",
    "nightlife": "nightlife", "coffee": "coffee",
    "park": "parks", "parks": "parks",
    "history": "history", "shopping": "shopping",
}

STEP_DEFS = [
    ("prefs", "Understanding your preferences"),
    ("places", "Finding places you'll probably like"),
    ("food", "Finding restaurants that fit"),
    ("times", "Checking travel times and weather"),
    ("days", "Organizing your days"),
    ("optimize", "Optimizing the itinerary"),
]

CATEGORY_SPECS = {
    "museums": {
        "label": "museums",
        "item_type": "experience",
        "query": "top named museums to visit in {dest} official museum names",
    },
    "food": {
        "label": "food",
        "item_type": "dining",
        "query": "best named restaurants in {dest} official restaurant names",
    },
    "walking": {
        "label": "walking",
        "item_type": "experience",
        "query": "best walking neighborhoods and parks in {dest} named places",
    },
    "hiking": {
        "label": "hiking",
        "item_type": "experience",
        "query": "best named hikes and trails near {dest}",
    },
    "beaches": {
        "label": "beaches",
        "item_type": "experience",
        "query": "best named beaches in {dest}",
    },
    "nightlife": {
        "label": "nightlife",
        "item_type": "experience",
        "query": "best named nightlife spots in {dest}",
    },
    "coffee": {
        "label": "coffee",
        "item_type": "dining",
        "query": "best named coffee shops in {dest}",
    },
    "shopping": {
        "label": "shopping",
        "item_type": "experience",
        "query": "best named shopping streets and markets in {dest}",
    },
    "sights": {
        "label": "sights",
        "item_type": "experience",
        "query": "top named attractions in {dest} official place names",
    },
}

_INTEREST_TO_CATEGORY = {
    "museums": "museums", "art": "museums",
    "food": "food",
    "walking": "walking", "parks": "walking",
    "hiking": "hiking",
    "beaches": "beaches",
    "nightlife": "nightlife",
    "coffee": "coffee",
    "history": "sights",
    "shopping": "shopping",
}

_ARTICLE_RE = re.compile(
    r"(?i)(\bthe top\b|\btop named\b|\bbest named\b|\bnamed (museums|restaurants|"
    r"attractions|places)\b|\bto visit in\b|\bofficial .{0,20} names\b|"
    r"\bbest\b|\btop\s+\d+|guide|bucket list|things to do|tripadvisor|"
    r"where to eat|foodie|ultimate|must-try|photos|useful guide|"
    r"first-time|conventions|right now|roundup|list of|to do in|"
    r"greatest|treasures|& their)"
)
_GENERIC_PLACES = {
    "new york", "nyc", "new york city", "san francisco", "los angeles",
    "chicago", "seattle", "boston", "miami", "united states", "usa",
}


class TripPrefs(BaseModel):
    destination: str = ""
    origin: str = ""
    start_date: str = ""
    end_date: str = ""
    duration_days: Optional[int] = None
    budget: str = ""
    interests: List[str] = Field(default_factory=list)
    food_preferences: str = ""
    travel_style: str = ""
    pace: str = ""
    must_see: List[str] = Field(default_factory=list)
    avoid: List[str] = Field(default_factory=list)
    accommodation: str = ""
    transportation: str = ""


class DraftItem(BaseModel):
    item_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str  # flight|hotel|ground|dining|experience
    title: str
    date: str = ""
    start_time: str = ""
    end_time: str = ""
    location: str = ""
    duration_minutes: Optional[int] = None
    importance: str = "normal"  # must_keep | normal
    flexibility: str = "high"  # low | high
    source: str = ""
    reason: str = ""


class TripDraft(BaseModel):
    session_id: str
    prefs: TripPrefs = Field(default_factory=TripPrefs)
    messages: List[dict] = Field(default_factory=list)
    research: Dict[str, Any] = Field(default_factory=dict)
    items: List[DraftItem] = Field(default_factory=list)
    trip_id: Optional[str] = None
    title: str = ""
    phase: str = "gathering"  # gathering | offering | done
    pending_categories: List[str] = Field(default_factory=list)
    current_category: str = ""
    current_offers: List[dict] = Field(default_factory=list)
    accepted: List[dict] = Field(default_factory=list)


def _today() -> date:
    return datetime.now(_PACIFIC).date()


def _parse_iso(value: str) -> Optional[date]:
    try:
        return date.fromisoformat((value or "").strip()[:10])
    except ValueError:
        return None


def _spoken_date(d: date) -> str:
    return f"{d.strftime('%b')} {d.day}"


def heuristic_extract(text: str, existing: Optional[TripPrefs] = None) -> TripPrefs:
    """Keyword extract so the tab works without an LLM in tests/CI."""
    prefs = (existing or TripPrefs()).model_copy(deep=True)
    raw = (text or "").strip()
    lower = raw.lower()

    for key, city in CITY_ALIASES.items():
        if re.search(rf"\bfrom\s+{re.escape(key)}\b", lower):
            prefs.origin = city
            break
    for key, city in CITY_ALIASES.items():
        if re.search(rf"\bto\s+{re.escape(key)}\b", lower):
            prefs.destination = city
            break
    if not prefs.destination:
        for key, city in CITY_ALIASES.items():
            if re.search(rf"\b{re.escape(key)}\b", lower):
                if city != prefs.origin:
                    prefs.destination = city
                    break

    days = re.search(r"\b(\d+)\s*-?\s*days?\b", lower)
    if days:
        prefs.duration_days = int(days.group(1))
    else:
        word = re.search(
            r"\b(" + "|".join(_WORD_DAYS) + r")\s*-?\s*days?\b", lower
        )
        if word:
            prefs.duration_days = _WORD_DAYS[word.group(1)]

    iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", raw)
    if iso and not prefs.start_date:
        prefs.start_date = iso.group(1)

    month = re.search(
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|"
        r"nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:\s*[–-]\s*(\d{1,2}))?"
        r"(?:,?\s*(20\d{2}))?",
        lower,
    )
    if month and not prefs.start_date:
        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        token = month.group(1)[:3]
        year = int(month.group(4) or _today().year)
        start = date(year, months[token], int(month.group(2)))
        prefs.start_date = start.isoformat()
        if month.group(3):
            prefs.end_date = date(year, months[token], int(month.group(3))).isoformat()

    if any(w in lower for w in ("affordable", "cheap", "budget", "not spend too much",
                                 "don't want to spend", "dont want to spend")):
        prefs.budget = "affordable"
    elif any(w in lower for w in ("luxury", "splurge", "nice hotels")):
        prefs.budget = "upscale"

    if "walk" in lower:
        prefs.transportation = "walking"
        prefs.travel_style = prefs.travel_style or "on foot"
    if "relax" in lower or "slow" in lower:
        prefs.pace = "relaxed"
    elif "packed" in lower or "busy" in lower:
        prefs.pace = "full"

    for word, label in INTEREST_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", lower) and label not in prefs.interests:
            prefs.interests.append(label)

    if "food" in prefs.interests and not prefs.food_preferences:
        prefs.food_preferences = "good food"
    if "good food" in lower and "food" not in prefs.interests:
        prefs.interests.append("food")
        prefs.food_preferences = prefs.food_preferences or "good food"

    must = re.search(r"(?:must(?:-|\s)?see|have to see|want to see|visit)\s+([^.!?]+)", lower)
    if must:
        bit = must.group(1).strip(" .")
        if bit and bit not in prefs.must_see:
            prefs.must_see.append(bit)

    avoid = re.search(r"(?:avoid|don't want|do not want)\s+([^.!?]+)", lower)
    if avoid:
        bit = avoid.group(1).strip(" .")
        if bit and bit not in prefs.avoid:
            prefs.avoid.append(bit)

    _fill_dates(prefs)
    return prefs


def _fill_dates(prefs: TripPrefs) -> None:
    start = _parse_iso(prefs.start_date)
    end = _parse_iso(prefs.end_date)
    days = prefs.duration_days
    if start and days and not end:
        prefs.end_date = (start + timedelta(days=max(days, 1) - 1)).isoformat()
    elif start and end and not days:
        prefs.duration_days = max((end - start).days + 1, 1)
    elif days and not start:
        start = _today() + timedelta(days=2)
        prefs.start_date = start.isoformat()
        prefs.end_date = (start + timedelta(days=max(days, 1) - 1)).isoformat()


def missing_fields(prefs: TripPrefs) -> List[str]:
    missing = []
    if not prefs.destination:
        missing.append("destination")
    if not prefs.start_date and not prefs.duration_days:
        missing.append("dates")
    return missing


def follow_up_question(prefs: TripPrefs) -> str:
    miss = missing_fields(prefs)
    if "destination" in miss:
        return "Where are you headed?"
    if "dates" in miss:
        dest = prefs.destination or "there"
        return f"Got it. What dates are you traveling to {dest}?"
    return ""


def _draft(session_id: str) -> TripDraft:
    if session_id not in _DRAFTS:
        _DRAFTS[session_id] = TripDraft(session_id=session_id)
    return _DRAFTS[session_id]


def category_queue(prefs: TripPrefs) -> List[str]:
    order: List[str] = []
    for interest in prefs.interests:
        cat = _INTEREST_TO_CATEGORY.get(interest, "sights")
        if cat not in order:
            order.append(cat)
    if not order:
        order = ["sights", "food"]
    return order


def _clean_place_title(title: str) -> str:
    title = (title or "").strip()
    title = re.split(r"\s+[|\-–—]\s+", title)[0].strip()
    title = re.sub(r"\s*\(wikipedia\)", "", title, flags=re.I)
    return title.strip(" .")


def _is_place_name(title: str, dest: str) -> bool:
    if not title or len(title) < 3 or len(title) > 70:
        return False
    if _ARTICLE_RE.search(title):
        return False
    lowered = title.lower().strip()
    if lowered in _GENERIC_PLACES or lowered == (dest or "").lower():
        return False
    if dest and re.search(rf"\bin {re.escape(dest)}\b", title, re.I):
        return False
    if re.match(r"^\d+\s", title):
        return False
    return bool(re.search(r"[A-Z]", title))


def extract_venues(blob: dict, dest: str, limit: int = 3) -> List[dict]:
    """Turn Tavily hits into named places. Drops listicle/article titles."""
    seen = set()
    venues: List[dict] = []

    def add(title: str, snippet: str) -> None:
        title = _clean_place_title(title)
        key = re.sub(r"[^a-z0-9]", "", title.lower())
        if not key or key in seen or not _is_place_name(title, dest):
            return
        seen.add(key)
        snippet = (snippet or "").strip()
        venues.append({
            "title": title,
            "snippet": snippet[:220],
            "why": snippet[:160] or f"A strong {dest} pick from live search.",
            "source": "tavily",
        })

    for place in blob.get("places") or []:
        add(place.get("title") or "", place.get("snippet") or "")
        if len(venues) >= limit:
            return venues[:limit]
    answer = (blob.get("answer") or "").strip()
    if answer:
        chunk = re.sub(r"\s+and\s+", ", ", answer)
        for part in chunk.split(","):
            part = re.split(r"\s+\b(are|is|was|were)\b", part)[0]
            add(part.split(".")[0], f"Often recommended in {dest}.")
            if len(venues) >= limit:
                break
    return venues[:limit]


def _short_name(title: str) -> str:
    if title.isupper() and 2 <= len(title) <= 6:
        return title
    if "(" in title and ")" in title:
        inner = title[title.find("(") + 1:title.find(")")]
        if inner:
            return inner
    words = [w for w in re.split(r"\s+", title) if w.lower() not in ("the", "of", "and")]
    if words:
        return words[0]
    return title


def parse_choice(text: str, offers: List[dict]) -> Optional[str]:
    """Map a traveler utterance onto an offer. None = ask again."""
    if not offers:
        return "skip"
    lower = (text or "").lower().strip()
    named = []
    for offer in offers:
        title = offer["title"]
        needles = {title.lower(), _short_name(title).lower()}
        if any(n and n in lower for n in needles if len(n) >= 3):
            named.append(title)
    if named:
        if len(named) > 1:
            return "all:" + "|".join(named)
        return named[0]
    if re.search(r"\b(all of them|add (them )?all|both)\b", lower):
        return "all"
    if re.search(r"\b(skip|pass|next category|not those)\b", lower):
        return "skip"
    if re.search(r"^\s*(no|nah|nope)\s*[.!]?\s*$", lower):
        return "skip"
    ordinals = [
        (r"\b(option\s*(1|one)|the first|number one)\b", 0),
        (r"\b(option\s*(2|two)|the second|number two)\b", 1),
        (r"\b(option\s*(3|three)|the third|number three)\b", 2),
    ]
    for pattern, idx in ordinals:
        if re.search(pattern, lower) and idx < len(offers):
            return offers[idx]["title"]
    if re.search(
        r"\b(yes|yeah|yep|yup|sure|okay|ok|add it|sounds good|that one|please|go ahead)\b",
        lower,
    ):
        return "recommended"
    if re.search(r"\b(just build|surprise me|skip (the )?questions|build (it|the trip|the itinerary))\b", lower):
        return "compose"
    return None


def _rewrite_last_reply(draft: TripDraft, payload: dict, reply: str) -> dict:
    payload["reply"] = reply
    if draft.messages and draft.messages[-1]["role"] == "assistant":
        draft.messages[-1]["text"] = reply
    return payload


def _payload(draft: TripDraft, reply: str, **extra: Any) -> dict:
    draft.messages.append({"role": "assistant", "text": reply})
    body = {
        "reply": reply,
        "prefs": draft.prefs.model_dump(),
        "ready": not missing_fields(draft.prefs),
        "missing": missing_fields(draft.prefs),
        "phase": draft.phase,
        "category": draft.current_category,
        "offers": list(draft.current_offers),
        "accepted": list(draft.accepted),
        "items": [i.model_dump() for i in draft.items],
        "title": draft.title,
        "session_id": draft.session_id,
    }
    body.update(extra)
    return body


def _speak_offer(dest: str, category: str, offers: List[dict]) -> str:
    spec = CATEGORY_SPECS.get(category, CATEGORY_SPECS["sights"])
    label = spec["label"]
    if not offers:
        return (
            f"I couldn't find live {label} listings in {dest} just now. "
            "Say skip and I'll move on, or say build it to assemble the trip."
        )
    rec = offers[0]
    lines = [f"For {label} in {dest}, here are {len(offers)} strong options."]
    for i, offer in enumerate(offers):
        mark = " I'd start here." if i == 0 else ""
        why = offer.get("why") or offer.get("snippet") or ""
        why = why.split(".")[0].strip()
        bit = f"{offer['title']}"
        if why:
            bit += f" — {why}"
        bit += mark
        lines.append(bit)
    lines.append(f"Want me to add {rec['title']}? Say yes, name another, or say skip.")
    return " ".join(lines)


async def _open_next_category(draft: TripDraft) -> dict:
    dest = draft.prefs.destination or "your destination"
    while draft.pending_categories:
        category = draft.pending_categories.pop(0)
        spec = CATEGORY_SPECS.get(category, CATEGORY_SPECS["sights"])
        query = spec["query"].format(dest=dest)
        _set_step(draft.session_id, "places", ["prefs"])
        blob = await _research_one(query)
        offers = extract_venues(blob, dest, limit=3)
        for offer in offers:
            offer["type"] = spec["item_type"]
            offer["category"] = category
            offer["recommended"] = False
        if offers:
            offers[0]["recommended"] = True
        draft.current_category = category
        draft.current_offers = offers
        draft.phase = "offering"
        return _payload(draft, _speak_offer(dest, category, offers))
    return await _compose_from_picks(draft)


def _accept_offers(draft: TripDraft, chosen: List[dict]) -> None:
    for offer in chosen:
        row = {
            "title": offer["title"],
            "snippet": offer.get("snippet") or "",
            "why": offer.get("why") or "",
            "type": offer.get("type") or "experience",
            "category": offer.get("category") or draft.current_category,
            "source": offer.get("source") or "tavily",
        }
        if not any(a["title"].lower() == row["title"].lower() for a in draft.accepted):
            draft.accepted.append(row)


async def _compose_from_picks(draft: TripDraft) -> dict:
    draft.phase = "done"
    draft.current_offers = []
    draft.current_category = ""
    built = await build_itinerary(draft.session_id)
    picks = ", ".join(a["title"] for a in draft.accepted) or "your preferences"
    reply = (
        f"Added to your itinerary. I shaped the days around {picks}. "
        "Star anything Cascade must protect."
    )
    built["reply"] = reply
    built["phase"] = "done"
    built["offers"] = []
    built["accepted"] = list(draft.accepted)
    draft.messages.append({"role": "assistant", "text": reply})
    return built


async def apply_turn(session_id: str, message: str) -> dict:
    """One conversational beat: gather prefs, offer a category, or confirm a pick."""
    draft = _draft(session_id)
    draft.messages.append({"role": "user", "text": message})
    text = (message or "").strip()

    if draft.phase == "offering":
        choice = parse_choice(text, draft.current_offers)
        if choice is None:
            if not draft.current_offers:
                return await _open_next_category(draft)
            rec = draft.current_offers[0]["title"]
            names = ", ".join(o["title"] for o in draft.current_offers)
            return _payload(
                draft,
                f"Say yes to add {rec}, name one of {names}, say all, or skip.",
            )
        if choice == "compose":
            return await _compose_from_picks(draft)
        if choice == "skip":
            skipped = CATEGORY_SPECS.get(draft.current_category, {}).get("label", "those")
            follow = await _open_next_category(draft)
            return _rewrite_last_reply(
                draft, follow, f"Skipped {skipped}. " + follow["reply"]
            )
        if choice == "all" or choice.startswith("all:"):
            if choice.startswith("all:"):
                wanted = {n.lower() for n in choice[4:].split("|")}
                chosen = [o for o in draft.current_offers if o["title"].lower() in wanted]
            else:
                chosen = list(draft.current_offers)
            _accept_offers(draft, chosen)
            names = ", ".join(o["title"] for o in chosen)
            follow = await _open_next_category(draft)
            return _rewrite_last_reply(
                draft, follow, f"Added {names}. " + follow["reply"]
            )
        if choice == "recommended":
            chosen = [draft.current_offers[0]]
        else:
            chosen = [o for o in draft.current_offers if o["title"] == choice]
            if not chosen:
                chosen = [draft.current_offers[0]]
        _accept_offers(draft, chosen)
        follow = await _open_next_category(draft)
        return _rewrite_last_reply(
            draft, follow, f"Added {chosen[0]['title']}. " + follow["reply"]
        )

    if draft.phase == "done":
        return _payload(
            draft,
            "Your itinerary is ready. Edit it on the timeline, or save it for Cascade.",
        )

    draft.prefs = heuristic_extract(text, draft.prefs)
    miss = missing_fields(draft.prefs)
    if miss:
        return _payload(draft, follow_up_question(draft.prefs))

    dest = draft.prefs.destination
    when = _spoken_date(_parse_iso(draft.prefs.start_date) or _today())
    until = _spoken_date(_parse_iso(draft.prefs.end_date) or _today())
    interests = ", ".join(draft.prefs.interests) or "a balanced mix"
    draft.pending_categories = category_queue(draft.prefs)
    intro = (
        f"Got it — {dest} from {when} to {until}, shaped around {interests}"
        + (f", {draft.prefs.budget} budget" if draft.prefs.budget else "")
        + ". I'll go one interest at a time. Say yes to add a pick."
    )
    follow = await _open_next_category(draft)
    return _rewrite_last_reply(draft, follow, intro + " " + follow["reply"])


def progress_for(session_id: str) -> List[dict]:
    return list(_PROGRESS.get(session_id) or [
        {"id": sid, "label": label, "state": "pending"} for sid, label in STEP_DEFS
    ])


def _set_step(session_id: str, active: str, done: Optional[List[str]] = None) -> None:
    done_set = set(done or [])
    seen_active = False
    steps = []
    for sid, label in STEP_DEFS:
        if sid in done_set:
            state = "done"
        elif sid == active:
            state = "active"
            seen_active = True
        elif not seen_active and sid != active:
            state = "done"
            done_set.add(sid)
        else:
            state = "pending"
        steps.append({"id": sid, "label": label, "state": state})
    _PROGRESS[session_id] = steps


def _tavily_research(query: str) -> dict:
    """Named places + a short answer. Raises if Tavily is unavailable."""
    from api import concierge

    client = concierge._tavily_client()
    if client is None:
        raise RuntimeError("TAVILY_API_KEY is not set")
    response = client.search(
        query, search_depth="basic", include_answer=True, max_results=5,
    )
    places = []
    for row in response.get("results") or []:
        title = (row.get("title") or "").strip()
        snippet = concierge._speakable(row.get("content") or "")
        if title:
            places.append({
                "title": title[:120],
                "snippet": snippet[:280],
                "source": "tavily",
            })
    answer = concierge._speakable(response.get("answer") or "")
    return {"answer": answer, "places": places}


async def _research_one(query: str) -> dict:
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_tavily_research, query), timeout=8.0,
        )
    except Exception:  # noqa: BLE001 — research is best-effort
        logger.warning("trip-builder research failed for %r", query, exc_info=True)
        return {"answer": "", "places": []}


def _place_titles(blob: dict) -> List[dict]:
    return list(blob.get("places") or [])


def compose_itinerary(prefs: TripPrefs, research: Dict[str, Any]) -> List[DraftItem]:
    """Schedule only retrieved names (or unlabeled interest blocks)."""
    start = _parse_iso(prefs.start_date) or (_today() + timedelta(days=2))
    end = _parse_iso(prefs.end_date) or start
    if end < start:
        end = start
    n_days = max((end - start).days + 1, 1)

    attractions = list(research.get("attractions") or [])
    restaurants = list(research.get("restaurants") or [])
    neighborhoods = list(research.get("neighborhoods") or [])
    weather = (research.get("weather") or {}).get("answer") or ""
    hotel_area = ""
    if neighborhoods:
        hotel_area = neighborhoods[0]["title"]
    elif prefs.destination:
        hotel_area = prefs.destination

    items: List[DraftItem] = []
    dest = prefs.destination or "destination"
    origin = prefs.origin or "home"

    def day_iso(offset: int) -> str:
        return (start + timedelta(days=offset)).isoformat()

    # Arrival
    items.append(DraftItem(
        type="flight",
        title=f"Arrive in {dest}",
        date=day_iso(0),
        start_time="15:30",
        end_time="16:30",
        location=f"{origin} → {dest}",
        duration_minutes=60,
        importance="must_keep",
        flexibility="low",
        source=research.get("flight_source") or "structured",
        reason="Arrival anchors hotel check-in and the first evening.",
    ))
    items.append(DraftItem(
        type="hotel",
        title=f"Hotel check-in" + (f" — {hotel_area}" if hotel_area else ""),
        date=day_iso(0),
        start_time="17:00",
        end_time="18:00",
        location=hotel_area or dest,
        duration_minutes=60,
        importance="must_keep",
        flexibility="low",
        source="tavily" if neighborhoods else "preference",
        reason="Check-in time Cascade protects if the flight slips.",
    ))
    dinner0 = restaurants.pop(0) if restaurants else None
    items.append(DraftItem(
        type="dining",
        title=(dinner0["title"] if dinner0 else "Dinner"),
        date=day_iso(0),
        start_time="19:00",
        end_time="21:00",
        location=dinner0["title"] if dinner0 else dest,
        duration_minutes=120,
        importance="normal",
        flexibility="high",
        source="tavily" if dinner0 else "preference",
        reason=dinner0["snippet"] if dinner0 else "Evening meal after arrival.",
    ))

    attr_i = 0
    rest_i = 0
    leftover_r = restaurants
    leftover_a = attractions
    for d in range(1, n_days):
        is_last = d == n_days - 1
        iso = day_iso(d)
        # Morning
        if leftover_a:
            place = leftover_a.pop(0)
            must = any(
                m.lower() in place["title"].lower() for m in prefs.must_see
            ) or attr_i == 0
            items.append(DraftItem(
                type="experience",
                title=place["title"],
                date=iso,
                start_time="10:00",
                end_time="13:00",
                location=place["title"],
                duration_minutes=180,
                importance="must_keep" if must else "normal",
                flexibility="low" if must else "high",
                source="tavily",
                reason=place.get("snippet") or "Matches what you said you care about.",
            ))
            attr_i += 1
        elif prefs.interests:
            label = prefs.interests[min(d - 1, len(prefs.interests) - 1)]
            items.append(DraftItem(
                type="experience",
                title=f"{label.capitalize()} morning",
                date=iso,
                start_time="10:00",
                end_time="13:00",
                location=dest,
                duration_minutes=180,
                importance="normal",
                flexibility="high",
                source="preference",
                reason="Placeholder from your interests — no live listing yet.",
            ))
        lunch = leftover_r.pop(0) if leftover_r else None
        items.append(DraftItem(
            type="dining",
            title=(lunch["title"] if lunch else "Lunch"),
            date=iso,
            start_time="13:15",
            end_time="14:30",
            location=lunch["title"] if lunch else dest,
            duration_minutes=75,
            importance="normal",
            flexibility="high",
            source="tavily" if lunch else "preference",
            reason=lunch["snippet"] if lunch else "Flexible midday meal.",
        ))
        rest_i += 1
        if not is_last and leftover_a:
            place = leftover_a.pop(0)
            items.append(DraftItem(
                type="experience",
                title=place["title"],
                date=iso,
                start_time="15:00",
                end_time="17:30",
                location=place["title"],
                duration_minutes=150,
                importance="normal",
                flexibility="high",
                source="tavily",
                reason=place.get("snippet") or "",
            ))
        if is_last:
            items.append(DraftItem(
                type="flight",
                title=f"Fly home from {dest}",
                date=iso,
                start_time="16:00",
                end_time="19:00",
                location=f"{dest} → {origin}",
                duration_minutes=180,
                importance="must_keep",
                flexibility="low",
                source="structured",
                reason="Return flight Cascade can rebook if the outbound slips.",
            ))
            continue
        dinner = leftover_r.pop(0) if leftover_r else None
        items.append(DraftItem(
            type="dining",
            title=(dinner["title"] if dinner else "Dinner"),
            date=iso,
            start_time="19:00",
            end_time="21:00",
            location=dinner["title"] if dinner else dest,
            duration_minutes=120,
            importance="normal",
            flexibility="high",
            source="tavily" if dinner else "preference",
            reason=dinner["snippet"] if dinner else "Flexible evening meal.",
        ))

    if weather:
        items[0].reason = (items[0].reason + " " + weather).strip()

    return items


async def _maybe_flight(prefs: TripPrefs) -> Optional[dict]:
    origin_city = prefs.origin
    dest_city = prefs.destination
    dest_code = ORIGIN_AIRPORTS.get(dest_city, "")
    origin_code = ORIGIN_AIRPORTS.get(origin_city, "")
    if not dest_code or not prefs.start_date:
        return None
    if not origin_code:
        origin_code = "SFO" if dest_code == "JFK" else "JFK"
    try:
        search = await sabre_client.instaflights_search(
            shapes.InstaFlightsRequest(
                origin=origin_code,
                destination=dest_code,
                departuredate=prefs.start_date,
                limit=6,
            )
        )
        options = _parse_instaflights_options(
            search, origin_code, dest_code, max_options=6,
        )
    except Exception:  # noqa: BLE001
        logger.warning("trip-builder flight shop failed", exc_info=True)
        return None
    if not options:
        return None
    pick = min(options, key=lambda o: (o.stops, o.price))
    return {
        "title": f"{pick.airline_name or pick.airline} to {dest_city}",
        "start_time": pick.depart_time,
        "end_time": pick.arrive_time,
        "location": f"{pick.origin} → {pick.destination}",
        "source": "sabre",
        "reason": f"Live Sabre option · ${int(round(pick.price))}"
        + ("" if pick.stops == 0 else f" · {pick.stops} stop"),
        "price": pick.price,
        "details": {
            "airline": pick.airline,
            "flight_number": pick.flight_number,
            "airline_name": pick.airline_name,
        },
    }


async def build_itinerary(session_id: str) -> dict:
    draft = _draft(session_id)
    prefs = draft.prefs
    _fill_dates(prefs)
    if missing_fields(prefs):
        return {
            "ok": False,
            "reply": follow_up_question(prefs),
            "prefs": prefs.model_dump(),
            "ready": False,
            "missing": missing_fields(prefs),
            "items": [],
            "progress": progress_for(session_id),
        }

    dest = prefs.destination
    interests = ", ".join(prefs.interests) or "popular sights"
    budget = prefs.budget or "mid-range"

    accepted_attr = [
        {"title": a["title"], "snippet": a.get("why") or a.get("snippet") or ""}
        for a in draft.accepted if a.get("type") != "dining"
    ]
    accepted_food = [
        {"title": a["title"], "snippet": a.get("why") or a.get("snippet") or ""}
        for a in draft.accepted if a.get("type") == "dining"
    ]

    _set_step(session_id, "prefs", [])
    _set_step(session_id, "places", ["prefs"])
    attr_q = f"best {interests} attractions in {dest} for a {budget} traveler"
    food_q = f"best restaurants in {dest} for {prefs.food_preferences or budget} visitors"
    hood_q = f"best neighborhoods to stay in {dest} for a {budget} trip"
    wx_q = (
        f"weather in {dest} {prefs.start_date} to {prefs.end_date}"
        if prefs.start_date else f"typical weather in {dest} this week"
    )
    transit_q = f"getting around {dest} public transit walking times"

    if accepted_attr or accepted_food:
        hood, wx, transit, flight = await asyncio.gather(
            _research_one(hood_q),
            _research_one(wx_q),
            _research_one(transit_q),
            _maybe_flight(prefs),
        )
        attr, food = {"places": []}, {"places": []}
    else:
        attr, food, hood, wx, transit, flight = await asyncio.gather(
            _research_one(attr_q),
            _research_one(food_q),
            _research_one(hood_q),
            _research_one(wx_q),
            _research_one(transit_q),
            _maybe_flight(prefs),
        )
    _set_step(session_id, "food", ["prefs", "places"])
    _set_step(session_id, "times", ["prefs", "places", "food"])
    _set_step(session_id, "days", ["prefs", "places", "food", "times"])

    research = {
        "attractions": accepted_attr or extract_venues(attr, dest, limit=6),
        "restaurants": accepted_food or extract_venues(food, dest, limit=6),
        "neighborhoods": extract_venues(hood, dest, limit=3),
        "weather": wx,
        "transport": transit,
        "flight_source": "sabre" if flight else "structured",
    }
    draft.research = research
    items = compose_itinerary(prefs, research)
    if flight:
        items[0].title = flight["title"]
        items[0].start_time = flight["start_time"]
        items[0].end_time = flight["end_time"]
        items[0].location = flight["location"]
        items[0].source = "sabre"
        items[0].reason = flight["reason"]
        draft.research["flight"] = flight
    _set_step(session_id, "optimize", [s[0] for s in STEP_DEFS[:-1]])
    _PROGRESS[session_id] = [
        {"id": s[0], "label": s[1], "state": "done"} for s in STEP_DEFS
    ]
    draft.items = items
    start = _parse_iso(prefs.start_date)
    end = _parse_iso(prefs.end_date)
    span = ""
    if start and end:
        span = f"{_spoken_date(start)}–{_spoken_date(end)}"
    draft.title = f"{dest} — {span}".strip(" —")
    return {
        "ok": True,
        "reply": f"Here's a structured trip to {dest}. Star what Cascade must protect.",
        "prefs": prefs.model_dump(),
        "ready": True,
        "missing": [],
        "title": draft.title,
        "items": [i.model_dump() for i in items],
        "research_used": {
            "attractions": len(research["attractions"]),
            "restaurants": len(research["restaurants"]),
            "has_weather": bool((wx or {}).get("answer")),
            "has_flight": bool(flight),
        },
        "progress": progress_for(session_id),
        "session_id": session_id,
    }


def replace_items(session_id: str, items: List[dict]) -> dict:
    draft = _draft(session_id)
    draft.items = [DraftItem.model_validate(i) for i in items]
    return {
        "ok": True,
        "items": [i.model_dump() for i in draft.items],
        "title": draft.title,
        "prefs": draft.prefs.model_dump(),
    }


def _item_timestamps(item: DraftItem) -> tuple:
    day = _parse_iso(item.date) or _today()
    def clock(value: str, default: str) -> datetime:
        raw = value or default
        try:
            h, m = int(raw[:2]), int(raw[3:5] or 0)
        except (TypeError, ValueError):
            h, m = 12, 0
        return datetime(day.year, day.month, day.day, h, m, tzinfo=_PACIFIC)
    start = clock(item.start_time, "12:00")
    end = clock(item.end_time, "13:00")
    if end <= start:
        end = start + timedelta(hours=1)
    return start, end


def save_trip(session_id: str, user_id: str = "demo-traveler") -> dict:
    """Persist the draft as a booked trip Cascade can repair."""
    draft = _draft(session_id)
    if not draft.items:
        raise ValueError("no itinerary to save")
    prefs = draft.prefs
    _fill_dates(prefs)
    start = _parse_iso(prefs.start_date)
    end = _parse_iso(prefs.end_date)
    dest = prefs.destination or "Trip"
    dest_code = ORIGIN_AIRPORTS.get(dest, dest)
    origin_code = ORIGIN_AIRPORTS.get(prefs.origin) or (
        "SFO" if dest_code == "JFK" else "JFK"
    )
    trip = Trip(
        user_id=user_id,
        title=draft.title or f"Trip to {dest}",
        status="booked",
        origin=origin_code,
        destinations=[dest],
        start_date=start,
        end_date=end,
    )
    success, _, error = trips.create_trip(trip)
    if not success:
        raise RuntimeError(f"trip insert failed: {error}")

    flight_meta = (draft.research or {}).get("flight") or {}
    flight_details = flight_meta.get("details") or {}
    stamped_prefs = False

    for row in draft.items:
        start_ts, end_ts = _item_timestamps(row)
        itype = row.type if row.type in (
            "flight", "hotel", "ground", "dining", "experience"
        ) else "experience"
        details = {
            "title": row.title,
            "importance": row.importance,
            "flexibility": row.flexibility,
            "source": row.source,
            "reason": row.reason,
            "must_keep": row.importance == "must_keep",
            "duration_minutes": row.duration_minutes,
            "built_by": "build_my_trip",
        }
        if not stamped_prefs:
            details["traveler_prefs"] = prefs.model_dump()
            stamped_prefs = True
        if itype == "flight":
            details.update({
                "airline": flight_details.get("airline") or "UA",
                "flight_number": flight_details.get("flight_number") or 100,
                "airline_name": flight_details.get("airline_name") or row.title,
            })
        item = ItineraryItem(
            trip_id=trip.trip_id,
            type=itype,
            status="booked",
            provider="sabre" if itype == "flight" and row.source == "sabre" else "other",
            start_ts=start_ts,
            end_ts=end_ts,
            location=row.location or dest,
            details=details,
            price=flight_meta.get("price") if itype == "flight" else None,
            currency="USD" if itype == "flight" and flight_meta.get("price") else None,
        )
        ok, _, err = itinerary_items.create_item(item)
        if not ok:
            raise RuntimeError(f"item insert failed: {err}")

    draft.trip_id = trip.trip_id
    return {
        "trip_id": trip.trip_id,
        "title": trip.title,
        "item_count": len(draft.items),
        "redirect": f"/v1/cascade/?trip_id={trip.trip_id}",
    }
