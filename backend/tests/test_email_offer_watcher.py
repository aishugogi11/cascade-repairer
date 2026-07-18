"""Phase 40 tests — the Call 2 email offer and its watcher, hermetic.

vb_cli, the classifier, and the send module are all monkeypatched; no
network, no OPENAI_API_KEY, no RESEND_API_KEY. The load-bearing contracts:
with no address on file Call 2 is byte-identical to the pre-40 callback
(no offer sentence, no watcher), with one on file the purpose carries
exactly one offer sentence and a watcher keyed on room_name follows the
call, only an unambiguous yes sends (to the stored address, with the
refund line when the run had one), every other outcome — no, ambiguous,
timeout, classifier failure, missing session key — sends nothing, watcher
exceptions never propagate, and a failed call placement spawns no watcher.
"""
import asyncio
from datetime import date

import pytest

from api import consent
from api import demo as demo_module
from api import trip_emails
from api.repositories.models import ItineraryItem, Trip


@pytest.fixture(autouse=True)
def fresh_state():
    trip_emails._reset()
    yield
    trip_emails._reset()


def _trip():
    return Trip(
        trip_id="t-7", user_id="demo-traveler", title="Trip to LAX",
        status="booked", origin="JFK", destinations=["LAX"],
        start_date=date(2026, 7, 21), end_date=date(2026, 7, 23),
    )


def _items():
    return [
        ItineraryItem(
            item_id="i-flight", trip_id="t-7", type="flight", status="fixed",
            location="JFK-LAX",
            details={
                "airline": "B6", "flight_number": 615,
                "airline_name": "JetBlue", "cabin": "Economy",
                "duration_minutes": 349, "layover_airports": [],
                "arrives_next_day": False, "stops": 0,
                "rebooked_from": {
                    "airline": "DL", "flight_number": 439,
                    "airline_name": "Delta", "depart_time": "8:05 AM",
                    "price": 214.0, "currency": "USD",
                },
            },
            price=189.0, currency="USD",
        ),
        ItineraryItem(
            item_id="i-hotel", trip_id="t-7", type="hotel", status="fixed",
            location="Hotel in LAX", price=412.0, currency="USD",
        ),
    ]


REFUND_LINE = (
    "And since the new flight was cheaper, I've already sent the 25 dollar "
    "difference back to you through PayPal."
)


def _wire_callback(monkeypatch, trip, items, refund_line=None, call_ok=True):
    """Wire _call_back_with_results hermetically and capture the placed
    call — the test_demo _wire_disrupt pattern."""
    monkeypatch.setattr(
        demo_module.trips, "get_trip", lambda tid: (True, trip, None)
    )
    monkeypatch.setattr(
        demo_module.itinerary_items, "list_items_for_trip",
        lambda tid: (True, items, None),
    )

    async def fake_details(tid, its):
        return {}

    monkeypatch.setattr(demo_module, "_details_for", fake_details)

    async def fake_refund(its):
        return refund_line

    monkeypatch.setattr(demo_module, "_maybe_refund_line", fake_refund)

    calls = []

    def fake_place_call(purpose, session_name):
        calls.append({"purpose": purpose, "session_name": session_name})
        if not call_ok:
            return False, None, "vb fell over"
        return True, {
            "call_id": "c-2", "room_name": "room-2", "status": "queued"
        }, None

    monkeypatch.setattr(demo_module.vb_cli, "place_call", fake_place_call)
    return calls


def _spy_watcher(monkeypatch):
    spawned = []

    async def fake_watch(trip_id, session_key, address, trip, items,
                         details, refund_line):
        spawned.append({
            "trip_id": trip_id, "session_key": session_key,
            "address": address, "refund_line": refund_line,
        })

    monkeypatch.setattr(demo_module, "_watch_email_offer", fake_watch)
    return spawned


def _capture_send(monkeypatch, status="sent"):
    sends = []

    async def fake_send(**kwargs):
        sends.append(kwargs)
        return {"status": status, "id": "email-1"}

    monkeypatch.setattr(demo_module, "send_email", fake_send)
    return sends


