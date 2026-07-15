"""Phase 12 tests — the demo orchestrator router.

Hermetic (the test_outbound_call.py pattern): vb_cli is mocked at the
function boundary, the composed seams (create_seed_trip, break_trip_flight,
launch_trip_repairs) are mocked where demo.py imported them, env via
monkeypatch, no network. Load-bearing invariants: the call fires before the
data writes, secrets never appear in any payload, and a failed call means no
data write.
"""
import asyncio
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

import main
from api import consent
from api import demo as demo_module
from api import vb_cli
from api.repositories.models import ItineraryItem, Trip

client = TestClient(main.app)

_PACIFIC = ZoneInfo("America/Los_Angeles")

TRANSCRIPT_YES = (
    "AGENT: Your flight from New York to Los Angeles was cancelled — I can "
    "rebook it and recheck the rest of the trip. Want me to?\n\n"
    "USER: Yeah, go ahead."
)

FAKE_API_KEY = "vb-secret-key-123"
FAKE_CALLEE = "+15555550123"
FAKE_AGENT_ID = "caller-agent-1"

FIVE_REPAIRS = [
    "rebook_flight", "change_hotel", "rebook_ground", "rebook_dining",
    "rebook_experience",
]


def _set_env(monkeypatch, api_key=FAKE_API_KEY, agent_id=FAKE_AGENT_ID, callee=FAKE_CALLEE):
    for name, value in (
        ("VOCAL_BRIDGE_API_KEY", api_key),
        ("VOCAL_BRIDGE_CALLER_AGENT_ID", agent_id),
        ("VOCAL_BRIDGE_CALLEE_PHONE", callee),
    ):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


def _trip_and_items(trip_id="t-7"):
    """A real JFK→LAX trip with all five item types — the disrupt purpose
    is composed from this data, so the fixtures use real models."""
    trip = Trip(
        trip_id=trip_id, user_id="demo-traveler", title="Trip to LAX",
        status="booked", origin="JFK", destinations=["LAX"],
        start_date=date(2026, 7, 17), end_date=date(2026, 7, 19),
    )
    items = [
        ItineraryItem(
            item_id="i-flight", trip_id=trip_id, type="flight",
            status="booked", location="JFK-LAX",
            start_ts=datetime(2026, 7, 17, 8, 0, tzinfo=_PACIFIC),
        ),
    ] + [
        ItineraryItem(item_id=f"i-{t}", trip_id=trip_id, type=t, status="booked")
        for t in ("hotel", "ground", "dining", "experience")
    ]
    return trip, items


def _happy_call(monkeypatch, events=None, call_id="c-1"):
    def fake_place_call(purpose, name=None):
        if events is not None:
            events.append(("place_call", purpose, name))
        return True, {"call_id": call_id, "status": "initiated"}, None

    monkeypatch.setattr(vb_cli, "place_call", fake_place_call)


# ── registration ───────────────────────────────────────────────────────


def test_routes_registered_with_phase_summaries():
    paths = main.app.openapi()["paths"]
    assert "/v1/demo/book" in paths
    assert "/v1/demo/disrupt" in paths
    assert "/v1/demo/" in paths
    assert paths["/v1/demo/book"]["post"]["summary"].startswith("[Phase 12]")
    # Phase 23 reworked disrupt into the consent-gated flow.
    assert paths["/v1/demo/disrupt"]["post"]["summary"].startswith("[Phase 23]")


# ── GET / (the demo page) ──────────────────────────────────────────────


