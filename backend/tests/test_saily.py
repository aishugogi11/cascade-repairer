"""Saily travel eSIM catalog — hermetic (no Saily API, no network)."""
import asyncio
from datetime import date

from api import concierge
from api.repositories.models import ItineraryItem, Trip
from api.saily import plan_for_places, plan_for_trip


def test_international_destination_gets_country_checkout():
    card = plan_for_places(["Tokyo"], "SFO")
    assert card["needed"] is True
    assert card["label"] == "Japan"
    assert card["from_price"] == "US$3.99"
    assert card["checkout_url"] == "https://saily.com/esim-japan/"
    assert card["source"] == "saily_catalog"
    assert "Japan" in card["speak"]
    assert "http" not in card["speak"].lower()


def test_nyc_itinerary_gets_united_states_plan():
    card = plan_for_places(["JFK", "Midtown", "SoHo"], "SFO")
    assert card["needed"] is False
    assert card["label"] == "New York (United States)"
    assert card["from_price"] == "US$3.99"
    assert card["checkout_url"] == "https://saily.com/esim-united-states/"
    assert "New York" in card["speak"]
    assert "New York" in card["blurb"]
    assert "http" not in card["speak"].lower()


def test_visitor_to_nyc_needs_us_esim():
    card = plan_for_places(["New York"], "Tokyo")
    assert card["needed"] is True
    assert card["checkout_url"] == "https://saily.com/esim-united-states/"
    assert "New York" in card["speak"]


def test_same_country_non_nyc_uses_country_page():
    card = plan_for_places(["Los Angeles"], "SFO")
    assert card["needed"] is False
    assert card["checkout_url"] == "https://saily.com/esim-united-states/"
    assert "New York" not in card["label"]


def test_unknown_places_degrade_to_optional_global():
    card = plan_for_places(["somewhere imaginary"], "")
    assert card["needed"] is False
    assert card["provider"] == "Saily"
    assert card["checkout_url"].startswith("https://saily.com/esim-")


def test_plan_for_trip_falls_back_to_item_places():
    card = plan_for_trip(
        origin="SFO",
        destinations=[],
        extra_places=["Hotel — Kyoto"],
    )
    assert card["needed"] is True
    assert card["checkout_url"] == "https://saily.com/esim-japan/"


def test_esim_plan_speaks_japan_for_pinned_tokyo_trip(monkeypatch):
    monkeypatch.setattr(concierge, "_SESSION_TRIPS", {})
    trip = Trip(
        trip_id="t-jp", user_id="demo-traveler", title="Tokyo",
        status="booked", origin="SFO", destinations=["Tokyo"],
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 8),
    )
    concierge._SESSION_TRIPS["room-1"] = concierge.TripContext(
        trip=trip,
        items=[ItineraryItem(trip_id="t-jp", type="flight", status="booked")],
        summary="summary",
    )
    spoken = asyncio.run(concierge.esim_plan_impl("room-1"))
    assert "Japan" in spoken
    assert "http" not in spoken.lower()


def test_esim_plan_speaks_new_york_for_nyc_trip(monkeypatch):
    monkeypatch.setattr(concierge, "_SESSION_TRIPS", {})
    trip = Trip(
        trip_id="t-nyc", user_id="demo-traveler", title="SFO → New York",
        status="booked", origin="SFO", destinations=["JFK"],
        start_date=date(2026, 9, 14), end_date=date(2026, 9, 16),
    )
    concierge._SESSION_TRIPS["room-1"] = concierge.TripContext(
        trip=trip,
        items=[
            ItineraryItem(
                trip_id="t-nyc", type="dining", status="booked",
                location="Midtown", details={"title": "Dinner — Rockefeller Center"},
            )
        ],
        summary="summary",
    )
    spoken = asyncio.run(concierge.esim_plan_impl("room-1"))
    assert "New York" in spoken
    assert "http" not in spoken.lower()


def test_esim_plan_unpinned_is_speakable_and_never_raises(monkeypatch):
    monkeypatch.setattr(concierge, "_SESSION_TRIPS", {})
    spoken = asyncio.run(concierge.esim_plan_impl("no-trip"))
    assert spoken
    assert "http" not in spoken.lower()


def test_esim_tool_always_registered():
    agent = concierge.build_agent("room-1")
    assert "esim_plan" in {t.name for t in agent.tools}
    assert "esim_plan" in concierge.BASE_INSTRUCTIONS
    assert "never read the checkout URL" in concierge.BASE_INSTRUCTIONS