def _set_classifier(monkeypatch, verdict="yes"):
    asked = []

    async def fake_classify(transcript):
        asked.append(transcript)
        if isinstance(verdict, Exception):
            raise verdict
        return verdict

    monkeypatch.setattr(consent, "classify_email_offer", fake_classify)
    return asked


def _set_transcript(monkeypatch, transcript="AGENT: email? USER: yes"):
    async def fake_await(session_key):
        return transcript

    monkeypatch.setattr(demo_module, "_await_call_transcript", fake_await)


# --- the callback's offer beat --------------------------------------------------


def test_no_address_on_file_is_byte_identical_and_spawns_no_watcher(monkeypatch):
    trip, items = _trip(), _items()
    calls = _wire_callback(monkeypatch, trip, items)
    spawned = _spy_watcher(monkeypatch)

    asyncio.run(demo_module._call_back_with_results("t-7", []))

    from api import call_purposes
    expected = call_purposes.build_results_purpose(trip, items, {})
    assert calls[0]["purpose"] == expected  # byte-identical, pre-40 shape
    assert demo_module._EMAIL_OFFER_PURPOSE not in calls[0]["purpose"]
    assert spawned == []


def test_address_on_file_appends_one_offer_and_spawns_the_watcher(monkeypatch):
    trip, items = _trip(), _items()
    calls = _wire_callback(monkeypatch, trip, items, refund_line=REFUND_LINE)
    spawned = _spy_watcher(monkeypatch)
    trip_emails.store("t-7", "Josh@Example.com")

    asyncio.run(demo_module._call_back_with_results("t-7", []))

    purpose = calls[0]["purpose"]
    assert purpose.endswith(demo_module._EMAIL_OFFER_PURPOSE)
    assert purpose.count(demo_module._EMAIL_OFFER_PURPOSE) == 1
    # The refund sentence stays ahead of the offer — Call 2 speaks results,
    # refund, then the wrap-up offer.
    assert purpose.index(REFUND_LINE) < purpose.index(
        demo_module._EMAIL_OFFER_PURPOSE
    )
    assert spawned == [{
        "trip_id": "t-7", "session_key": "room-2",
        "address": "josh@example.com", "refund_line": REFUND_LINE,
    }]


def test_call_2_is_placed_even_when_the_email_path_breaks(monkeypatch):
    # The offer beat must never cost the demo its results callback: the
    # call is placed before the watcher exists, and a watcher that blows
    # up on its first breath is a swallowed background failure.
    trip, items = _trip(), _items()
    calls = _wire_callback(monkeypatch, trip, items)
    trip_emails.store("t-7", "josh@example.com")

    async def broken_watch(*args, **kwargs):
        raise RuntimeError("email path broke")

    monkeypatch.setattr(demo_module, "_watch_email_offer", broken_watch)

    asyncio.run(demo_module._call_back_with_results("t-7", []))  # no raise

    assert len(calls) == 1


def test_failed_call_placement_spawns_no_watcher(monkeypatch):
    trip, items = _trip(), _items()
    _wire_callback(monkeypatch, trip, items, call_ok=False)
    spawned = _spy_watcher(monkeypatch)
    trip_emails.store("t-7", "josh@example.com")

    asyncio.run(demo_module._call_back_with_results("t-7", []))

    assert spawned == []


def test_call_id_is_the_legacy_session_key_fallback(monkeypatch):
    trip, items = _trip(), _items()
    monkeypatch.setattr(
        demo_module.trips, "get_trip", lambda tid: (True, trip, None)
    )
    monkeypatch.setattr(
        demo_module.itinerary_items, "list_items_for_trip",
        lambda tid: (True, items, None),
    )

    async def fake_details(tid, its):
        return {}

    async def fake_refund(its):
        return None

    monkeypatch.setattr(demo_module, "_details_for", fake_details)
    monkeypatch.setattr(demo_module, "_maybe_refund_line", fake_refund)
    monkeypatch.setattr(
        demo_module.vb_cli, "place_call",
        lambda purpose, name: (True, {"call_id": "c-2", "status": "queued"}, None),
    )
    spawned = _spy_watcher(monkeypatch)
    trip_emails.store("t-7", "josh@example.com")

    asyncio.run(demo_module._call_back_with_results("t-7", []))

    assert spawned[0]["session_key"] == "c-2"


