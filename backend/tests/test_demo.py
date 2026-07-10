"""Phase 12 tests — the demo orchestrator router.

Hermetic (the test_outbound_call.py pattern): vb_cli is mocked at the
function boundary, the composed seams (create_seed_trip, break_trip_flight,
launch_trip_repairs) are mocked where demo.py imported them, env via
monkeypatch, no network. Load-bearing invariants: the call fires before the
data writes, secrets never appear in any payload, and a failed call means no
data write.
"""
from fastapi.testclient import TestClient

import main
from api import demo as demo_module
from api import vb_cli

client = TestClient(main.app)

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


class _Item:
    def __init__(self, item_id, type_):
        self.item_id, self.type = item_id, type_


def _happy_call(monkeypatch, events=None, call_id="c-1"):
    def fake_place_call(purpose, name=None):
        if events is not None:
            events.append(("place_call", purpose, name))
        return True, {"call_id": call_id, "status": "initiated"}, None

    monkeypatch.setattr(vb_cli, "place_call", fake_place_call)


# ── registration ───────────────────────────────────────────────────────


def test_routes_registered_with_phase12_summaries():
    paths = main.app.openapi()["paths"]
    assert "/v1/demo/book" in paths
    assert "/v1/demo/disrupt" in paths
    assert "/v1/demo/" in paths
    assert paths["/v1/demo/book"]["post"]["summary"].startswith("[Phase 12]")
    assert paths["/v1/demo/disrupt"]["post"]["summary"].startswith("[Phase 12]")


# ── GET / (the demo page) ──────────────────────────────────────────────


def test_demo_page_is_served_as_html():
    resp = client.get("/v1/demo/")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/html")
    # The two operator controls are the page's whole point.
    assert "Trigger call" in resp.text
    assert "Flight canceled" in resp.text


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


def _wire_disrupt(monkeypatch, events):
    def fake_break(trip_id):
        events.append(("break", trip_id))
        return {"trip_id": trip_id, "item_id": "i-flight", "previous_status": "booked",
                "status": "broken", "affected_rows": 1}

    items = [_Item(f"i-{t}", t) for t in
             ("flight", "hotel", "ground", "dining", "experience")]

    def fake_list(trip_id):
        events.append(("list", trip_id))
        return True, items, None

    def fake_launch(session_id, launch_items):
        events.append(("launch", session_id, [i.item_id for i in launch_items]))
        return FIVE_REPAIRS, []

    monkeypatch.setattr(demo_module, "break_trip_flight", fake_break)
    monkeypatch.setattr(
        demo_module.itinerary_items, "list_items_for_trip", fake_list
    )
    monkeypatch.setattr(demo_module, "launch_trip_repairs", fake_launch)
    return items


def test_disrupt_missing_env_is_503_naming_the_var(monkeypatch):
    for missing in ("VOCAL_BRIDGE_API_KEY", "VOCAL_BRIDGE_CALLER_AGENT_ID",
                    "VOCAL_BRIDGE_CALLEE_PHONE"):
        _set_env(monkeypatch)
        monkeypatch.delenv(missing)
        resp = client.post("/v1/demo/disrupt", json={"trip_id": "t-1"})
        assert resp.status_code == 503
        assert missing in resp.json()["error"]


def test_disrupt_calls_then_breaks_then_launches_repairs(monkeypatch):
    _set_env(monkeypatch)
    events = []
    _happy_call(monkeypatch, events, call_id="c-disrupt")
    _wire_disrupt(monkeypatch, events)

    resp = client.post("/v1/demo/disrupt", json={"trip_id": "t-7"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["trip_id"] == "t-7"
    assert body["item_id"] == "i-flight"
    assert body["call_id"] == "c-disrupt"
    assert body["launched"] == FIVE_REPAIRS
    assert body["repair_session_id"].startswith("demo-")

    # Call first, then the break, then repairs over the trip's items.
    assert [e[0] for e in events] == ["place_call", "break", "list", "launch"]
    assert events[1] == ("break", "t-7")
    assert events[3][1] == body["repair_session_id"]
    assert FAKE_CALLEE not in resp.text
    assert FAKE_API_KEY not in resp.text


def test_disrupt_purpose_is_the_cancellation_script(monkeypatch):
    _set_env(monkeypatch)
    events = []
    _happy_call(monkeypatch, events)
    _wire_disrupt(monkeypatch, events)

    client.post("/v1/demo/disrupt", json={"trip_id": "t-7"})
    purpose = events[0][1]
    assert "cancelled" in purpose
    assert "thirty seconds" in purpose


def test_disrupt_404_passes_through_when_trip_has_no_flight(monkeypatch):
    _set_env(monkeypatch)
    _happy_call(monkeypatch)
    # The real break_trip_flight raises 404 for a flightless/unknown trip —
    # mocked here at the seam with the same contract.
    from fastapi import HTTPException

    def fake_break(trip_id):
        raise HTTPException(status_code=404, detail=f"trip {trip_id} has no flight item to break")

    launched = []
    monkeypatch.setattr(demo_module, "break_trip_flight", fake_break)
    monkeypatch.setattr(
        demo_module, "launch_trip_repairs",
        lambda sid, items: launched.append(1),
    )

    resp = client.post("/v1/demo/disrupt", json={"trip_id": "nope"})
    assert resp.status_code == 404
    assert launched == []


def test_disrupt_call_failure_is_502_and_breaks_nothing(monkeypatch):
    _set_env(monkeypatch)
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
