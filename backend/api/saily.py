"""Saily travel eSIM — destination catalog + checkout links.

Saily has no public booking API. We map the trip's places to a published
country page (https://saily.com/esim-<country>/) and speak starting prices
from their public catalog. Checkout happens on Saily; we never claim a
live quote or that we installed an eSIM.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Sequence

# Public starting prices from saily.com country pages (not a live quote).
_PLANS: Dict[str, Dict[str, str]] = {
    "japan": {"label": "Japan", "from_price": "US$3.99", "data": "from 1 GB"},
    "france": {"label": "France", "from_price": "US$3.99", "data": "from 1 GB"},
    "united-kingdom": {"label": "United Kingdom", "from_price": "US$3.99", "data": "from 1 GB"},
    "spain": {"label": "Spain", "from_price": "US$3.99", "data": "from 1 GB"},
    "italy": {"label": "Italy", "from_price": "US$3.99", "data": "from 1 GB"},
    "germany": {"label": "Germany", "from_price": "US$3.99", "data": "from 1 GB"},
    "mexico": {"label": "Mexico", "from_price": "US$3.99", "data": "from 1 GB"},
    "canada": {"label": "Canada", "from_price": "US$3.99", "data": "from 1 GB"},
    "south-korea": {"label": "South Korea", "from_price": "US$4.49", "data": "from 1 GB"},
    "china": {"label": "China", "from_price": "US$4.49", "data": "from 1 GB"},
    "thailand": {"label": "Thailand", "from_price": "US$3.99", "data": "from 1 GB"},
    "india": {"label": "India", "from_price": "US$4.49", "data": "from 1 GB"},
    "brazil": {"label": "Brazil", "from_price": "US$4.49", "data": "from 1 GB"},
    "australia": {"label": "Australia", "from_price": "US$4.49", "data": "from 1 GB"},
    "united-states": {"label": "United States", "from_price": "US$3.99", "data": "from 1 GB"},
}

_GLOBAL = {
    "slug": "global",
    "label": "Global (121 destinations)",
    "from_price": "US$7.64",
    "data": "from 1 GB / 7 days",
}

_ALIASES = {
    "tokyo": "japan", "osaka": "japan", "kyoto": "japan", "nrt": "japan", "hnd": "japan",
    "paris": "france", "cdg": "france", "ory": "france",
    "london": "united-kingdom", "lhr": "united-kingdom", "lgw": "united-kingdom",
    "uk": "united-kingdom", "britain": "united-kingdom", "england": "united-kingdom",
    "madrid": "spain", "barcelona": "spain",
    "rome": "italy", "milan": "italy", "fco": "italy",
    "berlin": "germany", "munich": "germany", "fra": "germany",
    "mexico city": "mexico", "cancun": "mexico", "cun": "mexico",
    "toronto": "canada", "vancouver": "canada", "yyz": "canada",
    "seoul": "south-korea", "icn": "south-korea", "korea": "south-korea",
    "beijing": "china", "shanghai": "china", "pek": "china",
    "bangkok": "thailand", "bkk": "thailand",
    "delhi": "india", "mumbai": "india", "del": "india",
    "sao paulo": "brazil", "rio": "brazil", "gru": "brazil",
    "sydney": "australia", "melbourne": "australia", "syd": "australia",
    "new york": "united-states", "nyc": "united-states", "jfk": "united-states",
    "lga": "united-states", "ewr": "united-states", "laguardia": "united-states",
    "newark": "united-states", "manhattan": "united-states", "midtown": "united-states",
    "soho": "united-states", "brooklyn": "united-states", "queens": "united-states",
    "financial district": "united-states", "rockefeller": "united-states",
    "central park": "united-states",
    "los angeles": "united-states", "lax": "united-states",
    "san francisco": "united-states", "sfo": "united-states",
    "chicago": "united-states", "ord": "united-states", "mia": "united-states",
    "seattle": "united-states", "boston": "united-states", "dfw": "united-states",
    "usa": "united-states", "us": "united-states", "united states": "united-states",
    "japan": "japan", "france": "france", "spain": "spain", "italy": "italy",
    "germany": "germany", "mexico": "mexico", "canada": "canada",
    "china": "china", "thailand": "thailand", "india": "india",
    "brazil": "brazil", "australia": "australia",
}


def _slug_for(text: str) -> Optional[str]:
    raw = (text or "").strip().lower()
    if not raw:
        return None
    if raw in _ALIASES:
        return _ALIASES[raw]
    if raw in _PLANS:
        return raw
    for token in raw.replace(",", " ").replace("—", " ").replace("-", " ").split():
        if token in _ALIASES:
            return _ALIASES[token]
        if token in _PLANS:
            return token
    return None


_NYC_HINTS = (
    "new york", "nyc", "jfk", "lga", "ewr", "laguardia", "newark",
    "manhattan", "midtown", "soho", "brooklyn", "queens",
    "financial district", "rockefeller", "central park",
)


def _is_nyc(text: str) -> bool:
    raw = (text or "").strip().lower()
    return any(hint in raw for hint in _NYC_HINTS)


def _checkout(slug: str) -> str:
    return f"https://saily.com/esim-{slug}/"


def _card(
    slug: str,
    *,
    needed: bool,
    reason: str,
    place_label: Optional[str] = None,
) -> Dict[str, Any]:
    if slug == "global" or slug not in _PLANS:
        plan = dict(_GLOBAL)
        url = _checkout("global")
        display = plan["label"]
    else:
        plan = dict(_PLANS[slug])
        plan["slug"] = slug
        url = _checkout(slug)
        display = (
            f"{place_label} ({plan['label']})" if place_label else plan["label"]
        )
    if needed:
        where = place_label or plan["label"]
        speak = (
            f"Saily has eSIM data for {where} from {plan['from_price']}. "
            "I put a Get Saily link on your itinerary — I can't install the eSIM from here."
        )
        blurb = (
            f"Prepaid data for {where}. Starting catalog price — checkout is on "
            "Saily; we don't install the eSIM from here."
        )
    elif place_label:
        speak = (
            f"Your {place_label} itinerary is domestic, so your usual SIM may "
            f"already work. Saily's {plan['label']} eSIM starts at "
            f"{plan['from_price']} if you want prepaid data for the city anyway."
        )
        blurb = (
            f"Optional prepaid data for {place_label}. Your usual SIM may already "
            "work on this trip — checkout is on Saily if you want a local eSIM."
        )
    else:
        speak = (
            "This trip looks domestic, so you may not need an eSIM. "
            f"Saily has {plan['label']} data from {plan['from_price']} if you "
            "want a prepaid plan anyway. The Get Saily link is on your itinerary."
        )
        blurb = (
            "This trip looks domestic. Keep a Saily plan handy if your usual "
            "SIM doesn't include data there."
        )
    return {
        "provider": "Saily",
        "needed": needed,
        "reason": reason,
        "label": display,
        "from_price": plan["from_price"],
        "data": plan["data"],
        "checkout_url": url,
        "source": "saily_catalog",
        "speak": speak,
        "blurb": blurb,
    }


def plan_for_places(
    destinations: Sequence[str] = (),
    origin: str = "",
) -> Dict[str, Any]:
    dest_slug = None
    for place in destinations:
        dest_slug = _slug_for(place)
        if dest_slug:
            break
    origin_slug = _slug_for(origin) or "united-states"
    nyc = any(_is_nyc(place) for place in destinations)
    place_label = "New York" if nyc else None
    if dest_slug and dest_slug != origin_slug:
        return _card(
            dest_slug,
            needed=True,
            reason=f"International hop {origin_slug} → {dest_slug}",
            place_label=place_label if dest_slug == "united-states" else None,
        )
    if nyc:
        return _card(
            "united-states",
            needed=False,
            reason="New York itinerary — United States eSIM is optional",
            place_label="New York",
        )
    if dest_slug:
        return _card(
            dest_slug,
            needed=False,
            reason="Same-country trip — Saily is optional until you leave the country",
        )
    return _card(
        "global",
        needed=False,
        reason="Same-country trip — Saily is optional until you leave the country",
    )


def plan_for_trip(
    *,
    origin: str = "",
    destinations: Sequence[str] = (),
    extra_places: Sequence[str] = (),
) -> Dict[str, Any]:
    dests = [d for d in destinations if (d or "").strip()]
    extras = [p for p in extra_places if (p or "").strip()]
    return plan_for_places(dests + extras if dests else extras, origin)