# --- the watcher ---------------------------------------------------------------


def _run_watcher(refund_line=None, session_key="room-2"):
    return asyncio.run(demo_module._watch_email_offer(
        "t-7", session_key, "josh@example.com",
        _trip(), _items(), {}, refund_line,
    ))


def test_yes_sends_the_repair_email_to_the_stored_address(monkeypatch):
    _set_transcript(monkeypatch)
    _set_classifier(monkeypatch, "yes")
    sends = _capture_send(monkeypatch)
    consent.reset()

    _run_watcher(refund_line=REFUND_LINE)

    assert len(sends) == 1
    assert sends[0]["to"] == "josh@example.com"
    assert sends[0]["subject"] == "Your trip to Los Angeles is fixed — July 21"
    assert "JetBlue 615" in sends[0]["text"]
    assert "Was Delta 439" in sends[0]["text"]
    assert REFUND_LINE in sends[0]["text"]
    # The email path never touches consent state (the purity contract).
    assert consent.current("t-7") is None


def test_yes_without_refund_line_sends_without_refund_copy(monkeypatch):
    _set_transcript(monkeypatch)
    _set_classifier(monkeypatch, "yes")
    sends = _capture_send(monkeypatch)

    _run_watcher(refund_line=None)

    assert len(sends) == 1
    assert "PayPal" not in sends[0]["text"]


@pytest.mark.parametrize("verdict", ["no", "ambiguous"])
def test_non_yes_verdicts_send_nothing(monkeypatch, verdict):
    _set_transcript(monkeypatch)
    _set_classifier(monkeypatch, verdict)
    sends = _capture_send(monkeypatch)

    _run_watcher()

    assert sends == []


def test_transcript_timeout_sends_nothing_without_classifying(monkeypatch):
    _set_transcript(monkeypatch, transcript=None)
    asked = _set_classifier(monkeypatch, "yes")
    sends = _capture_send(monkeypatch)

    _run_watcher()

    assert sends == []
    assert asked == []


def test_missing_session_key_sends_nothing(monkeypatch):
    # The real _await_call_transcript returns None immediately on a falsy
    # key — no poll loop, no classifier, no email.
    asked = _set_classifier(monkeypatch, "yes")
    sends = _capture_send(monkeypatch)

    _run_watcher(session_key=None)

    assert sends == []
    assert asked == []


def test_watcher_exceptions_never_propagate(monkeypatch):
    _set_transcript(monkeypatch)
    _set_classifier(monkeypatch, "yes")

    async def broken_send(**kwargs):
        raise RuntimeError("resend fell over")

    monkeypatch.setattr(demo_module, "send_email", broken_send)

    _run_watcher()  # must not raise


# --- the email-offer classifier -------------------------------------------------


def test_classify_email_offer_empty_transcript_is_ambiguous():
    assert asyncio.run(consent.classify_email_offer("")) == "ambiguous"
    assert asyncio.run(consent.classify_email_offer("   ")) == "ambiguous"


def test_classify_email_offer_uses_the_offer_instructions(monkeypatch):
    captured = {}

    async def fake_run(agent, input, max_turns):
        captured["instructions"] = agent.instructions

        class Result:
            final_output = "Yes."

        return Result()

    monkeypatch.setattr(consent.Runner, "run", fake_run)

    verdict = asyncio.run(
        consent.classify_email_offer("AGENT: email? USER: yes please")
    )

    assert verdict == "yes"
    assert captured["instructions"] == consent._EMAIL_OFFER_INSTRUCTIONS


def test_classify_email_offer_api_failure_is_ambiguous(monkeypatch):
    async def broken_run(agent, input, max_turns):
        raise RuntimeError("api fell over")

    monkeypatch.setattr(consent.Runner, "run", broken_run)

    assert asyncio.run(
        consent.classify_email_offer("USER: yes")
    ) == "ambiguous"
