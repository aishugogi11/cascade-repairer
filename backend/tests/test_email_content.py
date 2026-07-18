"""Phase 40 tests — the email content builders, hermetic.

Pure builders over loaded models, no I/O. The load-bearing contracts: copy
follows the spoken register (airline NAMES never codes, clocks labeled PT,
rounded prices), the "Was …" line appears exactly when details.rebooked_from
has something to say, the refund sentence appends only when passed, missing
data omits lines rather than raising (seed trips and pre-Phase-33 rows must
build), both variants are non-empty, and nothing carries a URL or reply-to
copy — the mailbox is outbound-only.
"""
from datetime import date, datetime, timezone

from api import email_content
from api.repositories.models import ItineraryItem, Trip


def _trip(**overrides) -> Trip:
    fields = dict(
        trip_id="t-1",
        user_id="demo-traveler",
        title="Trip to LAX",
        status="booked",
        origin="JFK",
        destinations=["LAX"],
        start_date=date(2026, 7, 21),
        end_date=date(2026, 7, 23),
    )
    fields.update(overrides)
    return Trip(**fields)


# 15:05 UTC in July is 8:05 AM PDT; 18:30 UTC is 11:30 AM PDT.
_DEPART = datetime(2026, 7, 21, 15, 5, tzinfo=timezone.utc)
_ARRIVE = datetime(2026, 7, 21, 18, 30, tzinfo=timezone.utc)

_RICH_DETAILS = {
    "airline": "DL",
    "flight_number": 439,
    "airline_name": "Delta",
    "cabin": "Economy",
    "duration_minutes": 349,
    "layover_airports": [],
    "arrives_next_day": False,
    "stops": 0,
}


def _rich_flight(**overrides) -> ItineraryItem:
    fields = dict(
        item_id="i-flight",
        trip_id="t-1",
        type="flight",
        status="booked",
        location="JFK-LAX",
        start_ts=_DEPART,
        end_ts=_ARRIVE,
        details=dict(_RICH_DETAILS),
        price=213.60,
        currency="USD",
    )
    fields.update(overrides)
    return ItineraryItem(**fields)


def _build_out_items():
    return [
        ItineraryItem(
            item_id="i-hotel", trip_id="t-1", type="hotel", status="booked",
            location="Hotel in LAX", start_ts=_DEPART, price=412.0,
            currency="USD",
        ),
        ItineraryItem(
            item_id="i-dining", trip_id="t-1", type="dining", status="booked",
            location="Dinner in LAX", price=120.0, currency="USD",
        ),
    ]


_REBOOKED_FROM = {
    "airline": "DL",
    "flight_number": 439,
    "airline_name": "Delta",
    "depart_time": "8:05 AM",
    "arrive_time": "11:30 AM",
    "price": 214.0,
    "currency": "USD",
}


def _assert_email_register(content):
    """The shared tone contract: names not codes, PT labels, no web/reply
    artifacts, both variants non-empty."""
    for variant in (content.html, content.text):
        assert variant.strip()
        assert "http" not in variant.lower()
        assert "www." not in variant.lower()
        assert "reply" not in variant.lower()
    assert content.subject.strip()


# --- itinerary email -----------------------------------------------------------


def test_itinerary_email_speaks_the_rich_flight():
    content = email_content.build_itinerary_email(
        _trip(), [_rich_flight()] + _build_out_items()
    )

    # The departure date rides in the subject (live-QA finding 2026-07-18:
    # same-city trips produced three identical subjects in one inbox).
    assert content.subject == "Your trip to Los Angeles — July 21"
    for variant in (content.html, content.text):
        assert "Delta 439" in variant
        assert "DL" not in variant  # names, never codes
        assert "8:05 AM PT" in variant
        assert "11:30 AM PT" in variant
        assert "$214" in variant  # rounded, like the spoken price
        assert "Economy" in variant
        assert "5h 49m" in variant
        assert "Nonstop" in variant
        assert "New York to Los Angeles" in variant
        assert "Hotel" in variant and "$412" in variant
        assert "Dinner" in variant and "$120" in variant
    _assert_email_register(content)


def test_itinerary_email_flight_only_when_build_out_has_not_landed():
    # A yes spoken right after book_flight: only the flight exists yet.
    content = email_content.build_itinerary_email(_trip(), [_rich_flight()])

    assert "Delta 439" in content.text
    assert "Hotel" not in content.text
    _assert_email_register(content)