def test_demo_page_is_served_as_html():
    resp = client.get("/v1/demo/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    # The two operator controls are the page's whole point.
    assert "Trigger call" in resp.text
    assert "Flight canceled" in resp.text


def test_demo_page_renders_times_pacific_labeled_pt():
    """Phase 19: same timezone discipline as the itinerary page — card times
    and the feed clock render America/Los_Angeles, labeled "PT"."""
    text = client.get("/v1/demo/").text
    assert text.count('timeZone: "America/Los_Angeles"') == 2
    assert text.count('" PT"') == 2
    assert "PST" not in text


# ── POST /book ─────────────────────────────────────────────────────────


def test_book_missing_env_is_503_naming_the_var(monkeypatch):
    for missing in ("VOCAL_BRIDGE_API_KEY", "VOCAL_BRIDGE_CALLER_AGENT_ID",
                    "VOCAL_BRIDGE_CALLEE_PHONE"):
        _set_env(monkeypatch)
        monkeypatch.delenv(missing)
        resp = client.post("/v1/demo/book", json={})
        assert resp.status_code == 503
        assert missing in resp.json()["error"]


def test_book_places_call_before_seeding_and_returns_exact_shape(monkeypatch):
    _set_env(monkeypatch)
    events = []
    _happy_call(monkeypatch, events, call_id="c-book")

    def fake_seed(user_id, title):
        events.append(("seed", user_id, title))
        return {"trip_id": "t-99", "items": [], "bookings": []}

    monkeypatch.setattr(demo_module, "create_seed_trip", fake_seed)

    resp = client.post("/v1/demo/book", json={})
    assert resp.status_code == 200
    assert resp.json() == {
        "trip_id": "t-99",
        "call_id": "c-book",
        "call_status": "initiated",
    }
    # The phone rings while the screen changes, not after: call first.
    assert [e[0] for e in events] == ["place_call", "seed"]
    assert events[1][1:] == ("demo-traveler", "The Complete Trip — hackathon demo")
    assert FAKE_CALLEE not in resp.text
    assert FAKE_API_KEY not in resp.text


def test_book_purpose_carries_the_trip_narrative(monkeypatch):
    _set_env(monkeypatch)
    events = []
    _happy_call(monkeypatch, events)
    monkeypatch.setattr(
        demo_module, "create_seed_trip",
        lambda user_id, title: {"trip_id": "t-1"},
    )

    client.post("/v1/demo/book", json={"title": "Josh's big trip"})
    purpose = events[0][1]
    # Voice and screen tell the same story: the title and the legs.
    assert "Josh's big trip" in purpose
    assert "Minneapolis" in purpose and "San Francisco" in purpose
    for leg in ("hotel", "ride", "dinner", "tour"):
        assert leg in purpose


def test_book_call_failure_is_502_scrubbed_and_seeds_nothing(monkeypatch):
    _set_env(monkeypatch)
    monkeypatch.setattr(
        vb_cli, "place_call",
        lambda purpose, name=None: (
            False, None, f"vb call {FAKE_CALLEE} failed: key {FAKE_API_KEY} rejected",
        ),
    )
    seeded = []
    monkeypatch.setattr(
        demo_module, "create_seed_trip",
        lambda user_id, title: seeded.append(1),
    )

    resp = client.post("/v1/demo/book", json={})
    assert resp.status_code == 502
    assert FAKE_CALLEE not in resp.text
    assert FAKE_API_KEY not in resp.text
    assert "[redacted]" in resp.json()["error"]
    assert seeded == []


# ── POST /disrupt ──────────────────────────────────────────────────────


def _wire_disrupt(monkeypatch, events, trip_id="t-7"):
    trip, items = _trip_and_items(trip_id)

    def fake_get_trip(requested_id):
        events.append(("get_trip", requested_id))
        return True, (trip if requested_id == trip_id else None), None

    def fake_list(requested_id):
        events.append(("list", requested_id))
        return True, items, None

    def fake_break(requested_id):
        events.append(("break", requested_id))
        return {"trip_id": requested_id, "item_id": "i-flight",
                "previous_status": "booked", "status": "broken",
                "affected_rows": 1}

    def fake_launch(session_id, launch_items):
        events.append(("launch", session_id, [i.item_id for i in launch_items]))
        return FIVE_REPAIRS, []

    def fake_watch(trip_id, call_id, token):
        # Called synchronously by the handler to create the watcher
        # coroutine — the spawn (and its args) is recorded here; the
        # coroutine itself is inert so endpoint tests stay hermetic.
        events.append(("watch", trip_id, call_id, token))

        async def _noop():
            return None

        return _noop()

    monkeypatch.setattr(demo_module.trips, "get_trip", fake_get_trip)
    monkeypatch.setattr(
        demo_module.itinerary_items, "list_items_for_trip", fake_list
    )
    monkeypatch.setattr(demo_module, "break_trip_flight", fake_break)
    monkeypatch.setattr(demo_module, "launch_trip_repairs", fake_launch)
    monkeypatch.setattr(demo_module, "_watch_consent_then_repair", fake_watch)
    return items


def test_disrupt_missing_env_is_503_naming_the_var(monkeypatch):
    for missing in ("VOCAL_BRIDGE_API_KEY", "VOCAL_BRIDGE_CALLER_AGENT_ID",
                    "VOCAL_BRIDGE_CALLEE_PHONE"):
        _set_env(monkeypatch)
        monkeypatch.delenv(missing)
        resp = client.post("/v1/demo/disrupt", json={"trip_id": "t-1"})
        assert resp.status_code == 503
        assert missing in resp.json()["error"]


def test_disrupt_calls_breaks_and_awaits_consent_without_repairs(monkeypatch):
    """Phase 23: the click does exactly two things — Call 1 and the break.
    No repairs launch at click time; the consent watcher is spawned with
    the registered token and the page learns the wait from the registry."""
    _set_env(monkeypatch)
    consent.reset()
    events = []
    _happy_call(monkeypatch, events, call_id="c-disrupt")
    _wire_disrupt(monkeypatch, events)

    resp = client.post("/v1/demo/disrupt", json={"trip_id": "t-7"})
    assert resp.status_code == 200
    assert resp.json() == {
        "trip_id": "t-7",
        "item_id": "i-flight",
        "call_id": "c-disrupt",
        "call_status": "initiated",
        "consent": consent.AWAITING,
    }

    # Reads may precede the call (the script needs the trip), but the call
    # fires before any write — and nothing launches at click time.
    assert [e[0] for e in events] == [
        "get_trip", "list", "place_call", "break", "watch",
    ]
    assert ("break", "t-7") in events

    record = consent.current("t-7")
    assert record.state == consent.AWAITING
    assert record.call_id == "c-disrupt"
    assert events[-1] == ("watch", "t-7", "c-disrupt", record.token)
    assert FAKE_CALLEE not in resp.text
    assert FAKE_API_KEY not in resp.text


def test_disrupt_purpose_speaks_the_real_trip_and_asks_consent(monkeypatch):
    """Phase 23: the script is composed from the pinned trip's data — the
    real route as cities — and asks for the traveler's go-ahead instead of
    claiming repairs are already running."""
    _set_env(monkeypatch)
    events = []
    _happy_call(monkeypatch, events)
    _wire_disrupt(monkeypatch, events)

    client.post("/v1/demo/disrupt", json={"trip_id": "t-7"})
    purpose = next(e[1] for e in events if e[0] == "place_call")
    assert "cancelled" in purpose
    assert "New York" in purpose and "Los Angeles" in purpose
    assert "Minneapolis" not in purpose and "San Francisco" not in purpose
    assert "want me to?" in purpose
    assert "already rebooking" not in purpose


def test_disrupt_404s_before_dialing_when_trip_cannot_break(monkeypatch):
    """An unknown trip or one with no flight item 404s from the pre-call
    read — no quota is spent on a call about a trip that can't break."""
    _set_env(monkeypatch)
    calls = []
    monkeypatch.setattr(
        vb_cli, "place_call",
        lambda purpose, name=None: calls.append(1) or (
            True, {"call_id": "c-1", "status": "initiated"}, None
        ),
    )
    events = []
    _wire_disrupt(monkeypatch, events, trip_id="t-7")

    # Unknown trip: get_trip returns None.
    resp = client.post("/v1/demo/disrupt", json={"trip_id": "nope"})
    assert resp.status_code == 404
    assert calls == []

    # Known trip, no flight item.
    trip, items = _trip_and_items("t-8")
    monkeypatch.setattr(
        demo_module.trips, "get_trip", lambda tid: (True, trip, None)
    )
    monkeypatch.setattr(
        demo_module.itinerary_items, "list_items_for_trip",
        lambda tid: (True, [i for i in items if i.type != "flight"], None),
    )
    resp = client.post("/v1/demo/disrupt", json={"trip_id": "t-8"})
    assert resp.status_code == 404
    assert calls == []


def test_disrupt_call_failure_is_502_and_breaks_nothing(monkeypatch):
    _set_env(monkeypatch)
    events = []
    _wire_disrupt(monkeypatch, events, trip_id="t-1")
    monkeypatch.setattr(
        vb_cli, "place_call",
        lambda purpose, name=None: (False, None, f"could not dial {FAKE_CALLEE}"),
    )
    broke = []
    monkeypatch.setattr(
        demo_module, "break_trip_flight", lambda trip_id: broke.append(1)
    )

    resp = client.post("/v1/demo/disrupt", json={"trip_id": "t-1"})
    assert resp.status_code == 502
    assert FAKE_CALLEE not in resp.text
    assert broke == []


def test_disrupt_requires_trip_id(monkeypatch):
    _set_env(monkeypatch)
    assert client.post("/v1/demo/disrupt", json={}).status_code == 422


# ── the consent watcher (Phase 23) — run directly, canned VB payloads ──


def _fast_watcher(monkeypatch):
    monkeypatch.setattr(demo_module, "_CONSENT_POLL_SECONDS", 0.001)
    monkeypatch.setattr(demo_module, "_CONSENT_TIMEOUT_SECONDS", 0.05)


def _wire_watcher(monkeypatch, trip_id, verdict="yes", find_session=None):
    """Common watcher wiring: canned find_session, a stubbed classifier,
    recorded launch/place_call, healthy repo reads. Returns the recorders."""
    order = []
    calls = []
    trip, items = _trip_and_items(trip_id)

    if find_session is None:
        def find_session(call_id, lookback=50):
            return True, {
                "id": call_id, "call_status": "completed",
                "transcript_text": TRANSCRIPT_YES,
            }, None
    monkeypatch.setattr(demo_module.vb_cli, "find_session", find_session)

    async def fake_classify(transcript):
        order.append(("classify", transcript))
        return verdict

    monkeypatch.setattr(demo_module.consent, "classify_consent", fake_classify)

    def fake_launch(session_id, launch_items):
        order.append(("launch", session_id))
        return FIVE_REPAIRS, []

    monkeypatch.setattr(demo_module, "launch_trip_repairs", fake_launch)
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

    def fake_place(purpose, name=None):
        order.append(("place_call", name))
        calls.append((purpose, name))
        return True, {"call_id": "c-2", "status": "initiated"}, None

    monkeypatch.setattr(demo_module.vb_cli, "place_call", fake_place)
    return order, calls, items


def test_watcher_yes_launches_repairs_then_places_the_results_call(monkeypatch):
    """The yes path end to end: transcript read → classified → repairs
    launched → registry granted → Call 2 placed with the results purpose
    only after the repair tasks land."""
    consent.reset()
    _fast_watcher(monkeypatch)
    order, calls, _items = _wire_watcher(monkeypatch, "t-9", verdict="yes")

    gate_done = []

    def gated_launch(session_id, launch_items):
        order.append(("launch", session_id))

        async def slow_repair():
            await asyncio.sleep(0.02)
            gate_done.append(True)

        return FIVE_REPAIRS, [asyncio.create_task(slow_repair())]

    monkeypatch.setattr(demo_module, "launch_trip_repairs", gated_launch)

    async def scenario():
        token = consent.register_awaiting("t-9", "c-9")
        await demo_module._watch_consent_then_repair("t-9", "c-9", token)

    asyncio.run(scenario())

    kinds = [step[0] for step in order]
    assert kinds == ["classify", "launch", "place_call"]
    assert gate_done == [True]  # Call 2 waited for the repairs
    assert consent.current("t-9").state == consent.GRANTED
    purpose, name = calls[0]
    assert name == "demo-beat3-results"
    assert "New York" in purpose and "Los Angeles" in purpose
    assert "Minneapolis" not in purpose


def test_watcher_no_stands_down_without_repairs_or_callback(monkeypatch):
    consent.reset()
    _fast_watcher(monkeypatch)
    order, calls, _items = _wire_watcher(monkeypatch, "t-10", verdict="no")

    async def scenario():
        token = consent.register_awaiting("t-10", "c-10")
        await demo_module._watch_consent_then_repair("t-10", "c-10", token)

    asyncio.run(scenario())
    assert [step[0] for step in order] == ["classify"]
    assert calls == []
    record = consent.current("t-10")
    assert record.state == consent.DECLINED
    assert "declined" in record.message


def test_watcher_ambiguous_stands_down_with_a_retry_message(monkeypatch):
    consent.reset()
    _fast_watcher(monkeypatch)
    order, calls, _items = _wire_watcher(monkeypatch, "t-11", verdict="ambiguous")

    async def scenario():
        token = consent.register_awaiting("t-11", "c-11")
        await demo_module._watch_consent_then_repair("t-11", "c-11", token)

    asyncio.run(scenario())
    assert calls == []
    record = consent.current("t-11")
    assert record.state == consent.DECLINED
    assert "wasn't a clear yes" in record.message


def test_watcher_times_out_when_the_call_never_completes(monkeypatch):
    consent.reset()
    _fast_watcher(monkeypatch)
    order, calls, _items = _wire_watcher(
        monkeypatch, "t-12",
        find_session=lambda call_id, lookback=50: (True, None, None),
    )

    async def scenario():
        token = consent.register_awaiting("t-12", "c-12")
        await demo_module._watch_consent_then_repair("t-12", "c-12", token)

    asyncio.run(scenario())
    # Never classified, never launched, never called back.
    assert order == [] and calls == []
    record = consent.current("t-12")
    assert record.state == consent.TIMED_OUT
    assert "standing by" in record.message


def test_watcher_absorbs_transcript_lag(monkeypatch):
    """The resolved spike: transcript_text can land a beat after the
    completed status — the watcher keeps polling until both are present."""
    consent.reset()
    _fast_watcher(monkeypatch)
    payloads = [
        (True, None, None),
        (True, {"id": "c-13", "call_status": "completed"}, None),
        (True, {"id": "c-13", "call_status": "completed",
                "transcript_text": TRANSCRIPT_YES}, None),
    ]

    def lagging_find(call_id, lookback=50):
        return payloads.pop(0) if len(payloads) > 1 else payloads[0]

    order, calls, _items = _wire_watcher(
        monkeypatch, "t-13", verdict="yes", find_session=lagging_find
    )

    async def scenario():
        token = consent.register_awaiting("t-13", "c-13")
        await demo_module._watch_consent_then_repair("t-13", "c-13", token)

    asyncio.run(scenario())
    assert consent.current("t-13").state == consent.GRANTED
    assert [step[0] for step in order] == ["classify", "launch", "place_call"]


def test_watcher_stands_down_when_superseded_by_a_retrigger(monkeypatch):
    """Clicking Cancel again mints a new token — the first watcher's
    resolution is dropped and it must not classify, launch, or call."""
    consent.reset()
    _fast_watcher(monkeypatch)
    order, calls, _items = _wire_watcher(monkeypatch, "t-14", verdict="yes")

    async def scenario():
        stale = consent.register_awaiting("t-14", "c-14a")
        fresh = consent.register_awaiting("t-14", "c-14b")
        await demo_module._watch_consent_then_repair("t-14", "c-14a", stale)
        return fresh

    fresh = asyncio.run(scenario())
    assert order == [] and calls == []
    record = consent.current("t-14")
    assert record.state == consent.AWAITING and record.token == fresh


def test_watcher_resolves_error_when_items_unreadable_after_yes(monkeypatch):
    consent.reset()
    _fast_watcher(monkeypatch)
    order, calls, _items = _wire_watcher(monkeypatch, "t-15", verdict="yes")
    monkeypatch.setattr(
        demo_module.itinerary_items, "list_items_for_trip",
        lambda tid: (False, None, "boom"),
    )

    async def scenario():
        token = consent.register_awaiting("t-15", "c-15")
        await demo_module._watch_consent_then_repair("t-15", "c-15", token)

    asyncio.run(scenario())
    assert calls == []
    assert consent.current("t-15").state == consent.ERROR
