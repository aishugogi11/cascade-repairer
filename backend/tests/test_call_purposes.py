"""Phase 23 tests — call scripts composed from the real trip's data.

Pure-function tests (no IO, no env, no network): the builders take loaded
models and return spoken-copy scripts. Load-bearing invariants: a
voice-booked JFK→LAX trip gets calls about JFK→LAX (never the retired
Minneapolis→San Francisco narrative), Call 1 asks consent instead of
claiming repairs are running, Call 2 speaks the actual post-repair state,
and a missing detail degrades — never raises.
"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

from api import call_purposes
from api.repositories.models import ItineraryItem, Trip
from api.sabre_tools import _SEED_ITEMS

_PACIFIC = ZoneInfo("America/Los_Angeles")


def _jfk_lax_trip():
    trip = Trip(
        user_id="demo-traveler",
        title="Trip to LAX",
        status="booked",
        origin="JFK",
        destinations=["LAX"],
        start_date=date(2026, 7, 17),
        end_date=date(2026, 7, 19),
    )
    items = [
        ItineraryItem(
            trip_id=trip.trip_id, type="flight", status="booked",
            location="JFK-LAX",
            start_ts=datetime(2026, 7, 17, 8, 0, tzinfo=_PACIFIC),
        ),
        ItineraryItem(trip_id=trip.trip_id, type="hotel", status="booked",
                      location="Hotel in LAX"),
        ItineraryItem(trip_id=trip.trip_id, type="ground", status="booked"),
        ItineraryItem(trip_id=trip.trip_id, type="dining", status="booked"),
        ItineraryItem(trip_id=trip.trip_id, type="experience", status="booked"),
    ]
    return trip, items


# ── Call 1: the disruption / consent-ask script ────────────────────────


def test_disrupt_purpose_names_the_real_route_never_the_old_narrative():
    trip, items = _jfk_lax_trip()
    purpose = call_purposes.build_disrupt_purpose(trip, items)
    assert "New York" in purpose and "Los Angeles" in purpose
    assert "Minneapolis" not in purpose
    assert "San Francisco" not in purpose
    # Spoken copy: plain city names, no bare airport codes read aloud.
    assert "JFK" not in purpose and "LAX" not in purpose


def test_disrupt_purpose_asks_consent_and_claims_no_running_repairs():
    trip, items = _jfk_lax_trip()
    purpose = call_purposes.build_disrupt_purpose(trip, items)
    assert "cancelled" in purpose
    # One clear consent question; the repairs wait for the yes.
    assert "want me to?" in purpose
    assert "NOT started" in purpose
    assert "already rebooking" not in purpose


def test_disrupt_purpose_speaks_the_flight_date_and_only_real_legs():
    trip, items = _jfk_lax_trip()
    purpose = call_purposes.build_disrupt_purpose(trip, items)
    assert "July 17th" in purpose
    for leg in ("the hotel", "the airport ride", "the dinner reservation",
                "and the tour"):
        assert leg in purpose

    flight_only = call_purposes.build_disrupt_purpose(trip, items[:1])
    assert "hotel" not in flight_only
    assert "rebook the flight" in flight_only


def test_disrupt_purpose_falls_back_to_the_trip_header_route():
    trip, items = _jfk_lax_trip()
    items[0].location = None  # no "JFK-LAX" on the item
    purpose = call_purposes.build_disrupt_purpose(trip, items)
    assert "New York" in purpose and "Los Angeles" in purpose


def test_disrupt_purpose_survives_a_trip_with_no_route_at_all():
    trip, items = _jfk_lax_trip()
    trip.origin = None
    trip.destinations = []
    items[0].location = None
    purpose = call_purposes.build_disrupt_purpose(trip, items)
    assert trip.title in purpose  # the title fallback keeps it speakable


# ── Call 2: the results callback ───────────────────────────────────────


def _fixed_trip_with_detail(price_delta="+$23"):
    trip, items = _jfk_lax_trip()
    for item in items:
        item.status = "fixed"
    details = {
        items[0].item_id: {
            "why_chosen": (
                "Rebooked on Delta 1445, nonstop, landing 11:30 AM — the "
                "closest available arrival to your original flight."
            ),
            "price_delta": price_delta,
            "impact": "Every downstream booking was re-checked.",
        }
    }
    return trip, items, details


def test_results_purpose_speaks_the_actual_rebooked_flight_and_delta():
    trip, items, details = _fixed_trip_with_detail()
    purpose = call_purposes.build_results_purpose(trip, items, details)
    assert "Delta 1445" in purpose and "11:30 AM" in purpose
    assert "$23 more" in purpose
    assert "re-checked" in purpose
    assert "New York" in purpose and "Los Angeles" in purpose
    assert "Minneapolis" not in purpose and "San Francisco" not in purpose


def test_results_purpose_speaks_cheaper_and_unchanged_fares():
    trip, items, details = _fixed_trip_with_detail(price_delta="-$15")
    assert "$15 cheaper" in call_purposes.build_results_purpose(trip, items, details)
    trip, items, details = _fixed_trip_with_detail(price_delta="$0")
    assert "no change in fare" in call_purposes.build_results_purpose(
        trip, items, details
    )


def test_results_purpose_degrades_without_detail_and_never_raises():
    trip, items = _jfk_lax_trip()
    for item in items:
        item.status = "fixed"
    purpose = call_purposes.build_results_purpose(trip, items, {})
    assert "rebooked and confirmed" in purpose


def test_results_purpose_is_honest_about_unresolved_legs():
    trip, items = _jfk_lax_trip()
    items[0].status = "fixed"
    items[1].status = "repairing"  # the hotel didn't land
    for item in items[2:]:
        item.status = "fixed"
    purpose = call_purposes.build_results_purpose(trip, items, {})
    assert "Not everything is settled yet" in purpose
    assert "the hotel" in purpose


def test_results_purpose_is_honest_about_an_unfixed_flight():
    trip, items = _jfk_lax_trip()
    items[0].status = "repairing"
    purpose = call_purposes.build_results_purpose(trip, items, {})
    assert "still in progress" in purpose


# ── Beat 1: the booking narrative derives from the seed data ───────────


def test_book_purpose_derives_from_the_seed_items():
    purpose = call_purposes.build_book_purpose("Josh's big trip", _SEED_ITEMS)
    assert "Josh's big trip" in purpose
    # The seed trip is MSP→SFO — spoken as cities, sourced from the data.
    assert "Minneapolis" in purpose and "San Francisco" in purpose
    for leg in ("hotel", "ride", "dinner", "tour"):
        assert leg in purpose
    assert "Mountain View" in purpose
    assert "Computer History Museum" in purpose


def test_book_purpose_survives_missing_seed_pieces():
    purpose = call_purposes.build_book_purpose("Trip", [
        {"type": "flight", "location": "JFK-LAX",
         "start": datetime(2026, 7, 17, 8, 0, tzinfo=_PACIFIC)},
    ])
    assert "New York" in purpose and "Los Angeles" in purpose
    assert "a hotel" in purpose and "a tour" in purpose  # graceful generics