def test_itinerary_email_builds_from_a_bare_seed_row():
    # Pre-Phase-33 shape: no details, no timestamps, no price — every rich
    # line is omitted, nothing raises.
    bare = ItineraryItem(trip_id="t-1", type="flight", status="booked")
    content = email_content.build_itinerary_email(
        _trip(title="The Complete Trip", origin=None, destinations=[],
              start_date=None, end_date=None),
        [bare],
    )

    # No route, no dates anywhere — the subject degrades to the title with
    # no date suffix, and nothing raises.
    assert content.subject == "Your trip: The Complete Trip"
    assert "Flight" in content.text
    assert "None" not in content.text
    assert "None" not in content.html
    _assert_email_register(content)


def test_subject_date_falls_back_to_the_flight_row():
    # A trip header without dates still gets the subject date from the
    # flight's PT departure day.
    content = email_content.build_itinerary_email(
        _trip(start_date=None, end_date=None), [_rich_flight()]
    )

    assert content.subject == "Your trip to Los Angeles — July 21"


def test_itinerary_email_connection_and_next_day_lines():
    details = dict(
        _RICH_DETAILS, layover_airports=["SFO"], stops=1, arrives_next_day=True
    )
    content = email_content.build_itinerary_email(
        _trip(), [_rich_flight(details=details)]
    )

    assert "Connects in San Francisco" in content.text
    assert "the next day" in content.text
    assert "Nonstop" not in content.text


# --- repair email ---------------------------------------------------------------


def _fixed_flight():
    return _rich_flight(
        status="fixed",
        details={**_RICH_DETAILS, "airline": "B6", "airline_name": "JetBlue",
                 "flight_number": 615, "rebooked_from": dict(_REBOOKED_FROM)},
        price=189.0,
    )


def test_repair_email_speaks_the_rebooked_flight_with_the_was_line():
    items = [_fixed_flight()] + [
        item.model_copy(update={"status": "fixed"})
        for item in _build_out_items()
    ]
    details = {"i-flight": {"why_chosen": "Closest arrival to your "
                            "original flight.", "price_delta": "-$25"}}

    content = email_content.build_repair_email(
        _trip(), items, details, refund_line="I sent the 25 dollar "
        "difference back to your PayPal — it's on its way now."
    )

    assert content.subject == "Your trip to Los Angeles is fixed — July 21"
    for variant in (content.html, content.text):
        assert "JetBlue 615" in variant
        assert "Was Delta 439" in variant
        assert "departed 8:05 AM" in variant
        assert "$214" in variant  # the original fare, in the was-line
        assert "Closest arrival" in variant
        assert "PayPal" in variant
        assert "re-checked and confirmed" in variant
    assert "<s style" in content.html  # struck through, like the cascade card
    _assert_email_register(content)


def test_repair_email_without_refund_or_why_has_no_extra_paragraphs():
    content = email_content.build_repair_email(
        _trip(), [_fixed_flight()], {}, refund_line=None
    )

    assert "PayPal" not in content.text
    assert "JetBlue 615" in content.text
    _assert_email_register(content)


def test_repair_email_without_rebooked_from_has_no_was_line():
    # Seed trips / pre-31 rows: the repair stamped no original identity.
    content = email_content.build_repair_email(
        _trip(), [_rich_flight(status="fixed")], {}
    )

    assert "Was " not in content.text
    assert "<s style" not in content.html
    _assert_email_register(content)


def test_repair_email_unfixed_flight_is_honest():
    content = email_content.build_repair_email(
        _trip(), [_rich_flight(status="repairing")], {}
    )

    # Never "fixed" in the subject while the repair is still in flight.
    assert content.subject == "Update on your trip to Los Angeles — July 21"
    assert "where the repair stands" in content.text
    _assert_email_register(content)


def test_repair_email_unresolved_legs_read_as_still_working():
    items = [_fixed_flight()] + [
        item.model_copy(update={"status": "repairing"})
        for item in _build_out_items()
    ]
    content = email_content.build_repair_email(_trip(), items, {})

    assert "still being worked on" in content.text


def test_repair_email_escapes_html_in_dynamic_values():
    flight = _rich_flight(
        status="fixed",
        details={**_RICH_DETAILS, "airline_name": "<b>Delta</b>"},
    )
    content = email_content.build_repair_email(_trip(), [flight], {})

    assert "<b>Delta</b>" not in content.html
    assert "&lt;b&gt;Delta&lt;/b&gt;" in content.html
